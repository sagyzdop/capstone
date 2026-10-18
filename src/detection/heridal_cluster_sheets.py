"""Contact sheets of the 29 KMeans background clusters (6 random frames each) for manual scene-type labelling.

Usage: python src/detection/heridal_cluster_sheets.py [DATASET_ROOT] [--out station/assets/heridal]
Reads OUT/images.csv (produced by heridal_profile.py), writes OUT/cluster_sheet_{0,1,2}.png.
"""
import argparse
import csv
import os

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("root", nargs="?", default="data/raw/heridal-roboflow")
ap.add_argument("--out", default="station/assets/heridal")
args = ap.parse_args()
ROOT, OUT = os.path.abspath(args.root), os.path.abspath(args.out)
rows = list(csv.DictReader(open(os.path.join(OUT, "images.csv"), encoding="utf-8")))
rng = np.random.default_rng(1)
T = 130
lines = []
for c in sorted({int(r["km_fine"]) for r in rows}):
    m = [r for r in rows if int(r["km_fine"]) == c]
    idx = rng.choice(len(m), min(6, len(m)), replace=False)
    tiles = []
    for i in range(6):
        t = np.zeros((T, T, 3), np.uint8)
        if i < len(idx):
            r = m[idx[i]]
            t = cv2.resize(cv2.imread(os.path.join(ROOT, r["split"], r["file"])), (T, T), interpolation=cv2.INTER_AREA)
            cv2.putText(t, r["loc"], (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1, cv2.LINE_AA)
        tiles.append(t)
    lab = np.zeros((T, 60, 3), np.uint8)
    cv2.putText(lab, f"C{c}", (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(lab, f"n={len(m)}", (5, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
    lines.append(np.hstack([lab] + tiles))
for k, start in enumerate(range(0, len(lines), 10)):
    cv2.imwrite(os.path.join(OUT, f"cluster_sheet_{k}.jpg"), np.vstack(lines[start:start + 10]),
                [cv2.IMWRITE_JPEG_QUALITY, 85])
