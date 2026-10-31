"""Export best.pt to ONNX for the station UI, plus a JSON with what the page shows about it.

Usage (from interface/):
    ../.venv/bin/python scripts/export_model.py [--weights best.pt]
Writes models/best.onnx (dynamic input size, raw [1, 4+nc, anchors] output, NMS runs in
lib/detector.ts) and models/best.json. Needs `ultralytics onnx onnxslim`.
"""

import argparse
import json
import shutil
from pathlib import Path

import torch
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", type=Path, default=HERE / "best.pt")
    args = ap.parse_args()

    out = HERE / "models"
    out.mkdir(exist_ok=True)
    model = YOLO(str(args.weights))
    # dynamic=True so the page can pick 640 / 960 / 1280 and tiles
    onnx = Path(model.export(format="onnx", dynamic=True, simplify=True))
    shutil.move(onnx, out / "best.onnx")

    ck = torch.load(args.weights, map_location="cpu", weights_only=False)
    a, m = ck.get("train_args") or {}, ck.get("train_metrics") or {}
    meta = {
        "weights": args.weights.name,
        "base": a.get("model"),
        "epochs": a.get("epochs"),
        "imgsz": a.get("imgsz", 640),
        "trained": ck.get("date"),
        "names": {int(k): v for k, v in model.names.items()},
        "metrics": {k.split("/")[1].removesuffix("(B)"): round(v, 3) for k, v in m.items() if k.startswith("metrics/")},
    }
    (out / "best.json").write_text(json.dumps(meta, indent=1))
    print(f"-> {out / 'best.onnx'}, {out / 'best.json'}")


if __name__ == "__main__":
    main()
