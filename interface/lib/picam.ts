// Logitech webcam on the Raspberry Pi -> MJPEG over Wi-Fi -> latest JPEG here.
// The Pi runs ustreamer (raspberry/webcam_setup.sh): GET /stream is multipart/x-mixed-replace JPEG parts.
// One upstream connection per process, whatever the number of open pages: the Wi-Fi link carries the feed once,
// /api/picam/stream re-serves it to the page and /api/picam/frame hands the newest frame to the detector.
import http from "node:http";

const DEFAULT_URL = process.env.PICAM_URL ?? "http://raspberrypi.local:8080/stream";
const IDLE_MS = 15_000; // nobody asked for frames this long: hang up, so the Pi stops sending
const STALE_MS = 3_000; // newest frame older than this: the link is down, don't detect on a frozen frame
const RETRY_MS = 1_000;
const SOCKET_TIMEOUT_MS = 5_000; // no bytes for this long: Wi-Fi dropped, reconnect
const MAX_BUF = 16 << 20;
const SOI = Buffer.from([0xff, 0xd8, 0xff]);
const EOI = Buffer.from([0xff, 0xd9]);

export type PiFrame = { jpeg: Buffer; at: number; n: number };
type Sub = (f: PiFrame) => void;
type State = {
  url: string;
  gen: number; // bumped on every (re)connect; callbacks of an older connection do nothing
  req: http.ClientRequest | null;
  latest: PiFrame | null;
  error: string | null;
  subs: Set<Sub>;
  used: number;
  n: number;
  times: number[];
};

const g = globalThis as typeof globalThis & { __picam?: State };

/** "10.42.0.1", "raspberrypi.local:8080" or a full http:// URL -> stream URL. */
export function piUrl(src?: string | null): string {
  const s = (src ?? "").trim();
  if (!s) return DEFAULT_URL;
  const u = new URL(/^[a-z]+:\/\//i.test(s) ? s : `http://${s}`);
  if (u.protocol !== "http:") throw new Error(`only http:// sources, got ${u.protocol}`);
  if (!u.port && !/^[a-z]+:\/\//i.test(s)) u.port = "8080";
  if (u.pathname === "/") u.pathname = "/stream";
  return u.toString();
}

export const piDefaultUrl = () => DEFAULT_URL;

function state(): State {
  return (g.__picam ??= { url: DEFAULT_URL, gen: 0, req: null, latest: null, error: null, subs: new Set(), used: 0, n: 0, times: [] });
}

const idle = (s: State) => s.subs.size === 0 && Date.now() - s.used > IDLE_MS;

function hangUp(s: State) {
  s.gen++;
  s.req?.destroy();
  s.req = null;
}

function onFrame(s: State, jpeg: Buffer) {
  const f: PiFrame = { jpeg, at: Date.now(), n: ++s.n };
  s.latest = f;
  s.error = null;
  s.times.push(f.at);
  while (s.times.length && f.at - s.times[0] > 2000) s.times.shift();
  for (const sub of s.subs) sub(f);
  if (idle(s)) hangUp(s);
}

/**
 * Cut complete JPEGs out of the multipart body; returns the unconsumed tail.
 * Uses the part's Content-Length when there is one (ustreamer sends it), else scans to EOI.
 */
function cut(s: State, buf: Buffer): Buffer {
  for (;;) {
    const soi = buf.indexOf(SOI);
    if (soi < 0) return buf.length > 1024 ? buf.subarray(buf.length - 1024) : buf; // part headers may be half in
    const head = buf.subarray(Math.max(0, soi - 1024), soi).toString("latin1");
    const m = [...head.matchAll(/content-length:\s*(\d+)/gi)].pop();
    let end: number;
    if (m) {
      end = soi + Number(m[1]);
      if (buf.length < end) return buf;
    } else {
      const eoi = buf.indexOf(EOI, soi + 2);
      if (eoi < 0) return buf;
      end = eoi + 2;
    }
    onFrame(s, Buffer.from(buf.subarray(soi, end)));
    buf = buf.subarray(end);
  }
}

function connect(s: State) {
  const gen = ++s.gen, url = s.url;
  const retry = (why: string) => {
    if (gen !== s.gen) return; // already retried, switched source or hung up
    s.gen++;
    s.req = null;
    s.error = why;
    if (!idle(s)) setTimeout(() => s.req === null && !idle(s) && connect(s), RETRY_MS);
  };
  const req = http.get(url, { timeout: SOCKET_TIMEOUT_MS, headers: { "user-agent": "station-ui" } }, (res) => {
    const type = String(res.headers["content-type"] ?? "");
    if (res.statusCode !== 200) {
      res.resume();
      return retry(`HTTP ${res.statusCode} from ${url}`);
    }
    if (!type.startsWith("multipart/")) {
      res.resume();
      return retry(`${url} is not an MJPEG stream (${type || "no content-type"}); the ustreamer one is /stream`);
    }
    let buf: Buffer = Buffer.alloc(0);
    res.on("data", (chunk: Buffer) => {
      if (gen !== s.gen) return;
      buf = cut(s, buf.length ? Buffer.concat([buf, chunk]) : chunk);
      if (buf.length > MAX_BUF) {
        buf = Buffer.alloc(0);
        s.error = `no JPEG frames in the last ${MAX_BUF >> 20} MB from ${url}`;
      }
    });
    res.on("end", () => retry(`${url} closed the stream`));
    res.on("error", (e) => retry(`${url}: ${e.message}`));
  });
  req.on("timeout", () => req.destroy(new Error(`no data for ${SOCKET_TIMEOUT_MS / 1000} s (Wi-Fi down?)`)));
  req.on("error", (e) => retry(`${url}: ${(e as NodeJS.ErrnoException).code === "ENOTFOUND" ? "host not found" : e.message}`));
  s.req = req;
}

/** Mark the feed as wanted; (re)connects, or switches to another Pi when src changed. */
function use(src?: string | null): State {
  const s = state(), url = piUrl(src);
  s.used = Date.now();
  if (url !== s.url) {
    hangUp(s);
    Object.assign(s, { url, latest: null, error: null, times: [] });
  }
  if (!s.req) connect(s);
  return s;
}

export type PiStatus = { url: string; frame: PiFrame | null; fps: number; error: string | null };

/** Newest frame, or null with the reason when there is none fresh enough to detect on. */
export function piFrame(src?: string | null): PiStatus {
  const s = use(src);
  const fresh = s.latest && Date.now() - s.latest.at < STALE_MS ? s.latest : null;
  const fps = s.times.length > 1 ? (s.times.length - 1) / ((s.times.at(-1)! - s.times[0]) / 1000) : 0;
  const error = fresh ? null : s.error ?? (s.latest ? `no frames from ${s.url} for ${Math.round((Date.now() - s.latest.at) / 1000)} s` : `connecting to ${s.url}…`);
  return { url: s.url, frame: fresh, fps, error };
}

/** Call fn with every new frame (and the current one right away); returns the unsubscribe. */
export function piSubscribe(src: string | null, fn: Sub): () => void {
  const s = use(src);
  s.subs.add(fn);
  if (s.latest) fn(s.latest);
  return () => {
    s.subs.delete(fn);
    s.used = Date.now();
  };
}
