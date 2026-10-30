"""Train one YOLO26 model per modality on the datasets SPEC.md lists, then score best.pt on each dataset.

rgb:     SARD + NII-CU-MAPD RGB
thermal: RGBTDronePerson thermal + NII-CU-MAPD thermal + HIT-UAV

Needs the datasets in data/yolo/ (see research/datasets/README.md#conversion-and-training). Writes
data/yolo/{rgb,thermal}.yaml, runs/<modality>/<name>/ (ultralytics output) and runs/<modality>/<name>/scores.md:
AP50, AP50-95, precision and recall on every split of every dataset, plus all val sets together.
Re-running resumes an interrupted run from last.pt, and only rescores a finished one.

Usage:
    python src/detection/train.py rgb thermal [--model yolo26n.pt] [--epochs 100] [--batch 32]
"""

import argparse
from pathlib import Path

import pandas as pd
from ultralytics import YOLO

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "yolo"
DATASETS = {
    "rgb": ["sard", "nii-cu-mapd-rgb"],
    "thermal": ["rgbtdroneperson-thermal", "nii-cu-mapd-thermal", "hit-uav"],
}


def splits(name):
    return [s for s in ["train", "val", "test"] if (DATA / name / "images" / s).is_dir()]


def combined_yaml(mod):
    """One data yaml listing every dataset of the modality; val is all their val splits."""
    names = DATASETS[mod]
    for n in names:
        assert (DATA / f"{n}.yaml").exists(), f"missing {DATA / n}.yaml: convert the dataset first"
    lines = lambda s: [f"  - {DATA / n / 'images' / s}" for n in names]
    y = DATA / f"{mod}.yaml"
    y.write_text("\n".join(["train:", *lines("train"), "val:", *lines("val"), "names:", "  0: person"]) + "\n")
    return y


def score(weights, mod, run):
    rows = []
    m = YOLO(weights)
    targets = [("all", "val", DATA / f"{mod}.yaml")]
    targets += [(n, s, DATA / f"{n}.yaml") for n in DATASETS[mod] for s in splits(n) if s != "train"]
    for name, split, y in targets:
        met = m.val(data=str(y), split=split, imgsz=640, batch=16, plots=False, verbose=False,
                    project=str(run.parent), name=f"{run.name}-{name}-{split}", exist_ok=True)
        rows.append({"dataset": name, "split": split, "AP50": met.box.map50, "AP50-95": met.box.map,
                     "P": met.box.mp, "R": met.box.mr})
    df = pd.DataFrame(rows).round(3)
    (run / "scores.md").write_text(f"{mod}, {weights}\n\n" + df.to_markdown(index=False) + "\n")
    print(df.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modality", nargs="+", choices=list(DATASETS))
    ap.add_argument("--model", default="yolo26n.pt")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    for mod in args.modality:
        run = REPO / "runs" / mod / f"{Path(args.model).stem}_e{args.epochs}"
        data = combined_yaml(mod)
        csv, last = run / "results.csv", run / "weights" / "last.pt"
        if not (csv.exists() and len(pd.read_csv(csv)) >= args.epochs):
            if last.exists():  # interrupted (sleep, Ctrl+C): continue from the last epoch
                YOLO(last).train(resume=True)
            else:  # patience = epochs: always run the full schedule
                YOLO(args.model).train(data=str(data), imgsz=640, epochs=args.epochs, patience=args.epochs,
                                       batch=args.batch, cache=False, workers=8, seed=0,
                                       project=str(run.parent), name=run.name, exist_ok=True)
        score(run / "weights" / "best.pt", mod, run)


if __name__ == "__main__":
    main()
