"""Station-side victim detection: images in, JSON list of detections out.

Usage:
    python src/detection/detect.py WEIGHTS SOURCE [--imgsz 640] [--conf 0.25] [--out detections.json]
SOURCE is an image file or a folder of images.
"""

import argparse
import json
import time
from pathlib import Path

from ultralytics import YOLO


def to_records(result, path):
    return [
        {
            "image": str(path),
            "bbox_xyxy": [round(v, 1) for v in box.xyxy[0].tolist()],
            "conf": round(float(box.conf), 3),
        }
        for box in result.boxes
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights")
    ap.add_argument("source", type=Path)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", type=Path, default=Path("detections.json"))
    args = ap.parse_args()

    model = YOLO(args.weights)
    t0 = time.perf_counter()
    records, n = [], 0
    # stream=True keeps memory flat on large folders
    for r in model.predict(str(args.source), imgsz=args.imgsz, conf=args.conf, stream=True, verbose=False):
        records += to_records(r, r.path)
        n += 1
    dt = time.perf_counter() - t0
    args.out.write_text(json.dumps(records, indent=1))
    print(f"{n} images, {len(records)} victims, {dt / max(n, 1) * 1000:.0f} ms/image -> {args.out}")


if __name__ == "__main__":
    main()
