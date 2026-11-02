"""Export a YOLO .pt to ONNX for the station UI, plus a JSON with what the page shows about it.

Usage (from interface/):
    ../.venv/bin/python scripts/export_model.py [--weights best.pt] [--name best] [--label ...] [--source ...]
    ../.venv/bin/python scripts/export_model.py --all     # best.pt + the pretrained VisDrone and pose models
Writes models/<name>.onnx (dynamic input size, raw [1, 4+nc(+kpts), anchors] output, NMS runs in
lib/detector.ts) and models/<name>.json. Needs `ultralytics onnx onnxslim`.
"""

import argparse
import json
import shutil
import urllib.request
from pathlib import Path

import torch
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent.parent
WEIGHTS = HERE / "weights"

# pretrained, nothing fine-tuned here; "person" lists the classes the page counts as a person
PRETRAINED = [
    {
        "name": "visdrone",
        "weights": WEIGHTS / "visdrone-yolo26n.pt",
        "url": "https://huggingface.co/dronefreak/visdrone-yolo26n/resolve/main/best.pt",
        "label": "VisDrone",
        "source": "dronefreak/visdrone-yolo26n (Hugging Face), YOLO26n fine-tuned on VisDrone-DET",
        "person": ["pedestrian", "people"],
        # the checkpoint carries no metrics; these are the model card's VisDrone-DET test scores, all 10 classes
        "metrics": {"precision": 0.511, "recall": 0.421, "mAP50": 0.399, "mAP50-95": 0.230},
    },
    {
        "name": "pose",
        "weights": WEIGHTS / "yolo26n-pose.pt",
        "url": None,  # ultralytics downloads its own release asset
        "label": "Pose",
        "source": "Ultralytics yolo26n-pose.pt (COCO keypoints), boxes only",
        "person": ["person"],
        # docs.ultralytics.com/tasks/pose, COCO val; pose mAP, box mAP isn't listed
        "metrics": {"mAP50": 0.833, "mAP50-95": 0.572},
    },
]


def fetch(spec):
    w = spec["weights"]
    if w.exists():
        return
    WEIGHTS.mkdir(exist_ok=True)
    if spec["url"]:
        print(f"downloading {spec['url']}")
        urllib.request.urlretrieve(spec["url"], w)
    else:
        YOLO(w.name)  # ultralytics fetches it into the cwd
        shutil.move(w.name, w)


def export(weights: Path, name: str, label: str, source: str | None, person: list[str] | None, metrics: dict | None):
    out = HERE / "models"
    out.mkdir(exist_ok=True)
    model = YOLO(str(weights))
    # dynamic=True so the page can pick 640 / 960 / 1280 and tiles
    onnx = Path(model.export(format="onnx", dynamic=True, simplify=True))
    shutil.move(onnx, out / f"{name}.onnx")

    ck = torch.load(weights, map_location="cpu", weights_only=False)
    a, m = ck.get("train_args") or {}, ck.get("train_metrics") or {}
    names = {int(k): v for k, v in model.names.items()}
    meta = {
        "name": name,
        "label": label,
        "source": source,
        "task": model.task,
        "weights": weights.name,
        "base": a.get("model"),
        "epochs": a.get("epochs"),
        "imgsz": a.get("imgsz", 640),
        "trained": ck.get("date"),
        "names": names,
        # class ids that count as a person; everything else is dropped by lib/detector.ts
        "person": [k for k, v in names.items() if v in person] if person else list(names),
        "metrics": metrics or {k.split("/")[1].removesuffix("(B)"): round(v, 3) for k, v in m.items() if k.startswith("metrics/")},
    }
    (out / f"{name}.json").write_text(json.dumps(meta, indent=1))
    print(f"-> {out / f'{name}.onnx'}, {out / f'{name}.json'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", type=Path, default=HERE / "best.pt")
    ap.add_argument("--name", default="best", help="models/<name>.onnx; the page's id for the model")
    ap.add_argument("--label", default="Fine-tuned")
    ap.add_argument("--source", default=None)
    ap.add_argument("--all", action="store_true", help="best.pt plus the pretrained models in PRETRAINED")
    args = ap.parse_args()

    if not args.all:
        export(args.weights, args.name, args.label, args.source, None, None)
        return
    export(HERE / "best.pt", "best", "Fine-tuned", "best.pt, YOLO26n fine-tuned in this repo", None, None)
    for spec in PRETRAINED:
        fetch(spec)
        export(spec["weights"], spec["name"], spec["label"], spec["source"], spec["person"], spec["metrics"])


if __name__ == "__main__":
    main()
