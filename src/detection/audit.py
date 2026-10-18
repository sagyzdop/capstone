"""Dataset suitability audit for victim detection.

For every prepared YOLO dataset (data/yolo/NAME): person density per image, box sizes and shapes,
where persons sit in the frame, crowding, image quality, person-vs-background contrast,
metadata coverage (HIT-UAV altitude/angle/day-night, C2A disaster type/pose) and
near-duplicate leakage between splits. Also checks WiSARD RGB/IR frame pairing.

Usage:
    python src/detection/audit.py --out station/assets/audit
Writes OUT/audit.json and comparison plots.
"""

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
YOLO = ROOT / "data" / "yolo"
C2A_POSE = ROOT / "data/raw/c2a/extracted/new_dataset3/All labels with Pose information/labels"
POSES = ["bent", "kneeling", "lying", "sitting", "upright"]  # C2A readme order
DATASETS = {"hit-uav": "thermal", "c2a": "rgb", "wisard-ir": "thermal", "wisard-vis": "rgb"}
SIZE_BINS = [0, 8, 12, 16, 24, 32, 64, 1e9]
QUALITY_SIDE = 640  # sharpness is measured after resizing to this long side so datasets compare


def dhash(gray):
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int(np.packbits(bits).view(">u8")[0])


def box_mean(integral, x0, y0, x1, y1):
    s = integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
    return s / max((x1 - x0) * (y1 - y0), 1)


def local_contrast(integral, std, W, H, x0, y0, x1, y1):
    """(mean inside box - mean of a ring one box-size wide around it) / image std."""
    bw, bh = x1 - x0, y1 - y0
    rx0, ry0, rx1, ry1 = max(0, x0 - bw), max(0, y0 - bh), min(W, x1 + bw), min(H, y1 + bh)
    inner = box_mean(integral, x0, y0, x1, y1)
    outer_sum = box_mean(integral, rx0, ry0, rx1, ry1) * (rx1 - rx0) * (ry1 - ry0)
    inner_sum = inner * bw * bh
    ring = (outer_sum - inner_sum) / max((rx1 - rx0) * (ry1 - ry0) - bw * bh, 1)
    return (inner - ring) / max(std, 1e-6)


def iou_any(boxes):
    """Per box: does it overlap any other box (IoU > 0)?"""
    b = np.array(boxes)
    if len(b) < 2:
        return np.zeros(len(b), bool)
    x0 = np.maximum(b[:, None, 0], b[None, :, 0])
    y0 = np.maximum(b[:, None, 1], b[None, :, 1])
    x1 = np.minimum(b[:, None, 2], b[None, :, 2])
    y1 = np.minimum(b[:, None, 3], b[None, :, 3])
    inter = (x1 > x0) & (y1 > y0)
    np.fill_diagonal(inter, False)
    return inter.any(1)


def nn_gap(boxes):
    """Per box: distance to nearest other person centre, in units of this box's size."""
    b = np.array(boxes, float)
    if len(b) < 2:
        return np.full(len(b), np.inf)
    c = np.stack([(b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2], 1)
    d = np.linalg.norm(c[:, None] - c[None], axis=2)
    np.fill_diagonal(d, np.inf)
    size = np.sqrt((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]))
    return d.min(1) / np.maximum(size, 1)


def meta(name, stem):
    if name == "hit-uav":  # scenario_altitude_angle_weather_id; scenario/weather order from tools/info/*.txt
        s, alt, ang, wx, _ = stem.split("_")
        return {"time": ["day", "night"][int(s)], "altitude_m": int(alt), "angle_deg": int(ang),
                "weather": ["sunny", "rainy"][int(wx)]}
    if name == "c2a":  # e.g. collapsed_building_image0001_3: AIDER scene + paste variant
        scene = stem.rsplit("_", 1)[0]
        return {"disaster": re.sub(r"_image\d+$", "", scene), "scene": scene}
    return {}


def poses(stem):
    f = C2A_POSE / f"{stem}.txt"
    if not f.exists():
        return []
    return [POSES[int(float(r.split()[5]))] for r in f.read_text().splitlines() if len(r.split()) >= 6]


