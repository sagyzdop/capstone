# C2A

> **Status:** Draft · **Updated:** 2026-10-25

Summary of the clean / rescale / augment / package work on the C2A dataset.

## Source

- Synthetic RGB aerial person-detection dataset: human figures from LSP/MPII-MPHB pasted onto real disaster photos from AIDER (collapsed building, fire, flood, traffic incident).
- Authors: Ragib Amin Nihal et al., "UAV-Enhanced Combination to Application", ICPR 2024 ([arXiv 2408.04922](https://arxiv.org/abs/2408.04922)).
- License: MIT (Kaggle dataset page).
- Link: https://www.kaggle.com/datasets/rgbnihal/c2a-dataset, [GitHub](https://github.com/Ragib-Amin-Nihal/C2A)
- RGB only, no thermal.

| | Train | Val | Test |
| --- | --- | --- | --- |
| Images (authors' split) | 6,129 | 2,043 | 2,043 |
| Person boxes (all splits) | | 360,467 | |

Images are RGBA PNGs (alpha is fully opaque in all 10,215), 123x152 to 5184x3456, median long side 430 px, 81% at or below 640 px. Labels ship as YOLO (class 0) and COCO json per split, plus a separate folder with a 6th YOLO column for pose (0 bent, 1 kneeling, 2 lying, 3 sitting, 4 upright). Full profile: [dataset-profiles.md](dataset-profiles.md) §2.

## 1. Clean

- Labels read from `All labels with Pose information/labels/` (same boxes as the split folders, plus pose). Class collapsed to `person` (0); pose kept as a side array.
- Boxes clipped to the image; zero-area boxes dropped. None were: all 360,467 boxes survive.
- Tiny boxes kept. Dropping them would leave visible people unlabelled, which teaches the model to ignore them.
- **Re-split by background photo.** Each AIDER photo appears 5 times with different pasted people (`<disaster>_imageNNNN_<0-4>`), and the authors' split puts 98% of val/test photos in train too, so their val/test scores measure memorised backgrounds. All 5 variants of a photo now go to the same split, 60/20/20 within each disaster type, seed 0. 5,714 of 10,215 images changed split; no photo is in more than one split. Photos from the same event or video can still land in different splits (≈400 visual scenes, see the profile), so val/test are less leaky, not leak-free.

| | Train | Val | Test |
| --- | --- | --- | --- |
| Images | 6,135 | 2,040 | 2,040 |
| Background photos | 1,227 | 408 | 408 |
| Person boxes | 216,295 | 72,452 | 71,720 |
| Lying persons | 41,139 | 13,854 | 13,558 |

Poses are near-uniform in every split (each 19-24%).

## 2. Rescale (640 only)

- **Letterbox resize** (aspect preserved, grey 114 pad), boxes re-derived for the padded canvas, normalized `cx, cy, w, h`. Same as [prepare_nii_cu_mapd.py](../../src/detection/prepare_nii_cu_mapd.py).
- **Only 640.** At 640 most C2A images are upscaled already, so 1280 adds no detail. At 128 people shrink to ≈3-6 px, below what YOLO can detect.

Person size at 640 (side = √(w·h)):

| | p5 | p25 | p50 | p75 | p95 | under 8 px |
| --- | --- | --- | --- | --- | --- | --- |
| Train | 3.6 | 8.3 | 15.9 | 27.7 | 49.2 | 24% |
| Val | 3.3 | 7.9 | 15.4 | 27.4 | 49.6 | 25% |
| Test | 3.7 | 8.5 | 16.2 | 28.4 | 47.9 | 23% |

About a quarter of persons stay under 8 px even at 640. That is a paste artefact (the profile's "too small" tail), not a resize loss.

## 3. Augmentation

Not pre-baked, same as NII-CU: `ultralytics` augments online (flips, HSV jitter, mosaic). One gap remains: C2A has no image without people, so a model trained only on it never learns "nobody here". Negatives would have to come from another set.

## 4. Format and where it lives

Sharded, compressed `.npz` with the NII-CU keys (`images`, `boxes`, `box_counts`, `names`) plus two extras:

- `poses` int8 per box (0-4)
- `orig_wh` int32 per image (source width, height)

`load_nii_cu_mapd.load_shards` reads them unchanged and ignores the extras.

| Split | Shards | Size |
| --- | --- | --- |
| Train | 15 | 4.2 GB |
| Val | 5 | 1.4 GB |
| Test | 5 | 1.4 GB |

Total ≈7.0 GB at 640, so it lives on Kaggle, not in git. Shards are ~500 MB raw (~427 images), larger than NII-CU's 85 MB since GitHub's file limit doesn't apply. Layout: `c2a/rgb/640/{train,val,test}/shard_*.npz`, plus `c2a/split.csv` (name, split, original split) and `c2a/stats.json`.

Kaggle dataset: https://www.kaggle.com/datasets/sagyzdop/capstone-c2a (created from the `prepare-c2a` notebook output).

## Using the data

```python
from load_nii_cu_mapd import load_shards, boxes_for

images, boxes, box_counts, names = load_shards("c2a/rgb/640/train")
# images: (6135, 640, 640, 3) uint8, ~7.5 GB in RAM for train
boxes_i = boxes_for(boxes, box_counts, i)
```

ultralytics trains from image files, so unpack the shards once (one shard in RAM at a time, ≈3.5 GB of PNGs out):

```
python src/detection/npz_to_yolo.py c2a/rgb/640 --out data/yolo/c2a
yolo detect train data=data/yolo/c2a/c2a.yaml model=yolo11n.pt imgsz=640
```

## Regenerating

On Kaggle (no download), from the repo root:

```
kaggle kernels push -p src/detection/kaggle/prepare-c2a
```

The kernel attaches `rgbnihal/c2a-dataset`, runs on CPU without internet and writes to `/kaggle/working/c2a`; it took about 11 minutes.

Locally, from the 4.9 GB Kaggle zip (read without extracting):

```
python src/detection/prepare_c2a.py PATH_TO_ZIP --out data/npy/c2a --sizes 640
```

## Files

| Path | Purpose |
| --- | --- |
| [src/detection/prepare_c2a.py](../../src/detection/prepare_c2a.py) | Cleans, re-splits, resizes, shards the dataset |
| [src/detection/kaggle/prepare-c2a/kernel-metadata.json](../../src/detection/kaggle/prepare-c2a/kernel-metadata.json) | Kaggle kernel that runs it |
| [src/detection/load_nii_cu_mapd.py](../../src/detection/load_nii_cu_mapd.py) | Loads the shards (shared with NII-CU) |
| [src/detection/npz_to_yolo.py](../../src/detection/npz_to_yolo.py) | Unpacks shards into a YOLO folder for ultralytics |
