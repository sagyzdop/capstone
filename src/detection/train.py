"""Train one YOLO26 model per modality on the datasets SPEC.md lists, then score best.pt on each dataset.

rgb:     SARD + NII-CU-MAPD RGB + HERIDAL (location split; runs before 2026-10-30 had no HERIDAL)
thermal: RGBTDronePerson thermal + NII-CU-MAPD thermal + HIT-UAV

With one modality, --data, --repeat and --val change the mix: train on a subset, list a dataset's train split
K times so it is sampled K times as often, and pick best.pt on some val splits only. --scale is ultralytics'
random rescale range (0.5 = 50% to 150%); a smaller one keeps tiny people from shrinking below the detectable size.

Needs the datasets in data/yolo/ (see research/datasets/README.md#conversion-and-training). Writes
runs/<modality>/<name>/: data.yaml (the run's train and val lists), ultralytics output, scores.md (AP50, AP50-95,
precision and recall on every split of every dataset of the modality, plus the run's val set as `all`) and
results.md (report.py). Re-running resumes an interrupted run from last.pt, and only rescores a finished one.

Usage:
    python src/detection/train.py rgb thermal [--model yolo26n.pt] [--epochs 100] [--batch 32] [--tag heridal]
    python src/detection/train.py rgb --repeat heridal=3 --val heridal --scale 0.25 --tag heridalx3_valh_s025
    python src/detection/train.py rgb --data heridal --tag heridal_only
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd
from ultralytics import YOLO

import report

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "yolo"
DATASETS = {
    "rgb": ["sard", "nii-cu-mapd-rgb", "heridal"],
    "thermal": ["rgbtdroneperson-thermal", "nii-cu-mapd-thermal", "hit-uav"],
}


def splits(name):
    return [s for s in ["train", "val", "test"] if (DATA / name / "images" / s).is_dir()]


def run_yaml(run, names, repeat, val):
    """The run's data yaml: each train split listed repeat[name] times (ultralytics keeps duplicates), val splits."""
    for n in set(names) | set(val):
        assert (DATA / f"{n}.yaml").exists(), f"missing {DATA / n}.yaml: convert the dataset first"
    train = [f"  - {DATA / n / 'images' / 'train'}" for n in names for _ in range(repeat.get(n, 1))]
    y = run / "data.yaml"
    run.mkdir(parents=True, exist_ok=True)
    y.write_text("\n".join(["train:", *train, "val:", *[f"  - {DATA / n / 'images' / 'val'}" for n in val],
                            "names:", "  0: person"]) + "\n")
    return y


def score(weights, mod, run):
    rows = []
    m = YOLO(weights)
    targets = [("all", "val", run / "data.yaml")]
    targets += [(n, s, DATA / f"{n}.yaml") for n in DATASETS[mod] for s in splits(n) if s != "train"]
    for name, split, y in targets:
        out = run.parent / f"{run.name}-{name}-{split}"
        met = m.val(data=str(y), split=split, imgsz=640, batch=16, plots=False, verbose=False,
                    project=str(out.parent), name=out.name, exist_ok=True)
        shutil.rmtree(out, ignore_errors=True)  # ultralytics always makes the folder; with plots off it stays empty
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
    ap.add_argument("--tag", default="", help="appended to the run name, e.g. the data change")
    ap.add_argument("--data", nargs="+", help="train on these datasets only (default: all of the modality)")
    ap.add_argument("--repeat", nargs="+", default=[], metavar="NAME=K", help="list NAME's train split K times")
    ap.add_argument("--val", nargs="+", help="pick best.pt on these val splits only (default: the training datasets)")
    ap.add_argument("--scale", type=float, default=0.5, help="random rescale range, ultralytics' `scale`")
    args = ap.parse_args()
    assert len(args.modality) == 1 or not (args.data or args.repeat or args.val), "--data/--repeat/--val need one modality"
    repeat = {n: int(k) for n, k in (r.split("=") for r in args.repeat)}

    for mod in args.modality:
        run = REPO / "runs" / mod / "_".join(filter(None, [Path(args.model).stem, f"e{args.epochs}", args.tag]))
        names = args.data or DATASETS[mod]
        data = run_yaml(run, names, repeat, args.val or names)
        csv, last = run / "results.csv", run / "weights" / "last.pt"
        if not (csv.exists() and len(pd.read_csv(csv)) >= args.epochs):
            if last.exists():  # interrupted (sleep, Ctrl+C): continue from the last epoch
                YOLO(last).train(resume=True)
            else:  # patience = epochs: always run the full schedule
                YOLO(args.model).train(data=str(data), imgsz=640, epochs=args.epochs, patience=args.epochs,
                                       batch=args.batch, scale=args.scale, cache=False, workers=8, seed=0,
                                       project=str(run.parent), name=run.name, exist_ok=True)
        score(run / "weights" / "best.pt", mod, run)
        report.write(run)


if __name__ == "__main__":
    main()