def audit(name):
    imgs, persons = [], []
    for split_dir in sorted((YOLO / name / "images").iterdir()):
        split = split_dir.name
        for p in sorted(split_dir.iterdir()):
            img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if img is None:
                continue
            gray_only = img.ndim == 2 or bool(np.array_equal(img[..., 0], img[..., 1]) and np.array_equal(img[..., 1], img[..., 2]))
            gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            H, W = gray.shape
            k = QUALITY_SIDE / max(W, H)
            g_small = cv2.resize(gray, (round(W * k), round(H * k)), interpolation=cv2.INTER_AREA)
            std = float(gray.std())
            integral = cv2.integral(gray.astype(np.float64))
            lbl = YOLO / name / "labels" / split / (p.stem + ".txt")
            rows = [list(map(float, r.split()[1:5])) for r in lbl.read_text().splitlines() if r.strip()] if lbl.exists() else []
            boxes = []  # integer pixel grid, for contrast / overlap; sizes below use exact label values
            for xc, yc, bw, bh in rows:
                x0, y0 = max(0, int((xc - bw / 2) * W)), max(0, int((yc - bh / 2) * H))
                x1, y1 = min(W, max(x0 + 1, int(round((xc + bw / 2) * W)))), min(H, max(y0 + 1, int(round((yc + bh / 2) * H))))
                boxes.append((x0, y0, x1, y1))
            pose_list = poses(p.stem) if name == "c2a" else []
            overlap, gap = iou_any(boxes), nn_gap(boxes)
            m = meta(name, p.stem)
            for i, (x0, y0, x1, y1) in enumerate(boxes):
                xc, yc, bw, bh = rows[i]
                w, h = bw * W, bh * H
                persons.append({
                    "split": split, "size": math.sqrt(w * h), "w": w, "h": h, "long_side": max(W, H),
                    "cx": xc, "cy": yc, "stem": p.stem,
                    "edge": x0 <= 1 or y0 <= 1 or x1 >= W - 1 or y1 >= H - 1,
                    "contrast": float(local_contrast(integral, std, W, H, x0, y0, x1, y1)),
                    "overlap": bool(overlap[i]), "nn_gap": float(gap[i]),
                    "pose": pose_list[i] if i < len(pose_list) else None, **m,
                })
            imgs.append({
                "split": split, "stem": p.stem, "W": W, "H": H, "n": len(boxes), "gray": gray_only,
                "brightness": float(gray.mean()), "contrast_rms": std,
                "dyn_range": float(np.percentile(gray, 99) - np.percentile(gray, 1)),
                "sharpness": float(cv2.Laplacian(g_small, cv2.CV_64F).var()),
                "hash": dhash(gray), **m,
            })
    return imgs, persons


def pct(a, qs=(5, 25, 50, 75, 95)):
    return [round(float(v), 2) for v in np.percentile(a, qs)] if len(a) else []


def near_dups(imgs, max_bits=4):
    """Share of each non-train split's images with a train image whose dHash differs by <= max_bits."""
    by = defaultdict(list)
    for im in imgs:
        by[im["split"]].append(im["hash"])
    if "train" not in by:
        return {}
    train = np.array(by["train"], dtype=np.uint64)
    out = {}
    for split, hs in by.items():
        if split == "train":
            continue
        hit = 0
        for h in hs:
            hit += int((np.bitwise_count(train ^ np.uint64(h)) <= max_bits).any())
        out[split] = round(hit / len(hs), 3)
    return out


