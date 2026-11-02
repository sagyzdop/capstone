"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type BBox = [number, number, number, number];
// by: with "merge models" on, every model that found this person (the box is the best-scoring one's)
type Det = { bbox_xyxy: BBox; conf: number; cls: number; name: string; model: string; by?: string[] };
type DetectResult = { width: number; height: number; ms: number; times: Record<string, number>; detections: Det[] };
type ModelInfo = {
  name: string;
  label: string;
  source: string | null;
  task: string;
  weights: string;
  base: string | null;
  epochs: number | null;
  imgsz: number;
  trained: string | null;
  classes: string[]; // the classes counted as a person
  metrics: Record<string, number>;
};
type Info = { models: ModelInfo[]; device: string; runtime: string; samples: string[] };
type Item = {
  id: number;
  name: string;
  file: Blob;
  url: string;
  W: number;
  H: number;
  dets: Det[] | null;
  ms: number | null;
  times: Record<string, number>;
  status: "pending" | "running" | "done" | "error";
  key: string | null; // settings the dets were made with
};
type Mode = "image" | "video" | "camera";
type Settings = { imgsz: number; tile: number; models: string[] };
type Media = { key: number; W: number; H: number; name: string };
type Live = { dets: Det[]; ms: number; times: Record<string, number>; fps: number; hist: number[] };
// a live detection kept in the list after it leaves the frame; det/at/thumb are from its best-scoring frame
type Saved = { id: number; det: Det; box: BBox; last: number; seen: number; at: string; thumb: string };

const TINY = 14; // boxes smaller than this many screen px get a ring
const MAX_SEND = 1280; // live frames go up at most this long side: the detector runs at 640-1280 anyway
const PALETTE = ["#ff7a1a", "#3fb9f0", "#a371f7", "#3fb950", "#e3b341", "#f778ba"];
// colour follows the model, so VisDrone and pose boxes can be told apart when both are on
const MODEL_COLOR: Record<string, string> = { best: PALETTE[0], visdrone: PALETTE[1], pose: PALETTE[2] };
const modelColor = (m: string) => MODEL_COLOR[m] ?? PALETTE[3 + ([...m].reduce((a, c) => a + c.charCodeAt(0), 0) % 3)];
const color = (d: Det) => (d.by && d.by.length > 1 ? PALETTE[3] : modelColor(d.model));
const pct = (d: Det) => `${Math.round(d.conf * 100)}%`;
const keyOf = (s: Settings) => `${s.imgsz}/${s.tile}/${s.models.join(",")}`;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const EMPTY_LIVE: Live = { dets: [], ms: 0, times: {}, fps: 0, hist: [] };
const KEEP_GAP = 1500; // ms: a box this soon after a saved one, on the same spot, is the same person
const KEEP_IOU = 0.3;
const MAX_SAVED = 500;
const MERGE_IOU = 0.5; // boxes from different models this close are one person
let seq = 0;

function iou(a: BBox, b: BBox) {
  const w = Math.min(a[2], b[2]) - Math.max(a[0], b[0]), h = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
  if (w <= 0 || h <= 0) return 0;
  return (w * h) / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h);
}

/** One box per person across models: greedy NMS by confidence, each kept box remembers who else found it. */
function mergeModels(ds: Det[]): Det[] {
  const keep: Det[] = [];
  for (const d of [...ds].sort((a, b) => b.conf - a.conf)) {
    const k = keep.find((k) => iou(k.bbox_xyxy, d.bbox_xyxy) >= MERGE_IOU);
    if (!k) keep.push({ ...d, by: [d.model] });
    else if (!k.by!.includes(d.model)) k.by!.push(d.model);
  }
  return keep;
}

// saved-list identity: a merged box may come from a different model each frame
const trackOf = (d: Det) => (d.by ? "*" : `${d.model}/${d.cls}`);

/** Square crop around a detection with its box drawn in. */
function drawCrop(c: HTMLCanvasElement, src: CanvasImageSource, det: Det, scale: number) {
  const [x1, y1, x2, y2] = det.bbox_xyxy.map((v) => v * scale);
  const side = Math.max(x2 - x1, y2 - y1) * 1.5 + 6, cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
  const g = c.getContext("2d")!;
  g.clearRect(0, 0, c.width, c.height);
  g.imageSmoothingQuality = "high";
  try {
    g.drawImage(src, cx - side / 2, cy - side / 2, side, side, 0, 0, c.width, c.height);
  } catch {}
  const k = c.width / side;
  g.strokeStyle = color(det);
  g.lineWidth = 2;
  g.strokeRect((x1 - cx + side / 2) * k, (y1 - cy + side / 2) * k, (x2 - x1) * k, (y2 - y1) * k);
}

let thumbCanvas: HTMLCanvasElement | undefined;
const thumbOf = (src: CanvasImageSource, det: Det, scale: number) => {
  thumbCanvas ??= Object.assign(document.createElement("canvas"), { width: 104, height: 104 });
  drawCrop(thumbCanvas, src, det, scale);
  return thumbCanvas.toDataURL("image/jpeg", 0.85);
};

/** Add one frame's detections (already above the threshold) to the saved list, newest first. */
function remember(log: Saved[], ds: Det[], now: number, at: string, src: CanvasImageSource, scale: number): Saved[] {
  const next = log.slice(), used = new Set<number>();
  for (const d of ds) {
    let bi = -1, bv = KEEP_IOU;
    next.forEach((e, i) => {
      if (used.has(e.id) || trackOf(e.det) !== trackOf(d) || now - e.last > KEEP_GAP) return;
      const v = iou(e.box, d.bbox_xyxy);
      if (v >= bv) (bv = v), (bi = i);
    });
    if (bi < 0) {
      next.unshift({ id: ++seq, det: d, box: d.bbox_xyxy, last: now, seen: 1, at, thumb: thumbOf(src, d, scale) });
      used.add(next[0].id);
      continue;
    }
    const e = next[bi];
    used.add(e.id);
    next[bi] = { ...e, box: d.bbox_xyxy, last: now, seen: e.seen + 1, ...(d.conf > e.det.conf ? { det: d, at, thumb: thumbOf(src, d, scale) } : {}) };
  }
  return next.slice(0, MAX_SAVED);
}

