"""Convert the datasets that `prepare.py` can't read into single-class `person` YOLO datasets, one per modality.

nii-cu-mapd:     the authors' `4-channel` variant. Labels are `x1 y1 x2 y2 + 3 flags` in RGB pixels; thermal is
                 cropped to the RGB field of view, so the same normalised boxes fit both. Writes
                 data/yolo/nii-cu-mapd-rgb and data/yolo/nii-cu-mapd-thermal.
rgbtdroneperson: thermal only (its labels are drawn on thermal and misaligned on RGB). person, rider and crowd
                 become `person`; `uncertain` regions are filled grey (masked), since they are neither person
                 nor background. Image size comes from the image, not the XML (three XMLs are wrong).
                 Writes data/yolo/rgbtdroneperson-thermal.
heridal:         the Roboflow v4 COCO export. Roboflow stretched the 4:3 frames to 640x640, so each frame is
                 resized back to 853x640 (people 25% too narrow otherwise). All boxes are `human` (id 1).
                 Roboflow's split leaks, so it is ignored and frames are split by location code (HERIDAL_SPLIT).
                 Consecutive frames often show the same ground, so frames are grouped by near-duplicate dHash
                 (16x16, Hamming <= 40, single linkage); val and test keep one frame per group and drop any frame
                 whose group reaches train. Train and val are cut into two overlapping 640x640 crops; test stays
                 whole for tiled scoring. Writes data/yolo/heridal.
nomad:           the 30 m subset (`a30`, 5472x3078 frames, one actor each, YOLO labels). Split by actor (ids ending
                 in 0 test, in 5 val), since an actor's frames come from one video. Each frame is shrunk to the
                 drone's 1280 px stream width (people at the size the drone sees at about 30 m) and, for train only,
                 to 2560 px as well (a lower flight). Train and val keep one 640x640 crop per frame and width, placed
                 at random around the actor (frames without anyone: a random crop); test keeps the whole 1280x720
                 frame for tiled scoring. Writes data/yolo/nomad.

Images are symlinked, except masked RGBTDronePerson frames (written as PNG), HERIDAL frames (JPEG, un-stretched) and
NOMAD crops (JPEG).

Usage:
    python src/detection/convert.py nii-cu-mapd data/raw/nii-cu-mapd/4-channel
    python src/detection/convert.py rgbtdroneperson data/raw/rgbtdroneperson
    python src/detection/convert.py heridal data/raw/heridal
    python src/detection/convert.py nomad data/raw/nomad
"""

import argparse
import json
import random
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2] / "data" / "yolo"
PERSON = {"person", "rider", "crowd"}
MASK = {"uncertain"}
FILL = 114  # ultralytics' letterbox grey
HERIDAL_SIZE = (853, 640)  # 4:3, as shot
# Split by location code, so val and test show places the model never trained on. MOB and GRO are the same
# scenes as BLA and GOR, so they stay with them. Test covers scene types train lacks: maquis, dark pine,
# riverbank, autumn forest, meadow, ravine.
HERIDAL_SPLIT = {
    **dict.fromkeys(["VRD", "GOR", "GRO", "JAS", "BRK", "ZRI", "TRS", "BLA", "MOB"], "train"),
    **dict.fromkeys(["RAK", "BRS"], "val"),
    **dict.fromkeys(["MED", "BRA", "CAP", "SB", "BLI", "CAB"], "test"),
}
DHASH_THR = 40  # Hamming distance; near-duplicates sit at 0-35, unrelated frames at 85-105
NOMAD_WIDTHS = {"train": [1280, 2560], "val": [1280], "test": [1280]}  # 1280: the drone's RGB stream


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
    W, H = HERIDAL_SIZE
    frames = []  # (location, img path, xyxy boxes in un-stretched px)
    for split in ["train", "valid", "test"]:
        d = json.loads((src / split / "_annotations.coco.json").read_text())
        boxes = {im["id"]: [] for im in d["images"]}
        for a in d["annotations"]:
            assert a["category_id"] == 1, a
            x, y, w, h = a["bbox"]
            boxes[a["image_id"]].append([x * W / 640, y * H / 640, (x + w) * W / 640, (y + h) * H / 640])
        for im in d["images"]:
            frames.append((im["file_name"].split("_")[1], src / split / im["file_name"], boxes[im["id"]]))
    frames.sort(key=lambda f: f[1].name)
    assert {f[0] for f in frames} <= set(HERIDAL_SPLIT), {f[0] for f in frames} - set(HERIDAL_SPLIT)
    group = view_groups([dhash(img) for _, img, _ in frames])
    train_groups = {g for f, g in zip(frames, group) if HERIDAL_SPLIT[f[0]] == "train"}
    seen = set()
    n = {s: [0, 0, 0, 0] for s in ["train", "val", "test"]}  # images, persons, empty, dropped as twin of another split
    for (loc, img, boxes), g in zip(frames, group):
        split = HERIDAL_SPLIT[loc]
        if split != "train" and (g in seen or g in train_groups):  # one frame per view; none seen in training
            n[split][3] += g in train_groups
            continue
        seen.add(g)
        image = cv2.resize(cv2.imread(str(img)), HERIDAL_SIZE, interpolation=cv2.INTER_CUBIC)
        if split == "test":  # whole frames: eval_sizes.py --tile 640 tiles them as the drone will
            crops = [(0, image, img, boxes)]
        else:  # two overlapping 640 crops, so people keep their native size at imgsz 640
            crops = []
            for x0 in [0, W - H]:
                # keep boxes with at least half their area inside the crop
                keep = [b for b in boxes if (min(b[2], x0 + H) - max(b[0], x0)) >= (b[2] - b[0]) / 2]
                crops.append((x0, image[:, x0:x0 + H], Path(f"{img.stem}_x{x0}.jpg"), [[b[0] - x0, b[1], b[2] - x0, b[3]] for b in keep]))
        for x0, im, name, bx in crops:
            rows = yolo_rows(bx, im.shape[1], im.shape[0])
            write(dst, split, name, rows, im, ".jpg")
            n[split][0] += 1
            n[split][1] += len(rows)
            n[split][2] += not rows
    for split, (i, pers, empty, twins) in n.items():
        locs = ", ".join(k for k, v in HERIDAL_SPLIT.items() if v == split)
        print(f"heridal {split} ({locs}): {i} images, {pers} persons, {empty} empty, {twins} dropped as twins of train")
    write_yaml("heridal", ["train", "val", "test"])


