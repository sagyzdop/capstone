"""Load sharded .npz NII-CU-MAPD data produced by prepare_nii_cu_mapd.py.

The data is split across several shard_*.npz files (GitHub's 100 MB-per-file limit
means one big array per resolution isn't an option) -- this hides that, so callers
just get back one plain numpy array, same as if it were a single file.

Usage:
    from load_nii_cu_mapd import load_shards, boxes_for

    images, boxes, box_counts, names = load_shards("data/npy/nii-cu-mapd/rgb/640/train")
    # images: (N, size, size, C) uint8, boxes: (total_boxes, 4) float32 cx,cy,w,h normalized

    # boxes belonging to image i:
    boxes_i = boxes_for(boxes, box_counts, i)

Run directly to sanity-check a folder:
    python load_nii_cu_mapd.py data/npy/nii-cu-mapd/rgb/640/train
"""

from pathlib import Path

import numpy as np


def load_shards(split_dir):
    """Load every shard_*.npz in split_dir and concatenate into one set of arrays."""
    paths = sorted(Path(split_dir).glob("shard_*.npz"))
    if not paths:
        raise FileNotFoundError(f"no shard_*.npz files in {split_dir}")
    images, boxes, box_counts, names = [], [], [], []
    for p in paths:
        d = np.load(p)
        images.append(d["images"])
        boxes.append(d["boxes"])
        box_counts.append(d["box_counts"])
        names.append(d["names"])
    return (
        np.concatenate(images),
        np.concatenate(boxes),
        np.concatenate(box_counts),
        np.concatenate(names),
    )


def boxes_for(boxes, box_counts, i):
    """Return the normalized cx,cy,w,h boxes belonging to image i."""
    offsets = np.concatenate([[0], np.cumsum(box_counts)])
    return boxes[offsets[i]:offsets[i + 1]]


if __name__ == "__main__":
    import sys

    images, boxes, box_counts, names = load_shards(sys.argv[1])
    print(f"{len(images)} images, {len(boxes)} boxes total")
    print(f"images: shape={images.shape} dtype={images.dtype}")
    print(f"first name: {names[0]}, boxes for it: {boxes_for(boxes, box_counts, 0)}")