const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

/** POST one frame. The URL is relative on purpose: it always hits the origin that served this page. */
async function requestDetect(blob: Blob, name: string, s: Settings): Promise<DetectResult> {
  const fd = new FormData();
  fd.append("file", blob, name);
  fd.append("imgsz", String(s.imgsz));
  fd.append("tile", String(s.tile));
  fd.append("models", s.models.join(","));
  let r: Response;
  try {
    r = await fetch("/api/detect", { method: "POST", body: fd });
  } catch (e) {
    throw new Error(`can't reach ${location.host}: ${(e as Error).message}`);
  }
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    throw new Error(`HTTP ${r.status} ${detail ?? r.statusText} from ${new URL(r.url).host}`);
  }
  return r.json();
}

/* ---------- icons ---------- */
const Corners = ({ size = 22, sw = 2 }: { size?: number; sw?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round">
    <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />
    <circle cx="12" cy="9" r="2.4" />
    <path d="M8 17c.6-2.6 2.1-4 4-4s3.4 1.4 4 4" />
  </svg>
);
const IUpload = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 15V3m0 0 4 4m-4-4-4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
);
const IPlay = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z" /></svg>;
const IStop = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>;
const ISpark = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></svg>
);
const ITrash = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
);
const IDownload = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
);
const MODE_ICON: Record<Mode, React.ReactNode> = {
  image: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 16-5-5-9 9" /></svg>,
  video: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m10 9 5 3-5 3z" /></svg>,
  camera: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M15 10l5-3v10l-5-3" /><rect x="3" y="6" width="12" height="12" rx="2" /></svg>,
};

/** Square crop around a detection, drawn from the image or the last live frame. */
function Crop({ src, det, scale }: { src: CanvasImageSource | null; det: Det; scale: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (c && src) drawCrop(c, src, det, scale);
  }, [src, det, scale]);
  return <canvas ref={ref} width={104} height={104} />;
}

function Toggle({ label: text, hint, checked, onChange, tint, disabled }: { label: React.ReactNode; hint?: string; checked: boolean; onChange: (v: boolean) => void; tint?: string; disabled?: boolean }) {
  return (
    <label className={`toggle${disabled ? " off" : ""}`} style={tint ? ({ "--accent": tint } as React.CSSProperties) : undefined}>
      <span>
        {text}
        {hint && <small>{hint}</small>}
      </span>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <i />
    </label>
  );
}

