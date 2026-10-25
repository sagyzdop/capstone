"""Prepare the RGBTDronePerson dataset (paired RGB + thermal, drone, tiny persons)
into resized, sharded, compressed .npz arrays for person detection.

Source: the extracted dataset folder with `train/` and `val/`, each holding
`visible/`, `thermal/` (640x512 JPGs, same stem = same pair) and `annotation/`
(Pascal VOC XML, classes person / rider / crowd / uncertain). Paper: Zhang et
al., "Drone-based RGBT tiny person detection", ISPRS JPRS 2023.

Cleaning:
- person, rider and crowd collapse to a single `person` (0); the source class
  is kept as a side array. crowd boxes are small groups (median side 14 px),
  still people.
- uncertain boxes are not persons and not background: they go to a separate
  ignore_boxes array, so a trainer can mask them or drop them.
- Image size is read from the JPG, not the XML: 3 train XMLs say 630x500 for
  640x512 images (boxes fit the 640x512 thermal frame).
- Boxes clipped to the image; zero-area boxes dropped (1 in train).
- Truncated boxes and images without persons are kept.
- Thermal JPGs are 3-channel but grey (R=G=B), stored as 1 channel.
- The authors' train/val split is kept, so scores compare with the paper.

Labels are drawn on the thermal frame. RGB and thermal are only weakly aligned:
the RGB person is often 10-30 px off the box at 640x512, more than the median
person size (11 px). The same boxes are written for RGB so shards stay paired
by index for fusion models, but they are not usable labels for an RGB-only
detector.

Resizing is letterbox (aspect-preserving, grey 114 pad), same as
prepare_nii_cu_mapd.py. Native size is 640x512 for both modalities, so 1280 is
a 2x upscale: no new detail, but persons cover more of the model's grid.

Output: <out>/<modality>/<size>/<split>/shard_0000.npz, each holding
    images         uint8   (n, size, size, 3) for rgb / (n, size, size, 1) for thermal
    boxes          float32 (total_boxes_in_shard, 4)  cx, cy, w, h, normalized 0..1
    box_counts     int32   (n,)   boxes per image, same order as `names`/`images`
    names          <U64    (n,)   source stem, e.g. "00065"
    classes        int8    (total_boxes_in_shard,)  0 person, 1 rider, 2 crowd
    ignore_boxes   float32 (total_ignore_in_shard, 4)  uncertain regions, cx, cy, w, h
    ignore_counts  int32   (n,)
The first four keys match prepare_nii_cu_mapd.py, so load_nii_cu_mapd.load_shards
reads these shards unchanged. rgb and thermal shards hold the same images in the
same order. Also writes <out>/stats.json.

Usage:
    python prepare_rgbtdroneperson.py data/RGBTDronePersonRaw --out data/npy/rgbtdroneperson
    python prepare_rgbtdroneperson.py SRC --out OUT --sizes 640 --modalities thermal
"""

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

PAD_VALUE = 114  # standard YOLO letterbox grey pad
CLASSES = {"person": 0, "rider": 1, "crowd": 2}
IGNORE = {"uncertain"}
MODALITY_DIR = {"rgb": "visible", "thermal": "thermal"}
DARK_LUMA = 50  # mean RGB luma below this: a night frame, persons visible only in thermal


