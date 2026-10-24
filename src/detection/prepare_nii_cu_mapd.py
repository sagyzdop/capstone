"""Prepare the NII-CU-MAPD dataset (4-channel variant) into resized, sharded,
compressed .npz arrays for RGB and thermal person detection.

Source: the `4-channel/` folder inside NII_CU_MAPD_dataset.zip. It is the
authors' pre-cleaned subset: only boxes visible in both modalities (type=0),
motion-blurred frames removed (bad=0). Thermal images are already cropped to
the RGB field of view, so YOLO-normalized box coordinates (computed from the
RGB image size) apply unchanged to the paired thermal image -- no separate
coordinate transform needed per modality.

Reads images directly out of the zip (no full extraction) to keep disk usage
low. Resizes with letterbox (aspect-preserving, padded to a square) rather
than a naive stretch-resize, and re-derives box coordinates for the padded
canvas. Thermal is skipped at 1280 by default: native thermal resolution is
~701x513, so upscaling to 1280 adds no real detail (override with
--allow-thermal-upscale).

Output: one directory tree per modality/resolution/split, each holding
compressed, size-capped .npz shards:
    <out>/<modality>/<size>/<split>/shard_0000.npz
Each shard holds:
    images       uint8   (n, size, size, 3) for rgb / (n, size, size, 1) for thermal
    boxes        float32 (total_boxes_in_shard, 4)  cx, cy, w, h, normalized 0..1
    box_counts   int32   (n,)   boxes per image, same order as `names`/`images`
    names        <U64    (n,)   "flightN_frameNNNNN" stem, to trace back to the source

To read a shard back:
    d = np.load("shard_0000.npz")
    imgs, boxes, counts, names = d["images"], d["boxes"], d["box_counts"], d["names"]
    offsets = np.concatenate([[0], np.cumsum(counts)])
    boxes_for_image_i = boxes[offsets[i]:offsets[i + 1]]

Usage:
    python prepare_nii_cu_mapd.py ZIP_PATH --out OUT_DIR --sizes 128 640
    python prepare_nii_cu_mapd.py ZIP_PATH --out OUT_DIR --sizes 1280 --modalities rgb
"""

import argparse
import io
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

PAD_VALUE = 114  # standard YOLO letterbox grey pad


def parse_labels(text):
    """Tab- or space-delimited: x1 y1 x2 y2 type occluded bad (4-channel: type=0, bad=0 always)."""
    boxes = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) < 4:
            continue
        x1, y1, x2, y2 = (float(p) for p in parts[:4])
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append((x1, y1, x2, y2))
    return boxes


def letterbox_and_normalize(img, boxes, size):
    """Resize `img` (PIL) to fit inside size x size preserving aspect, pad with grey,
    and return (array, normalized cx/cy/w/h boxes) for the padded canvas."""
    w, h = img.size
    scale = size / max(w, h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((new_w, new_h), Image.BILINEAR)

    pad_l = (size - new_w) // 2
    pad_t = (size - new_h) // 2

    pad_color = PAD_VALUE if img.mode == "L" else (PAD_VALUE,) * 3
    canvas = Image.new(img.mode, (size, size), pad_color)
    canvas.paste(resized, (pad_l, pad_t))

    out_boxes = []
    for x1, y1, x2, y2 in boxes:
        nx1, ny1 = x1 * scale + pad_l, y1 * scale + pad_t
        nx2, ny2 = x2 * scale + pad_l, y2 * scale + pad_t
        cx, cy = (nx1 + nx2) / 2 / size, (ny1 + ny2) / 2 / size
        bw, bh = (nx2 - nx1) / size, (ny2 - ny1) / size
        out_boxes.append((cx, cy, bw, bh))
    return np.array(canvas), out_boxes


def iter_split(z, split, modality):
    """Yield (stem, image_bytes, boxes) for one split/modality of 4-channel."""
    img_prefix = f"4-channel/images/{modality}/{split}/"
    lbl_prefix = f"4-channel/labels/{split}/"
    names = z.namelist()
    img_names = sorted(n for n in names if n.startswith(img_prefix) and n.endswith(".jpg"))
    name_set = set(names)
    for img_name in img_names:
        stem = Path(img_name).stem
        lbl_name = f"{lbl_prefix}{stem}.txt"
        with z.open(img_name) as f:
            img_bytes = f.read()
        boxes = []
        if lbl_name in name_set:
            with z.open(lbl_name) as f:
                boxes = parse_labels(f.read().decode("utf-8", errors="replace"))
        yield stem, img_bytes, boxes


class ShardWriter:
    """Accumulates samples and flushes a compressed .npz once ~max_mb (raw, pre-compression) is reached."""

    def __init__(self, out_dir, max_mb):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_mb * 1024 * 1024
        self.shard_idx = 0
        self._reset()

    def _reset(self):
        self.images, self.boxes, self.box_counts, self.names, self.raw_bytes = [], [], [], [], 0

    def add(self, name, img_arr, boxes):
        if img_arr.ndim == 2:
            img_arr = img_arr[:, :, None]
        self.images.append(img_arr)
        self.boxes.extend(boxes)
        self.box_counts.append(len(boxes))
        self.names.append(name)
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
        )
        n = len(self.images)
        print(f"  wrote {path.name}: {n} images, {sum(self.box_counts)} boxes, {path.stat().st_size / 1e6:.1f} MB")
        self.shard_idx += 1
        self._reset()


def run(zip_path, out_dir, sizes, modalities, splits, max_mb, allow_thermal_upscale):
    z = zipfile.ZipFile(zip_path)
    for modality in modalities:
        mode = "RGB" if modality == "rgb" else "L"
        sizes_here = sizes
        if modality == "thermal" and not allow_thermal_upscale:
            skipped = [s for s in sizes if s > 640]
            sizes_here = [s for s in sizes if s <= 640]
            if skipped:
                print(f"thermal: skipping size(s) {skipped} -- native res is ~701x513, "
                      f"upscaling adds no real detail (use --allow-thermal-upscale to force)")
        for split in splits:
            samples = list(iter_split(z, split, modality))
            print(f"\n{modality}/{split}: {len(samples)} images")
            writers = {s: ShardWriter(Path(out_dir) / modality / str(s) / split, max_mb) for s in sizes_here}
            for i, (stem, img_bytes, boxes) in enumerate(samples):
                img = Image.open(io.BytesIO(img_bytes)).convert(mode)
                for size in sizes_here:
                    arr, norm_boxes = letterbox_and_normalize(img, boxes, size)
                    writers[size].add(stem, arr, norm_boxes)
                if (i + 1) % 500 == 0:
                    print(f"  {i + 1}/{len(samples)}")
            for w in writers.values():
                w.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip_path")
    ap.add_argument("--out", required=True, help="output root directory")
    ap.add_argument("--sizes", type=int, nargs="+", default=[128, 640, 1280])
    ap.add_argument("--modalities", nargs="+", default=["rgb", "thermal"], choices=["rgb", "thermal"])
    ap.add_argument("--splits", nargs="+", default=["train", "val"])
    ap.add_argument("--shard-mb", type=int, default=85, help="approx. max shard size in MB, measured before compression")
    ap.add_argument("--allow-thermal-upscale", action="store_true")
    args = ap.parse_args()
    run(args.zip_path, args.out, args.sizes, args.modalities, args.splits, args.shard_mb, args.allow_thermal_upscale)


if __name__ == "__main__":
    main()
