"""Prepare the C2A dataset (RGB, synthetic disaster) into resized, sharded,
compressed .npz arrays for person detection.

Source: `C2A_Dataset/new_dataset3/` from https://www.kaggle.com/datasets/rgbnihal/c2a-dataset
(MIT). Images are RGBA PNGs; labels are YOLO (normalized cx cy w h, class 0).
Labels are read from `All labels with Pose information/labels/`, which holds
the same boxes as the split label folders plus a 6th column: the pose
(0 bent, 1 kneeling, 2 lying, 3 sitting, 4 upright).

Cleaning:
- Class collapsed to a single `person` (0); pose kept as a side array.
- Boxes clipped to the image; boxes with zero width/height after clipping dropped.
- Tiny boxes are kept: dropping them would leave visible people unlabelled.
- Re-split by AIDER background photo. Each photo appears 5 times with different
  pasted people (`<scene>_imageNNNN_<0-4>`), and the authors' split puts 98% of
  val/test photos in train too. Here all 5 variants of a photo go to the same
  split, 60/20/20 per disaster type, fixed seed. The original split is kept
  in `split.csv`.

Resizing is letterbox (aspect-preserving, grey 114 pad), same as
prepare_nii_cu_mapd.py. 81% of C2A images have a long side <= 640 px, so 640
is mostly an upscale; larger sizes add no detail.

Output: <out>/rgb/<size>/<split>/shard_0000.npz, each holding
    images       uint8   (n, size, size, 3)
    boxes        float32 (total_boxes_in_shard, 4)  cx, cy, w, h, normalized 0..1
    box_counts   int32   (n,)   boxes per image, same order as `names`/`images`
    names        <U64    (n,)   source stem, e.g. "flood_image0363_4"
    poses        int8    (total_boxes_in_shard,)  pose id per box, -1 if unknown
    orig_wh      int32   (n, 2) source image width, height
The first four keys match prepare_nii_cu_mapd.py, so load_nii_cu_mapd.load_shards
reads these shards unchanged. Also writes <out>/split.csv and <out>/stats.json.

Usage:
    python prepare_c2a.py C2A_DIR_OR_ZIP --out OUT_DIR --sizes 640
    python prepare_c2a.py              # on Kaggle: finds the attached dataset, writes /kaggle/working/c2a
"""

import argparse
import csv
import io
import json
import random
import re
import zipfile
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

PAD_VALUE = 114  # standard YOLO letterbox grey pad
SPLITS = {"train": 0.6, "val": 0.2, "test": 0.2}
POSE_DIR = "new_dataset3/All labels with Pose information/labels/"


class Source:
    """Read files from either the extracted C2A_Dataset folder or the zip."""

    def __init__(self, path):
        path = Path(path)
        if path.suffix == ".zip":
            self.zip = zipfile.ZipFile(path)
            names = self.zip.namelist()
            prefix = next(n[: n.index("new_dataset3/")] for n in names if "new_dataset3/" in n)
            self.files = {n[len(prefix):]: n for n in names if n.startswith(prefix)}
        else:
            self.zip = None
            self.files = {str(p.relative_to(path)): str(p) for p in path.rglob("*") if p.is_file()}

    def read(self, rel):
        if self.zip:
            return self.zip.read(self.files[rel])
        return Path(self.files[rel]).read_bytes()


def find_kaggle_input():
    hits = sorted(Path("/kaggle/input").rglob("C2A_Dataset"))
    if not hits:
        raise SystemExit("no C2A_Dataset under /kaggle/input; pass the path explicitly")
    return hits[0]


