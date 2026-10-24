"""Unpack .npz shards (from prepare_c2a.py / prepare_nii_cu_mapd.py) into an
ultralytics YOLO folder: images/<split>/*.png, labels/<split>/*.txt, plus a
data yaml. ultralytics reads image files, not arrays, so this runs once before
training. Shards are read one at a time, so RAM stays at one shard.

Usage:
    python npz_to_yolo.py c2a/rgb/640 --out data/yolo/c2a
    yolo detect train data=data/yolo/c2a/c2a.yaml model=yolo11n.pt imgsz=640
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def convert(shard_root, out, name):
    shard_root, out = Path(shard_root), Path(out)
    splits = sorted(p.name for p in shard_root.iterdir() if p.is_dir())
    for split in splits:
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        n = 0
        for shard in sorted((shard_root / split).glob("shard_*.npz")):
            d = np.load(shard)
            images, boxes, counts, names = d["images"], d["boxes"], d["box_counts"], d["names"]
            offsets = np.concatenate([[0], np.cumsum(counts)])
            for i, stem in enumerate(names):
                img = images[i][:, :, 0] if images[i].shape[2] == 1 else images[i]
                Image.fromarray(img).save(out / "images" / split / f"{stem}.png")
                rows = [f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in boxes[offsets[i]:offsets[i + 1]]]
                (out / "labels" / split / f"{stem}.txt").write_text("\n".join(rows) + "\n" if rows else "")
            n += len(names)
        print(f"{split}: {n} images")

    yaml = out / f"{name}.yaml"
    yaml.write_text(f"path: {out.resolve()}\n" + "".join(f"{s}: images/{s}\n" for s in splits) + "names:\n  0: person\n")
    print(f"wrote {yaml}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shard_root", help="folder holding <split>/shard_*.npz, e.g. c2a/rgb/640")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default=None, help="yaml name (default: out folder name)")
    args = ap.parse_args()
    convert(args.shard_root, args.out, args.name or Path(args.out).name)


if __name__ == "__main__":
    main()
