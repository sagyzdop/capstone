"""Profile of the HERIDAL dataset (Roboflow "Heridal Human Detection" v4, COCO export, 640x640 stretched).

Usage:
    python src/detection/heridal_profile.py [DATASET_ROOT] [--out research/datasets/assets/heridal]

DATASET_ROOT holds train/ valid/ test/, each with _annotations.coco.json (default: data/raw/heridal-roboflow).

Outputs (in --out):
    summary.json    all aggregate statistics quoted in research/datasets/heridal-profile.md
    images.csv      one row per image  (split, location code, counts, contrast, sharpness, crowding, ...)
    persons.csv     one row per annotation (size, local contrast, nearest-neighbour distance, ...)
    *.png           plots and example montages

The "compat" block in summary.json uses the exact definitions of src/detection/audit.py (signed contrast in
image-std units, Laplacian ksize 1 on the 640 image, person box grown 25%), so HERIDAL can be compared with the
datasets in station/dataset-profiles.md. Everything is deterministic (fixed seeds, sorted file order).
"""
import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

SEED = 0
SPLITS = ["train", "valid", "test"]
PCTS = [5, 25, 50, 75, 95]
# Original HERIDAL frames are 4000x3000 (assumed, see profile); Roboflow stretched them to 640x640.
ORIG_W, ORIG_H = 4000, 3000

ap = argparse.ArgumentParser()
ap.add_argument("root", nargs="?", default="data/raw/heridal-roboflow")
ap.add_argument("--out", default="research/datasets/assets/heridal")
args = ap.parse_args()
ROOT = os.path.abspath(args.root)
OUT = FIG = os.path.abspath(args.out)
JPG = [cv2.IMWRITE_JPEG_QUALITY, 85]  # photo montages as JPEG to keep the repo small
os.makedirs(FIG, exist_ok=True)


def stats(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"n": 0}
    d = {"n": int(len(x)), "mean": float(x.mean()), "std": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
         "min": float(x.min()), "max": float(x.max()), "median": float(np.median(x))}
    for p in PCTS:
        d[f"p{p}"] = float(np.percentile(x, p))
    return d


def location_code(fname):
    # e.g. train_VRD_3032_JPG.rf.<hash>.jpg  ->  VRD
    m = re.match(r"^(?:train|valid|test)_([A-Z]+)_", fname)
    return m.group(1) if m else "UNK"


def original_name(fname):
    return re.sub(r"\.rf\..*$", "", fname)


# ----------------------------------------------------------------------------- load
images, persons = [], []
for split in SPLITS:
    with open(os.path.join(ROOT, split, "_annotations.coco.json"), encoding="utf-8") as f:
        coco = json.load(f)
    by_img = defaultdict(list)
    for a in coco["annotations"]:
        by_img[a["image_id"]].append(a)
    for im in sorted(coco["images"], key=lambda i: i["file_name"]):
        path = os.path.join(ROOT, split, im["file_name"])
        images.append({
            "split": split, "file": im["file_name"], "path": path, "orig": original_name(im["file_name"]),
            "loc": location_code(im["file_name"]), "json_w": im["width"], "json_h": im["height"],
            "bytes": os.path.getsize(path), "anns": by_img.get(im["id"], []),
        })

# ----------------------------------------------------------------------------- disk size
disk = {"total_bytes": 0, "image_bytes": 0, "json_bytes": 0, "other_bytes": 0}
for dirpath, dirnames, files in os.walk(ROOT):
    if os.path.join(ROOT, "analysis") in dirpath:
        continue
    for fn in files:
        b = os.path.getsize(os.path.join(dirpath, fn))
        disk["total_bytes"] += b
        if fn.lower().endswith((".jpg", ".jpeg", ".png")):
            disk["image_bytes"] += b
        elif fn.endswith(".json"):
            disk["json_bytes"] += b
        else:
            disk["other_bytes"] += b


# ----------------------------------------------------------------------------- helpers
def lbp_hist(gray):
    """Uniform-ish 8-neighbour LBP histogram (256 bins collapsed to 32) - texture descriptor."""
    g = gray.astype(np.int16)
    c = g[1:-1, 1:-1]
    code = np.zeros_like(c, dtype=np.uint8)
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    for k, (dy, dx) in enumerate(offs):
        n = g[1 + dy:g.shape[0] - 1 + dy, 1 + dx:g.shape[1] - 1 + dx]
        code |= ((n >= c).astype(np.uint8) << k)
    h = np.bincount((code >> 3).ravel(), minlength=32).astype(float)
    return h / h.sum()