def nomad_split(img):
    actor = int(img.name[5:8])  # ActorNNN_a30_...
    return "test" if actor % 10 == 0 else "val" if actor % 10 == 5 else "train"


def nomad_frame(args):
    """Write one frame's crops (or the whole frame, for test). Returns (split, images, persons, empty)."""
    img, lbl = args
    split, n = nomad_split(img), [0, 0, 0]
    rows = [list(map(float, r.split()[1:])) for r in lbl.read_text().splitlines() if r.strip()] if lbl else []
    full = cv2.imread(str(img), cv2.IMREAD_REDUCED_COLOR_2)  # 2736x1539: decodes 4x faster, still above 2560
    for W in NOMAD_WIDTHS[split]:
        H = round(W * full.shape[0] / full.shape[1])
        im = cv2.resize(full, (W, H), interpolation=cv2.INTER_AREA)
        boxes = [[(cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H] for cx, cy, w, h in rows]
        name = Path(f"{img.stem}_w{W}.jpg")
        if split != "test":  # a 640 crop holding the whole actor, at a random spot seeded by the frame
            rnd = random.Random(name.stem)
            x0 = rnd.randint(*(sorted([max(0, int(boxes[0][2]) + 1 - 640), min(int(boxes[0][0]), W - 640)]) if boxes else [0, W - 640]))
            y0 = rnd.randint(*(sorted([max(0, int(boxes[0][3]) + 1 - 640), min(int(boxes[0][1]), H - 640)]) if boxes else [0, H - 640]))
            im, boxes = im[y0:y0 + 640, x0:x0 + 640], [[b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0] for b in boxes]
        out = yolo_rows(boxes, im.shape[1], im.shape[0])
        write(ROOT / "nomad", split, name, out, im, ".jpg")
        n = [n[0] + 1, n[1] + len(out), n[2] + (not out)]
    return split, *n


def nomad(src):
    labels = {p.stem: p for p in (src / "lables").glob("*/*.txt")}  # sic: the dataset's folder name
    frames = [(img, labels.get(img.stem)) for img in sorted((src / "Images").glob("*/*.jpg"))]
    n = {s: [0, 0, 0] for s in NOMAD_WIDTHS}
    with Pool(12) as pool:
        for split, *k in pool.imap_unordered(nomad_frame, frames, chunksize=8):
            n[split] = [a + b for a, b in zip(n[split], k)]
    for split, (i, pers, empty) in n.items():
        print(f"nomad {split}: {i} images, {pers} persons, {empty} empty")
    write_yaml("nomad", ["train", "val", "test"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["nii-cu-mapd", "rgbtdroneperson", "heridal", "nomad"])
    ap.add_argument("src", type=Path)
    args = ap.parse_args()
    {"nii-cu-mapd": nii, "rgbtdroneperson": rgbtdroneperson, "heridal": heridal, "nomad": nomad}[args.dataset](args.src)


if __name__ == "__main__":
    assert yolo_rows([[-5, 0, 5, 10], [3, 3, 3.5, 9]], 10, 10) == ["0 0.250000 0.500000 0.500000 1.000000"]
    assert view_groups([[0] * 100, [1] * 30 + [0] * 70, [0] * 30 + [1] * 70]) == [1, 1, 2]  # 30 bits apart join, 70 don't
    main()
