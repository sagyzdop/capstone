"""Convert the datasets that `prepare.py` can't read into single-class `person` YOLO datasets, one per modality.

nii-cu-mapd:     the authors' `4-channel` variant. Labels are `x1 y1 x2 y2 + 3 flags` in RGB pixels; thermal is
                 cropped to the RGB field of view, so the same normalised boxes fit both. Writes
                 data/yolo/nii-cu-mapd-rgb and data/yolo/nii-cu-mapd-thermal.
rgbtdroneperson: thermal only (its labels are drawn on thermal and misaligned on RGB). person, rider and crowd
                 become `person`; `uncertain` regions are filled grey (masked), since they are neither person
                 nor background. Image size comes from the image, not the XML (three XMLs are wrong).
                 Writes data/yolo/rgbtdroneperson-thermal.
heridal:         the Roboflow v4 COCO export, a test set only. Roboflow stretched the 4:3 frames to 640x640, so each
                 frame is resized back to 853x640 (people 25% too narrow otherwise). All boxes are `human` (id 1).
                 Consecutive frames often show the same ground, so frames are grouped by near-duplicate dHash
                 (16x16, Hamming <= 40, single linkage). Splits: `unique` keeps the first frame of each group over
                 all of train/valid/test (we never train on HERIDAL, so its leaky split doesn't matter); `test` is
                 Roboflow's test split, for comparison with published numbers. Writes data/yolo/heridal.

Images are symlinked, except masked RGBTDronePerson frames (written as PNG) and HERIDAL frames (JPEG, un-stretched).

Usage:
    python src/detection/convert.py nii-cu-mapd data/raw/nii-cu-mapd/4-channel
    python src/detection/convert.py rgbtdroneperson data/raw/rgbtdroneperson
    python src/detection/convert.py heridal data/raw/heridal
"""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2] / "data" / "yolo"
PERSON = {"person", "rider", "crowd"}
MASK = {"uncertain"}
FILL = 114  # ultralytics' letterbox grey
HERIDAL_SIZE = (853, 640)  # 4:3, as shot
DHASH_THR = 40  # Hamming distance; near-duplicates sit at 0-35, unrelated frames at 85-105


