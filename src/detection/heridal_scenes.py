"""Aggregate images into manually-labelled scene types.

The 29 KMeans background clusters (seed 0) were inspected visually via cluster_sheet_*.png and each was
assigned to one scene type below. Usage:
    python src/detection/heridal_scenes.py [--out research/datasets/assets/heridal]
Reads OUT/images.csv, writes OUT/scene_types.json.
"""
import argparse
import csv
import json
import os
from collections import Counter, defaultdict

import numpy as np

# cluster id -> scene type (manual, see report section 3)
CLUSTER_TO_SCENE = {
    1: "Urban park", 15: "Urban park", 21: "Urban park", 24: "Urban park", 9: "Urban park",
    8: "Dry karst grassland", 11: "Dry karst grassland", 4: "Dry karst grassland",
    5: "Karst mosaic (grass + conifer/shrub clumps)", 18: "Karst mosaic (grass + conifer/shrub clumps)",
    22: "Karst mosaic (grass + conifer/shrub clumps)",
    0: "Mediterranean shrubland / maquis", 13: "Mediterranean shrubland / maquis",
    7: "Mediterranean shrubland / maquis",
    3: "Closed forest canopy", 6: "Closed forest canopy", 14: "Closed forest canopy", 17: "Closed forest canopy",
    10: "Dark sparse woodland (low light)", 16: "Dark sparse woodland (low light)",
    27: "Dark sparse woodland (low light)",
    28: "Autumn-coloured deciduous forest",
    2: "Leafless / grey winter scrub & hazy meadow",
    12: "Snow-covered terrain", 19: "Snow-covered terrain",
    20: "Cliffs / ravines with hard shadows", 25: "Cliffs / ravines with hard shadows",
    23: "Riverside meadow & woodland edge", 26: "Riverside meadow & woodland edge",
}

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="research/datasets/assets/heridal")
OUT = os.path.abspath(ap.parse_args().out)
rows = list(csv.DictReader(open(os.path.join(OUT, "images.csv"), encoding="utf-8")))
assert set(int(r["km_fine"]) for r in rows) == set(CLUSTER_TO_SCENE), "cluster ids changed - relabel"
agg = defaultdict(list)
for r in rows:
    r["scene"] = CLUSTER_TO_SCENE[int(r["km_fine"])]
    agg[r["scene"]].append(r)
res = {}
for s, rs in sorted(agg.items(), key=lambda kv: -len(kv[1])):
    n = np.array([int(r["n_people"]) for r in rs])
    res[s] = {
        "n_images": len(rs),
        "by_split": dict(Counter(r["split"] for r in rs)),
        "locations": dict(Counter(r["loc"] for r in rs).most_common()),
        "people_mean": float(n.mean()), "empty_frac": float((n == 0).mean()),
        "rms_contrast_median": float(np.median([float(r["rms_contrast"]) for r in rs])),
        "lap_var_median": float(np.median([float(r["lap_var"]) for r in rs])),
    }
json.dump(res, open(os.path.join(OUT, "scene_types.json"), "w", encoding="utf-8"), indent=2)
for s, v in res.items():
    print(f"{s:45s} {v['n_images']:4d} {v['by_split']} ppl={v['people_mean']:.2f} empty={v['empty_frac']:.2f} "
          f"rms={v['rms_contrast_median']:.3f} lap={v['lap_var_median']:.0f}")