def crete_blur(g):
    """Crete-Roffet et al. (2007) no-reference blur metric: 0 = sharp ... 1 = maximally blurred.
    Compares neighbour differences of the image with those of a 9-tap re-blurred copy; insensitive to the
    absolute amount of texture, unlike variance of Laplacian."""
    out = []
    # cv2 ksize is (width, height): axis 0 (rows) -> vertical 1x9 blur, axis 1 (cols) -> horizontal 9x1 blur
    for axis, ksize in ((0, (1, 9)), (1, (9, 1))):
        b = cv2.blur(g, ksize)
        df = np.abs(np.diff(g, axis=axis))
        db = np.abs(np.diff(b, axis=axis))
        v = np.maximum(0, df - db)
        sf = df[1:-1, 1:-1].sum()
        out.append((sf - v[1:-1, 1:-1].sum()) / max(sf, 1e-9))
    return float(max(out))


def dhash(gray, size=16):
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    return (small[:, 1:] > small[:, :-1]).ravel()


def local_contrast(gray, lab, x, y, w, h):
    """Contrast of a person box vs. a surrounding ring of width max(w,h, 4) px."""
    H, W = gray.shape
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    x1, y1 = int(np.ceil(x + w)), int(np.ceil(y + h))
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0:
        return np.nan, np.nan, np.nan
    r = int(max(w, h, 4))
    X0, Y0, X1, Y1 = max(x0 - r, 0), max(y0 - r, 0), min(x1 + r, W), min(y1 + r, H)
    mask = np.zeros((Y1 - Y0, X1 - X0), bool)
    mask[:] = True
    mask[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = False
    gin = gray[y0:y1, x0:x1].astype(float)
    gring = gray[Y0:Y1, X0:X1].astype(float)[mask]
    lin = lab[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    lring = lab[Y0:Y1, X0:X1].reshape(-1, 3).astype(float)[mask.ravel()]
    dmean = abs(gin.mean() - gring.mean())
    cnr = dmean / (gring.std() + 1e-6)
    # OpenCV 8-bit Lab: L*255/100, a+128, b+128 -> convert to CIE units before Delta E 1976
    scale = np.array([100 / 255, 1, 1])
    de = float(np.linalg.norm((lin.mean(0) - lring.mean(0)) * scale))
    return dmean, cnr, de


def compat_person(gray, integral, std, x, y, w, h):
    """Signed contrast and sharpness exactly as src/detection/audit.py (local_contrast, person_sharpness)."""
    H, W = gray.shape
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, max(x0 + 1, int(round(x + w)))), min(H, max(y0 + 1, int(round(y + h))))

    def box_mean(a0, b0, a1, b1):
        s = integral[b1, a1] - integral[b0, a1] - integral[b1, a0] + integral[b0, a0]
        return s / max((a1 - a0) * (b1 - b0), 1)

    bw, bh = x1 - x0, y1 - y0
    rx0, ry0, rx1, ry1 = max(0, x0 - bw), max(0, y0 - bh), min(W, x1 + bw), min(H, y1 + bh)
    inner = box_mean(x0, y0, x1, y1)
    outer_sum = box_mean(rx0, ry0, rx1, ry1) * (rx1 - rx0) * (ry1 - ry0)
    ring = (outer_sum - inner * bw * bh) / max((rx1 - rx0) * (ry1 - ry0) - bw * bh, 1)
    px, py = max(1, bw // 4), max(1, bh // 4)
    crop = gray[max(0, y0 - py):min(H, y1 + py), max(0, x0 - px):min(W, x1 + px)]
    sharp = float(cv2.Laplacian(crop, cv2.CV_64F).var()) if min(crop.shape) >= 3 else float("nan")
    return float((inner - ring) / max(std, 1e-6)), sharp


# ----------------------------------------------------------------------------- per-image pass
feats, hashes = [], []
for rec in images:
    bgr = cv2.imread(rec["path"], cv2.IMREAD_COLOR)
    rec["h"], rec["w"] = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    g = gray.astype(np.float64)

    # --- contrast (global)
    rec["rms_contrast"] = float(g.std() / 255.0)
    p1, p99 = np.percentile(g, [1, 99])
    rec["michelson_p1p99"] = float((p99 - p1) / (p99 + p1 + 1e-6))
    rec["mean_lum"] = float(g.mean() / 255.0)

    # --- sharpness
    rec["lap_var"] = float(cv2.Laplacian(g, cv2.CV_64F, ksize=3).var())
    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    rec["tenengrad"] = float(np.mean(gx ** 2 + gy ** 2))
    rec["crete_blur"] = crete_blur(g)
    # audit.py-compatible: grey std (0-255) and Laplacian (ksize 1) on the 640-long-side image
    assert max(gray.shape) == 640, "compat metrics assume the 640 export (no resize needed)"
    rec["compat_rms"] = float(gray.std())
    rec["compat_sharp640"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    integral = cv2.integral(gray.astype(np.float64))

    # --- background descriptor (computed on the image with people masked out is unnecessary:
    #     people occupy <0.2 % of pixels on average)
    small = cv2.resize(bgr, (128, 128), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hh = cv2.calcHist([hsv], [0], None, [18], [0, 180]).ravel()
    sh = cv2.calcHist([hsv], [1], None, [8], [0, 256]).ravel()
    vh = cv2.calcHist([hsv], [2], None, [8], [0, 256]).ravel()
    sg = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    tex = lbp_hist(sg)
    gm = np.hypot(cv2.Sobel(sg.astype(float), cv2.CV_64F, 1, 0), cv2.Sobel(sg.astype(float), cv2.CV_64F, 0, 1))
    edge_hist = np.histogram(gm, bins=8, range=(0, 400))[0].astype(float)
    f = np.concatenate([hh / hh.sum(), sh / sh.sum(), vh / vh.sum(), tex, edge_hist / edge_hist.sum(),
                        [hsv[..., 1].mean() / 255, hsv[..., 2].mean() / 255, gm.mean() / 100]])
    feats.append(f)
    hashes.append(dhash(gray))

    # --- persons
    boxes = np.array([a["bbox"] for a in rec["anns"]], dtype=float).reshape(-1, 4)
    rec["n_people"] = len(boxes)
    cx = boxes[:, 0] + boxes[:, 2] / 2
    cy = boxes[:, 1] + boxes[:, 3] / 2
    size = np.sqrt(boxes[:, 2] * boxes[:, 3])
    nn_px = np.full(len(boxes), np.inf)
    n_overlap = np.zeros(len(boxes), int)
    if len(boxes) > 1:
        d = np.hypot(cx[:, None] - cx[None], cy[:, None] - cy[None])
        np.fill_diagonal(d, np.inf)
        nn_px = d.min(1)
        bx0, by0 = boxes[:, 0], boxes[:, 1]
        bx1, by1 = bx0 + boxes[:, 2], by0 + boxes[:, 3]
        iw = np.clip(np.minimum(bx1[:, None], bx1[None]) - np.maximum(bx0[:, None], bx0[None]), 0, None)
        ih = np.clip(np.minimum(by1[:, None], by1[None]) - np.maximum(by0[:, None], by0[None]), 0, None)
        inter = iw * ih
        np.fill_diagonal(inter, 0)
        n_overlap = (inter > 0).sum(1)
    nn_norm = nn_px / np.maximum(size, 1e-6)
    for i, (x, y, w, h) in enumerate(boxes):
        dmean, cnr, de = local_contrast(gray, lab, x, y, w, h)
        c_con, c_sharp = compat_person(gray, integral, rec["compat_rms"], x, y, w, h)
        persons.append({
            "compat_contrast": c_con, "compat_sharp640": c_sharp,
            "split": rec["split"], "file": rec["file"], "loc": rec["loc"], "x": x, "y": y, "w": w, "h": h,
            "area_px": w * h, "area_orig_px": w * h * (ORIG_W / rec["w"]) * (ORIG_H / rec["h"]),
            "aspect_w_over_h": w / h, "dgray": dmean, "cnr": cnr, "deltaE": de,
            "nn_px": nn_px[i], "nn_norm": nn_norm[i], "overlaps": int(n_overlap[i]),
            "n_in_image": len(boxes),
        })

    # --- crowding (image level)
    if len(boxes) == 0:
        rec.update(crowd_ccr=np.nan, crowd_mean_nn_norm=np.nan, crowd_pairs_close=0, crowd_groups=0,
                   person_px_frac=0.0)
    else:
        close = nn_norm < 5.0  # neighbour centre within 5 person-sizes
        rec["crowd_ccr"] = float(close.mean()) if len(boxes) > 1 else 0.0
        rec["crowd_mean_nn_norm"] = float(np.mean(nn_norm[np.isfinite(nn_norm)])) if len(boxes) > 1 else np.nan
        # groups = connected components where centres closer than 5 person-sizes (mean of pair sizes)
        parent = list(range(len(boxes)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        pairs = 0
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if np.hypot(cx[i] - cx[j], cy[i] - cy[j]) < 5.0 * (size[i] + size[j]) / 2:
                    pairs += 1
                    parent[find(i)] = find(j)
        rec["crowd_pairs_close"] = pairs
        rec["crowd_groups"] = len({find(i) for i in range(len(boxes))})
        rec["person_px_frac"] = float((boxes[:, 2] * boxes[:, 3]).sum() / (rec["w"] * rec["h"]))
    rec["largest_group"] = 0 if len(boxes) == 0 else int(max(Counter(
        [find(i) for i in range(len(boxes))]).values())) if len(boxes) > 1 else 1

feats = np.array(feats)
hashes = np.array(hashes)

# ----------------------------------------------------------------------------- backgrounds
X = StandardScaler().fit_transform(feats)
Xp = PCA(n_components=0.95, random_state=SEED).fit_transform(X)
sil = {}
for k in range(2, 31):
    lab_k = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit_predict(Xp)
    sil[k] = float(silhouette_score(Xp, lab_k, random_state=SEED))
k_best = max(sil, key=sil.get)
# A second, more granular operating point: best silhouette among k >= 6 (scene-type granularity)
k_fine = max((k for k in sil if k >= 6), key=sil.get)
km_best = KMeans(n_clusters=k_best, n_init=10, random_state=SEED).fit_predict(Xp)
km_fine = KMeans(n_clusters=k_fine, n_init=10, random_state=SEED).fit_predict(Xp)
locs = [r["loc"] for r in images]
ari_best = adjusted_rand_score(locs, km_best)
ari_fine = adjusted_rand_score(locs, km_fine)
# Agglomerative (Ward) with a distance threshold, as an independent check on cluster count
ward_counts = {}
from scipy.cluster.hierarchy import fcluster, linkage

Z = linkage(Xp, method="ward")
for t in [0.5, 0.6, 0.7, 0.8]:
    thr = t * Z[:, 2].max()
    ward_counts[t] = int(len(set(fcluster(Z, thr, criterion="distance"))))
ward_gaps = np.diff(Z[::-1, 2])[:30]
ward_k_gap = int(np.argmin(ward_gaps) + 2)  # largest drop in merge height -> natural cluster count

# near-duplicate / overlapping views (dHash Hamming distance)
n = len(hashes)
ham = (hashes[:, None, :] != hashes[None, :, :]).sum(-1)
dup_thr = 40  # out of 256 bits; chosen from the histogram valley (see fig)
parent = list(range(n))


def findp(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


cross_split_pairs = 0
for i in range(n):
    for j in range(i + 1, n):
        if ham[i, j] <= dup_thr:
            parent[findp(i)] = findp(j)
            if images[i]["split"] != images[j]["split"]:
                cross_split_pairs += 1
dup_groups = Counter(findp(i) for i in range(n))
for i, r in enumerate(images):
    r["km_best"] = int(km_best[i])
    r["km_fine"] = int(km_fine[i])
    r["view_group"] = int(findp(i))

# ----------------------------------------------------------------------------- write tables
img_cols = ["split", "file", "loc", "w", "h", "bytes", "n_people", "rms_contrast", "michelson_p1p99", "mean_lum",
            "lap_var", "tenengrad", "crete_blur", "crowd_ccr", "crowd_mean_nn_norm", "crowd_pairs_close", "crowd_groups",
            "largest_group", "person_px_frac", "km_best", "km_fine", "view_group"]
with open(os.path.join(OUT, "images.csv"), "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, fieldnames=img_cols, extrasaction="ignore")
    wr.writeheader()
    wr.writerows(images)
with open(os.path.join(OUT, "persons.csv"), "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, fieldnames=list(persons[0].keys()))
    wr.writeheader()
    wr.writerows(persons)

# ----------------------------------------------------------------------------- summary
npp = np.array([r["n_people"] for r in images])
pos = npp > 0
P = {k: np.array([p[k] for p in persons], dtype=float) for k in persons[0] if k not in ("split", "file", "loc")}
side = np.sqrt(P["area_px"])
summary = {
    "disk": disk,
    "n_images": len(images),
    "n_images_by_split": dict(Counter(r["split"] for r in images)),
    "n_annotations": int(npp.sum()),
    "n_annotations_by_split": {s: int(sum(r["n_people"] for r in images if r["split"] == s)) for s in SPLITS},
    "n_empty_images_by_split": {s: int(sum(1 for r in images if r["split"] == s and r["n_people"] == 0))
                                for s in SPLITS},
    "resolutions": dict(Counter(f"{r['w']}x{r['h']}" for r in images)),
    "json_matches_file_resolution": all(r["w"] == r["json_w"] and r["h"] == r["json_h"] for r in images),
    "file_kb": stats([r["bytes"] / 1024 for r in images]),
    "locations": dict(Counter(locs).most_common()),
    "locations_by_split": {s: dict(Counter(r["loc"] for r in images if r["split"] == s)) for s in SPLITS},
    "people_per_image_all": stats(npp),
    "people_per_image_nonempty": stats(npp[pos]),
    "people_per_image_by_split": {s: stats([r["n_people"] for r in images if r["split"] == s]) for s in SPLITS},
    "people_count_hist": {int(k): int(v) for k, v in sorted(Counter(npp.tolist()).items())},
    "person_area_px640": stats(P["area_px"]),
    "person_side_px640": stats(side),
    "person_w_px640": stats(P["w"]),
    "person_h_px640": stats(P["h"]),
    "person_area_orig_px_est": stats(P["area_orig_px"]),
    "person_aspect_w_over_h": stats(P["aspect_w_over_h"]),
    "person_frac_lt_8x8": float(np.mean(P["area_px"] < 64)),
    "person_frac_lt_16x16": float(np.mean(P["area_px"] < 256)),
    "person_frac_coco_small_lt_32x32": float(np.mean(P["area_px"] < 1024)),
    "person_px_frac_of_image_nonempty": stats([r["person_px_frac"] for r in images if r["n_people"] > 0]),
    "rms_contrast": stats([r["rms_contrast"] for r in images]),
    "michelson_p1p99": stats([r["michelson_p1p99"] for r in images]),
    "mean_luminance": stats([r["mean_lum"] for r in images]),
    "person_dgray": stats(P["dgray"]),
    "person_cnr": stats(P["cnr"]),
    "person_deltaE": stats(P["deltaE"]),
    "person_frac_cnr_lt_1": float(np.nanmean(P["cnr"] < 1)),
    "person_frac_deltaE_lt_10": float(np.nanmean(P["deltaE"] < 10)),
    "lap_var": stats([r["lap_var"] for r in images]),
    "tenengrad": stats([r["tenengrad"] for r in images]),
    "crete_blur": stats([r["crete_blur"] for r in images]),
    "compat": {
        "person_contrast": stats(P["compat_contrast"]),
        "person_abs_contrast": stats(np.abs(P["compat_contrast"])),
        "low_contrast_pct": float(np.mean(np.abs(P["compat_contrast"]) < 0.5) * 100),
        "person_sharpness_640": stats(P["compat_sharp640"]),
        "image_rms_contrast": stats([r["compat_rms"] for r in images]),
        "image_sharpness_640": stats([r["compat_sharp640"] for r in images]),
        "nn_gap_body_sizes": stats(P["nn_norm"]),
        "pct_neighbour_lt_2_sizes": float(np.mean(P["nn_norm"] < 2) * 100),
    },
    "corr_lapvar_tenengrad_spearman": None,
    "crowd_ccr_multi": stats([r["crowd_ccr"] for r in images if r["n_people"] > 1]),
    "crowd_ccr_nonempty": stats([r["crowd_ccr"] for r in images if r["n_people"] > 0]),
    "crowd_mean_nn_norm_multi": stats([r["crowd_mean_nn_norm"] for r in images if r["n_people"] > 1]),
    "person_nn_norm": stats(P["nn_norm"]),
    "person_nn_px640": stats(P["nn_px"]),
    "person_frac_overlapping_box": float(np.mean(P["overlaps"] > 0)),
    "person_frac_nn_lt_2sizes": float(np.mean(P["nn_norm"] < 2)),
    "person_frac_nn_lt_5sizes": float(np.mean(P["nn_norm"] < 5)),
    "person_frac_alone": float(np.mean(~np.isfinite(P["nn_norm"]))),
    "crowd_groups_nonempty": stats([r["crowd_groups"] for r in images if r["n_people"] > 0]),
    "largest_group_nonempty": stats([r["largest_group"] for r in images if r["n_people"] > 0]),
    "frac_images_multi_person": float(np.mean(npp > 1)),
    "backgrounds": {
        "n_location_codes": len(set(locs)),
        "feature_dim": int(feats.shape[1]), "pca_dim": int(Xp.shape[1]),
        "silhouette_by_k": sil, "k_best_silhouette": k_best, "k_fine": k_fine,
        "ari_kbest_vs_location": float(ari_best), "ari_kfine_vs_location": float(ari_fine),
        "ward_cluster_counts_by_threshold": ward_counts, "ward_k_largest_gap": ward_k_gap,
        "cluster_sizes_fine": dict(Counter(km_fine.tolist())),
        "cluster_location_table_fine": {int(c): dict(Counter(l for l, k in zip(locs, km_fine) if k == c).most_common())
                                        for c in sorted(set(km_fine.tolist()))},
        "dhash_threshold": dup_thr,
        "n_view_groups": len(dup_groups),
        "n_singleton_views": int(sum(1 for v in dup_groups.values() if v == 1)),
        "largest_view_group": int(max(dup_groups.values())),
        "near_duplicate_pairs_cross_split": int(cross_split_pairs),
        "hamming_stats_nearest": stats(np.sort(ham + np.eye(n, dtype=int) * 999, 1)[:, 0]),
    },
}
from scipy.stats import spearmanr

summary["corr_lapvar_tenengrad_spearman"] = float(spearmanr([r["lap_var"] for r in images],
                                                            [r["tenengrad"] for r in images]).correlation)
summary["corr_lapvar_vs_crete_spearman"] = float(spearmanr([r["lap_var"] for r in images],
                                                           [r["crete_blur"] for r in images]).correlation)
summary["corr_rms_vs_lapvar_spearman"] = float(spearmanr([r["rms_contrast"] for r in images],
                                                         [r["lap_var"] for r in images]).correlation)
summary["corr_person_size_vs_cnr_spearman"] = float(spearmanr(P["area_px"], P["cnr"], nan_policy="omit").correlation)
summary["by_location"] = {
    l: {"n_images": int(sum(1 for r in images if r["loc"] == l)),
        "people_mean": float(np.mean([r["n_people"] for r in images if r["loc"] == l])),
        "rms_contrast_median": float(np.median([r["rms_contrast"] for r in images if r["loc"] == l])),
        "lap_var_median": float(np.median([r["lap_var"] for r in images if r["loc"] == l])),
        "person_area_median": float(np.median([p["area_px"] for p in persons if p["loc"] == l]))
        if any(p["loc"] == l for p in persons) else None,
        "empty_frac": float(np.mean([r["n_people"] == 0 for r in images if r["loc"] == l]))}
    for l in sorted(set(locs))}


def jdefault(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, default=jdefault)

# ----------------------------------------------------------------------------- figures
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.3, "font.size": 9})
C1, C2, C3 = "#3366aa", "#cc6633", "#559955"


def pct_lines(ax, x, color="k"):
    for p, ls in zip([5, 50, 95], [":", "--", ":"]):
        v = np.percentile(x, p)
        ax.axvline(v, color=color, ls=ls, lw=1)
        ax.text(v, ax.get_ylim()[1] * 0.95, f" P{p}={v:.3g}", rotation=90, va="top", fontsize=7)


# people per image
fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
cnt = Counter(npp.tolist())
ks = np.arange(0, npp.max() + 1)
ax[0].bar(ks, [cnt.get(k, 0) for k in ks], color=C1)
ax[0].set(xlabel="people in image", ylabel="images", title="People per image (all 1579 images)")
for s, c in zip(SPLITS, [C1, C2, C3]):
    v = np.sort([r["n_people"] for r in images if r["split"] == s])
    ax[1].step(v, np.arange(1, len(v) + 1) / len(v), where="post", label=s, color=c)
ax[1].set(xlabel="people in image", ylabel="ECDF", title="ECDF by split")
ax[1].legend()
fig.tight_layout()
fig.savefig(os.path.join(FIG, "people_per_image.png"))
plt.close(fig)

# person size
fig, ax = plt.subplots(1, 3, figsize=(13, 3.4))
ax[0].hist(P["area_px"], bins=np.logspace(np.log10(max(P["area_px"].min(), 1)), np.log10(P["area_px"].max()), 50),
           color=C1)
ax[0].set_xscale("log")
ax[0].set(xlabel="box area [px², 640x640 frame]", ylabel="persons", title="Person box area")
pct_lines(ax[0], P["area_px"])
ax[1].scatter(P["w"], P["h"], s=3, alpha=0.4, color=C1)
ax[1].set(xlabel="box width [px]", ylabel="box height [px]", title="Box width vs height (640 frame)")
ax[2].hist(P["area_orig_px"], bins=np.logspace(np.log10(P["area_orig_px"].min()), np.log10(P["area_orig_px"].max()),
                                               50), color=C2)
ax[2].set_xscale("log")
ax[2].set(xlabel="est. area [px², original 4000x3000]", ylabel="persons", title="Person area rescaled to source")
pct_lines(ax[2], P["area_orig_px"])
fig.tight_layout()
fig.savefig(os.path.join(FIG, "person_size.png"))
plt.close(fig)

# contrast
rms = np.array([r["rms_contrast"] for r in images])
fig, ax = plt.subplots(1, 3, figsize=(13, 3.4))
ax[0].hist(rms, bins=50, color=C1)
ax[0].set(xlabel="RMS contrast (σ of luminance / 255)", ylabel="images", title="Global RMS contrast")
pct_lines(ax[0], rms)
cnr = P["cnr"][np.isfinite(P["cnr"])]
ax[1].hist(np.clip(cnr, 0, 8), bins=50, color=C2)
ax[1].set(xlabel="person CNR  |μ_box − μ_ring| / σ_ring  (clipped at 8)", ylabel="persons",
          title="Person-vs-surround contrast")
pct_lines(ax[1], cnr)
de = P["deltaE"][np.isfinite(P["deltaE"])]
ax[2].hist(np.clip(de, 0, 80), bins=50, color=C3)
ax[2].set(xlabel="ΔE*ab (box vs ring, clipped at 80)", ylabel="persons", title="Person-vs-surround colour difference")
pct_lines(ax[2], de)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "contrast.png"))
plt.close(fig)

# sharpness
lv = np.array([r["lap_var"] for r in images])
tg = np.array([r["tenengrad"] for r in images])
cb = np.array([r["crete_blur"] for r in images])
fig, ax = plt.subplots(1, 3, figsize=(14, 3.4))
ax[2].hist(cb, bins=50, color=C3)
ax[2].set(xlabel="Crété-Roffet blur (0 sharp → 1 blurred)", ylabel="images", title="Sharpness: re-blur metric")
pct_lines(ax[2], cb)
ax[0].hist(lv, bins=np.logspace(np.log10(lv.min()), np.log10(lv.max()), 50), color=C1)
ax[0].set_xscale("log")
ax[0].set(xlabel="variance of Laplacian (log)", ylabel="images", title="Sharpness: variance of Laplacian")
pct_lines(ax[0], lv)
ax[1].scatter(lv, tg, s=4, alpha=0.5, c=[["train", "valid", "test"].index(r["split"]) for r in images], cmap="viridis")
ax[1].set(xscale="log", yscale="log", xlabel="variance of Laplacian", ylabel="Tenengrad",
          title=f"Laplacian vs Tenengrad (Spearman ρ={summary['corr_lapvar_tenengrad_spearman']:.2f})")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "sharpness.png"))
plt.close(fig)

# crowding
ccr = np.array([r["crowd_ccr"] for r in images if r["n_people"] > 1])
nnn = P["nn_norm"][np.isfinite(P["nn_norm"])]
fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
ax[0].hist(np.clip(nnn, 0, 100), bins=np.logspace(np.log10(max(nnn.min(), 0.1)), 2, 50), color=C1)
ax[0].set_xscale("log")
ax[0].axvline(5, color="r", lw=1)
ax[0].set(xlabel="NN centre distance / person size (log, clipped 100)", ylabel="persons",
          title="Normalised nearest-neighbour distance")
ax[1].hist(ccr, bins=np.linspace(0, 1, 11), color=C2)
ax[1].set(xlabel="close-companion ratio (CCR)", ylabel="images", title="CCR, images with ≥2 people")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "crowding.png"))
plt.close(fig)

# location codes & silhouette
fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
lc = Counter(locs).most_common()
ax[0].bar([l for l, _ in lc], [v for _, v in lc], color=C1)
ax[0].set(ylabel="images", title="Images per HERIDAL location code (filename prefix)")
ax[0].tick_params(axis="x", rotation=60)
ax[1].plot(list(sil), list(sil.values()), "o-", color=C2)
ax[1].axvline(k_best, color="k", ls="--", lw=1)
ax[1].axvline(k_fine, color="r", ls=":", lw=1)
ax[1].set(xlabel="k (KMeans)", ylabel="silhouette", title="Background clustering: silhouette vs k")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "backgrounds.png"))
plt.close(fig)