export default function Station() {
  const [info, setInfo] = useState<Info | null>(null);
  const [server, setServer] = useState<"connecting" | "ok" | "err">("connecting");
  const [mode, setMode] = useState<Mode>("image");
  const [conf, setConf] = useState(0.25);
  const [imgsz, setImgsz] = useState(640);
  const [tile, setTile] = useState(false);
  const [models, setModels] = useState<string[]>(["best"]); // enabled, in info.models order
  const [merge, setMerge] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [showRings, setShowRings] = useState(true);
  const [items, setItemsState] = useState<Item[]>([]);
  const [cur, setCurState] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState(-1);
  const [view, setView] = useState({ s: 1, x: 0, y: 0 });
  const [animate, setAnimate] = useState(false);
  const [media, setMedia] = useState<Media | null>(null); // video / camera source on stage
  const [live, setLive] = useState<Live>(EMPTY_LIVE);
  const [saved, setSavedState] = useState<Saved[]>([]);
  const [savedSel, setSavedSel] = useState(-1); // id of the saved entry clicked in the list
  const [running, setRunning] = useState(false);
  const [cams, setCams] = useState<MediaDeviceInfo[]>([]);
  const [camId, setCamId] = useState<string | null>(null);
  const [imgReady, setImgReady] = useState(0); // id of the item whose <img> has loaded
  const [toast, setToast] = useState({ msg: "", err: false, show: false });
  const [dragOver, setDragOver] = useState(false);
  const [dragging, setDragging] = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const captureRef = useRef<HTMLCanvasElement | null>(null); // frame being sent
  const frameRef = useRef<HTMLCanvasElement | null>(null); // frame the current live dets belong to
  const imagesInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const itemsRef = useRef<Item[]>([]);
  const curRef = useRef(-1);
  const queueBusy = useRef(false);
  const liveToken = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const videoUrl = useRef<string | null>(null);
  const histRef = useRef<number[]>([]);
  const savedRef = useRef<Saved[]>([]); // the live loop appends to this synchronously
  const dragRef = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean; target: EventTarget | null } | null>(null);
  const dragDepth = useRef(0);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const settings: Settings = useMemo(() => ({ imgsz, tile: tile ? 640 : 0, models }), [imgsz, tile, models]);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const confRef = useRef(conf);
  confRef.current = conf;
  const merging = merge && models.length > 1;
  const mergingRef = useRef(merging);
  mergingRef.current = merging;
  const multi = models.length > 1;

  const modelOf = useMemo(() => new Map((info?.models ?? []).map((m) => [m.name, m])), [info]);
  const short = (m: string) => modelOf.get(m)?.label ?? m;
  // the model goes in the label only when there is more than one on the stage
  const label = (d: Det) => (d.by ? `${d.by.map((m) => short(m)[0]).join("+")} ${d.name} ${pct(d)}` : multi ? `${short(d.model)} · ${d.name} ${pct(d)}` : `${d.name} ${pct(d)}`);
  // list entry heading: class, plus which model(s) when there is more than one
  const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
  const title = (d: Det) => cap(d.name) + (d.by ? ` · ${d.by.map(short).join(" + ")}` : multi ? ` · ${short(d.model)}` : "");

  const curItem = mode === "image" ? items[cur] : undefined;
  const stage = mode === "image" ? (curItem ? { key: curItem.id, W: curItem.W, H: curItem.H } : null) : media;
  const stageDims = useRef<{ W: number; H: number } | null>(null);
  stageDims.current = stage ? { W: stage.W, H: stage.H } : null;
  // per-model boxes above the slider, before merging: the per-model counts come from these
  const raw = useMemo(
    () => (mode === "image" ? curItem?.dets ?? [] : live.dets).filter((d) => d.conf >= conf),
    [mode, curItem, live.dets, conf],
  );
  const dets = useMemo(() => (merging ? mergeModels(raw) : raw), [raw, merging]);

  const showToast = useCallback((msg: string, err = false) => {
    setToast({ msg, err, show: true });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast((t) => ({ ...t, show: false })), 2600);
  }, []);

  const setSaved = useCallback((log: Saved[]) => {
    savedRef.current = log;
    setSavedState(log);
  }, []);

  const setItems = useCallback((fn: (prev: Item[]) => Item[]) => {
    itemsRef.current = fn(itemsRef.current); // the queue reads this synchronously
    setItemsState(itemsRef.current);
  }, []);
  const patchItem = useCallback((id: number, patch: Partial<Item>) => setItems((list) => list.map((it) => (it.id === id ? { ...it, ...patch } : it))), [setItems]);
  const setCur = useCallback((i: number) => {
    curRef.current = i;
    setCurState(i);
    setSel(-1);
  }, []);

  /* ---------- view transform ---------- */
  const fitScale = useCallback(() => {
    const st = stageRef.current, d = stageDims.current;
    if (!st || !d) return 1;
    return Math.min(st.clientWidth / d.W, st.clientHeight / d.H) * 0.94;
  }, []);
  const fit = useCallback(() => {
    const st = stageRef.current, d = stageDims.current;
    if (!st || !d) return;
    const s = fitScale();
    setView({ s, x: (st.clientWidth - d.W * s) / 2, y: (st.clientHeight - d.H * s) / 2 });
  }, [fitScale]);
  const zoomAt = useCallback(
    (f: number, cx: number, cy: number) =>
      setView((v) => {
        const s = Math.min(Math.max(v.s * f, fitScale() * 0.5), 40);
        return { s, x: cx - ((cx - v.x) * s) / v.s, y: cy - ((cy - v.y) * s) / v.s };
      }),
    [fitScale],
  );
  const zoomTo = useCallback((d: Det) => {
    const st = stageRef.current!;
    const [x1, y1, x2, y2] = d.bbox_xyxy, w = Math.max(x2 - x1, 8), h = Math.max(y2 - y1, 8);
    const s = Math.min(Math.max(Math.min(st.clientWidth / w, st.clientHeight / h) * 0.25, fitScale()), 40);
    setAnimate(true);
    setView({ s, x: st.clientWidth / 2 - ((x1 + x2) / 2) * s, y: st.clientHeight / 2 - ((y1 + y2) / 2) * s });
    setTimeout(() => setAnimate(false), 260);
  }, [fitScale]);

  // refit when a different frame or source goes on stage, and when the stage resizes
  useEffect(() => fit(), [stage?.key, stage?.W, stage?.H, fit]);
  useEffect(() => {
    const ro = new ResizeObserver(() => fit());
    ro.observe(stageRef.current!);
    return () => ro.disconnect();
  }, [fit]);
  useEffect(() => {
    const st = stageRef.current!;
    const onWheel = (e: WheelEvent) => {
      if (!stageDims.current) return;
      e.preventDefault();
      const r = st.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    };
    st.addEventListener("wheel", onWheel, { passive: false });
    return () => st.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const select = useCallback(
    (i: number, zoom: boolean) => {
      const next = i >= 0 && i < dets.length && i !== sel ? i : -1;
      setSel(next);
      if (next >= 0 && zoom) zoomTo(dets[next]);
    },
    [dets, sel, zoomTo],
  );
  useEffect(() => {
    document.querySelector(".det.sel")?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  /* ---------- image batch ---------- */
  const runQueue = useCallback(async () => {
    if (queueBusy.current) return;
    queueBusy.current = true;
    setBusy(true);
    try {
      for (;;) {
        const key = keyOf(settingsRef.current), list = itemsRef.current;
        // current frame first, then the rest in order
        const it = [curRef.current, ...list.keys()].map((i) => list[i]).find((it) => it && it.key !== key && it.status !== "error");
        if (!it) break;
        patchItem(it.id, { status: "running" });
        try {
          const r = await requestDetect(it.file, it.name, settingsRef.current);
          patchItem(it.id, { dets: r.detections, ms: r.ms, times: r.times, status: "done", key });
        } catch (e) {
          patchItem(it.id, { status: "error", key });
          showToast(`${it.name}: ${(e as Error).message}`, true);
        }
      }
    } finally {
      queueBusy.current = false;
      setBusy(false);
    }
  }, [patchItem, showToast]);

  useEffect(() => {
    setItems((list) => list.map((it) => (it.status === "error" ? { ...it, status: "pending" } : it)));
    runQueue();
  }, [settings, runQueue, setItems]);
  useEffect(() => {
    if (cur >= 0) runQueue();
  }, [cur, runQueue]);

  const addImages = useCallback(
    async (files: File[]) => {
      const start = itemsRef.current.length, added: Item[] = [];
      for (const f of files) {
        const url = URL.createObjectURL(f);
        const dim = await new Promise<[number, number] | null>((res) => {
          const im = new Image();
          im.onload = () => res([im.naturalWidth, im.naturalHeight]);
          im.onerror = () => res(null);
          im.src = url;
        });
        if (!dim) {
          URL.revokeObjectURL(url);
          showToast(`Can't read ${f.name}`, true);
          continue;
        }
        added.push({ id: ++seq, name: f.name, file: f, url, W: dim[0], H: dim[1], dets: null, ms: null, times: {}, status: "pending", key: null });
      }
      if (!added.length) return;
      setItems((list) => [...list, ...added]);
      setCur(start);
      runQueue();
    },
    [runQueue, setCur, setItems, showToast],
  );

  const clearItems = () => {
    itemsRef.current.forEach((i) => URL.revokeObjectURL(i.url));
    setItems(() => []);
    setCur(-1);
  };

  const loadSamples = async () => {
    if (!info?.samples.length) return;
    const files = await Promise.all(
      info.samples.map(async (n) => {
        const r = await fetch(`/api/samples/${encodeURIComponent(n)}`);
        return new File([await r.blob()], n, { type: r.headers.get("content-type") ?? "image/jpeg" });
      }),
    );
    addImages(files);
  };

  /* ---------- live: video file & camera ---------- */
  const stopLive = useCallback(() => {
    liveToken.current++;
    setRunning(false);
    const v = videoRef.current;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (v) v.srcObject = null;
      setMedia(null);
    } else v?.pause();
  }, []);

  const liveLoop = useCallback(
    async (token: number) => {
      const v = videoRef.current!;
      const cap = (captureRef.current ??= document.createElement("canvas"));
      const frame = (frameRef.current ??= document.createElement("canvas"));
      const g = cap.getContext("2d")!;
      const times: number[] = [];
      while (liveToken.current === token) {
        if (v.readyState < 2 || !v.videoWidth) {
          await sleep(50);
          continue;
        }
        const k = Math.min(1, MAX_SEND / Math.max(v.videoWidth, v.videoHeight));
        const w = Math.round(v.videoWidth * k), h = Math.round(v.videoHeight * k);
        if (cap.width !== w || cap.height !== h) (cap.width = w), (cap.height = h);
        g.drawImage(v, 0, 0, w, h);
        const blob = await new Promise<Blob | null>((r) => cap.toBlob(r, "image/jpeg", 0.85));
        if (!blob) continue;
        try {
          const r = await requestDetect(blob, "frame.jpg", settingsRef.current);
          if (liveToken.current !== token) break;
          // keep the frame these boxes belong to, for the crops in the list
          if (frame.width !== w || frame.height !== h) (frame.width = w), (frame.height = h);
          frame.getContext("2d")!.drawImage(cap, 0, 0);
          const sx = v.videoWidth / r.width;
          const ds = r.detections.map((d) => ({ ...d, bbox_xyxy: d.bbox_xyxy.map((x) => x * sx) as BBox }));
          const now = performance.now();
          times.push(now);
          while (times.length && now - times[0] > 2000) times.shift();
          const fps = times.length > 1 ? (times.length - 1) / ((now - times[0]) / 1000) : 0;
          const above = ds.filter((d) => d.conf >= confRef.current);
          const keep = mergingRef.current ? mergeModels(above) : above;
          histRef.current = [...histRef.current, keep.length].slice(-120);
          setLive({ dets: ds, ms: r.ms, times: r.times, fps, hist: histRef.current });
          // camera: wall clock; video file: position in the clip
          const at = streamRef.current ? new Date().toLocaleTimeString([], { hour12: false }) : clock(v.currentTime);
          if (keep.length) setSaved(remember(savedRef.current, keep, now, at, frame, w / v.videoWidth));
          setSel((s) => (s >= ds.length ? -1 : s));
        } catch (e) {
          showToast(`Detector error: ${(e as Error).message}`, true);
          await sleep(1000);
        }
      }
    },
    [setSaved, showToast],
  );

  const startLive = useCallback(() => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const token = ++liveToken.current;
    setRunning(true);
    if (!streamRef.current) v.play().catch(() => {});
    liveLoop(token);
  }, [liveLoop]);

  const startCamera = useCallback(
    async (id: string | null = camId) => {
      stopLive();
      if (!navigator.mediaDevices?.getUserMedia) {
        showToast(`Camera needs a secure page: open http://localhost:${location.port} instead of ${location.host}`, true);
        return;
      }
      try {
        const video: MediaTrackConstraints = { width: { ideal: 1920 }, height: { ideal: 1080 } };
        if (id) video.deviceId = { exact: id };
        const stream = await navigator.mediaDevices.getUserMedia({ video, audio: false });
        streamRef.current = stream;
        const v = videoRef.current!;
        v.removeAttribute("src");
        v.loop = false;
        v.srcObject = stream;
        await v.play();
        const track = stream.getVideoTracks()[0];
        // device labels are only readable once permission is granted
        setCams((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput"));
        setCamId(track?.getSettings().deviceId ?? id);
        histRef.current = [];
        setLive(EMPTY_LIVE);
        setSaved([]);
        setMedia({ key: ++seq, W: v.videoWidth, H: v.videoHeight, name: track?.label || "Camera" });
        startLive();
      } catch (e) {
        showToast(`Camera unavailable: ${(e as Error).message}`, true);
      }
    },
    [camId, setSaved, showToast, startLive, stopLive],
  );

  const switchMode = useCallback(
    (m: Mode) => {
      stopLive();
      const v = videoRef.current;
      if (v) {
        v.pause();
        v.removeAttribute("src");
        v.srcObject = null;
        v.load();
      }
      setMedia(null);
      setLive(EMPTY_LIVE);
      setSaved([]);
      histRef.current = [];
      setSel(-1);
      setMode(m);
      history.replaceState(null, "", m === "image" ? location.pathname : `#${m}`);
    },
    [setSaved, stopLive],
  );

  const openVideo = useCallback(
    (f: File) => {
      if (mode !== "video") switchMode("video");
      else stopLive();
      const v = videoRef.current!;
      if (videoUrl.current) URL.revokeObjectURL(videoUrl.current);
      videoUrl.current = URL.createObjectURL(f);
      v.srcObject = null;
      v.loop = true;
      v.onloadedmetadata = () => {
        histRef.current = [];
        setLive(EMPTY_LIVE);
        setSaved([]);
        setMedia({ key: ++seq, W: v.videoWidth, H: v.videoHeight, name: f.name });
        startLive();
      };
      v.onerror = () => showToast("This browser can't play that video", true);
      v.src = videoUrl.current;
    },
    [mode, setSaved, showToast, startLive, stopLive, switchMode],
  );

  const addFiles = useCallback(
    (list: FileList | File[]) => {
      const files = [...list];
      const imgs = files.filter((f) => f.type.startsWith("image/"));
      const vid = files.find((f) => f.type.startsWith("video/"));
      if (vid && !imgs.length) return openVideo(vid);
      if (!imgs.length) return showToast("No images in the selection", true);
      if (mode !== "image") switchMode("image");
      addImages(imgs);
    },
    [addImages, mode, openVideo, showToast, switchMode],
  );

  /* ---------- startup: model info, then #camera / #video ---------- */
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/info");
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.detail ?? `HTTP ${r.status}`);
        setInfo(body);
        if (!body.models.some((m: ModelInfo) => m.name === "best")) setModels([body.models[0].name]);
        setServer("ok");
      } catch (e) {
        setServer("err");
        showToast(`Detector not ready: ${(e as Error).message}`, true);
      }
      const m = location.hash.slice(1);
      if (m === "video" || m === "camera") switchMode(m);
      if (m === "camera") startCamera(null);
    })();
    // once, on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------- keyboard, paste ---------- */
  const addFilesRef = useRef(addFiles);
  addFilesRef.current = addFiles;
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {});
  keyRef.current = (e) => {
    const t = e.target as HTMLElement;
    // the slider keeps its arrow keys, everything else still works after touching it
    if (t.matches("select") || (t.matches("input") && e.key.startsWith("Arrow"))) return;
    if (mode === "image" && e.key === "ArrowRight" && cur < items.length - 1) setCur(cur + 1);
    else if (mode === "image" && e.key === "ArrowLeft" && cur > 0) setCur(cur - 1);
    else if (e.key === "Escape") setSel(-1);
    else if (e.key === "f") fit();
    else if (e.key === " " && mode === "video" && media) {
      e.preventDefault();
      if (running) stopLive();
      else startLive();
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => keyRef.current(e);
    const onPaste = (e: ClipboardEvent) => {
      const f = [...(e.clipboardData?.files ?? [])];
      if (f.length) addFilesRef.current(f);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("paste", onPaste);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("paste", onPaste);
    };
  }, []);

  /* ---------- export ---------- */
  const isLive = mode !== "image";
  const shownSaved = saved.filter((e) => e.det.conf >= conf);
  const exportJson = () => {
    // same record format as src/detection/detect.py, plus the class; live: the saved list, with when it was seen
    const rec = (d: Det) => ({ bbox_xyxy: d.bbox_xyxy, conf: d.conf, cls: d.cls, name: d.name, model: d.model, ...(d.by ? { by: d.by } : {}) });
    const recs = isLive
      ? shownSaved.map((e) => ({ image: media?.name ?? "", at: e.at, seen: e.seen, ...rec(e.det) }))
      : itemsRef.current.flatMap((it) => {
          const above = (it.dets ?? []).filter((d) => d.conf >= conf);
          return (merging ? mergeModels(above) : above).map((d) => ({ image: it.name, ...rec(d) }));
        });
    const a = document.createElement("a");
    a.download = "detections.json";
    a.href = URL.createObjectURL(new Blob([JSON.stringify(recs, null, 1)], { type: "application/json" }));
    a.click();
    URL.revokeObjectURL(a.href);
    showToast(isLive ? `Exported ${recs.length} saved detections` : `Exported ${recs.length} detections from ${itemsRef.current.length} images`);
  };

  /* ---------- stage pointer ---------- */
  const onPointerDown = (e: React.PointerEvent) => {
    if (!stage || (e.target as HTMLElement).closest(".hud, .empty")) return;
    dragRef.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false, target: e.target };
    stageRef.current!.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    d.moved = true;
    setDragging(true);
    setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
  };
  const onPointerUp = () => {
    const d = dragRef.current;
    if (d && !d.moved) {
      const i = (d.target as Element | null)?.getAttribute?.("data-i");
      select(i != null ? Number(i) : -1, false);
    }
    dragRef.current = null;
    setDragging(false);
  };

  /* ---------- derived display ---------- */
  const s = view.s;
  const countOf = (ds: Det[] | null) => {
    const above = (ds ?? []).filter((d) => d.conf >= conf);
    return merging ? mergeModels(above).length : above.length;
  };
  const tot = items.reduce((a, i) => a + countOf(i.dets), 0);
  const times = isLive ? live.times : curItem?.times ?? {};
  const perModel = models.map((name) => ({ name, n: raw.filter((d) => d.model === name).length, ms: times[name] }));
  const toggleModel = (name: string, on: boolean) => {
    const order = (info?.models ?? []).map((m) => m.name);
    setModels((cur) => order.filter((n) => (n === name ? on : cur.includes(n))));
    setSel(-1);
  };
  const statusText = server === "err" ? "Server offline" : server === "connecting" ? "Connecting" : running ? "Live" : busy ? "Detecting" : "Ready";
  const statusDot = server === "err" ? "err" : server === "connecting" ? "" : running || busy ? "busy" : "ok";
  const hudDot = isLive ? (running ? "live" : "") : curItem?.status === "done" ? "ok" : curItem?.status === "error" ? "err" : "busy";
  const hudName = isLive ? media?.name ?? "" : curItem ? `${curItem.name}  ·  ${cur + 1}/${items.length}` : "";
  const cropSrc: CanvasImageSource | null = isLive ? frameRef.current : imgReady === curItem?.id ? imgRef.current : null;
  const cropScale = isLive && media && frameRef.current ? frameRef.current.width / media.W : 1;
  const sparkPts = live.hist.map((c, i) => `${((i + 120 - live.hist.length) * 120) / 119},${38 - (c / Math.max(1, ...live.hist)) * 34}`);
  const countSub = !stage
    ? "no frame yet"
    : isLive
      ? running ? "in current frame" : "last frame"
      : curItem?.status === "running" ? "detecting…" : curItem?.status === "error" ? "failed" : `at conf ≥ ${conf.toFixed(2)}`;
  const countNote = multi && !merging ? `boxes from ${models.length} models, not merged` : merging ? "merged across models" : "";
  const fmt = (v: number | undefined) => (v == null ? "—" : v.toFixed(3));

  const fs = 11 / s, pad = 3 / s;

  return (
    <div className="app">
      <header>
        <div className="brand">
          <Corners />
          Victim Detection <small>· Station</small>
        </div>
        <div className="spacer" />
        {/* the files are what runs; base is only the architecture each was fine-tuned from */}
        <span className="chip hide-sm" title={models.map((n) => modelOf.get(n)?.source ?? n).join("\n")}>
          {multi ? "Models" : "Model"} <b>{info ? models.map(short).join(" + ") : "…"}</b>
          {info && !multi && modelOf.get(models[0])?.base ? ` · ${modelOf.get(models[0])!.base!.replace(/\.pt$/, "").toUpperCase()}` : ""}
        </span>
        <span className="chip hide-sm">Runtime <b>{info ? `${info.runtime} · ${info.device.toUpperCase()}` : "…"}</b></span>
        <span className="chip"><span className={`dot ${statusDot}`} /><b>{statusText}</b></span>
      </header>

      <main>
        {/* ======== controls ======== */}
        <aside className="left">
          <section className="block">
            <h3>Source</h3>
            <div className="seg">
              {(["image", "video", "camera"] as Mode[]).map((k) => (
                <button key={k} className={mode === k ? "on" : ""} onClick={() => mode !== k && switchMode(k)}>
                  {MODE_ICON[k]}
                  {k === "image" ? "Images" : k === "video" ? "Video" : "Camera"}
                </button>
              ))}
            </div>
            <div className="row">
              {mode === "image" && <button className="btn" onClick={() => imagesInput.current?.click()}><IUpload />Add images</button>}
              {mode === "video" && <button className="btn" onClick={() => videoInput.current?.click()}><IUpload />Open video</button>}
              {mode === "camera" &&
                (running ? (
                  <button className="btn danger" onClick={stopLive}><IStop />Stop camera</button>
                ) : (
                  <button className="btn primary" onClick={() => startCamera()}><IPlay />Start camera</button>
                ))}
            </div>
            {mode === "image" && items.length > 0 && (
              <div className="row"><button className="btn" onClick={clearItems}><ITrash />Clear</button></div>
            )}
            {mode === "video" && media && (
              <div className="row">
                {running ? (
                  <button className="btn danger" onClick={stopLive}><IStop />Stop</button>
                ) : (
                  <button className="btn primary" onClick={startLive}><IPlay />Play &amp; detect</button>
                )}
              </div>
            )}
            {mode === "camera" && cams.length > 1 && (
              <select
                className="cam-select"
                value={camId ?? ""}
                onChange={(e) => {
                  setCamId(e.target.value);
                  if (running) startCamera(e.target.value);
                }}
              >
                {cams.map((c, i) => <option key={c.deviceId} value={c.deviceId}>{c.label || `Camera ${i + 1}`}</option>)}
              </select>
            )}
          </section>

          <section className="block">
            <h3>Models</h3>
            {(info?.models ?? []).map((md) => {
              const on = models.includes(md.name);
              return (
                <div className="field" key={md.name}>
                  <Toggle
                    label={md.label}
                    hint={`${md.weights} · ${md.classes.join(", ")} · trained at ${md.imgsz}px`}
                    tint={modelColor(md.name)}
                    checked={on}
                    disabled={on && models.length === 1}
                    onChange={(v) => toggleModel(md.name, v)}
                  />
                </div>
              );
            })}
            {multi && (
              <div className="field">
                <Toggle label="Merge models" hint={`one box per person, IoU ≥ ${MERGE_IOU}; green = found by several`} checked={merge} onChange={(v) => { setMerge(v); setSel(-1); }} />
              </div>
            )}
          </section>

          <section className="block">
            <h3>Detection</h3>
            <div className="field">
              <div className="field-head"><span>Confidence</span><output>{conf.toFixed(2)}</output></div>
              <input type="range" min={0.05} max={0.95} step={0.01} value={conf} onChange={(e) => { setConf(Number(e.target.value)); setSel(-1); }} />
            </div>
            <div className="field">
              <div className="field-head"><span>Input size</span></div>
              <select value={imgsz} onChange={(e) => setImgsz(Number(e.target.value))}>
                <option value={640}>640 px</option>
                <option value={960}>960 px</option>
                <option value={1280}>1280 px · small persons</option>
              </select>
            </div>
            <div className="field"><Toggle label="Tiled inference" hint="640 px tiles, 20% overlap" checked={tile} onChange={setTile} /></div>
          </section>

          <section className="block">
            <h3>Display</h3>
            <div className="field"><Toggle label="Labels" checked={showLabels} onChange={setShowLabels} /></div>
            <div className="field"><Toggle label="Rings on tiny boxes" checked={showRings} onChange={setShowRings} /></div>
          </section>

          <section className="block">
            <h3>Model scores</h3>
            <table className="mtable">
              <thead><tr><th /><th>mAP50</th><th>50-95</th><th>P</th><th>R</th></tr></thead>
              <tbody>
                {(info?.models ?? []).map((md) => (
                  <tr key={md.name} className={models.includes(md.name) ? "" : "faded"}>
                    <th style={{ color: modelColor(md.name) }}>{md.label}</th>
                    {["mAP50", "mAP50-95", "precision", "recall"].map((k) => <td key={k}>{fmt(md.metrics[k])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            {info && (
              <div className="meta">
                {info.models.map((md) => (
                  <div key={md.name}><b>{md.label}</b>: {md.source ?? md.weights}{md.epochs ? ` · ${md.epochs} ep` : ""}{md.trained ? ` · ${md.trained.slice(0, 10)}` : ""}</div>
                ))}
                Each on its own val set (ours, VisDrone-DET test, COCO pose), so not comparable across rows: compare them on the stage.
              </div>
            )}
          </section>
        </aside>

        {/* ======== viewer ======== */}
        <div className="center">
          <div
            ref={stageRef}
            className={`stage${dragging ? " dragging" : ""}${dragOver ? " over" : ""}`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onDoubleClick={(e) => !(e.target as HTMLElement).closest(".hud") && fit()}
            onDragEnter={(e) => { e.preventDefault(); if (++dragDepth.current === 1) setDragOver(true); }}
            onDragLeave={() => { if (--dragDepth.current === 0) setDragOver(false); }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              dragDepth.current = 0;
              setDragOver(false);
              if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
            }}
          >
            <div className="world" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${s})`, transition: animate ? "transform .25s ease" : undefined }}>
              {curItem && (
                <img
                  ref={imgRef}
                  key={curItem.id}
                  src={curItem.url}
                  width={curItem.W}
                  height={curItem.H}
                  alt=""
                  draggable={false}
                  onLoad={() => setImgReady(curItem.id)}
                />
              )}
              {/* always mounted, so a camera can be attached before the first render of its mode */}
              <video ref={videoRef} muted playsInline width={media?.W} height={media?.H} style={{ display: isLive && media ? "block" : "none" }} />
              {stage && (
                <svg width={stage.W} height={stage.H} viewBox={`0 0 ${stage.W} ${stage.H}`} className={sel >= 0 ? "dim" : ""}>
                  {dets.map((d, i) => {
                    const [x1, y1, x2, y2] = d.bbox_xyxy, w = x2 - x1, h = y2 - y1, on = i === sel ? " sel" : "";
                    const style = { "--c": color(d) } as React.CSSProperties;
                    const txt = label(d), tw = txt.length * fs * 0.62 + pad * 2, th = fs + pad * 2, ty = y1 - th < 0 ? y2 : y1 - th;
                    return (
                      <g key={i}>
                        {showRings && Math.max(w, h) * s < TINY && (
                          <circle className={`ring${on}`} style={style} cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} r={12 / s} strokeWidth={1.5 / s} />
                        )}
                        <rect className={`box${on}`} style={style} x={x1} y={y1} width={w} height={h} data-i={i} strokeWidth={(on ? 2.5 : 1.5) / s} strokeOpacity={0.45 + 0.55 * d.conf} />
                        {showLabels && (
                          <g className={`tag${on}`} style={style}>
                            <rect x={x1} y={ty} width={tw} height={th} rx={2 / s} />
                            <text x={x1 + pad} y={ty + th - pad - fs * 0.15} fontSize={fs}>{txt}</text>
                          </g>
                        )}
                      </g>
                    );
                  })}
                </svg>
              )}
            </div>

            <div className="hud tl" hidden={!stage}>
              <div className="pill"><span className={`dot ${hudDot}`} /><span id="hudName" className="mono">{hudName}</span></div>
              {isLive && running && (
                <div className="pill mono">
                  <b style={{ color: "var(--err)" }}>LIVE</b>
                  <span>{live.fps ? live.fps.toFixed(1) : "—"}</span><span className="k">fps</span>
                  <span>{live.ms ? live.ms.toFixed(0) : "—"}</span><span className="k">ms</span>
                </div>
              )}
            </div>
            <div className="hud tr" hidden={!stage}>
              <div className="pill">
                <span className="icon-btn" title="Zoom out" onClick={() => zoomAt(1 / 1.4, stageRef.current!.clientWidth / 2, stageRef.current!.clientHeight / 2)}>−</span>
                <span className="mono" style={{ minWidth: 42, textAlign: "center" }}>{Math.round(s * 100)}%</span>
                <span className="icon-btn" title="Zoom in" onClick={() => zoomAt(1.4, stageRef.current!.clientWidth / 2, stageRef.current!.clientHeight / 2)}>+</span>
                <span className="icon-btn" title="Fit (double-click)" onClick={fit}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
                </span>
              </div>
            </div>
            <div className="hud bl" hidden={!stage}>
              <div className="pill"><span className="k">scroll</span> zoom <span className="k">drag</span> pan <span className="k">click</span> select <kbd>←</kbd><kbd>→</kbd></div>
            </div>

            <div className="empty" hidden={!!stage}>
              <div className="drop">
                <Corners size={42} sw={1.5} />
                {mode === "image" && (
                  <>
                    <h2>Drop drone frames here</h2>
                    <p>One or many images. Everything runs locally on this station.</p>
                    <div className="row">
                      <button className="btn primary" onClick={() => imagesInput.current?.click()}><IUpload />Choose images</button>
                      {!!info?.samples.length && <button className="btn" onClick={loadSamples}><ISpark />Try samples</button>}
                    </div>
                  </>
                )}
                {mode === "video" && (
                  <>
                    <h2>Drop a video file</h2>
                    <p>Recorded drone footage. Frames are sent to the detector as it plays.</p>
                    <div className="row"><button className="btn primary" onClick={() => videoInput.current?.click()}><IUpload />Choose video</button></div>
                  </>
                )}
                {mode === "camera" && (
                  <>
                    <h2>Live camera</h2>
                    <p>Use a webcam or a capture card carrying the drone feed.</p>
                    <div className="row"><button className="btn primary" onClick={() => startCamera()}><IPlay />Start camera</button></div>
                  </>
                )}
              </div>
            </div>
          </div>

          {mode === "image" && items.length > 0 && (
            <div className="strip">
              {items.map((it, i) => {
                const n = countOf(it.dets), wait = it.status === "pending" || it.status === "running";
                return (
                  <div key={it.id} className={`thumb${i === cur ? " on" : ""}`} title={it.name} onClick={() => setCur(i)}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={it.url} alt="" />
                    {wait ? <div className="spinner" /> : <span className={`badge${n > 0 ? " hit" : ""}`}>{it.status === "error" ? "!" : n}</span>}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ======== results ======== */}
        <aside className={`right${isLive ? " live-on" : ""}`}>
          <section className="block">
            <h3>Persons detected</h3>
            <div className="count"><b className={dets.length ? "hit" : ""}>{stage ? dets.length : "—"}</b><span>{countSub}</span></div>
            <div className="stats">
              <div><span>Inference</span><b>{isLive ? (live.ms ? `${live.ms.toFixed(0)} ms` : "—") : curItem?.ms != null ? `${curItem.ms.toFixed(0)} ms` : "—"}</b></div>
              <div><span>Frame</span><b>{stage ? `${stage.W}×${stage.H}` : "—"}</b></div>
              <div><span>{isLive ? "FPS" : "Batch"}</span><b>{isLive ? (live.fps ? live.fps.toFixed(1) : "—") : items.length ? `${tot} / ${items.length}` : "—"}</b></div>
            </div>
            {multi && (
              <div className="per-model">
                {perModel.map((p) => (
                  <div key={p.name}>
                    <i style={{ background: modelColor(p.name) }} />
                    <span>{short(p.name)}</span>
                    <b>{stage ? p.n : "—"}</b>
                    <small>{p.ms != null ? `${p.ms.toFixed(0)} ms` : ""}</small>
                  </div>
                ))}
                <div className="note">{countNote}</div>
              </div>
            )}
            <svg className="spark" viewBox="0 0 120 40" preserveAspectRatio="none">
              <polygon points={sparkPts.length ? `${sparkPts[0].split(",")[0]},40 ${sparkPts.join(" ")} 120,40` : ""} />
              <polyline points={sparkPts.join(" ")} />
            </svg>
          </section>
          <div className="list-wrap">
            <div className="list-head">
              <h3>Detections</h3>
              {isLive ? (
                <span className="list-meta">
                  {shownSaved.length} saved at ≥ {conf.toFixed(2)}
                  <button className="link" disabled={!saved.length} onClick={() => { setSaved([]); setSavedSel(-1); }}>Clear</button>
                </span>
              ) : (
                <span className="list-meta">by confidence</span>
              )}
            </div>
            <div className="list">
              {isLive ? (
                shownSaved.length === 0 ? (
                  <div className="none">
                    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
                    {stage ? <>Nothing saved yet.<br />Every person at ≥ {conf.toFixed(2)} is kept here.</> : "Results appear here."}
                  </div>
                ) : (
                  shownSaved.slice(0, 200).map((e) => {
                    const [x1, y1, x2, y2] = e.det.bbox_xyxy;
                    return (
                      <div key={e.id} className={`det${e.id === savedSel ? " sel" : ""}`} onClick={() => { const on = e.id !== savedSel; setSavedSel(on ? e.id : -1); if (on) zoomTo(e.det); }}>
                        <img src={e.thumb} alt="" />
                        <div>
                          <div className="t" style={{ color: color(e.det) }}>{title(e.det)}<small>{e.at}</small></div>
                          <div className="s">{Math.round(x2 - x1)}×{Math.round(y2 - y1)} px · seen {e.seen}×</div>
                          <div className="bar"><i style={{ width: `${e.det.conf * 100}%`, background: color(e.det) }} /></div>
                        </div>
                        <div className="pct">{Math.round(e.det.conf * 100)}%</div>
                      </div>
                    );
                  })
                )
              ) : dets.length === 0 ? (
                <div className="none">
                  <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
                  {stage ? <>No detections above {conf.toFixed(2)}.<br />Lower the threshold or try tiling.</> : "Results appear here."}
                </div>
              ) : (
                dets.slice(0, 200).map((d, i) => {
                  const [x1, y1, x2, y2] = d.bbox_xyxy;
                  return (
                    <div key={i} className={`det${i === sel ? " sel" : ""}`} onClick={() => select(i, !isLive)}>
                      <Crop src={cropSrc} det={d} scale={cropScale} />
                      <div>
                        <div className="t" style={{ color: color(d) }}>{title(d)}<small>#{i + 1}</small></div>
                        <div className="s">{Math.round(x2 - x1)}×{Math.round(y2 - y1)} px · ({Math.round((x1 + x2) / 2)}, {Math.round((y1 + y2) / 2)})</div>
                        <div className="bar"><i style={{ width: `${d.conf * 100}%`, background: color(d) }} /></div>
                      </div>
                      <div className="pct">{Math.round(d.conf * 100)}%</div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
          <div className="foot">
            <button className="btn" disabled={isLive ? !shownSaved.length : !items.some((i) => i.dets)} onClick={exportJson}><IDownload />Export detections.json</button>
          </div>
        </aside>
      </main>

      <input ref={imagesInput} type="file" accept="image/*" multiple hidden onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
      <input ref={videoInput} type="file" accept="video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) openVideo(f); e.target.value = ""; }} />
      <div className={`toast${toast.show ? " show" : ""}${toast.err ? " err" : ""}`}>{toast.msg}</div>
    </div>
  );
}