def summarize(name, imgs, persons):
    n = np.array([im["n"] for im in imgs])
    size = np.array([p["size"] for p in persons])
    contrast = np.array([p["contrast"] for p in persons])
    aspect = np.array([p["w"] / max(p["h"], 1) for p in persons])
    gap = np.array([p["nn_gap"] for p in persons])
    s = {
        "modality": DATASETS[name],
        "images": len(imgs),
        "splits": dict(Counter(im["split"] for im in imgs)),
        "persons": len(persons),
        "negatives_pct": round(float((n == 0).mean() * 100), 1),
        "persons_per_image": {"mean": round(float(n.mean()), 2), "pcts": pct(n), "max": int(n.max())},
        "density_buckets_pct": {k: round(float(v * 100), 1) for k, v in {
            "0": (n == 0).mean(), "1": (n == 1).mean(), "2-5": ((n >= 2) & (n <= 5)).mean(),
            "6-20": ((n >= 6) & (n <= 20)).mean(), ">20": (n > 20).mean()}.items()},
        "resolutions_top": Counter(f"{im['W']}x{im['H']}" for im in imgs).most_common(5),
        "grayscale_pct": round(float(np.mean([im["gray"] for im in imgs]) * 100), 1),
        "size_px_pcts": pct(size),
        "size_bins_pct": {f"{SIZE_BINS[i]:g}-{SIZE_BINS[i + 1]:g}": round(float(((size >= SIZE_BINS[i]) & (size < SIZE_BINS[i + 1])).mean() * 100), 1)
                          for i in range(len(SIZE_BINS) - 1)},
        "rel_area_pct_median": round(float(np.median([p["w"] * p["h"] for p in persons]) /
                                     np.median([im["W"] * im["H"] for im in imgs]) * 100), 4),
        "aspect_wh_pcts": pct(aspect),
        "elongated_pct": round(float(((aspect > 1.5) | (aspect < 1 / 1.5)).mean() * 100), 1),
        "edge_truncated_pct": round(float(np.mean([p["edge"] for p in persons]) * 100), 1),
        "overlapping_pct": round(float(np.mean([p["overlap"] for p in persons]) * 100), 1),
        "nn_gap_lt2_pct": round(float((gap < 2).mean() * 100), 1),
        "nn_gap_pcts": pct(gap[np.isfinite(gap)]),
        "contrast_pcts": pct(contrast),
        "low_contrast_pct": round(float((np.abs(contrast) < 0.5).mean() * 100), 1),
        "quality": {k: pct([im[k] for im in imgs]) for k in ["brightness", "contrast_rms", "dyn_range", "sharpness"]},
        "near_dup_with_train": near_dups(imgs),
    }
    if name == "hit-uav":
        for key in ["time", "altitude_m", "angle_deg", "weather"]:
            groups = defaultdict(list)
            for p in persons:
                groups[p[key]].append(p)
            s[f"by_{key}"] = {
                str(k): {"images": sum(im[key] == k for im in imgs), "persons": len(v),
                         "median_px": round(float(np.median([p["size"] for p in v])), 1),
                         "median_contrast": round(float(np.median([p["contrast"] for p in v])), 2),
                         "brightness_median": round(float(np.median([im["brightness"] for im in imgs if im[key] == k])), 1)}
                for k, v in sorted(groups.items())}
        s["altitude_x_angle_images"] = {f"{a}m/{g}deg": c for (a, g), c in sorted(Counter((im["altitude_m"], im["angle_deg"]) for im in imgs).items())}
    if name == "c2a":
        s["by_disaster"] = {k: {"images": sum(im["disaster"] == k for im in imgs),
                                "persons": sum(p["disaster"] == k for p in persons)}
                            for k in sorted({im["disaster"] for im in imgs})}
        pc = Counter(p["pose"] for p in persons)
        s["pose_pct"] = {k: round(pc[k] / len(persons) * 100, 1) for k in POSES + [None] if pc[k]}
        s["pose_median_px"] = {k: round(float(np.median([p["size"] for p in persons if p["pose"] == k])), 1) for k in POSES if pc[k]}
        scenes = defaultdict(set)
        for im in imgs:
            scenes[im["split"]].add(im["scene"])
        s["scenes_per_split"] = {k: len(v) for k, v in scenes.items()}
        s["scenes_shared_with_train_pct"] = {k: round(len(v & scenes["train"]) / len(v) * 100, 1)
                                             for k, v in scenes.items() if k != "train"}
    return s


def wisard_pairing():
    """WiSARD IR and VIS frames share an index. Fit IR-normalised = a * VIS-normalised + b from frames
    where both have the same person count (persons paired by x order) to measure the footprint overlap."""
    def load(name, split="val"):
        out = {}
        for f in (YOLO / name / "labels" / split).glob("*.txt"):
            idx = int(f.stem.rsplit("_", 1)[1])
            out[idx] = sorted(tuple(map(float, r.split()[1:5])) for r in f.read_text().splitlines() if r.strip())
        return out
    ir, vis = load("wisard-ir"), load("wisard-vis")
    common = sorted(set(ir) & set(vis))
    same = [i for i in common if len(ir[i]) == len(vis[i]) and ir[i]]
    xs_v, xs_i, ys_v, ys_i, sz_ratio = [], [], [], [], []
    for i in same:
        for a, b in zip(vis[i], ir[i]):
            xs_v.append(a[0]); xs_i.append(b[0]); ys_v.append(a[1]); ys_i.append(b[1])
            sz_ratio.append(math.sqrt(a[2] * 3840 * a[3] * 2160) / max(math.sqrt(b[2] * 640 * b[3] * 512), 1e-6))
    ax, bx = np.polyfit(xs_v, xs_i, 1)
    ay, by = np.polyfit(ys_v, ys_i, 1)
    res = np.hypot(np.array(xs_i) - (ax * np.array(xs_v) + bx), np.array(ys_i) - (ay * np.array(ys_v) + by))
    # IR frame [0,1] maps back to this VIS-normalised window
    win = [(-bx) / ax, (1 - bx) / ax, (-by) / ay, (1 - by) / ay]
    return {
        "frames_common": len(common), "frames_same_count": len(same),
        "fit_x": [round(ax, 3), round(bx, 3)], "fit_y": [round(ay, 3), round(by, 3)],
        "residual_ir_norm_median": round(float(np.median(res)), 4),
        "residual_ir_px_median": round(float(np.median(res) * 640), 1),
        "ir_window_in_vis_norm": [round(v, 3) for v in win],
        "ir_footprint_share_of_vis_pct": round(float((win[1] - win[0]) * (win[3] - win[2]) * 100), 1),
        "vis_over_ir_person_px_ratio_median": round(float(np.median(sz_ratio)), 2),
    }


