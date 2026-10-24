# NII-CU-MAPD

> **Status:** Draft · **Updated:** 2026-10-25

Summary of the clean / rescale / augment / package work on the NII-CU-MAPD dataset.

## Source

- Multispectral (RGB + far-infrared) aerial person-detection dataset. 5,880 aligned RGB/thermal pairs, drone at 20-50 m over a baseball field, Chiba, Japan, Jan 2020.
- Authors: Simon Speth, Artur Gonçalves, Bastien Rigault, Helmut Prendinger, Satoshi Suzuki.
- License: CC BY-NC-SA 3.0 (non-commercial - fine for this project; authors offer other terms for commercial use).
- Link: https://www.nii-cu-multispectral.org/
- Download: `NII_CU_MAPD_dataset.zip` (9.1 GB, images + labels). The raw unlabeled video archive (15.2 GB) is not used.

## Variant used: `4-channel`

The zip ships two variants; we use `4-channel`, the authors' pre-cleaned subset:

- Only boxes visible in **both** modalities (`type=0`)
- Motion-blurred frames removed (`bad=0`)
- Thermal images cropped to the RGB field of view (no black margins)

| | Train | Val |
| --- | --- | --- |
| Images | 2,653 | 485 |
| Person boxes | 10,144 | 891 |
| Images with no person (negatives) | 55 | 71 |

Native resolution: RGB 2706x1980, thermal 701x513 - same field of view, so YOLO-normalized box coordinates are identical for both modalities (no separate coordinate transform needed per modality).

The other variant, `rgb-t` (full 5,880 pairs; boxes visible in only one modality are kept via a `type` field; thermal has black margins), has ~35% more boxes (19,764 vs 10,144 in train) but needs margin-cropping and per-modality box filtering that we haven't implemented. Worth revisiting if more real training data is needed later.

## 1. Clean

- Parsed the tab-delimited label files (`x1 y1 x2 y2 type occluded bad`); degenerate boxes (zero/negative width or height) dropped.
- Occluded persons kept (partial visibility is still a real detection target - same treatment as HERIDAL's lying/hidden cases).
- Images with no persons kept as negatives, consistent with `src/detection/prepare.py`.

## 2. Rescale (128 / 640 / 1280)

- **Letterbox resize** (aspect ratio preserved, padded to a square with grey 114), not a stretch-resize - avoids the aspect distortion already flagged as a problem for HERIDAL's Roboflow export.
- Box coordinates re-derived for the padded canvas and saved as normalized `cx, cy, w, h`, single class `person` (id 0) - same label convention as `src/detection/prepare.py`.
- **Thermal is skipped at 1280**: native thermal resolution is ~701x513, so 1280 would be a ~1.8x upscale with no real detail gained. This matches the station's already-decided resolutions (thermal 640x512, RGB 1280x1024 - see [CHANGELOG, 2026-10-18](../../CHANGELOG.md)).

## 3. Augmentation

Not pre-baked into the saved arrays. `ultralytics` (used for YOLO11n training here) already does online augmentation during training (flips, HSV jitter, mosaic), so a static augmented copy on disk would be redundant. Worth reconsidering only if we move off the ultralytics trainer.

## 4. Format and what's committed

Saved as **sharded, compressed `.npz`**, not one big `.npy`: an uncompressed array for the whole dataset at one resolution would be several GB, over GitHub's 100 MB/file limit, and `.npz` lets each shard carry images and variable-length boxes together (a plain `.npy` can't hold a different number of boxes per image).

| Resolution | RGB | Thermal | Committed? |
| --- | --- | --- | --- |
| 128 | 73 MB | 19 MB | Yes |
| 640 | 1,531 MB | 315 MB | Yes |
| 1280 | 5,696 MB | - (see above) | No - regenerate locally, see below |

Committed total: ~1.94 GB, under `data/npy/nii-cu-mapd/{rgb,thermal}/{128,640}/{train,val}/shard_*.npz`. `.gitignore` has explicit exceptions for exactly these paths; everything else under `data/` (1280, and any other dataset's local output) stays ignored by default.

## Using the data

```python
from load_nii_cu_mapd import load_shards, boxes_for

images, boxes, box_counts, names = load_shards("data/npy/nii-cu-mapd/rgb/640/train")
# images: (N, 640, 640, 3) uint8
# boxes: (total_boxes, 4) float32, cx/cy/w/h normalized 0..1

boxes_i = boxes_for(boxes, box_counts, i)  # boxes belonging to images[i]
```

`src/detection/load_nii_cu_mapd.py` hides the sharding - callers always get back one plain numpy array.

## Regenerating 1280 (or anything else) locally

Not committed - download the dataset yourself and run the prepare script:

1. Download `NII_CU_MAPD_dataset.zip` from https://www.nii-cu-multispectral.org/ (9.1 GB - need ~15 GB free disk).
2. `pip install numpy pillow`
3. ```
   python src/detection/prepare_nii_cu_mapd.py PATH_TO_ZIP --out data/npy/nii-cu-mapd --sizes 1280 --modalities rgb
   ```

The script reads images directly out of the zip (no extraction step), so disk use stays close to the output size rather than the 9 GB input.

## Files

| Path | Purpose |
| --- | --- |
| [src/detection/prepare_nii_cu_mapd.py](../../src/detection/prepare_nii_cu_mapd.py) | Cleans, resizes, shards the dataset |
| [src/detection/load_nii_cu_mapd.py](../../src/detection/load_nii_cu_mapd.py) | Loads shards back into one array |
| `data/npy/nii-cu-mapd/` | Output (128/640 committed, 1280 local-only) |
