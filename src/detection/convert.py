"""Convert the datasets that `prepare.py` can't read into single-class `person` YOLO datasets, one per modality.

nii-cu-mapd:     the authors' `4-channel` variant. Labels are `x1 y1 x2 y2 + 3 flags` in RGB pixels; thermal is
                 cropped to the RGB field of view, so the same normalised boxes fit both. Writes
                 data/yolo/nii-cu-mapd-rgb and data/yolo/nii-cu-mapd-thermal.
rgbtdroneperson: thermal only (its labels are drawn on thermal and misaligned on RGB). person, rider and crowd
                 become `person`; `uncertain` regions are filled grey (masked), since they are neither person
                 nor background. Image size comes from the image, not the XML (three XMLs are wrong).
                 Writes data/yolo/rgbtdroneperson-thermal.

Images are symlinked, except masked RGBTDronePerson frames, which are written as PNG.

Usage:
    python src/detection/convert.py nii-cu-mapd data/raw/nii-cu-mapd/4-channel
    python src/detection/convert.py rgbtdroneperson data/raw/rgbtdroneperson
"""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parents[2] / "data" / "yolo"
PERSON = {"person", "rider", "crowd"}
MASK = {"uncertain"}
FILL = 114  # ultralytics' letterbox grey


def yolo_rows(boxes, W, H):
    """xyxy px -> `0 cx cy w h` lines, clipped to the image; boxes under 1 px dropped."""
    rows = []
    for x1, y1, x2, y2 in boxes:
        x1, x2 = max(0.0, min(x1, W)), max(0.0, min(x2, W))
        y1, y2 = max(0.0, min(y1, H)), max(0.0, min(y2, H))
        if x2 - x1 >= 1 and y2 - y1 >= 1:
            rows.append(f"0 {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
    return rows


def write(dst, split, img, rows, image=None):
    """Symlink `img` (or write `image` as PNG) and its label file under dst/{images,labels}/split."""
    (dst / "images" / split).mkdir(parents=True, exist_ok=True)
    (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
    if image is None:
        link = dst / "images" / split / img.name
        if not link.exists():
            link.symlink_to(img.resolve())
    else:
        cv2.imwrite(str(dst / "images" / split / f"{img.stem}.png"), image)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["nii-cu-mapd", "rgbtdroneperson"])
    ap.add_argument("src", type=Path)
    args = ap.parse_args()
    {"nii-cu-mapd": nii, "rgbtdroneperson": rgbtdroneperson}[args.dataset](args.src)


if __name__ == "__main__":
    assert yolo_rows([[-5, 0, 5, 10], [3, 3, 3.5, 9]], 10, 10) == ["0 0.250000 0.500000 0.500000 1.000000"]
    main()
