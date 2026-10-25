# RGBTDronePerson

> **Status:** Draft · **Updated:** 2026-10-25

Summary of the clean / rescale / augment / package work on the RGBTDronePerson dataset.

## Source

- Paired RGB + thermal drone images of tiny persons: streets, campuses, parks, piers; day and night, nadir and oblique views.
- Paper: "Drone-based RGBT tiny person detection", ISPRS Journal of Photogrammetry and Remote Sensing, 2023. Code: [mmdet-rgbtdroneperson](https://github.com/NNNNerd/mmdet-rgbtdroneperson).
- License: not verified (see [datasets.md](datasets.md)).
- Local copy: `data/RGBTDronePersonRaw/` (1.9 GB, extracted).

Layout: `{train,val}/{visible,thermal,annotation}/NNNNN.{jpg,xml}`, same stem = same pair. All 6,125 pairs are complete (no image without its partner or XML). Both modalities are 640x512 JPGs. Labels are Pascal VOC XML with four classes.

| | Train | Val |
| --- | --- | --- |
| Pairs | 4,900 | 1,225 |
| person | 43,169 | 11,009 |
| rider | 4,633 | 1,447 |
| crowd | 7,172 | 2,004 |
| uncertain | 1,340 | 106 |

Persons are tiny: median side √(w·h) ≈ 11 px at native 640x512, p95 ≈ 17 px. crowd boxes (a few people too close to separate) have a median side of 14 px.

## Labels are in the thermal frame

The XMLs are drawn on the thermal image (`<folder>Thermal</folder>`, `path ...\Thermal\NNNNN.jpg`). RGB and thermal are only weakly aligned: on RGB the person is often 10-30 px away from its box, more than the person itself. Phase correlation of edge maps gives a confident global shift on only ~3% of frames, and neighbouring frames disagree by 3-12 px, so a per-frame translation can't fix it.

Also, ~35% of RGB frames are night shots (mean luma < 50) where people are not visible in RGB at all.

Consequences:

- **Thermal is the primary modality.** Its labels are exact.
- RGB shards get the same boxes so that `rgb` and `thermal` stay paired by index for a fusion model that predicts in the thermal frame (as the paper does). **Don't train an RGB-only detector on these labels.**

## 1. Clean

- person, rider, crowd → single class `person` (0). The source class is kept as a side array (`classes`: 0 person, 1 rider, 2 crowd).
- `uncertain` is neither a person nor background. It goes to separate `ignore_boxes` instead of being dropped silently, so a trainer can mask those regions.
- Image size is taken from the JPG, not the XML: 3 train XMLs (`00065`, `00067`, `00076`) say 630x500 for 640x512 images; their boxes fit the 640x512 thermal image as-is.
- Boxes clipped to the image; zero-area boxes dropped (1 in train).
- Truncated boxes (1,003 train / 250 val) kept, same as occluded persons in NII-CU.
- Images without persons kept as negatives: 59 train / 9 val (counting images whose only boxes are `uncertain`).
- Thermal JPGs are 3-channel but grey (R=G=B in every file), stored as 1 channel.
- **Split: the authors' train/val, unchanged**, so scores compare with the paper. The frames come from videos and the split may share scenes: at 16x16 thumbnail level, ~5% of val frames have a near-identical train frame (correlation > 0.98). Not checked further.

No exact duplicate files.

## 2. Rescale (128 / 640 / 1280)

- **Letterbox resize** (aspect preserved, grey 114 pad), boxes re-derived for the padded canvas, normalized `cx, cy, w, h`. Same as [prepare_nii_cu_mapd.py](../../src/detection/prepare_nii_cu_mapd.py). 640x512 → 640x640 adds 64 px of pad above and below.
- Native is 640x512, so **1280 is a 2x upscale for both modalities**: no new detail, but persons cover twice as many pixels of the model's stride-8 grid, which helps tiny objects. Same effect as `imgsz=1280` at train time on the 640 shards.
- **128 is not usable for detection**: persons shrink to ≈2 px. Kept because it was requested (e.g. for scene-level work).

Person size (side = √(w·h), px):

| Size | Split | p5 | p25 | p50 | p75 | p95 | under 8 px |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 128 | Train | 1.5 | 1.9 | 2.2 | 2.6 | 3.4 | 100% |
| 128 | Val | 1.7 | 2.0 | 2.3 | 2.7 | 3.7 | 100% |
| 640 | Train | 7.3 | 9.5 | 11.2 | 13.0 | 17.0 | 9% |
| 640 | Val | 8.4 | 9.9 | 11.4 | 13.7 | 18.4 | 3% |
| 1280 | Train | 14.7 | 19.0 | 22.4 | 26.1 | 33.9 | 0% |
| 1280 | Val | 16.7 | 19.8 | 22.8 | 27.3 | 36.8 | 0% |

## 3. Augmentation

Not pre-baked, same as NII-CU and C2A: `ultralytics` augments online (flips, HSV jitter, mosaic, scale), so a static augmented copy on disk only costs space.

Things specific to this set, to set at train time rather than on disk:

- Tiny persons: the default `scale=0.5` can shrink an 11 px person to ~5 px. A smaller `scale` (e.g. 0.2-0.3) is worth trying.
- Mostly top-down views: `flipud=0.5` is a valid extra flip (off by default in ultralytics).
- HSV jitter does nothing useful on 1-channel thermal (ultralytics loads it as 3 equal channels); harmless.
- A fusion model trained outside ultralytics needs the same geometric transform on both modalities. Not implemented here.

## 4. Format and where it lives

Sharded, compressed `.npz` with the NII-CU keys (`images`, `boxes`, `box_counts`, `names`) plus:

- `classes` int8 per box (0 person, 1 rider, 2 crowd)
- `ignore_boxes` float32 (k, 4) `uncertain` regions, normalized `cx, cy, w, h`; `ignore_counts` int32 per image

`load_nii_cu_mapd.load_shards` reads them unchanged and ignores the extras. `rgb` and `thermal` shards for the same size/split hold the same images in the same order. Shards are capped at ~85 MB raw, like NII-CU.

Layout: `data/npy/rgbtdroneperson/{thermal,rgb}/{128,640,1280}/{train,val}/shard_*.npz`, plus `stats.json`.

| Size | Thermal | RGB |
| --- | --- | --- |
| 128 | 65 MB | 176 MB |
| 640 | 1.5 GB | 3.8 GB |
| 1280 | 4.7 GB | 13.5 GB |

Total 23.7 GB, too large for git; regenerate locally (below).

## Using the data

```python
from load_nii_cu_mapd import load_shards, boxes_for

images, boxes, box_counts, names = load_shards("data/npy/rgbtdroneperson/thermal/640/train")
# images: (4900, 640, 640, 1) uint8
boxes_i = boxes_for(boxes, box_counts, i)
```

For ultralytics, unpack once:

```
python src/detection/npz_to_yolo.py data/npy/rgbtdroneperson/thermal/640 --out data/yolo/rgbtdroneperson-thermal
yolo detect train data=data/yolo/rgbtdroneperson-thermal/rgbtdroneperson-thermal.yaml model=yolo11n.pt imgsz=1280 flipud=0.5
```

## Regenerating

From the extracted folder (all sizes and both modalities by default):

```
python src/detection/prepare_rgbtdroneperson.py data/RGBTDronePersonRaw --out data/npy/rgbtdroneperson
python src/detection/prepare_rgbtdroneperson.py data/RGBTDronePersonRaw --out OUT --sizes 640 --modalities thermal
```

## Files

| Path | Purpose |
| --- | --- |
| [src/detection/prepare_rgbtdroneperson.py](../../src/detection/prepare_rgbtdroneperson.py) | Cleans, resizes, shards the dataset |
| [src/detection/load_nii_cu_mapd.py](../../src/detection/load_nii_cu_mapd.py) | Loads the shards (shared with NII-CU, C2A) |
| [src/detection/npz_to_yolo.py](../../src/detection/npz_to_yolo.py) | Unpacks shards into a YOLO folder for ultralytics |