def parse_annotation(text, w, h):
    """VOC XML -> (person boxes x1 y1 x2 y2 in px, class ids, ignore boxes, dropped count),
    clipped to the w x h image."""
    boxes, classes, ignore, dropped = [], [], [], 0
    for obj in ET.fromstring(text).iter("object"):
        name = obj.findtext("name").strip()
        bb = obj.find("bndbox")
        x1, y1, x2, y2 = (float(bb.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
        x1, y1, x2, y2 = max(0.0, x1), max(0.0, y1), min(float(w), x2), min(float(h), y2)
        if x2 <= x1 or y2 <= y1:
            dropped += 1
            continue
        if name in IGNORE:
            ignore.append((x1, y1, x2, y2))
        elif name in CLASSES:
            boxes.append((x1, y1, x2, y2))
            classes.append(CLASSES[name])
        else:
            raise ValueError(f"unknown class {name!r}")
    return boxes, classes, ignore, dropped


def letterbox_and_normalize(img, boxes_list, size):
    """Resize `img` (PIL) to fit inside size x size preserving aspect, pad with grey,
    and return (array, [normalized cx/cy/w/h boxes for each list in boxes_list]).
    Boxes are x1 y1 x2 y2 in source pixels."""
    w, h = img.size
    scale = size / max(w, h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((new_w, new_h), Image.BILINEAR)

    pad_l = (size - new_w) // 2
    pad_t = (size - new_h) // 2

    pad_color = PAD_VALUE if img.mode == "L" else (PAD_VALUE,) * 3
    canvas = Image.new(img.mode, (size, size), pad_color)
    canvas.paste(resized, (pad_l, pad_t))

    sx, sy = new_w / w, new_h / h
    out = []
    for boxes in boxes_list:
        norm = []
        for x1, y1, x2, y2 in boxes:
            nx1, ny1 = x1 * sx + pad_l, y1 * sy + pad_t
            nx2, ny2 = x2 * sx + pad_l, y2 * sy + pad_t
            norm.append(((nx1 + nx2) / 2 / size, (ny1 + ny2) / 2 / size, (nx2 - nx1) / size, (ny2 - ny1) / size))
        out.append(norm)
    arr = np.array(canvas)
    return (arr[:, :, None] if arr.ndim == 2 else arr), out


class ShardWriter:
    """Accumulates samples and flushes a compressed .npz once ~max_mb (raw, pre-compression) is reached."""

    def __init__(self, out_dir, max_mb):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_mb * 1024 * 1024
        self.shard_idx = 0
        self._reset()

    def _reset(self):
        self.images, self.boxes, self.box_counts, self.names = [], [], [], []
        self.classes, self.ignore_boxes, self.ignore_counts = [], [], []
        self.raw_bytes = 0

    def add(self, name, img_arr, boxes, classes, ignore_boxes):
        self.images.append(img_arr)
        self.boxes.extend(boxes)
        self.box_counts.append(len(boxes))
        self.names.append(name)
        self.classes.extend(classes)
        self.ignore_boxes.extend(ignore_boxes)
        self.ignore_counts.append(len(ignore_boxes))
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
            classes=np.array(self.classes, dtype=np.int8),
            ignore_boxes=np.array(self.ignore_boxes, dtype=np.float32).reshape(-1, 4),
            ignore_counts=np.array(self.ignore_counts, dtype=np.int32),
        )
        print(f"  wrote {'/'.join(path.parts[-4:])}: {len(self.images)} images, {sum(self.box_counts)} boxes, "
              f"{path.stat().st_size / 1e6:.1f} MB", flush=True)
        self.shard_idx += 1
        self._reset()


_cfg = None


def _init(cfg):
    global _cfg
    _cfg = cfg


def process(item):
    """Worker: decode one RGB/thermal pair, parse its labels, letterbox at every size."""
    split, stem = item
    root, sizes, modalities = _cfg
    d = Path(root) / split
    xml_text = (d / "annotation" / f"{stem}.xml").read_text(encoding="utf-8", errors="replace")
    xml_wh = tuple(int(ET.fromstring(xml_text).findtext(f"size/{k}")) for k in ("width", "height"))

    imgs = {}
    for m in modalities:
        img = Image.open(d / MODALITY_DIR[m] / f"{stem}.jpg")
        imgs[m] = img.convert("RGB" if m == "rgb" else "L")
    sizes_seen = {img.size for img in imgs.values()}
    if len(sizes_seen) != 1:
        raise ValueError(f"{split}/{stem}: rgb and thermal sizes differ: {sizes_seen}")
    w, h = sizes_seen.pop()

    boxes, classes, ignore, dropped = parse_annotation(xml_text, w, h)
    out = {
        (m, size): letterbox_and_normalize(img, [boxes, ignore], size)
        for m, img in imgs.items()
        for size in sizes
    }
    luma = float(np.asarray(imgs["rgb"].convert("L")).mean()) if "rgb" in imgs else None
    return stem, out, classes, dropped, xml_wh != (w, h), luma


def run(src, out_dir, sizes, modalities, splits, max_mb, workers):
    src, out_dir = Path(src), Path(out_dir)
    stats = {"sizes": sizes, "modalities": modalities, "label_frame": "thermal", "splits": {}}
    for split in splits:
        d = src / split
        stems = {m: {p.stem for p in (d / MODALITY_DIR[m]).glob("*.jpg")} for m in modalities}
        labelled = {p.stem for p in (d / "annotation").glob("*.xml")}
        paired = sorted(set.intersection(labelled, *stems.values()))
        unpaired = len(set.union(labelled, *stems.values())) - len(paired)
        print(f"\n{split}: {len(paired)} labelled pairs, {unpaired} files without a partner skipped", flush=True)

        writers = {(m, s): ShardWriter(out_dir / m / str(s) / split, max_mb) for m in modalities for s in sizes}
        class_counts, n_ignore, n_dropped, n_xml_mismatch, n_negative, n_dark = Counter(), 0, 0, 0, 0, 0
        sides = {s: [] for s in sizes}
        with Pool(workers, initializer=_init, initargs=((str(src), sizes, modalities),)) as pool:
            items = [(split, s) for s in paired]
            for i, (stem, out, classes, dropped, xml_mismatch, luma) in enumerate(pool.imap(process, items, chunksize=16)):
                for (m, size), (arr, (boxes, ignore)) in out.items():
                    writers[m, size].add(stem, arr, boxes, classes, ignore)
                    if m == modalities[0]:
                        sides[size].extend(np.sqrt(b[2] * b[3]) * size for b in boxes)
                ignore_here = len(next(iter(out.values()))[1][1])
                class_counts.update(classes)
                n_ignore += ignore_here
                n_dropped += dropped
                n_xml_mismatch += xml_mismatch
                n_negative += not classes
                n_dark += luma is not None and luma < DARK_LUMA
                if (i + 1) % 1000 == 0:
                    print(f"  {i + 1}/{len(items)}", flush=True)
        for w in writers.values():
            w.flush()

        names = {v: k for k, v in CLASSES.items()}
        stats["splits"][split] = {
            "images": len(paired),
            "unpaired_files_skipped": unpaired,
            "boxes": sum(class_counts.values()),
            "classes": {names[k]: v for k, v in sorted(class_counts.items())},
            "ignore_boxes": n_ignore,
            "zero_area_dropped": n_dropped,
            "xml_size_mismatch": n_xml_mismatch,
            "images_without_person": n_negative,
            f"rgb_dark_frames_luma_lt_{DARK_LUMA}": n_dark if "rgb" in modalities else None,
            "box_side_px": {
                str(size): {f"p{q}": round(float(np.percentile(v, q)), 1) for q in (5, 25, 50, 75, 95)}
                | {"under_8px": round(float(np.mean(np.array(v) < 8)), 3)}
                for size, v in sides.items()
            },
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="dataset folder holding train/ and val/")
    ap.add_argument("--out", required=True, help="output root directory")
    ap.add_argument("--sizes", type=int, nargs="+", default=[128, 640, 1280])
    ap.add_argument("--modalities", nargs="+", default=["thermal", "rgb"], choices=["thermal", "rgb"])
    ap.add_argument("--splits", nargs="+", default=["train", "val"])
    ap.add_argument("--shard-mb", type=int, default=85, help="approx. max shard size in MB, measured before compression")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    run(args.src, args.out, args.sizes, args.modalities, args.splits, args.shard_mb, args.workers)


if __name__ == "__main__":
    main()