def parse_labels(text):
    """YOLO rows `cls cx cy w h [pose]` -> (normalized cx/cy/w/h clipped to the image, pose ids)."""
    boxes, poses = [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cx, cy, w, h = (float(p) for p in parts[1:5])
        x1, y1 = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
        x2, y2 = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append((x1, y1, x2, y2))
        poses.append(int(float(parts[5])) if len(parts) >= 6 else -1)
    return boxes, poses


def letterbox_and_normalize(img, boxes, size):
    """Resize `img` (PIL) to fit inside size x size preserving aspect, pad with grey,
    and return (array, normalized cx/cy/w/h boxes) for the padded canvas.
    `boxes` are normalized x1 y1 x2 y2 on the source image."""
    w, h = img.size
    scale = size / max(w, h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((new_w, new_h), Image.BILINEAR)

    pad_l = (size - new_w) // 2
    pad_t = (size - new_h) // 2

    canvas = Image.new("RGB", (size, size), (PAD_VALUE,) * 3)
    canvas.paste(resized, (pad_l, pad_t))

    out_boxes = []
    for x1, y1, x2, y2 in boxes:
        nx1, ny1 = x1 * new_w + pad_l, y1 * new_h + pad_t
        nx2, ny2 = x2 * new_w + pad_l, y2 * new_h + pad_t
        out_boxes.append(((nx1 + nx2) / 2 / size, (ny1 + ny2) / 2 / size, (nx2 - nx1) / size, (ny2 - ny1) / size))
    return np.array(canvas), out_boxes


def assign_splits(stems, seed):
    """Group stems by AIDER photo, then split photos 60/20/20 within each disaster type."""
    by_photo = defaultdict(list)
    for s in stems:
        by_photo[s.rsplit("_", 1)[0]].append(s)
    by_disaster = defaultdict(list)
    for photo in sorted(by_photo):
        by_disaster[re.sub(r"_image\d+$", "", photo)].append(photo)

    rng = random.Random(seed)
    split_of = {}
    for disaster in sorted(by_disaster):
        photos = by_disaster[disaster]
        rng.shuffle(photos)
        n_train = round(len(photos) * SPLITS["train"])
        n_val = round(len(photos) * SPLITS["val"])
        for i, photo in enumerate(photos):
            split = "train" if i < n_train else "val" if i < n_train + n_val else "test"
            for s in by_photo[photo]:
                split_of[s] = split
    return split_of


class ShardWriter:
    """Accumulates samples and flushes a compressed .npz once ~max_mb (raw, pre-compression) is reached."""

    def __init__(self, out_dir, max_mb):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_mb * 1024 * 1024
        self.shard_idx = 0
        self._reset()

    def _reset(self):
        self.images, self.boxes, self.box_counts, self.names, self.poses, self.orig_wh = [], [], [], [], [], []
        self.raw_bytes = 0

    def add(self, name, img_arr, boxes, poses, orig_wh):
        self.images.append(img_arr)
        self.boxes.extend(boxes)
        self.box_counts.append(len(boxes))
        self.names.append(name)
        self.poses.extend(poses)
        self.orig_wh.append(orig_wh)
        self.raw_bytes += img_arr.nbytes
        if self.raw_bytes >= self.max_bytes:
            self.flush()

    def flush(self):
        if not self.images:
            return
        path = self.out_dir / f"shard_{self.shard_idx:04d}.npz"
        np.savez_compressed(
            path,
            images=np.stack(self.images),
            boxes=np.array(self.boxes, dtype=np.float32).reshape(-1, 4),
            box_counts=np.array(self.box_counts, dtype=np.int32),
            names=np.array(self.names, dtype="<U64"),
            poses=np.array(self.poses, dtype=np.int8),
            orig_wh=np.array(self.orig_wh, dtype=np.int32),
        )
        n = len(self.images)
        print(f"  wrote {path.parent.name}/{path.name}: {n} images, {sum(self.box_counts)} boxes, "
              f"{path.stat().st_size / 1e6:.1f} MB", flush=True)
        self.shard_idx += 1
        self._reset()


_src, _sizes = None, None


def _init(src_path, sizes):
    global _src, _sizes
    _src, _sizes = Source(src_path), sizes


def process(item):
    """Worker: decode one image and letterbox it at every size."""
    stem, img_rel, lbl_rel = item
    img = Image.open(io.BytesIO(_src.read(img_rel)))
    has_alpha = img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255
    orig_wh = img.size
    img = img.convert("RGB")
    boxes, poses = parse_labels(_src.read(lbl_rel).decode("utf-8", errors="replace"))
    out = {size: letterbox_and_normalize(img, boxes, size) for size in _sizes}
    return stem, out, poses, orig_wh, has_alpha


def run(src_path, out_dir, sizes, max_mb, seed, workers):
    src = Source(src_path)
    out_dir = Path(out_dir)
    images = {}  # stem -> (original split, image path)
    for rel in src.files:
        m = re.fullmatch(r"new_dataset3/(train|val|test)/images/(.+)\.png", rel)
        if m:
            images[m.group(2)] = (m.group(1), rel)
    stems = sorted(s for s in images if POSE_DIR + s + ".txt" in src.files)
    print(f"{len(images)} images, {len(stems)} with pose labels", flush=True)

    split_of = assign_splits(stems, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "split.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "split", "orig_split"])
        for s in stems:
            w.writerow([s, split_of[s], images[s][0]])

    stats = {"seed": seed, "sizes": sizes, "splits": {}}
    for split in SPLITS:
        items = [(s, images[s][1], POSE_DIR + s + ".txt") for s in stems if split_of[s] == split]
        print(f"\n{split}: {len(items)} images", flush=True)
        writers = {size: ShardWriter(out_dir / "rgb" / str(size) / split, max_mb) for size in sizes}
        n_boxes, n_alpha, pose_counts, sides = 0, 0, Counter(), {size: [] for size in sizes}
        with Pool(workers, initializer=_init, initargs=(src_path, sizes)) as pool:
            for i, (stem, out, poses, orig_wh, has_alpha) in enumerate(pool.imap(process, items, chunksize=8)):
                for size, (arr, boxes) in out.items():
                    writers[size].add(stem, arr, boxes, poses, orig_wh)
                    sides[size].extend(np.sqrt(b[2] * b[3]) * size for b in boxes)
                n_boxes += len(poses)
                n_alpha += has_alpha
                pose_counts.update(poses)
                if (i + 1) % 500 == 0:
                    print(f"  {i + 1}/{len(items)}", flush=True)
        for w in writers.values():
            w.flush()
        stats["splits"][split] = {
            "images": len(items),
            "photos": len({s.rsplit("_", 1)[0] for s, _, _ in items}),
            "boxes": n_boxes,
            "images_with_transparency": n_alpha,
            "poses": {str(k): v for k, v in sorted(pose_counts.items())},
            "box_side_px": {
                str(size): {f"p{q}": round(float(np.percentile(v, q)), 1) for q in (5, 25, 50, 75, 95)}
                | {"under_8px": round(float(np.mean(np.array(v) < 8)), 3)}
                for size, v in sides.items()
            },
        }
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", help="C2A_Dataset folder or the Kaggle zip (default: find it under /kaggle/input)")
    ap.add_argument("--out", default="/kaggle/working/c2a", help="output root directory")
    ap.add_argument("--sizes", type=int, nargs="+", default=[640])
    ap.add_argument("--shard-mb", type=int, default=500, help="approx. max shard size in MB, measured before compression")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    src = args.src or find_kaggle_input()
    run(src, args.out, args.sizes, args.shard_mb, args.seed, args.workers)


if __name__ == "__main__":
    main()
