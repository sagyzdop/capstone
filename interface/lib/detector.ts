// Server-side victim detector: ONNX Runtime on the CPU, same pre/post-processing as ultralytics.
// Several models can sit in models/ (<name>.onnx + <name>.json); each request names the ones to run.
import fs from "node:fs";
import path from "node:path";
import * as ort from "onnxruntime-node";
import sharp from "sharp";

export const CONF_FLOOR = 0.05; // the page filters by its own slider, so return everything above this
const IOU = 0.7; // ultralytics predict default
const TILE_IOU = 0.5; // merging tiles, as in src/detection/eval_sizes.py
const MAX_DET = 300;
const STRIDE = 32;
const PAD = 114; // ultralytics letterbox grey

export const MODEL_DIR = path.join(process.cwd(), "models");
export const DEFAULT_MODEL = "best";

export type Detection = { bbox_xyxy: [number, number, number, number]; conf: number; cls: number; name: string; model: string };
export type ModelMeta = {
  name: string;
  label: string;
  source: string | null;
  task: string;
  weights: string;
  base: string | null;
  epochs: number | null;
  imgsz: number;
  trained: string | null;
  names: Record<string, string>;
  person: number[]; // class ids kept as persons; the rest (cars, bikes...) are dropped
  metrics: Record<string, number>;
};
type Model = { session: ort.InferenceSession; meta: ModelMeta; nc: number; person: Set<number>; queue: Promise<unknown> };
type Raw = { data: Buffer; width: number; height: number };

/** Every exported model in MODEL_DIR, default first. Older JSONs (one model, no name) are filled in. */
export function listModels(): ModelMeta[] {
  if (!fs.existsSync(MODEL_DIR)) return [];
  return fs
    .readdirSync(MODEL_DIR)
    .filter((f) => f.endsWith(".json") && fs.existsSync(path.join(MODEL_DIR, f.replace(/\.json$/, ".onnx"))))
    .map((f) => {
      const name = f.replace(/\.json$/, "");
      const m = JSON.parse(fs.readFileSync(path.join(MODEL_DIR, f), "utf8")) as Partial<ModelMeta> & { names: Record<string, string> };
      return {
        label: name === DEFAULT_MODEL ? "Fine-tuned" : name,
        source: null,
        task: "detect",
        weights: `${name}.pt`,
        base: null,
        epochs: null,
        imgsz: 640,
        trained: null,
        person: Object.keys(m.names).map(Number),
        metrics: {},
        ...m,
        name, // the file name is the id
      } as ModelMeta;
    })
    .sort((a, b) => Number(b.name === DEFAULT_MODEL) - Number(a.name === DEFAULT_MODEL) || a.name.localeCompare(b.name));
}

// one session per model per process; globalThis survives dev hot reloads
const g = globalThis as typeof globalThis & { __detectors?: Map<string, Promise<Model>> };

export function getModel(name = DEFAULT_MODEL): Promise<Model> {
  const cache = (g.__detectors ??= new Map());
  let p = cache.get(name);
  if (!p) {
    p = load(name).catch((e) => {
      cache.delete(name); // let the next request retry instead of caching the failure
      throw e;
    });
    cache.set(name, p);
  }
  return p;
}

async function load(name: string): Promise<Model> {
  const meta = listModels().find((m) => m.name === name);
  if (!meta) throw new Error(`no model "${name}" in ${MODEL_DIR}: run \`npm run export-model -- --all\``);
  const onnx = path.join(MODEL_DIR, `${name}.onnx`);
  // CPU beats the CoreML provider for this model on Apple silicon (17 vs 36 ms at 640)
  const session = await ort.InferenceSession.create(onnx, { executionProviders: ["cpu"], graphOptimizationLevel: "all" });
  const model: Model = { session, meta, nc: Object.keys(meta.names).length, person: new Set(meta.person), queue: Promise.resolve() };
  await infer(model, { data: Buffer.alloc(640 * 640 * 3, PAD), width: 640, height: 640 }, 640); // warm-up
  return model;
}

/** Decode any image (EXIF-rotated) to packed RGB. */
export async function decode(buf: Buffer): Promise<Raw> {
  const { data, info } = await sharp(buf).rotate().removeAlpha().toColourspace("srgb").raw().toBuffer({ resolveWithObject: true });
  return { data, width: info.width, height: info.height };
}

/** Aspect-preserving resize into imgsz, padded to a multiple of 32 (ultralytics LetterBox, auto=True). */
async function letterbox(img: Raw, imgsz: number) {
  const r = Math.min(imgsz / img.height, imgsz / img.width);
  const nw = Math.round(img.width * r), nh = Math.round(img.height * r);
  const pw = Math.ceil(nw / STRIDE) * STRIDE, ph = Math.ceil(nh / STRIDE) * STRIDE;
  const left = Math.floor((pw - nw) / 2), top = Math.floor((ph - nh) / 2);
  const px = await sharp(img.data, { raw: { width: img.width, height: img.height, channels: 3 } })
    .resize(nw, nh, { kernel: "linear", fit: "fill" })
    .extend({ top, bottom: ph - nh - top, left, right: pw - nw - left, background: { r: PAD, g: PAD, b: PAD } })
    .raw()
    .toBuffer();
  // HWC uint8 -> CHW float 0..1
  const n = pw * ph, x = new Float32Array(3 * n);
  for (let i = 0, j = 0; i < n; i++, j += 3) {
    x[i] = px[j] / 255;
    x[n + i] = px[j + 1] / 255;
    x[2 * n + i] = px[j + 2] / 255;
  }
  return { tensor: new ort.Tensor("float32", x, [1, 3, ph, pw]), r, left, top };
}