def yolo_rows(boxes, W, H):
    """xyxy px -> `0 cx cy w h` lines, clipped to the image; boxes under 1 px dropped."""
    rows = []
    for x1, y1, x2, y2 in boxes:
        x1, x2 = max(0.0, min(x1, W)), max(0.0, min(x2, W))
        y1, y2 = max(0.0, min(y1, H)), max(0.0, min(y2, H))
        if x2 - x1 >= 1 and y2 - y1 >= 1:
            rows.append(f"0 {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
    return rows


def write(dst, split, img, rows, image=None, ext=".png"):
    """Symlink `img` (or write `image` as PNG) and its label file under dst/{images,labels}/split."""
    (dst / "images" / split).mkdir(parents=True, exist_ok=True)
    (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
    if image is None:
        link = dst / "images" / split / img.name
        if not link.exists():
            link.symlink_to(img.resolve())
    else:
        cv2.imwrite(str(dst / "images" / split / f"{img.stem}{ext}"), image, [cv2.IMWRITE_JPEG_QUALITY, 95] if ext == ".jpg" else [])
    (dst / "labels" / split / f"{img.stem}.txt").write_text("\n".join(rows) + ("\n" if rows else ""))


def write_yaml(name, splits):
    dst = ROOT / name
    yaml = [f"path: {dst}"] + [f"{s}: images/{s}" for s in splits] + ["names:", "  0: person"]
    (ROOT / f"{name}.yaml").write_text("\n".join(yaml) + "\n")


def nii(src):
    for split in ["train", "val"]:
        n_img = n_person = 0
        for lbl in sorted((src / "labels" / split).glob("*.txt")):
            boxes = [list(map(float, r.split()[:4])) for r in lbl.read_text().splitlines() if r.strip()]
            # boxes are in RGB pixels; normalised, they fit the (cropped-to-match) thermal frame too
            rows = yolo_rows(boxes, *Image.open(src / "images" / "rgb" / split / f"{lbl.stem}.jpg").size)
            for mod in ["rgb", "thermal"]:
                write(ROOT / f"nii-cu-mapd-{mod}", split, src / "images" / mod / split / f"{lbl.stem}.jpg", rows)
            n_img += 1
            n_person += len(rows)
        print(f"nii-cu-mapd {split}: {n_img} pairs, {n_person} persons")
    for mod in ["rgb", "thermal"]:
        write_yaml(f"nii-cu-mapd-{mod}", ["train", "val"])


def rgbtdroneperson(src):
    dst = ROOT / "rgbtdroneperson-thermal"
    for split in ["train", "val"]:
        n_img = n_person = n_masked = 0
        for xml in sorted((src / split / "annotation").glob("*.xml")):
            img = src / split / "thermal" / f"{xml.stem}.jpg"
            W, H = Image.open(img).size
            person, mask = [], []
            for o in ET.parse(xml).getroot().iter("object"):
                b = o.find("bndbox")
                box = [float(b.find(k).text) for k in ("xmin", "ymin", "xmax", "ymax")]
                name = o.find("name").text.strip()
                assert name in PERSON | MASK, f"{xml}: unknown class {name}"
                (person if name in PERSON else mask).append(box)
            image = None
            if mask:
                image = cv2.imread(str(img))
                for x1, y1, x2, y2 in mask:
                    image[int(y1):int(y2) + 1, int(x1):int(x2) + 1] = FILL
                n_masked += 1
            rows = yolo_rows(person, W, H)
            write(dst, split, img, rows, image)
            n_img += 1
            n_person += len(rows)
        print(f"rgbtdroneperson {split}: {n_img} images, {n_person} persons, {n_masked} with masked regions")
    write_yaml("rgbtdroneperson-thermal", ["train", "val"])


def dhash(path):
    g = cv2.resize(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), (17, 16), interpolation=cv2.INTER_AREA)
    return (g[:, 1:] > g[:, :-1]).ravel()


def view_groups(hashes):
    """Single-linkage groups of frames whose dHashes differ in <= DHASH_THR bits. Returns a group id per frame."""
    h = np.array(hashes)
    dist = (h[:, None, :] != h[None, :, :]).sum(-1)
    group = list(range(len(h)))
    find = lambda i: i if group[i] == i else find(group[i])
    for i, j in zip(*np.nonzero(np.triu(dist <= DHASH_THR, 1))):
        group[find(i)] = find(j)
    return [find(i) for i in range(len(h))]


def heridal(src):
    dst = ROOT / "heridal"
    frames = []  # (split, img path, xyxy boxes in 640x640 px)
    for split in ["train", "valid", "test"]:
        d = json.loads((src / split / "_annotations.coco.json").read_text())
        boxes = {im["id"]: [] for im in d["images"]}
        for a in d["annotations"]:
            assert a["category_id"] == 1, a
            x, y, w, h = a["bbox"]
            boxes[a["image_id"]].append([x, y, x + w, y + h])
        frames += [(split, src / split / im["file_name"], boxes[im["id"]]) for im in sorted(d["images"], key=lambda im: im["file_name"])]
    group = view_groups([dhash(img) for _, img, _ in frames])
    seen = set()
    for out in ["unique", "test"]:
        n_img = n_person = n_empty = 0
        for (split, img, boxes), g in zip(frames, group):
            if out == "test" and split != "test" or out == "unique" and g in seen:
                continue
            seen.add(g)
            # normalised boxes survive the un-stretch unchanged
            rows = yolo_rows(boxes, 640, 640)
            write(dst, out, img, rows, cv2.resize(cv2.imread(str(img)), HERIDAL_SIZE, interpolation=cv2.INTER_CUBIC), ".jpg")
            n_img += 1
            n_person += len(rows)
            n_empty += not rows
        print(f"heridal {out}: {n_img} images, {n_person} persons, {n_empty} empty")
    print(f"{len(frames)} frames in {len(set(group))} view groups")
    write_yaml("heridal", ["unique", "test"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["nii-cu-mapd", "rgbtdroneperson", "heridal"])
    ap.add_argument("src", type=Path)
    args = ap.parse_args()
    {"nii-cu-mapd": nii, "rgbtdroneperson": rgbtdroneperson, "heridal": heridal}[args.dataset](args.src)


if __name__ == "__main__":
    assert yolo_rows([[-5, 0, 5, 10], [3, 3, 3.5, 9]], 10, 10) == ["0 0.250000 0.500000 0.500000 1.000000"]
    assert view_groups([[0] * 100, [1] * 30 + [0] * 70, [0] * 30 + [1] * 70]) == [1, 1, 2]  # 30 bits apart join, 70 don't
    main()
