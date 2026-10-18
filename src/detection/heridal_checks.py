"""Extra checks quoted in station/heridal-profile.md that heridal_profile.py does not print: location mix of the
metric extremes, share of fully grouped images (CCR = 1), and sensitivity of the near-duplicate count to the
dHash threshold.

Usage: python src/detection/heridal_checks.py [DATASET_ROOT] [--out station/assets/heridal]
Reads OUT/images.csv and OUT/persons.csv (produced by heridal_profile.py); prints to stdout.
"""
import argparse
import csv
import os
from collections import Counter

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("root", nargs="?", default="data/raw/heridal-roboflow")
ap.add_argument("--out", default="station/assets/heridal")
args = ap.parse_args()
ROOT, OUT = os.path.abspath(args.root), os.path.abspath(args.out)
imgs = list(csv.DictReader(open(os.path.join(OUT, "images.csv"), encoding="utf-8")))
pers = list(csv.DictReader(open(os.path.join(OUT, "persons.csv"), encoding="utf-8")))


def locs_where(rows, key, pred):
    return Counter(r["loc"] for r in rows if r[key] and pred(float(r[key]))).most_common(5)


multi = [r for r in imgs if int(r["n_people"]) > 1]
grouped = [r for r in multi if float(r["crowd_ccr"]) == 1.0]
print(f"CCR = 1: {len(grouped)} of {len(multi)} multi-person images", Counter(r["loc"] for r in grouped).most_common(5))
for key in ["rms_contrast", "crete_blur"]:
    v = np.array([float(r[key]) for r in imgs])
    lo, hi = np.percentile(v, [5, 95])
    print(f"{key} < P5:", locs_where(imgs, key, lambda x: x < lo), f"| > P95:", locs_where(imgs, key, lambda x: x > hi))
print("person CNR > 2:", locs_where(pers, "cnr", lambda x: x > 2))


def dhash(path):
    g = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2GRAY)
    s = cv2.resize(g, (17, 16), interpolation=cv2.INTER_AREA)
    return (s[:, 1:] > s[:, :-1]).ravel()


H = np.array([dhash(os.path.join(ROOT, r["split"], r["file"])) for r in imgs])
ham = (H[:, None] != H[None]).sum(-1)
n = len(imgs)
for thr in (30, 35, 40, 45, 50):
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    ii, jj = np.where(np.triu(ham <= thr, 1))
    for i, j in zip(ii, jj):
        parent[find(i)] = find(j)
    cross = [(i, j) for i, j in zip(ii, jj) if imgs[i]["split"] != imgs[j]["split"]]
    test_twins = {k for i, j in cross for k in (i, j) if imgs[k]["split"] == "test"}
    print(f"dHash <= {thr}: {len({find(i) for i in range(n)})} view groups, {len(cross)} cross-split pairs, "
          f"{len(test_twins)} test images with a twin")