fig, ax = plt.subplots(figsize=(5, 3.2))
nearest = np.sort(ham + np.eye(n, dtype=int) * 999, 1)[:, 0]
ax.hist(nearest, bins=range(0, 140, 4), color=C1)
ax.axvline(dup_thr, color="r", lw=1)
ax.set(xlabel="Hamming distance to nearest other image (256-bit dHash)", ylabel="images",
       title="Near-duplicate structure")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "dhash_nearest.png"))
plt.close(fig)


# ----------------------------------------------------------------------------- example montages
def montage(recs, title, fname, labels, crop_person=False, tile=256):
    tiles = []
    for r, lab_txt in zip(recs, labels):
        im = cv2.imread(r["path"])
        for a in r["anns"]:
            x, y, w, h = map(int, map(round, a["bbox"]))
            cv2.rectangle(im, (x - 2, y - 2), (x + w + 2, y + h + 2), (0, 0, 255), 2)
        im = cv2.resize(im, (tile, tile), interpolation=cv2.INTER_AREA)
        cv2.rectangle(im, (0, 0), (tile, 18), (0, 0, 0), -1)
        cv2.putText(im, lab_txt, (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(im)
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    grid = np.vstack(rows)
    head = np.zeros((26, grid.shape[1], 3), np.uint8)
    cv2.putText(head, title, (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(FIG, fname), np.vstack([head, grid]), JPG)


def extremes(key, recs, k=4):
    s = sorted(recs, key=lambda r: r[key])
    mid = len(s) // 2
    return s[:k], s[mid - k // 2: mid + k - k // 2], s[-k:]


for key, nice in [("rms_contrast", "RMS contrast"), ("lap_var", "Laplacian var"), ("crete_blur", "Crete blur")]:
    lo, md, hi = extremes(key, images)
    montage(lo + md + hi, f"{nice}: row1 lowest, row2 median, row3 highest", f"examples_{key}.jpg",
            [f"{r['loc']} {nice}={r[key]:.3g}" for r in lo + md + hi])

multi = [r for r in images if r["n_people"] > 1]
s = sorted(multi, key=lambda r: (r["crowd_ccr"], -r["crowd_mean_nn_norm"]))
mid = len(s) // 2
pick = s[:4] + s[mid - 2:mid + 2] + sorted(multi, key=lambda r: (r["crowd_ccr"], r["n_people"]))[-4:]
montage(pick, "Crowding (CCR): row1 lowest, row2 median, row3 highest", "examples_crowding.jpg",
        [f"{r['loc']} n={r['n_people']} CCR={r['crowd_ccr']:.2f}" for r in pick])

empties = [r for r in images if r["n_people"] == 0]
rng = np.random.default_rng(SEED)
pick = [empties[i] for i in rng.choice(len(empties), 12, replace=False)]
montage(pick, "Random sample of images with ZERO annotations", "examples_empty.jpg",
        [f"{r['split']} {r['loc']}" for r in pick], tile=320)

# (per-cluster contact sheets for manual scene-type labelling: heridal_cluster_sheets.py)
# per-location overview (6 random frames per location code) - used for manual scene-type labelling
rows = []
for l in sorted(set(locs)):
    members = [r for r in images if r["loc"] == l]
    idx = rng.choice(len(members), min(6, len(members)), replace=False)
    ts = []
    for i in range(6):
        t = np.zeros((150, 150, 3), np.uint8)
        if i < len(idx):
            t = cv2.resize(cv2.imread(members[idx[i]]["path"]), (150, 150), interpolation=cv2.INTER_AREA)
        ts.append(t)
    lab_t = np.zeros((150, 70, 3), np.uint8)
    cv2.putText(lab_t, l, (5, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(lab_t, f"n={len(members)}", (5, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
    rows.append(np.hstack([lab_t] + ts))
half = (len(rows) + 1) // 2
cv2.imwrite(os.path.join(FIG, "locations_overview_a.jpg"), np.vstack(rows[:half]), JPG)
cv2.imwrite(os.path.join(FIG, "locations_overview_b.jpg"), np.vstack(rows[half:]), JPG)

# cross-split near-duplicate pairs (leakage check), sorted by Hamming distance, sampled across the range
pairs = [(ham[i, j], i, j) for i in range(n) for j in range(i + 1, n)
         if ham[i, j] <= dup_thr and images[i]["split"] != images[j]["split"]]
pairs.sort()
if pairs:
    sel = [pairs[int(q)] for q in np.linspace(0, len(pairs) - 1, min(8, len(pairs)))]
    rows = []
    for hd, i, j in sel:
        a = cv2.resize(cv2.imread(images[i]["path"]), (220, 220), interpolation=cv2.INTER_AREA)
        b = cv2.resize(cv2.imread(images[j]["path"]), (220, 220), interpolation=cv2.INTER_AREA)
        for t, r in ((a, images[i]), (b, images[j])):
            cv2.rectangle(t, (0, 0), (220, 16), (0, 0, 0), -1)
            cv2.putText(t, f"{r['split']} {r['orig'][-12:]} d={hd}", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (255, 255, 255), 1, cv2.LINE_AA)
        rows.append(np.hstack([a, b, np.zeros((220, 10, 3), np.uint8)]))
    grid = np.vstack([np.hstack(rows[k:k + 2]) for k in range(0, len(rows) - len(rows) % 2, 2)])
    cv2.imwrite(os.path.join(FIG, "examples_cross_split_near_duplicates.jpg"), grid, JPG)
summary["backgrounds"]["cross_split_pairs_by_split"] = dict(Counter(
    "-".join(sorted((images[i]["split"], images[j]["split"]))) for _, i, j in pairs))
summary["backgrounds"]["images_with_cross_split_twin"] = int(len({i for _, i, j in pairs} | {j for _, i, j in pairs}))
summary["backgrounds"]["test_images_with_trainval_twin"] = int(len(
    {k for _, i, j in pairs for k in (i, j) if images[k]["split"] == "test"}))
with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, default=jdefault)

# person crops: lowest / median / highest CNR (upscaled so tiny people are visible)
valid_p = [p for p in persons if np.isfinite(p["cnr"])]
sp = sorted(valid_p, key=lambda p: p["cnr"])
m = len(sp) // 2
sel = sp[:6] + sp[m - 3:m + 3] + sp[-6:]
crops = []
for p in sel:
    im = cv2.imread(os.path.join(ROOT, p["split"], p["file"]))
    cx, cy, r = p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, int(max(p["w"], p["h"]) * 2 + 8)
    x0, y0 = int(max(cx - r, 0)), int(max(cy - r, 0))
    crop = im[y0:int(min(cy + r, 640)), x0:int(min(cx + r, 640))]
    crop = cv2.resize(crop, (128, 128), interpolation=cv2.INTER_NEAREST)
    cv2.putText(crop, f"{p['cnr']:.2f}", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
    crops.append(crop)
grid = np.vstack([np.hstack(crops[i:i + 6]) for i in range(0, 18, 6)])
cv2.imwrite(os.path.join(FIG, "examples_person_cnr.png"), grid)

print(json.dumps({k: summary[k] for k in ["n_images", "n_annotations", "people_per_image_all"]}, indent=1))
print("done ->", OUT)