# --- plots -------------------------------------------------------------------------------------
# Colours follow the dataset, never its rank (validated categorical palette, light surface).
COLOR = {"hit-uav": "#2a78d6", "c2a": "#eb6834", "wisard-ir": "#1baf7a", "wisard-vis": "#eda100"}
TIME_COLOR = {"day": "#eb6834", "night": "#2a78d6"}
ORDINAL_BLUE = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # light -> dark
BOX = "#eda100"  # label boxes drawn on images
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "lines.linewidth": 2, "legend.frameon": False,
    "axes.titlesize": 11, "axes.titlelocation": "left", "font.size": 9,
})


def save(fig, out, name):
    fig.tight_layout()
    fig.savefig(out / name, dpi=130)
    plt.close(fig)


def draw_boxes(ax, lbl, W, H, lw=1.0):
    for r in lbl.read_text().splitlines() if lbl.exists() else []:
        _, xc, yc, bw, bh = map(float, r.split()[:5])
        ax.add_patch(plt.Rectangle(((xc - bw / 2) * W, (yc - bh / 2) * H), bw * W, bh * H, fill=False, ec=BOX, lw=lw))


def show(ax, name, split, stem, title=None):
    img = next((YOLO / name / "images" / split).glob(stem + ".*"))
    im = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    ax.imshow(im)
    draw_boxes(ax, YOLO / name / "labels" / split / (stem + ".txt"), im.shape[1], im.shape[0])
    ax.set_title(title or stem, fontsize=8)
    ax.axis("off")
    return im


