"""Count distinct backgrounds per dataset by clustering ImageNet ResNet-50 embeddings.

Images are first grouped by what the metadata already tells us is one background
(C2A: AIDER source scene; HIT-UAV: recording clip = run of consecutive frame ids with the same
day/night, altitude and angle; WiSARD: one frame each), group embeddings are averaged, then
greedy leader clustering (cosine to a cluster's first member) merges groups that look like the same place.

Usage:
    python src/detection/backgrounds.py --out research/datasets/assets/audit
Writes OUT/backgrounds.json and OUT/backgrounds_<name>.png (one tile per cluster, to eyeball).
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torchvision

ROOT = Path(__file__).resolve().parents[2]
YOLO = ROOT / "data" / "yolo"
THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5]  # cosine distance at which two groups count as one place


def groups(name):
    """{group key: [image paths]} using metadata only."""
    paths = sorted(p for p in (YOLO / name / "images").glob("*/*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if name == "c2a":  # collapsed_building_image0001_3 -> collapsed_building_image0001
        g = defaultdict(list)
        for p in paths:
            g[p.stem.rsplit("_", 1)[0]].append(p)
        return dict(g)
    if name == "hit-uav":  # day_alt_angle_weather_id; clip breaks on a key change or an id jump > 60
        rows = sorted((int(p.stem.split("_")[4]), tuple(p.stem.split("_")[:3]), p) for p in paths)
        g, prev = [], None
        for i, key, p in rows:
            if prev and key == prev[1] and i - prev[0] <= 60:
                g[-1].append(p)
            else:
                g.append([p])
            prev = (i, key)
        return {f"clip{k:03d}_{'_'.join(v[0].stem.split('_')[:3])}": v for k, v in enumerate(g)}
    return {p.stem: [p] for p in paths}


@torch.no_grad()
def embed(paths, model, device, batch=32):
    mean, std = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1), torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    out = []
    for i in range(0, len(paths), batch):
        ims = []
        for p in paths[i:i + batch]:
            im = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
            ims.append(cv2.resize(im, (224, 224), interpolation=cv2.INTER_AREA))
        x = (torch.from_numpy(np.stack(ims)).permute(0, 3, 1, 2).float() / 255 - mean) / std
        f = model(x.to(device)).cpu().numpy()
        out.append(f / np.linalg.norm(f, axis=1, keepdims=True))
    return np.concatenate(out)


def cluster(emb, t):
    """Greedy leader clustering: join the nearest leader within cosine distance t, else become a leader."""
    # ponytail: order-dependent; swap for agglomerative clustering once scipy/sklearn import on this machine
    leaders, labels = [], []
    for v in emb:
        d = 1 - np.array([emb[i] @ v for i in leaders]) if leaders else np.array([])
        if len(d) and d.min() <= t:
            labels.append(int(d.argmin()))
        else:
            leaders.append(len(labels))
            labels.append(len(leaders) - 1)
    return np.array(labels)


def montage(name, keys, g, labels, out, max_tiles=60):
    reps = {}
    for k, lab in zip(keys, labels):
        reps.setdefault(lab, g[k][len(g[k]) // 2])
    tiles = list(reps.values())[:max_tiles]
    cols = 10
    rows = (len(tiles) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 1.6, rows * 1.4))
    for ax in np.atleast_1d(axes).ravel():
        ax.axis("off")
    for ax, p in zip(np.atleast_1d(axes).ravel(), tiles):
        ax.imshow(cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB))
    fig.suptitle(f"{name}: one frame per background cluster ({len(reps)} clusters, first {len(tiles)} shown)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"backgrounds_{name}.png", dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--datasets", nargs="+", default=["hit-uav", "c2a", "wisard-ir", "wisard-vis"])
    ap.add_argument("--threshold", type=float, default=0.3, help="threshold used for the montage and headline count")
    ap.add_argument("--threads", type=int, default=3)
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = torchvision.models.resnet50(weights="IMAGENET1K_V2")
    model.fc = torch.nn.Identity()
    model.eval().to(device)
    report = json.loads((args.out / "backgrounds.json").read_text()) if (args.out / "backgrounds.json").exists() else {}
    for name in args.datasets:
        print(f"backgrounds {name} ...", flush=True)
        g = groups(name)
        keys = list(g)
        flat = [p for k in keys for p in g[k]]
        e = embed(flat, model, device)
        idx = np.cumsum([0] + [len(g[k]) for k in keys])
        ge = np.stack([e[a:b].mean(0) for a, b in zip(idx, idx[1:])])
        ge /= np.linalg.norm(ge, axis=1, keepdims=True)
        counts = {str(t): int(len(set(cluster(ge, t)))) for t in THRESHOLDS}
        labels = cluster(ge, args.threshold)
        report[name] = {"images": len(flat), "metadata_groups": len(keys), "clusters_by_threshold": counts,
                        "headline_threshold": args.threshold, "clusters": int(len(set(labels)))}
        montage(name, keys, g, labels, args.out)
    (args.out / "backgrounds.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    a = np.array([[1, 0], [0.99, 0.14], [0, 1]], float)
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    assert len(set(cluster(a, 0.1))) == 2
    assert len(groups("hit-uav")) > 0 if (YOLO / "hit-uav").exists() else True
    main()
