"""Convert a YOLO-labelled dataset into a single-class `person` dataset for ultralytics.

Images are symlinked (not copied); labels are rewritten keeping only person classes as id 0.
Images without persons are kept as negatives.

Usage:
    python src/detection/prepare.py NAME --person-ids 0 \
        --split train=IMG_DIR:LBL_DIR --split val=IMG_DIR:LBL_DIR --split test=IMG_DIR:LBL_DIR
LBL_DIR may instead be a COCO json file (bbox = [x, y, w, h] px); it is converted to YOLO txt first.
Output: data/yolo/NAME/{images,labels}/{split}/ and data/yolo/NAME.yaml
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "data" / "yolo"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def person_lines(text, person_ids):
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and int(float(parts[0])) in person_ids:
            out.append("0 " + " ".join(parts[1:5]))
    return out


def coco_to_yolo(coco_json, out_dir):
    d = json.loads(Path(coco_json).read_text())
    anns = d.get("annotations", d.get("annotation"))  # HIT-UAV uses "annotation"
    by_img = defaultdict(list)
    for a in anns:
        by_img[a["image_id"]].append(a)
    out_dir.mkdir(parents=True, exist_ok=True)
    for im in d["images"]:
        W, H = im["width"], im["height"]
        name = im.get("file_name", im.get("filename"))
        rows = []
        for a in by_img[im["id"]]:
            x, y, w, h = a["bbox"]
            rows.append(f"{a['category_id']} {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}")
        (out_dir / (Path(name).stem + ".txt")).write_text("\n".join(rows) + "\n")
    return out_dir


def convert_split(img_dir, lbl_dir, dst, split, person_ids):
    (dst / "images" / split).mkdir(parents=True, exist_ok=True)
    (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
    n_img = n_person = n_missing = 0
    for img in sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXT):
        lbl = lbl_dir / (img.stem + ".txt")
        n_missing += not lbl.exists()
        lines = person_lines(lbl.read_text(), person_ids) if lbl.exists() else []
        link = dst / "images" / split / img.name
        if not link.exists():
            link.symlink_to(img.resolve())
        (dst / "labels" / split / (img.stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
        n_img += 1
        n_person += len(lines)
    print(f"{split}: {n_img} images, {n_person} persons, {n_missing} without label file")
    assert n_img, f"no images in {img_dir}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--person-ids", type=int, nargs="+", required=True)
    ap.add_argument("--split", action="append", required=True, help="split=IMG_DIR:LBL_DIR")
    args = ap.parse_args()

    dst = ROOT / args.name
    splits = []
    for s in args.split:
        split, dirs = s.split("=", 1)
        img_dir, lbl_dir = (Path(d) for d in dirs.split(":", 1))
        if lbl_dir.suffix == ".json":
            lbl_dir = coco_to_yolo(lbl_dir, dst / "_coco_labels" / split)
        convert_split(img_dir, lbl_dir, dst, split, set(args.person_ids))
        splits.append(split)

    yaml = [f"path: {dst}"] + [f"{s}: images/{s}" for s in splits] + ["names:", "  0: person"]
    (ROOT / f"{args.name}.yaml").write_text("\n".join(yaml) + "\n")
    print(f"wrote {ROOT / (args.name + '.yaml')}")


if __name__ == "__main__":
    assert person_lines("0 .5 .5 .1 .1\n1 .2 .2 .1 .1\n3 .1 .1 .1 .1 0.9", {0, 3}) == [
        "0 .5 .5 .1 .1",
        "0 .1 .1 .1 .1",
    ]
    assert person_lines("", {0}) == []
    main()
