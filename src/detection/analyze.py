"""Dataset analysis for victim detection.

Reads a YOLO-format dataset (images/ + labels/ with "cls xc yc w h" normalized),
reports person box sizes and how many persons shrink below MIN_PX at each
model input size (YOLO imgsz = long side). Bigger imgsz: more persons kept, slower inference.

Usage:
    python src/detection/analyze.py IMAGES_DIR LABELS_DIR --person-class 0 --out OUT_DIR
"""

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

IMGSZ = [320, 640, 960, 1280, None]  # model input long side; None = original
MIN_PX = 8  # below this, small-object detectors mostly miss persons


def load_persons(label_file, person_class):
    if not label_file.exists():
        return []
    rows = [line.split() for line in label_file.read_text().splitlines() if line.strip()]
    return [tuple(map(float, r[1:5])) for r in rows if int(float(r[0])) == person_class]


def scaled_sizes(sizes, long_sides, imgsz):
    return sizes * np.minimum(1.0, imgsz / long_sides) if imgsz else sizes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", type=Path)
    ap.add_argument("labels", type=Path)
    ap.add_argument("--person-class", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    imgs = sorted(p for p in args.images.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    assert imgs, f"no images in {args.images}"

    # person box size in px as sqrt(w*h), plus each box's image long side
    sizes, long_sides, n_with_person, example = [], [], 0, None
    for p in imgs:
        boxes = load_persons(args.labels / p.relative_to(args.images).with_suffix(".txt"), args.person_class)
        if not boxes:
            continue
        n_with_person += 1
        example = example or (p, boxes)
        w, h = Image.open(p).size
        for _, _, bw, bh in boxes:
            sizes.append(math.sqrt(bw * w * bh * h))
            long_sides.append(max(w, h))
    sizes, long_sides = np.array(sizes), np.array(long_sides)
    assert len(sizes), "no person boxes found; check --person-class"

    lines = [
        f"images: {len(imgs)}, with persons: {n_with_person}, persons: {len(sizes)}",
        f"image long side: {sorted(set(long_sides.astype(int).tolist()))[:10]}",
        "person size px (sqrt area) p5/p25/p50/p75/p95: "
        + " / ".join(f"{v:.1f}" for v in np.percentile(sizes, [5, 25, 50, 75, 95])),
        "",
        f"| imgsz | median person px | persons < {MIN_PX}px |",
        "|---|---|---|",
    ]
    for imgsz in IMGSZ:
        s = scaled_sizes(sizes, long_sides, imgsz)
        lines.append(f"| {imgsz or 'full'} | {np.median(s):.1f} | {(s < MIN_PX).mean() * 100:.0f}% |")
    report = "\n".join(lines)
    (args.out / "stats.md").write_text(report + "\n")
    print(report)

    plt.figure(figsize=(6, 3.5))
    plt.hist(sizes, bins=np.arange(0, np.percentile(sizes, 99) + 2, 2))
    plt.axvline(MIN_PX, color="k", ls="--", lw=1)
    plt.xlabel("person size, px (sqrt of box area, original resolution)")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(args.out / "person_sizes.png", dpi=120)

    # visual check: one image downscaled to each imgsz, upscaled back for viewing
    p, boxes = example
    orig = Image.open(p).convert("RGB")
    W, H = orig.size
    fig, axes = plt.subplots(1, len(IMGSZ), figsize=(4 * len(IMGSZ), 3.5))
    for ax, imgsz in zip(axes, IMGSZ):
        small = orig.copy()
        if imgsz:
            small.thumbnail((imgsz, imgsz))
        view = small.resize(orig.size, Image.NEAREST)
        d = ImageDraw.Draw(view)
        for xc, yc, bw, bh in boxes:
            d.rectangle([(xc - bw / 2) * W, (yc - bh / 2) * H, (xc + bw / 2) * W, (yc + bh / 2) * H], outline="red")
        ax.imshow(view)
        ax.set_title(f"imgsz {imgsz or 'full'}")
        ax.axis("off")
    plt.tight_layout()
    plt.savefig(args.out / "imgsz_examples.png", dpi=100)


if __name__ == "__main__":
    assert scaled_sizes(np.array([20.0]), np.array([1280]), 640)[0] == 10.0
    assert scaled_sizes(np.array([20.0]), np.array([320]), 640)[0] == 20.0  # never upscale
    main()
