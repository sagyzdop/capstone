// MLX90640 UDP frames -> JPEG + person boxes. Packet format is the one raspberry/mlx_stream.cpp sends:
// <IIQff header (24 bytes) + 768 little-endian float32 temperatures = 3096 bytes.
import dgram from "node:dgram";
import fs from "node:fs";
import path from "node:path";
import * as ort from "onnxruntime-node";
import sharp from "sharp";
import { MODEL_DIR, type Detection } from "./detector";

const MAGIC = 0x3039584d; // "MX90"
const PACKET = 24 + 768 * 4;
const W = 32, H = 24, SCALE = 20; // sensor px -> JPEG px (640x480)
const PORT = Number(process.env.THERMAL_UDP_PORT ?? 5005);
const HOST = process.env.THERMAL_UDP_HOST ?? "0.0.0.0";
const STOPS = [[0, 0, 4], [87, 16, 110], [187, 55, 84], [249, 142, 8], [252, 255, 164]];

export type ThermalDetections = { width: number; height: number; ms: number; detections: Detection[] };
export type ThermalFrame = {
  jpeg: Buffer;
  at: number;
  frameId: number;
  min: number;
  max: number;
  ta: number;
  det: ThermalDetections | null; // null when models/thermal.onnx is not there
};
type ThermalMeta = { weights: string; note: string; threshold: number; min_pixels: number; names: Record<string, string> };
type ThermalModel = { session: ort.InferenceSession; meta: ThermalMeta };
type State = { latest: ThermalFrame | null; error: string | null; modelError: string | null; seq: number; shown: number };

// one socket and one session per process; globalThis survives dev hot reloads and is shared by every route
const g = globalThis as typeof globalThis & { __thermal?: State; __thermalModel?: Promise<ThermalModel> };

function colorize(temps: Float32Array, min: number, max: number) {
  const raw = Buffer.alloc(768 * 3);
  const span = Math.max(max - min, 0.5);
  for (let i = 0; i < 768; i++) {
    const v = Math.min(1, Math.max(0, (temps[i] - min) / span));
    const p = v * (STOPS.length - 1);
    const lo = Math.min(STOPS.length - 2, Math.floor(p));
    const f = p - lo;
    for (let c = 0; c < 3; c++) raw[i * 3 + c] = Math.round(STOPS[lo][c] * (1 - f) + STOPS[lo + 1][c] * f);
  }
  return raw;
}

function getThermalModel(): Promise<ThermalModel> {
  g.__thermalModel ??= (async () => {
    const onnx = path.join(MODEL_DIR, "thermal.onnx");
    if (!fs.existsSync(onnx)) throw new Error(`${onnx} is missing: run \`python scripts/make_thermal_model.py\``);
    const meta = JSON.parse(fs.readFileSync(path.join(MODEL_DIR, "thermal.json"), "utf8")) as ThermalMeta;
    const session = await ort.InferenceSession.create(onnx, { executionProviders: ["cpu"] });
    return { session, meta };
  })().catch((e) => {
    g.__thermalModel = undefined; // retry on the next frame, e.g. after the model is written
    throw e;
  });
  return g.__thermalModel;
}

/** Person-probability map -> one box per 8-connected blob above threshold, in JPEG pixels. */
function blobs(p: Float32Array, meta: ThermalMeta): Detection[] {
  const seen = new Uint8Array(W * H);
  const out: Detection[] = [];
  for (let i = 0; i < W * H; i++) {
    if (seen[i] || p[i] < meta.threshold) continue;
    let x0 = W, y0 = H, x1 = -1, y1 = -1, sum = 0, n = 0;
    const stack = [i];
    seen[i] = 1;
    while (stack.length) {
      const j = stack.pop()!;
      const x = j % W, y = (j - x) / W;
      x0 = Math.min(x0, x), x1 = Math.max(x1, x), y0 = Math.min(y0, y), y1 = Math.max(y1, y);
      sum += p[j], n++;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy, k = ny * W + nx;
          if (nx < 0 || ny < 0 || nx >= W || ny >= H || seen[k] || p[k] < meta.threshold) continue;
          seen[k] = 1;
          stack.push(k);
        }
      }
    }
    if (n < meta.min_pixels) continue;
    out.push({
      bbox_xyxy: [x0 * SCALE, y0 * SCALE, (x1 + 1) * SCALE, (y1 + 1) * SCALE],
      conf: Math.round((sum / n) * 1000) / 1000,
      cls: 0,
      name: meta.names[0] ?? "person",
    });
  }
  return out.sort((a, b) => b.conf - a.conf);
}

async function detectThermal(s: State, temps: Float32Array): Promise<ThermalDetections | null> {
  let model: ThermalModel;
  try {
    model = await getThermalModel();
    s.modelError = null;
  } catch (e) {
    s.modelError = (e as Error).message;
    return null;
  }
  const t = performance.now();
  const out = await model.session.run({ [model.session.inputNames[0]]: new ort.Tensor("float32", temps, [1, 1, H, W]) });
  const detections = blobs(out[model.session.outputNames[0]].data as Float32Array, model.meta);
  return { width: W * SCALE, height: H * SCALE, ms: Math.round((performance.now() - t) * 10) / 10, detections };
}

function start(): State {
  if (g.__thermal) return g.__thermal;
  const s: State = (g.__thermal = { latest: null, error: null, modelError: null, seq: 0, shown: 0 });
  const sock = dgram.createSocket("udp4");
  sock.on("error", (e) => {
    s.error = e.message;
  });
  sock.on("message", (msg) => {
    if (msg.length !== PACKET || msg.readUInt32LE(0) !== MAGIC) return;
    const frameId = msg.readUInt32LE(4);
    const ta = msg.readFloatLE(16);
    const temps = new Float32Array(768);
    let min = Infinity, max = -Infinity;
    for (let i = 0; i < 768; i++) {
      const t = msg.readFloatLE(24 + i * 4);
      temps[i] = t;
      if (t < min) min = t;
      if (t > max) max = t;
    }
    const seq = ++s.seq;
    const jpeg = sharp(colorize(temps, min, max), { raw: { width: W, height: H, channels: 3 } })
      .resize(W * SCALE, H * SCALE, { kernel: "cubic" })
      .jpeg({ quality: 85 })
      .toBuffer();
    void Promise.all([jpeg, detectThermal(s, temps)])
      .then(([jpeg, det]) => {
        if (seq < s.shown) return; // an older frame finished after a newer one
        s.shown = seq;
        s.latest = { jpeg, at: Date.now(), frameId, min, max, ta, det };
      })
      .catch((e) => { s.error = (e as Error).message; });
  });
  sock.bind(PORT, HOST);
  return s;
}

export function thermalFrame(): ThermalFrame | null {
  return start().latest;
}

export function thermalError(): string | null {
  return start().error;
}

export function thermalModelError(): string | null {
  return start().modelError;
}

export function thermalPort() {
  return PORT;
}