def plots(all_p, all_i, out):
    names = list(all_p)

    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for n in names:
        s = np.array([p["size"] for p in all_p[n]])
        h, e = np.histogram(s, bins=np.arange(0, 110, 2), density=True)
        ax.step(e[:-1], h, where="post", color=COLOR[n], label=f"{n} (median {np.median(s):.0f} px)")
    ax.axvline(8, color=MUTED, ls="--", lw=1)
    ax.text(8.5, ax.get_ylim()[1] * 0.95, "8 px", color=MUTED, fontsize=8)
    ax.set(xlabel="person size, px (√ box area, native resolution)", ylabel="share of persons", title="Person size per dataset")
    ax.legend()
    save(fig, out, "size_compare.png")

    fig, axes = plt.subplots(1, len(names), figsize=(3.4 * len(names), 3), sharey=True)
    for ax, n in zip(axes, names):
        k = np.array([im["n"] for im in all_i[n]])
        edges = np.arange(0, min(int(k.max()), 80) + 2) - 0.5
        ax.hist(np.minimum(k, 80), bins=edges, weights=np.full(len(k), 100 / len(k)), color=COLOR[n], rwidth=0.85)
        ax.set(title=f"{n}  (median {np.median(k):.0f})", xlabel="persons in image")
    axes[0].set_ylabel("% of images")
    save(fig, out, "density_compare.png")

    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for n in names:
        c = np.clip([p["contrast"] for p in all_p[n]], -4, 6)
        h, e = np.histogram(c, bins=np.linspace(-4, 6, 61), density=True)
        ax.step(e[:-1], h, where="post", color=COLOR[n], label=f"{n} (median {np.median(c):.2f})")
    ax.axvspan(-0.5, 0.5, color=GRID, alpha=0.6, lw=0)
    ax.text(0, ax.get_ylim()[1] * 0.95, "low contrast", ha="center", color=MUTED, fontsize=8)
    ax.set(xlabel="person vs surrounding ring, grey-level contrast (image std units)", ylabel="share of persons",
           title="How much persons stand out from their surroundings")
    ax.legend()
    save(fig, out, "contrast_compare.png")

    fig, axes = plt.subplots(1, len(names), figsize=(3.4 * len(names), 3.2))
    for ax, n in zip(axes, names):
        hh, _, _ = np.histogram2d([p["cy"] for p in all_p[n]], [p["cx"] for p in all_p[n]], bins=20, range=[[0, 1], [0, 1]])
        im = ax.imshow(hh / hh.sum() * 100, cmap="Blues", extent=[0, 1, 1, 0], aspect="equal")
        ax.set(title=n, xlabel="x (frame width)")
        ax.grid(False)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03, label="% of persons")
    axes[0].set_ylabel("y (frame height)")
    save(fig, out, "centre_heatmaps.png")

    fig, axes = plt.subplots(1, 4, figsize=(13, 3.2))
    for ax, (key, label) in zip(axes, [("brightness", "mean brightness (0-255)"), ("contrast_rms", "RMS contrast (grey std)"),
                                       ("dyn_range", "dynamic range p99-p1"), ("sharpness", "sharpness (Laplacian var, log)")]):
        data = [[im[key] for im in all_i[n]] for n in names]
        b = ax.boxplot(data, showfliers=False, patch_artist=True, widths=0.5, medianprops={"color": INK})
        for patch, n in zip(b["boxes"], names):
            patch.set(facecolor=COLOR[n], alpha=0.85, edgecolor=SURFACE)
        ax.set_xticks(range(1, len(names) + 1), names, rotation=20)
        ax.set_title(label)
        if key == "sharpness":
            ax.set_yscale("log")
    save(fig, out, "quality_compare.png")

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for n in names:
        a = np.log2([max(p["w"], 0.5) / max(p["h"], 0.5) for p in all_p[n]])
        h, e = np.histogram(np.clip(a, -3, 3), bins=np.linspace(-3, 3, 25), density=True)
        axes[0].step(e[:-1], h, where="post", color=COLOR[n], label=n)
        g = np.array([p["nn_gap"] for p in all_p[n]])
        g = g[np.isfinite(g)]
        h, e = np.histogram(np.clip(g, 0, 15), bins=np.linspace(0, 15, 46), density=True)
        axes[1].step(e[:-1], h, where="post", color=COLOR[n], label=f"{n} ({(g < 2).mean() * 100:.0f}% < 2)")
    axes[0].set_xticks([-2, -1, 0, 1, 2], ["1:4", "1:2", "1:1", "2:1", "4:1"])
    axes[0].set(xlabel="box width : height", ylabel="share of persons", title="Box shape")
    axes[1].axvline(2, color=MUTED, ls="--", lw=1)
    axes[1].set(xlabel="distance to nearest other person, body sizes (clipped at 15)", title="Crowding")
    axes[0].legend(); axes[1].legend()
    save(fig, out, "shape_crowding.png")

    if "hit-uav" in all_p:
        p, ims = all_p["hit-uav"], all_i["hit-uav"]
        alts, angs = sorted({x["altitude_m"] for x in p}), sorted({x["angle_deg"] for x in p})
        fig, axes = plt.subplots(1, 3, figsize=(14, 3.6))
        axes[0].boxplot([[x["size"] for x in p if x["altitude_m"] == a] for a in alts], showfliers=False,
                        patch_artist=True, boxprops={"facecolor": COLOR["hit-uav"], "edgecolor": SURFACE}, medianprops={"color": INK})
        axes[0].set_xticks(range(1, len(alts) + 1), alts)
        axes[0].set(xlabel="altitude, m", ylabel="person px", title="Size vs altitude")
        axes[1].boxplot([[x["size"] for x in p if x["angle_deg"] == a] for a in angs], showfliers=False,
                        patch_artist=True, boxprops={"facecolor": COLOR["hit-uav"], "edgecolor": SURFACE}, medianprops={"color": INK})
        axes[1].set_xticks(range(1, len(angs) + 1), angs)
        axes[1].set(xlabel="camera angle, deg (90 = straight down)", title="Size vs camera angle")
        for t in ["day", "night"]:
            c = np.clip([x["contrast"] for x in p if x["time"] == t], -3, 6)
            h, e = np.histogram(c, bins=np.linspace(-3, 6, 55), density=True)
            axes[2].step(e[:-1], h, where="post", color=TIME_COLOR[t], label=f"{t} (median {np.median(c):.2f})")
        axes[2].axvspan(-0.5, 0.5, color=GRID, alpha=0.6, lw=0)
        axes[2].set(xlabel="person contrast (std units)", title="Contrast: day vs night"); axes[2].legend()
        save(fig, out, "hituav_altitude_daynight.png")

        grid = np.zeros((len(alts), len(angs)))
        for im in ims:
            grid[alts.index(im["altitude_m"]), angs.index(im["angle_deg"])] += 1
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        hm = ax.imshow(grid, cmap="Blues", aspect="auto")
        for i in range(len(alts)):
            for j in range(len(angs)):
                ax.text(j, i, int(grid[i, j]), ha="center", va="center", fontsize=8, color=SURFACE if grid[i, j] > grid.max() * 0.6 else INK)
        ax.set_xticks(range(len(angs)), angs); ax.set_yticks(range(len(alts)), alts)
        ax.set(xlabel="camera angle, deg", ylabel="altitude, m", title="HIT-UAV images per altitude × angle")
        ax.grid(False)
        fig.colorbar(hm, ax=ax, label="images")
        save(fig, out, "hituav_alt_angle_grid.png")

        rng = np.random.default_rng(1)
        fig, axes = plt.subplots(2, 3, figsize=(12, 6.6))
        for row, t in zip(axes, ["day", "night"]):
            pool = [im for im in ims if im["time"] == t and im["n"] >= 3]
            for ax in row:
                im = pool[rng.integers(len(pool))]
                show(ax, "hit-uav", im["split"], im["stem"], f"{t}, {im['altitude_m']} m, {im['angle_deg']}°, {im['n']} persons")
        save(fig, out, "hituav_samples.png")

    if "c2a" in all_p:
        p, ims = all_p["c2a"], all_i["c2a"]
        pc = Counter(x["pose"] for x in p if x["pose"])
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
        axes[0].bar(POSES, [pc[k] / sum(pc.values()) * 100 for k in POSES], color=COLOR["c2a"], width=0.6)
        for i, k in enumerate(POSES):
            axes[0].text(i, pc[k] / sum(pc.values()) * 100 + 0.5, f"{pc[k] / sum(pc.values()) * 100:.0f}%", ha="center", fontsize=8, color=INK2)
        axes[0].set(ylabel="% of persons", title="C2A pose share")
        axes[1].boxplot([[x["size"] for x in p if x["pose"] == k] for k in POSES], showfliers=False,
                        patch_artist=True, boxprops={"facecolor": COLOR["c2a"], "edgecolor": SURFACE}, medianprops={"color": INK})
        axes[1].set_xticks(range(1, len(POSES) + 1), POSES)
        axes[1].set(ylabel="person px", title="C2A size by pose")
        save(fig, out, "c2a_pose_size.png")

        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        ls = np.array([x["long_side"] for x in p]); sz = np.array([x["size"] for x in p])
        hb = axes[0].hexbin(ls, sz, gridsize=45, xscale="log", bins="log", cmap="Blues", mincnt=1)
        axes[0].set(xlabel="image long side, px (log)", ylabel="person px", title="Person px does not follow image scale")
        fig.colorbar(hb, ax=axes[0], label="persons (log)")
        axes[0].grid(False)
        long_sides = [max(im["W"], im["H"]) for im in ims]
        axes[1].hist(long_sides, bins=np.logspace(np.log10(min(long_sides)), np.log10(max(long_sides)), 40),
                     weights=np.full(len(long_sides), 100 / len(long_sides)), color=COLOR["c2a"], rwidth=0.85)
        axes[1].axvline(640, color=MUTED, ls="--", lw=1)
        axes[1].text(660, axes[1].get_ylim()[1] * 0.9, "640", color=MUTED, fontsize=8)
        axes[1].set_xscale("log")
        axes[1].set(xlabel="image long side, px (log)", ylabel="% of images",
                    title=f"C2A resolution: {np.mean(np.array(long_sides) < 640) * 100:.0f}% below 640 px")
        save(fig, out, "c2a_scale.png")

        dis = sorted({im["disaster"] for im in ims})
        rng = np.random.default_rng(2)
        fig, axes = plt.subplots(1, len(dis), figsize=(4 * len(dis), 3.6))
        for ax, d in zip(axes, dis):
            pool = [im for im in ims if im["disaster"] == d and max(im["W"], im["H"]) >= 500]
            im = pool[rng.integers(len(pool))]
            show(ax, "c2a", im["split"], im["stem"], f"{d}: {im['n']} persons, {im['W']}×{im['H']}")
        save(fig, out, "c2a_samples.png")

        by_scene = defaultdict(dict)
        for im in ims:
            by_scene[im["scene"]][im["split"]] = im
        leak = next(v for _, v in sorted(by_scene.items()) if "train" in v and "test" in v and max(v["train"]["W"], v["train"]["H"]) >= 500)
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
        for ax, s in zip(axes, ["train", "test"]):
            show(ax, "c2a", s, leak[s]["stem"], f"{s}: {leak[s]['stem']}")
        save(fig, out, "c2a_leak_example.png")