type Box = { x1: number; y1: number; x2: number; y2: number; conf: number; cls: number };

function iou(a: Box, b: Box) {
  const w = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1), h = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
  if (w <= 0 || h <= 0) return 0;
  const inter = w * h;
  return inter / ((a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter);
}

/** Greedy class-aware NMS, highest confidence first. */
function nms(boxes: Box[], thr: number, max = MAX_DET) {
  boxes.sort((a, b) => b.conf - a.conf);
  const keep: Box[] = [];
  for (const b of boxes) {
    if (keep.every((k) => k.cls !== b.cls || iou(k, b) <= thr)) keep.push(b);
    if (keep.length >= max) break;
  }
  return keep;
}

/** One forward pass; boxes in img pixels. Runs are queued so frames never compete for the CPU. */
async function infer(model: Model, img: Raw, imgsz: number): Promise<Box[]> {
  const { tensor, r, left, top } = await letterbox(img, imgsz);
  const run = model.queue.then(() => model.session.run({ [model.session.inputNames[0]]: tensor }));
  model.queue = run.catch(() => {});
  const out = (await run)[model.session.outputNames[0]];
  // [1, 4 + nc (+ 3 * keypoints for pose), A]: rows cx, cy, w, h, one score per class, then keypoints (ignored)
  const [, rows, A] = out.dims as number[];
  if (rows < 4 + model.nc) throw new Error(`${model.meta.name}.onnx: output ${out.dims.join("x")} is not [1, 4+nc, anchors]; re-export it`);
  const d = out.data as Float32Array, end = 4 + model.nc;
  const boxes: Box[] = [];
  for (let a = 0; a < A; a++) {
    let conf = 0, cls = 0;
    for (let c = 4; c < end; c++) if (d[c * A + a] > conf) (conf = d[c * A + a]), (cls = c - 4);
    // best class over all of them first, as ultralytics does with classes=[...], so a car never turns into a person
    if (conf < CONF_FLOOR || !model.person.has(cls)) continue;
    const cx = d[a], cy = d[A + a], w = d[2 * A + a], h = d[3 * A + a];
    const clip = (v: number, hi: number) => Math.min(Math.max(v, 0), hi);
    boxes.push({
      x1: clip((cx - w / 2 - left) / r, img.width),
      y1: clip((cy - h / 2 - top) / r, img.height),
      x2: clip((cx + w / 2 - left) / r, img.width),
      y2: clip((cy + h / 2 - top) / r, img.height),
      conf,
      cls,
    });
  }
  return nms(boxes, IOU);
}

/** Tiled pass for small persons: tile-px crops with 20% overlap at imgsz = tile, merged by NMS. */
async function inferTiled(model: Model, img: Raw, tile: number): Promise<Box[]> {
  const step = Math.floor(tile * 0.8);
  const starts = (L: number) => {
    const s: number[] = [];
    for (let v = 0; v <= Math.max(L - tile, 0); v += step) s.push(v);
    if (L > tile && (L - tile) % step) s.push(L - tile);
    return s;
  };
  const all: Box[] = [];
  for (const y of starts(img.height)) {
    for (const x of starts(img.width)) {
      const w = Math.min(tile, img.width - x), h = Math.min(tile, img.height - y);
      const data = await sharp(img.data, { raw: { width: img.width, height: img.height, channels: 3 } })
        .extract({ left: x, top: y, width: w, height: h })
        .raw()
        .toBuffer();
      for (const b of await infer(model, { data, width: w, height: h }, tile)) {
        all.push({ ...b, x1: b.x1 + x, y1: b.y1 + y, x2: b.x2 + x, y2: b.y2 + y });
      }
    }
  }
  return nms(all, TILE_IOU);
}

/** Run each named model on the frame, one after the other; every box is tagged with its model. */
export async function detect(img: Raw, imgsz: number, tile: number, names: string[] = [DEFAULT_MODEL]) {
  const r1 = (v: number) => Math.round(v * 10) / 10;
  const detections: Detection[] = [], times: Record<string, number> = {};
  let ms = 0;
  for (const name of names) {
    const model = await getModel(name);
    const t = performance.now();
    const boxes = tile ? await inferTiled(model, img, tile) : await infer(model, img, imgsz);
    times[name] = r1(performance.now() - t);
    ms += times[name];
    for (const b of boxes) {
      detections.push({
        bbox_xyxy: [r1(b.x1), r1(b.y1), r1(b.x2), r1(b.y2)],
        conf: Math.round(b.conf * 1000) / 1000,
        cls: b.cls,
        name: model.meta.names[b.cls] ?? String(b.cls),
        model: name,
      });
    }
  }
  return { width: img.width, height: img.height, ms: r1(ms), times, detections };
}
