# Operator UI

> **Status:** Draft · **Updated:** 2026-11-01

Next.js page in front of the victim detector (`best.pt`, YOLO26n, single class `person`). One Node process does everything: the page, the API and inference (ONNX Runtime on the CPU, ~15 ms per 640 px frame on Apple silicon). No Python at runtime and no CDNs, so it works offline on the station.

## Run

```bash
cd interface
npm install
conda activate capstone
npm run export-model     # once: best.pt -> models/best.onnx + models/best.json (active python, needs ultralytics onnx onnxslim)
npm run thermal-model    # once: models/thermal.onnx + models/thermal.json for the MLX90640 page (needs onnx)
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
| Pi cam | The Logitech webcam on the Raspberry Pi, over Wi-Fi (see below) |

- Every box is labelled with its class and confidence (`person 87%`), coloured per class; the stage shows live FPS and inference ms.
- The server returns every box above conf 0.05; the confidence slider filters in the page, so it reacts instantly.
- Video and camera: every person at or above the slider is saved to the Detections list with a frozen crop and when it was seen, so it stays after leaving the frame. The same box over consecutive frames (IoU ≥ 0.3 within 1.5 s) updates one entry rather than adding new ones; Clear empties it, a new source starts over.
- Input size 640 / 960 / 1280 and tiled inference (640 px tiles, 20% overlap, same as `src/detection/eval_sizes.py`) re-run the detector.
- Boxes smaller than 14 screen px get a dashed ring so tiny persons stay visible; scroll zooms, drag pans, clicking a detection zooms to it.
- **Export detections.json** writes the same records as `src/detection/detect.py`, plus `cls` and `name`; in video and camera mode it writes the saved list, with `at` and `seen`.

## Raspberry Pi webcam

The Pi only captures. It runs `ustreamer`, which passes the Logitech webcam's own MJPEG through without re-encoding, at `http://<pi>:8080/stream`. Inference runs here. Pi setup (Wi-Fi client or hotspot, systemd service) is in [`../raspberry/README.md`](../raspberry/README.md).

- Open http://localhost:8765/#pi, enter the Pi address (`raspberrypi.local:8080`, `10.42.0.1:8080` on the Pi's hotspot, or a full `/stream` URL) and press **Connect**. The address is remembered in the browser. The default comes from `PICAM_URL` (default `http://raspberrypi.local:8080/stream`).
- `lib/picam.ts` keeps **one** connection to the Pi per server process, so Wi-Fi carries the feed once. It reconnects after 1 s on errors or after 5 s without data, and hangs up 15 s after the last page stops asking.
- `GET /api/picam/stream?src=` re-serves the feed from this origin for the stage `<img>`, dropping frames for slow readers. `GET /api/picam/frame?src=` returns the newest JPEG, which the page posts to `/api/detect` as is. It answers 503 with the reason (connecting, host not found, not an MJPEG stream) when there is no frame from the last 3 s, so the detector never runs on a frozen frame.
- No Pi: `python ../raspberry/fake_cam_stream.py [--video clip.mp4 | --webcam]` serves the same `/stream` on port 8080 (needs ffmpeg).

## MLX90640 thermal

The Pi runs `raspberry/mlx_stream.cpp` (in git history, `e560cd2`) and sends 3096-byte UDP packets (768 float32 °C, 24×32) to this machine on port 5005 (`THERMAL_UDP_PORT` to change). `lib/thermal.ts` listens, renders each frame to a 640×480 JPEG and runs `models/thermal.onnx` on the raw temperatures.

- http://localhost:8765/thermal shows the live frame with person boxes, min/max/sensor °C and frame age.
- `GET /api/thermal/frame` is the JPEG; header `x-thermal-detections` carries that frame's boxes. `GET /api/thermal/detections` is the same as JSON. Both answer 503 until frames arrive.
- `thermal.onnx` is not trained: no labelled MLX90640 data exists yet. It is a fixed body-temperature band (28 to 40 °C, `scripts/make_thermal_model.py --lo --hi`) with a 3×3 smoothing, giving a per-pixel person probability; blobs of 3+ pixels above 0.5 become boxes (`threshold`, `min_pixels` in `thermal.json`). A trained model drops in if it keeps the contract: input `[1,1,24,32]` °C, output `[1,1,24,32]` probability. Two people touching merge into one box, and a warm room (≥ 28 °C) lights up everywhere.

## Layout

| Path | What |
| --- | --- |
| `server.mjs` | Starts Next on one port, both loopbacks, with the busy-port checks above |
| `lib/detector.ts` | Decode (sharp), letterbox, ONNX Runtime, NMS, tiling, one session per model in `models/`; matches ultralytics boxes on `data/samples` (IoU > 0.9) |
| `app/api/{info,detect,samples}` | Model info, detection, example frames |
| `components/Station.tsx` | The whole page |
| `scripts/export_model.py` | ONNX export with dynamic input size |
| `lib/thermal.ts`, `app/api/thermal/*`, `app/thermal/` | MLX90640 UDP ingest, person boxes, live page |
| `lib/picam.ts`, `app/api/picam/{frame,stream}` | Pi webcam MJPEG ingest, newest frame, re-served stream |
| `scripts/make_thermal_model.py` | Writes `models/thermal.onnx` + `thermal.json` |