def wisard_figures(pairing, out):
    ir_dir, vis_dir = YOLO / "wisard-ir" / "images" / "val", YOLO / "wisard-vis" / "images" / "val"
    stem = sorted(p.stem for p in vis_dir.iterdir())[100]
    idx = stem.rsplit("_", 1)[1]
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.9), gridspec_kw={"width_ratios": [1.6, 1]})
    vis = show(axes[0], "wisard-vis", "val", stem, "RGB 3840×2160 (IR footprint dashed)")
    x0, x1, y0, y1 = pairing["ir_window_in_vis_norm"]
    H, W = vis.shape[:2]
    axes[0].add_patch(plt.Rectangle((x0 * W, y0 * H), (x1 - x0) * W, (y1 - y0) * H, fill=False, ec=COLOR["wisard-ir"], lw=2, ls="--"))
    ir_stem = next(p.stem for p in ir_dir.iterdir() if p.stem.endswith(idx))
    show(axes[1], "wisard-ir", "val", ir_stem, "IR 640×512, same frame index")
    save(fig, out, "wisard_footprint.png")


def person_crops(names, out, n=12, seed=0):
    """Random person crops at native resolution (box + 1 box-size margin), one row per dataset."""
    rng = np.random.default_rng(seed)
    fig, axes = plt.subplots(len(names), n, figsize=(n * 1.1, len(names) * 1.3))
    for row, name in zip(axes, names):
        lbls = [f for f in sorted((YOLO / name / "labels").rglob("*.txt")) if f.stat().st_size]
        for ax in row:
            f = lbls[rng.integers(len(lbls))]
            rows = [r.split() for r in f.read_text().splitlines() if r.strip()]
            _, xc, yc, bw, bh = map(float, rows[rng.integers(len(rows))])
            img = next((YOLO / name / "images" / f.parent.name).glob(f.stem + ".*"))
            im = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
            H, W = im.shape[:2]
            x0, y0, x1, y1 = (xc - bw * 1.5) * W, (yc - bh * 1.5) * H, (xc + bw * 1.5) * W, (yc + bh * 1.5) * H
            ax.imshow(im[max(0, int(y0)):int(y1) + 1, max(0, int(x0)):int(x1) + 1], interpolation="nearest")
            ax.set_title(f"{math.sqrt(bw * W * bh * H):.0f}px", fontsize=7, loc="center")
            ax.axis("off")
        row[0].text(-0.15, 0.5, name, transform=row[0].transAxes, ha="right", va="center", fontsize=9)
    save(fig, out, "person_crops.png")


