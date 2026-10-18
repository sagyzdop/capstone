"""Measure how input resolution (and tiling) changes detection, per person size. Inference only.

Runs a model on a YOLO split at several imgsz values, optionally also tiled, and reports
AP50, precision/recall at conf 0.25, recall per person-size bin and ms per image.
COCO weights work too: only class 0 (person) is kept.

Usage:
    python src/detection/eval_sizes.py MODEL.pt DATASET SPLIT --imgsz 320 640 960 [--tile 640] [--iou 0.5] --out OUT.json
"""

import argparse
import json
import math
import os
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision.ops import nms
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2] / "data" / "yolo"
SIZE_BINS = [0, 8, 12, 16, 24, 32, 64, 1e9]
CONF = 0.25  # operating point for precision / recall


def load_gt(lbl, W, H):
    rows = [list(map(float, r.split()[1:5])) for r in lbl.read_text().splitlines() if r.strip()] if lbl.exists() else []
    return np.array([[(x - w / 2) * W, (y - h / 2) * H, (x + w / 2) * W, (y + h / 2) * H] for x, y, w, h in rows]).reshape(-1, 4)


def iou(a, b):
    x0, y0 = np.maximum(a[:, None, 0], b[None, :, 0]), np.maximum(a[:, None, 1], b[None, :, 1])
    x1, y1 = np.minimum(a[:, None, 2], b[None, :, 2]), np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    area = lambda z: (z[:, 2] - z[:, 0]) * (z[:, 3] - z[:, 1])
    return inter / (area(a)[:, None] + area(b)[None] - inter + 1e-9)


def match(pred, conf, gt, thr):
    """Greedy by confidence. Returns per-pred TP flags and per-GT matched confidence (-1 = missed)."""
    order = np.argsort(-conf)
    tp, gt_conf = np.zeros(len(pred), bool), np.full(len(gt), -1.0)
    if len(pred) and len(gt):
        ious = iou(pred[order], gt)
        for k, i in enumerate(order):
            j = int(np.argmax(np.where(gt_conf < 0, ious[k], -1)))
            if gt_conf[j] < 0 and ious[k, j] >= thr:
                tp[i], gt_conf[j] = True, conf[i]
    return tp, gt_conf


def ap(confs, tps, n_gt):
    order = np.argsort(-confs)
    tp = np.cumsum(tps[order]); fp = np.cumsum(~tps[order])
    rec, prec = tp / max(n_gt, 1), tp / np.maximum(tp + fp, 1)
    prec = np.maximum.accumulate(prec[::-1])[::-1]
    r = np.concatenate([[0], rec]); p = np.concatenate([[prec[0] if len(prec) else 0], prec])
    return float(np.sum((r[1:] - r[:-1]) * p[1:]))


def predict(model, img, imgsz, tile, device):
    """Boxes (xyxy, native px) and confidences for class 0, plus ms per image."""
    t = time.perf_counter()
    if not tile:
        r = model.predict(img, imgsz=imgsz, conf=0.001, classes=[0], device=device, verbose=False)[0]
        return r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), (time.perf_counter() - t) * 1000
    im = cv2.imread(str(img))
    H, W = im.shape[:2]
    step = int(tile * 0.8)  # 20% overlap so persons on a seam appear whole in one tile
    xs = list(range(0, max(W - tile, 0) + 1, step)) + ([W - tile] if W > tile and (W - tile) % step else [])
    ys = list(range(0, max(H - tile, 0) + 1, step)) + ([H - tile] if H > tile and (H - tile) % step else [])
    boxes, confs = [], []
    for y in ys:
        for x in xs:
            r = model.predict(im[y:y + tile, x:x + tile], imgsz=tile, conf=0.001, classes=[0], device=device, verbose=False)[0]
            boxes.append(r.boxes.xyxy.cpu().numpy() + [x, y, x, y]); confs.append(r.boxes.conf.cpu().numpy())
    b, c = np.concatenate(boxes), np.concatenate(confs)
    keep = nms(torch.from_numpy(b).float(), torch.from_numpy(c).float(), 0.5).numpy()
    return b[keep], c[keep], (time.perf_counter() - t) * 1000


def evaluate(model, name, split, imgsz, tile, device, thr):
    img_dir = ROOT / name / "images" / split
    all_conf, all_tp, gt_sizes, gt_hit, ms = [], [], [], [], []
    for p in sorted(img_dir.iterdir()):
        W, H = Image.open(p).size
        gt = load_gt(ROOT / name / "labels" / split / (p.stem + ".txt"), W, H)
        b, c, t = predict(model, p, imgsz, tile, device)
        ms.append(t)
        tp, gconf = match(b, c, gt, thr)
        all_conf.append(c); all_tp.append(tp)
        gt_sizes += [math.sqrt((g[2] - g[0]) * (g[3] - g[1])) for g in gt]
        gt_hit += list(gconf >= CONF)
    conf, tp = np.concatenate(all_conf), np.concatenate(all_tp)
    sizes, hit = np.array(gt_sizes), np.array(gt_hit)
    op = conf >= CONF
    bins = {}
    for lo, hi in zip(SIZE_BINS[:-1], SIZE_BINS[1:]):
        m = (sizes >= lo) & (sizes < hi)
        if m.sum():
            bins[f"{lo:g}-{hi:g}"] = {"n": int(m.sum()), "recall": round(float(hit[m].mean()), 3)}
    return {
        "imgsz": imgsz, "tile": tile, "iou": thr, "images": len(ms), "persons": len(sizes),
        "ap": round(ap(conf, tp, len(sizes)), 3),
        "precision": round(float(tp[op].mean()) if op.any() else 0.0, 3),
        "recall": round(float(hit.mean()), 3),
        "recall_by_size": bins,
        "ms_per_image_median": round(float(np.median(ms[3:] or ms)), 1),  # first calls include warm-up
    }


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("model")
    ap_.add_argument("dataset")
    ap_.add_argument("split")
    ap_.add_argument("--imgsz", type=int, nargs="+", default=[640])
    ap_.add_argument("--tile", type=int, default=0, help="also run tiled: crop size in native px, inferred at imgsz = tile")
    ap_.add_argument("--iou", type=float, default=0.5)
    ap_.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 2) // 4))
    ap_.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap_.add_argument("--out", type=Path, required=True)
    args = ap_.parse_args()
    torch.set_num_threads(args.threads)
    cv2.setNumThreads(args.threads)
    model = YOLO(args.model)
    runs = [(s, 0) for s in args.imgsz] + ([(args.tile, args.tile)] if args.tile else [])
    results = []
    for imgsz, tile in runs:
        r = evaluate(model, args.dataset, args.split, imgsz, tile, args.device, args.iou)
        r.update(model=Path(args.model).name, dataset=args.dataset, split=args.split)
        print(json.dumps(r), flush=True)
        results.append(r)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    g = np.array([[0, 0, 10, 10], [20, 20, 30, 30]], float)
    tp, gc = match(np.array([[0, 0, 10, 10], [0, 0, 10, 10]], float), np.array([0.9, 0.8]), g, 0.5)
    assert tp.tolist() == [True, False] and gc.tolist() == [0.9, -1.0]  # duplicate is a FP, 2nd GT missed
    assert abs(ap(np.array([0.9]), np.array([True]), 2) - 0.5) < 1e-9
    main()
