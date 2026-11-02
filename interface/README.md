# Operator UI

> **Status:** Draft · **Updated:** 2026-11-01

Next.js page in front of the victim detector (`best.pt`, YOLO26n, single class `person`). One Node process does everything: the page, the API and inference (ONNX Runtime on the CPU, ~15 ms per 640 px frame on Apple silicon). No Python at runtime and no CDNs, so it works offline on the station.

## Run

```bash
cd interface
npm install
npm run export-model     # once: best.pt -> models/best.onnx + models/best.json (uses ../.venv, needs ultralytics onnx onnxslim)
npm run export-model -- --all   # also the pretrained VisDrone and pose models (downloads into weights/)
npm run dev              # or: npm run build && npm start
```

## Models

Every `models/<name>.onnx` + `<name>.json` shows up as a toggle under **Models**; any one, or several at once. Nothing here is trained or fine-tuned beyond `best.pt`:

| Toggle | Weights | Counted as person |
| --- | --- | --- |
| Fine-tuned | `best.pt`, YOLO26n trained in this repo | `person` |
| VisDrone | [`dronefreak/visdrone-yolo26n`](https://huggingface.co/dronefreak/visdrone-yolo26n), YOLO26n fine-tuned on VisDrone-DET at 1280 px (Ultralytics ships no VisDrone weights of its own) | `pedestrian`, `people`; cars, bikes etc. are dropped |
| Pose | Ultralytics `yolo26n-pose.pt` (COCO keypoints) | its `person` boxes; keypoints are ignored |

With two or more on, boxes are coloured per model and the right panel counts each one. **Merge models** keeps one box per person across models (greedy NMS at IoU 0.5, in the page); a green box was found by more than one model. The scores table shows each model's own val numbers (ours, the VisDrone model card's test split over all 10 classes, COCO pose mAP), which are not comparable with each other.

Open http://localhost:8765, or http://localhost:8765/#camera to go straight to the live webcam feed. Another port: `npm run dev -- --port 8800`. Example frames for "Try samples" come from `../data/samples` (override with `SAMPLES_DIR`).

## Ports

`server.mjs` is the only place a port is chosen; the page calls `/api/...` relative to wherever it was loaded from.

- One explicit port (default 8765). If it is busy the server exits with a message; it never moves to another port the way `next dev` does.
- It listens on both `127.0.0.1` and `::1`, so `localhost`, `127.0.0.1` and `[::1]` all reach the same server. Before binding it probes both; if anything already answers it refuses to start. This catches macOS AirPlay on 5000 and 7000, which otherwise answers the page's requests with `403 Forbidden`.
- `next.config.ts` allows `127.0.0.1` and `[::1]` in `allowedDevOrigins`; without that, dev mode answers `403` to hot-reload and `/_next` requests from those addresses.
- The camera needs a secure page: `localhost` / `127.0.0.1` count, a LAN address over plain http does not.

## What it does

| Source | How |
| --- | --- |
| Images | Drop, pick or paste one or many; each is detected once, the filmstrip shows counts |
| Video | A local file plays in the page; frames go to `POST /api/detect` as fast as the model returns |
| Camera | Webcam or a capture card carrying the drone feed; pick the device when there is more than one |

- Every box is labelled with its class and confidence (`person 87%`), coloured per class; the stage shows live FPS and inference ms.
- The server returns every box above conf 0.05; the confidence slider filters in the page, so it reacts instantly.
- Video and camera: every person at or above the slider is saved to the Detections list with a frozen crop and when it was seen, so it stays after leaving the frame. The same box over consecutive frames (IoU ≥ 0.3 within 1.5 s) updates one entry rather than adding new ones; Clear empties it, a new source starts over.
- Input size 640 / 960 / 1280 and tiled inference (640 px tiles, 20% overlap, same as `src/detection/eval_sizes.py`) re-run the detector.
- Boxes smaller than 14 screen px get a dashed ring so tiny persons stay visible; scroll zooms, drag pans, clicking a detection zooms to it.
- **Export detections.json** writes the same records as `src/detection/detect.py`, plus `cls` and `name`; in video and camera mode it writes the saved list, with `at` and `seen`.

## Layout

| Path | What |
| --- | --- |
| `server.mjs` | Starts Next on one port, both loopbacks, with the busy-port checks above |
| `lib/detector.ts` | Decode (sharp), letterbox, ONNX Runtime, NMS, tiling, one session per model in `models/`; matches ultralytics boxes on `data/samples` (IoU > 0.9) |
| `app/api/{info,detect,samples}` | Model info, detection, example frames |
| `components/Station.tsx` | The whole page |
| `scripts/export_model.py` | ONNX export with dynamic input size; `--all` fetches and exports the pretrained models |