def eval_plots(out):
    """Charts from eval_sizes.py results in OUT/eval/ (inference only)."""
    ev = out / "eval"
    if not (ev / "hituav-model_hituav-test.json").exists():
        return
    runs = json.loads((ev / "hituav-model_hituav-test.json").read_text())
    bins = ["8-12", "12-16", "16-24", "24-32"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for r, c in zip(runs, ORDINAL_BLUE):
        y = [r["recall_by_size"][b]["recall"] for b in bins]
        axes[0].plot(bins, y, "-o", ms=5, color=c, label=f"imgsz {r['imgsz']}")
    axes[0].set(xlabel="person size bin, native px", ylabel="recall (conf 0.25, IoU 0.5)", ylim=(0, 1),
                title="HIT-UAV test: recall per size vs input size")
    axes[0].legend(loc="lower right")
    xs = [r["ms_per_image_median"] for r in runs]; ys = [r["ap"] for r in runs]
    axes[1].plot(xs, ys, "-", color=COLOR["hit-uav"], lw=1.5)
    for r, c in zip(runs, ORDINAL_BLUE):
        axes[1].plot(r["ms_per_image_median"], r["ap"], "o", ms=8, color=c)
        axes[1].annotate(f"{r['imgsz']}", (r["ms_per_image_median"], r["ap"]), xytext=(6, -3), textcoords="offset points", fontsize=8, color=INK2)
    axes[1].set(xlabel="ms per image (Apple M4, YOLO11n)", ylabel="AP50", ylim=(0.5, 1), title="Accuracy vs speed")
    save(fig, out, "eval_hituav_imgsz.png")

    vis = json.loads((ev / "coco-model_wisard-vis.json").read_text())
    labels = [f"tiles {r['tile']}" if r["tile"] else f"resize {r['imgsz']}" for r in vis]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.bar(labels, [r["ap"] for r in vis], color=COLOR["wisard-vis"], width=0.55)
    for i, r in enumerate(vis):
        ax.text(i, r["ap"] + 0.01, f"AP50 {r['ap']:.2f}\n{r['ms_per_image_median']:.0f} ms", ha="center", fontsize=8, color=INK2)
    ax.set(ylabel="AP50", ylim=(0, 0.45), title="WiSARD 4K RGB: resize vs tiling (COCO YOLO11n, zero-shot)")
    save(fig, out, "eval_wisard_vis_tiling.png")

    gap = [("HIT-UAV model\n→ HIT-UAV test", "hituav-model_hituav-test.json", 640, COLOR["hit-uav"]),
           ("HIT-UAV model\n→ WiSARD IR", "hituav-model_wisard-ir.json", 640, COLOR["wisard-ir"]),
           ("COCO model\n→ HIT-UAV test", "coco-model_hituav-test.json", 640, COLOR["hit-uav"]),
           ("COCO model\n→ WiSARD IR", "coco-model_wisard-ir.json", 640, COLOR["wisard-ir"]),
           ("COCO model\n→ C2A test", "coco-model_c2a-test.json", 640, COLOR["c2a"])]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for i, (lab, f, sz, c) in enumerate(gap):
        v = next(r["ap"] for r in json.loads((ev / f).read_text()) if r["imgsz"] == sz and not r["tile"])
        ax.bar(i, v, color=c, width=0.55)
        ax.text(i, v + 0.015, f"{v:.2f}", ha="center", fontsize=8, color=INK2)
    ax.set_xticks(range(len(gap)), [g[0] for g in gap], fontsize=8)
    ax.set(ylabel="AP50 at imgsz 640", ylim=(0, 1), title="Domain gap: same model, different data")
    save(fig, out, "eval_domain_gap.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--datasets", nargs="+", default=list(DATASETS))
    ap.add_argument("--threads", type=int, default=3)
    args = ap.parse_args()
    cv2.setNumThreads(args.threads)
    args.out.mkdir(parents=True, exist_ok=True)
    report, all_p, all_i = {}, {}, {}
    for n in args.datasets:
        print(f"auditing {n} ...", flush=True)
        imgs, persons = audit(n)
        all_i[n], all_p[n] = imgs, persons
        report[n] = summarize(n, imgs, persons)
    if {"wisard-ir", "wisard-vis"} <= set(args.datasets):
        report["wisard_pairing"] = wisard_pairing()
        wisard_figures(report["wisard_pairing"], args.out)
    (args.out / "audit.json").write_text(json.dumps(report, indent=1))
    plots(all_p, all_i, args.out)
    person_crops(args.datasets, args.out)
    eval_plots(args.out)


if __name__ == "__main__":
    g = np.zeros((10, 10)); g[4:6, 4:6] = 10
    I = cv2.integral(g)
    assert box_mean(I, 4, 4, 6, 6) == 10 and local_contrast(I, g.std(), 10, 10, 4, 4, 6, 6) > 0
    assert iou_any([(0, 0, 2, 2), (1, 1, 3, 3), (5, 5, 6, 6)]).tolist() == [True, True, False]
    assert meta("hit-uav", "1_130_90_0_04077") == {"time": "night", "altitude_m": 130, "angle_deg": 90, "weather": "sunny"}
    assert meta("c2a", "collapsed_building_image0001_3")["disaster"] == "collapsed_building"
    main()
