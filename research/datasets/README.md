# Datasets and detection

The station runs two YOLO26 models, one RGB and one thermal, and fuses their boxes late. The design is in [SPEC.md](../../SPEC.md#detection). This file covers the data each model trains and is tested on, how to convert and train, the laptop test, which data to add next and, at the bottom, what the training runs found.

## Training data

Every dataset is converted to one class, `person`, and trained at `imgsz=640`. Datasets with both modalities are split by modality, and each model sees only its own.

| Dataset | Model | What it is | License |
| --- | --- | --- | --- |
| [SARD](https://www.kaggle.com/datasets/nikolasgegenava/sard-search-and-rescue) (Kaggle copy; the [IEEE DataPort original](https://ieee-dataport.org/documents/search-and-rescue-image-dataset-person-detection-sard) needs a paid subscription) | RGB | Actors in search-and-rescue poses, including lying | Not stated |
| [NII-CU-MAPD](https://www.nii-cu-multispectral.org/) | RGB and thermal | 5,880 aligned pairs from a drone at 20 to 50 m over a baseball field in Chiba, Japan, January 2020 | CC BY-NC-SA 3.0 |
| [HERIDAL](https://universe.roboflow.com/drone-internship/heridal-human-detection) (Roboflow export v4) | RGB | Real SAR exercises in Croatian karst, forest, maquis, snow and a city park; volunteers stand, walk, sit and lie | CC BY 4.0 |
| [RGBTDronePerson](https://nnnnerd.github.io/RGBTDronePerson/) ([code](https://github.com/NNNNerd/mmdet-rgbtdroneperson)) | Thermal | 6,125 pairs of tiny people in streets, campuses, parks and piers, day and night, top-down and oblique | Not verified |
| [HIT-UAV](https://zenodo.org/record/7633134) | Thermal | 2,898 images at 640×512 from 60 to 130 m over a campus and roads, day and night | CC0 on Zenodo; GitHub says CC BY 4.0 |

### SARD

Our copy is the Roboflow export `sard-8xjhy` v17 "TILES_3x3". Each source photo is cut into a 3×3 grid and every tile is stretched to 640×640, which makes people about 3× larger than in the full photo and changes their aspect ratio. It has one class, `human`; the original's pose classes are gone. The splits are by source photo, so no photo has tiles in two splits.

| | Train | Valid | Test |
| --- | --- | --- | --- |
| Tiles | 4,041 | 1,144 | 570 |
| Source photos | 1,387 | 396 | 197 |
| Persons | 5,229 | 1,463 | 732 |
| Tiles with no person | 571 | 177 | 84 |

### NII-CU-MAPD

We train on the `4-channel` variant, the authors' cleaned subset. It keeps only boxes visible in both modalities, drops motion-blurred frames and crops thermal to the RGB field of view, so the normalised boxes fit both images. Train has 2,653 images and 10,144 boxes, val 485 images and 891 boxes.

Native size is RGB 2706×1980 and thermal 701×513. At `imgsz=640` the RGB frame shrinks about 4×, so its people end up 8 to 15 px, about the drone's size. The other variant, `rgb-t`, has all 5,880 pairs and about 35% more boxes, but it's the same field.

### HERIDAL

The Roboflow export has 1,579 frames and 3,073 people, every frame stretch-resized from 4:3 to 640×640. People are tiny: median 11 px, 90% under 16 px. Roboflow's own split leaks (44 of its 101 test frames have a near-identical frame in train or valid), so `convert.py heridal` ignores it and does the following:

- Resizes every frame back to 853×640. The stretch made people 25% narrower than they are. Boxes keep their normalised coordinates.
- Splits by location code (the filename prefix), so val and test show places the model never trained on. MOB and GRO are the same scenes as BLA and GOR and stay with them.
- Groups frames that show the same ground (difference hash, Hamming distance 40 or less): 304 of the 1,579 frames repeat another view. Val and test keep one frame per view, and none of their views appears in train.
- Cuts train and val frames into two overlapping 640×640 crops, so people keep their native 8 to 16 px at `imgsz=640`. A box goes to a crop when at least half of it is inside. Test frames stay whole and are scored tiled, the way the drone's RGB will run.

| Split | Locations | Scenes | Images | Persons | Empty |
| --- | --- | --- | --- | --- | --- |
| train | VRD, GOR, GRO, JAS, BRK, ZRI, TRS, BLA, MOB | karst, snow, pasture, pine and deciduous canopy, city park | 2,180 crops of 1,090 frames | 2,262 (3,805 boxes over both crops; 57% in the ZRI park) | 907 crops |
| val | RAK, BRS | karst grassland, dark sparse woodland | 238 crops | 174 boxes | 117 crops |
| test | MED, BRA, CAP, SB, BLI, CAB | maquis, dark pine forest, riverbank, autumn forest, meadow, ravine | 303 frames | 582 | 105 |

The test locations hold scene types that train lacks. HERIDAL val is small next to SARD and NII-CU-MAPD val, so it has little say in which epoch becomes `best.pt`.

The 8.3 GB [Zenodo original](https://zenodo.org/records/5662351) (about 4000×3000, CC BY 3.0) has about 29× more pixels per person and no stretch or re-compression. We don't need it at the drone's scale yet, but it would allow scale augmentation from sharp frames.

### RGBTDronePerson

| | Train | Val |
| --- | --- | --- |
| Pairs | 4,900 | 1,225 |
| person | 43,169 | 11,009 |
| rider | 4,633 | 1,447 |
| crowd | 7,172 | 2,004 |
| uncertain | 1,340 | 106 |

Both modalities are 640×512. People have a median size of about 11 px, p95 about 17 px.

- Thermal only. The labels are drawn on the thermal image, and on RGB the person is often 10 to 30 px from its box, more than the person's own size. No per-frame shift fixes it, and about 35% of RGB frames are night shots where nobody is visible. An RGB model trained with these labels scored AP50 0.06 on them.
- person, rider and crowd all become `person`. `uncertain` regions are filled grey, since they are neither a person nor background.
- Three train XMLs (`00065`, `00067`, `00076`) say 630×500 for 640×512 images, so the size comes from the image.
- The authors split by video, and about 5% of val frames have a near-identical train frame.

### HIT-UAV

Thermal, 640×512, with classes Person, Car, Bicycle, OtherVehicle and DontCare. Only Person is kept, and the 148 DontCare boxes become background.

| | Train | Val | Test |
| --- | --- | --- | --- |
| Images | 2,008 | 287 | 571 |
| Persons | 8,533 | 1,168 | 2,611 |

42% of its images have no person, our main source of thermal negatives. Its own scores are optimistic: the 2,898 images come from video and were split per frame, so 31% of val/test images are near-duplicates of train.

## Test data

The RGB test that counts is HERIDAL's six held-out locations, above. Thermal has no held-out test yet; its scores come from the training sets' own splits, which share flights with train.

WiSARD (real wilderness SAR, RGB and thermal) is out of scope for now. We had a 264-frame sample of one flight and four volunteers, which is too narrow for more than a sanity check.

## Conversion and training

Raw datasets go in `data/raw/`, unpacked as downloaded. Each is converted to single-class `person` YOLO under `data/yolo/`, with images symlinked to `data/raw/` (HERIDAL's resized frames and crops, and RGBTDronePerson's masked frames, are written out instead):

```
R=data/raw/sard; python src/detection/prepare.py sard --person-ids 0 --split train=$R/train/images:$R/train/labels --split val=$R/valid/images:$R/valid/labels --split test=$R/test/images:$R/test/labels
R=data/raw/hit-uav; python src/detection/prepare.py hit-uav --person-ids 0 --split train=$R/images/train:$R/labels/train --split val=$R/images/val:$R/labels/val --split test=$R/images/test:$R/labels/test
python src/detection/convert.py nii-cu-mapd data/raw/nii-cu-mapd/4-channel
python src/detection/convert.py rgbtdroneperson data/raw/rgbtdroneperson
python src/detection/convert.py heridal data/raw/heridal
```

Train under a memory cap; caching images in RAM once ran the 30 GB lab computer out of memory, so `train.py` doesn't cache:

```
systemd-inhibit --what=sleep:idle --why=train systemd-run --user --scope -p MemoryMax=18G -p MemorySwapMax=0 .venv/bin/python src/detection/train.py rgb --model yolo26n.pt --epochs 60 --tag heridal
```

`train.py` trains one model per modality on all its datasets, scores `best.pt` on every val and test split into `scores.md`, and writes `results.md`. `--tag` is added to the run folder name for runs that differ in data. A run that gets interrupted resumes when the same command runs again. Then score the held-out test tiled:

```
python src/detection/eval_sizes.py runs/rgb/RUN/weights/best.pt heridal test --imgsz 640 --tile 640 --device 0 --out runs/rgb/RUN/eval/heridal-test.json
```

Settings: YOLO26 from COCO weights, `imgsz=640`, batch 32, seed 0, no early stopping, Ultralytics' default augmentation. Each model's val set is all its datasets' val splits together, and that picks `best.pt` (mostly by AP50-95). The lab computer has an RTX 5080 (16 GB); an RGB epoch takes about 25 s.

## Test on the station laptop

Nano first, then small.

1. Latency per frame for each model alone: thermal at 640×512, and RGB at 1280×1024 tiled into six 640 crops.
2. Both models at once on all four streams (drone thermal 30 FPS, drone RGB 10 FPS, robot thermal and RGB 5 FPS each), which is the real load.
3. Sustained rate over at least 10 minutes, since a laptop without a fan throttles and the first minute overstates it.
4. Memory use with both models loaded.
5. PyTorch on the GPU against an exported model (`yolo export`, in the laptop's native format).

These numbers replace the predicted frame rates in [SPEC.md](../../SPEC.md#streams) and [communication/](../communication/).

## What the data says about the drone

### Measures

- Person size: √(box width × height) in pixels. Detectors mostly miss people below about 8 px; 16 to 32 px is workable, and above 32 px is easy.
- Contrast: (mean grey inside the box − mean grey of a ring one box wide around it) ÷ grey standard deviation of the whole image. +1 means one standard deviation brighter (warmer, in thermal) than the ground next to the person. |c| < 0.5 is low contrast.
- Sharpness: variance of the Laplacian after resizing to a 640 px long side. Under 100 is soft, above 1,000 crisp or heavily textured.
- Crowding: distance from a person's centre to the nearest other person's centre, in that person's body sizes. Under 1 they touch, above 5 they're isolated.

### Input size and tiling

- Thermal shouldn't be downscaled below about 480 px. A HIT-UAV model scored AP50 0.664 at 320, 0.840 at 480, 0.872 at 640, 0.851 at 960 and 0.754 at 1280 on HIT-UAV test. Recall falls once a person drops to about 6 px at the model input.
- Running a model above the size it trained at hurts: its 16 to 24 px recall fell from 0.90 at 640 to 0.57 at 1280, because it had never seen people that large.
- High-resolution RGB has to be tiled. On 4K WiSARD frames, COCO weights scored AP50 0.030 resized to 640 and 0.324 on 640 tiles with 20% overlap.

### Thermal by day and night

![HIT-UAV person size against altitude and camera angle, and day/night contrast](assets/hituav_altitude_daynight.png)

HIT-UAV thermal. Left: person size against flight altitude, from about 16 px at 60 m to about 11 px at 120 to 130 m. Middle: person size against camera angle (90° is straight down); oblique 30 to 40° views give the smallest people. Right: person contrast by day and by night; the grey band is low contrast.

By day the ground warms up and most people barely stand out (median contrast 0.23); at night they do (1.06). The thermal sets are 8-bit JPEGs with no temperature values, so body temperature can't be learned from them. Sunlit rock can reach body temperature, which risks false alarms.

### RGB and thermal together

![WiSARD RGB frame with the thermal camera's footprint, next to the thermal frame](assets/wisard_footprint.png)

One WiSARD frame from both cameras. The green dashed box is the part of the 3840×2160 RGB frame that the 640×512 thermal camera also sees, and the orange boxes are the same four people.

From 264 WiSARD pairs, a fixed linear map from RGB to thermal coordinates aligns people to a median 7.7 thermal px, about half a person. The thermal footprint covers 64% of the RGB frame, and a person is 3.9× larger in RGB pixels. That's close enough to match boxes but too coarse to stack pixels, hence late fusion. Trust thermal more at night and RGB more by day. Dust-covered victims will look grey in RGB, which makes thermal worth more to us than WiSARD's brightly dressed volunteers suggest.

### How high the drone can fly

A standing person is about 0.45 m across from above (√area), a lying one about 0.9 m. With detection down to 8 px (10 to be safe):

`max altitude ≈ person size (m) × image width (px) ÷ (8 × 2·tan(HFOV/2))`

With the assumed cameras (thermal 640×512 at 40° HFOV, RGB 1280×1024 at 72°), both give the same person size at every altitude, about 400 ÷ altitude px for a standing person. The camera specs are assumptions until we have the real drone.

| Altitude | Ground per pixel | Thermal native, or RGB 1280 tiled (standing / lying px) | RGB resized to 640 |
| --- | --- | --- | --- |
| 20 m | 2.3 cm | 20 / 40 | 10 / 20 |
| 30 m | 3.4 cm | 13 / 26 | 7 / 13 |
| 40 m | 4.5 cm | 10 / 20 | 5 / 10 |
| 50 m | 5.7 cm | 8 / 16 | 4 / 8 |
| 60 m | 6.8 cm | 7 / 13 | 3 / 7 |
| 80 m | 9.1 cm | 5 / 10 | 2 / 5 |
| 100 m | 11.4 cm | 4 / 8 | 2 / 4 |

The ceiling is about 49 m for standing people (40 m at 10 px) and about 80 m for lying ones. Resized RGB fails above about 25 m, which is why the station tiles it.

| Dataset | Flight altitude | What it means for us |
| --- | --- | --- |
| HIT-UAV | 60 to 130 m (paper) | Its people (16 px at 60 m, 11 px at 120 to 130 m) match our thermal camera at about 25 to 36 m, so its lens is much narrower than ours. |
| HERIDAL | 40 to 65 m, 4K cameras ([paper](https://arxiv.org/pdf/2111.09406)) | The 853×640 export has a median 11 px person, about what our tiled 1280 RGB sees at 40 m. |
| NII-CU-MAPD | 20 to 50 m | Our altitude band. Its 2706 px RGB shrinks about 4× at `imgsz=640`, which puts its people at 8 to 15 px; thermal (701 px) is close to ours. |
| RGBTDronePerson | 50 to 80 m, 45 to 60° tilt (from a [secondary blog](https://zeeklog.com/gou-jian-ji-yu-wu-ren-ji-rgb-hong-wai-rgbt-shuang-mo-tai-xiao-mu-biao-xing-ren-jian-ce-xi-tong-wu-ren-ji-shi-jiao-xia-rgb-hong-wai-dui-qi-xing-ren-xiao-mu-biao-jian-ce-shu-ju-ji-hang-pa-4), not the paper) | Its median 11 px thermal person equals ours at about 36 m. Its oblique views aren't what a hovering drone sees. |
| Archangel | 15 to 50 m in 5 m steps ([paper](https://arxiv.org/pdf/2209.00128)) | Reports accuracy by altitude across our whole band. Not read yet. |
| NOMAD | 10 to 90 m ([paper](https://ar5iv.labs.arxiv.org/html/2309.09518)) | Goes past our ceiling, so it could show where detection stops. |

Real SAR datasets fly at about 40 to 65 m, in line with this estimate. Lying victims, the likely case after an earthquake, allow about twice the altitude of standing ones.

## More data

RGB needs it most ([findings](#findings)). In order:

| Dataset | Model | Why | Catch | Link |
| --- | --- | --- | --- | --- |
| NOMAD (2024) | RGB | Real footage of 100 actors walking, lying and hiding at 10 to 90 m, 42,825 frames | License and size unknown | [GitHub](https://github.com/ArtRuss/NOMAD) |
| C2A (2024) | RGB | People on real disaster photos of rubble, fire and flood, 19% lying; MIT license | The people are pasted in at 4 to 24 px whatever the scene's scale, every image is crowded (median 34 people, none empty), and 98% of val/test backgrounds are also in train. Re-split by background and use a capped sample. | [GitHub](https://github.com/Ragib-Amin-Nihal/C2A) |
| HERIDAL original | RGB | Same people at 4000×3000, for scale augmentation | 8.3 GB | [Zenodo](https://zenodo.org/records/5662351) |
| AIResQ (2025) | Thermal | Real SAR, 9,788 images | Full set on request | [Sci. Data](https://www.nature.com/articles/s41597-026-07663-9) |
| BIRDSAI (2020) | Thermal | Real aerial thermal, mostly night, CDLA-Permissive | Savanna, not disaster | [LILA](https://lila.science/datasets/conservationdrones/) |
| VisDrone-DET (2018) | RGB | Many tiny people | City crowds; academic use only (unverified) | [GitHub](https://github.com/VisDrone/VisDrone-Dataset) |

No dataset we know of has real people in real rubble. Our own staged clips would fill that: actors lying on rubble or a construction site, day and night, 20 to 60 m, both cameras. Even 200 to 500 labelled frames would be the most useful test set we could have.

## Scripts

In [src/detection/](../../src/detection/); each docstring has full usage. Raw data goes in `data/` and weights in `runs/`, both git-ignored. Setup: `python3 -m venv .venv && .venv/bin/pip install ultralytics pandas tabulate`.

| Script | Does |
| --- | --- |
| `prepare.py` | Converts a YOLO- or COCO-labelled dataset to single-class `person` YOLO under `data/yolo/`. |
| `convert.py` | Converts NII-CU-MAPD (`4-channel`, both modalities), RGBTDronePerson (thermal, `uncertain` masked) and HERIDAL (resized to 4:3, split by location, train and val cut into 640 crops). |
| `train.py` | Trains one model per modality, scores `best.pt` on every val and test split, writes `results.md`. |
| `eval_sizes.py` | AP50, precision and recall at confidence 0.25, and recall by person size, at any `imgsz` and tiled. Writing into a run's `eval/` refreshes its `results.md`. |
| `report.py` | Rewrites a run's `results.md` from the files in its folder. `python src/detection/report.py --all` |
| `detect.py` | Runs a model on an image or folder and writes the station's JSON detections. |

## Results

### Reading the metrics

A detection counts as correct when its box overlaps a labelled person enough. Two settings sit behind that:

- IoU (intersection over union): the overlap of the predicted and labelled boxes divided by the area they cover together. 1 is identical, 0 is no overlap.
- Confidence: the model's 0 to 1 score for each box. A threshold keeps only boxes above it; `detect.py` uses 0.25. Lowering it finds more people and raises more false alarms.

| Metric | What it measures | How much it matters here |
| --- | --- | --- |
| Recall | Share of the labelled people the model found. 0.80 means 1 person in 5 is missed. | Most. A missed person is a missed victim. |
| Precision | Share of the model's boxes that are real people. 0.90 means 1 box in 10 is a false alarm. | Less. The operator checks every detection, and a false alarm costs seconds. |
| AP50 | Area under the precision-recall curve, with a box correct at IoU 0.5 or more. One number for finding people with few false alarms across all thresholds. With one class it equals mAP50. | The main number for comparing models. |
| AP50-95 | The same, averaged over IoU 0.50, 0.55 up to 0.95, so it rewards tight boxes. | A check on box quality only. |
| Recall by size | Recall for people in size bins (√(box area) in px at the model input, or native px when tiled). | High. Our people are 10 to 15 px, and the totals hide how recall falls with size. |

`scores.md` comes from Ultralytics, and its precision and recall are taken at the confidence with the best F1. `eval_sizes.py` takes them at 0.25, matching `detect.py`, and computes its own AP50, which differs from Ultralytics' in the third decimal. So the two recalls differ a little: SARD val is 0.908 in `scores.md` and 0.934 at 0.25.

AP50-95 sits far below AP50 here because people are small. For a 10 px person, a box 2 px off on both axes has IoU 0.47 and already fails at 0.5, while the same error on a 50 px person still gives 0.85. AP50-95 ÷ AP50 is 0.68 on SARD (about 50 px people) and 0.34 on RGBTDronePerson (about 11 px). A 2 px error on a 10 px person doesn't change where the operator looks, so judge the models by recall and AP50.

A rough guide for this project: AP50 above 0.9 is strong, 0.7 to 0.9 usable, below 0.5 poor.

### Runs

Each run folder has a `results.md` with its setup, val curve, the epoch `best.pt` came from, `scores.md`, every `eval_sizes.py` result and the plots.

| Run | Data | Epochs (`best.pt`) | Own val AP50 | HERIDAL test, tiled: AP50 / recall |
| --- | --- | --- | --- | --- |
| [RGB YOLO26n](../../runs/rgb/yolo26n_e100/results.md) | SARD, NII-CU-MAPD | 100 (68) | 0.907 | 0.015 / 0.02 |
| [RGB YOLO26s](../../runs/rgb/yolo26s_e70/results.md) | SARD, NII-CU-MAPD | 70 (55) | 0.889 | 0.009 / 0.03 |
| [RGB YOLO26n + HERIDAL](../../runs/rgb/yolo26n_e60_heridal/results.md) | SARD, NII-CU-MAPD, HERIDAL train locations | 60 (52) | 0.862 (HERIDAL val included) | 0.215 / 0.22 |
| [RGB YOLO26n + HERIDAL ×3](../../runs/rgb/yolo26n_e60_heridalx3_valh_s025/results.md) | Same, HERIDAL listed 3×; `best.pt` picked on HERIDAL val; rescale ±25% | 60 (11) | 0.242 (HERIDAL val only) | 0.166 / 0.17 (`last.pt` 0.122 / 0.14) |
| [RGB YOLO26n, HERIDAL only](../../runs/rgb/yolo26n_e100_heridal_only/results.md) | HERIDAL train locations | 100 (76) | 0.246 (HERIDAL val only) | 0.195 / 0.20 (`last.pt` 0.184 / 0.19) |
| [Thermal YOLO26n](../../runs/thermal/yolo26n_e100/results.md) | RGBTDronePerson, NII-CU-MAPD, HIT-UAV | 100 (28) | 0.650 | n/a |
| [Thermal YOLO26s](../../runs/thermal/yolo26s_e50/results.md) | RGBTDronePerson, NII-CU-MAPD, HIT-UAV | 50 (28) | 0.666 | n/a |

The current RGB model is YOLO26n + HERIDAL (`yolo26n_e60_heridal`), and the current thermal model is YOLO26n (`yolo26n_e100`).

### Per dataset

AP50 from `scores.md`. RGB rows without a split note are from the training sets' own val/test splits, which share flights or photos with train.

| Data | Split | RGB n | RGB s | RGB n + HERIDAL | Thermal n | Thermal s |
| --- | --- | --- | --- | --- | --- | --- |
| SARD | val | 0.952 | 0.948 | 0.945 | | |
| SARD | test | 0.945 | 0.946 | 0.941 | | |
| NII-CU-MAPD RGB | val | 0.834 | 0.788 | 0.848 | | |
| HERIDAL | val (unseen locations) | | | 0.220 | | |
| HERIDAL | test (unseen locations), whole frames | 0.011 | 0.006 | 0.152 | | |
| HERIDAL | test (unseen locations), tiled | 0.015 | 0.009 | 0.215 | | |
| RGBTDronePerson | val | | | | 0.584 | 0.602 |
| NII-CU-MAPD thermal | val | | | | 0.986 | 0.977 |
| HIT-UAV | val | | | | 0.911 | 0.914 |
| HIT-UAV | test | | | | 0.921 | 0.934 |

HERIDAL rows are from `eval_sizes.py`, except val, which is Ultralytics.

The two HERIDAL experiments, against the current RGB model:

| Data | Split | RGB n + HERIDAL | HERIDAL ×3 | HERIDAL only |
| --- | --- | --- | --- | --- |
| SARD | val | 0.945 | 0.832 | 0.001 |
| SARD | test | 0.941 | 0.833 | 0.001 |
| NII-CU-MAPD RGB | val | 0.848 | 0.778 | 0.141 |
| HERIDAL | val | 0.220 | 0.242 | 0.246 |
| HERIDAL | test, tiled, `best.pt` | 0.215 | 0.166 | 0.195 |
| HERIDAL | test, tiled, `last.pt` | (`best.pt` is epoch 52 of 60) | 0.122 | 0.184 |

Recall at confidence 0.25 by person size, on the sets with people at the drone's size:

| Data | Model | Under 8 px | 8 to 12 px | 12 to 16 px | 16 to 24 px |
| --- | --- | --- | --- | --- | --- |
| HERIDAL test, tiled | RGB n | 0.00 (49) | 0.00 (210) | 0.01 (195) | 0.08 (119) |
| HERIDAL test, tiled | RGB n + HERIDAL | 0.22 (49) | 0.18 (210) | 0.26 (195) | 0.23 (119) |
| HERIDAL test, tiled | RGB n, HERIDAL only | 0.10 (49) | 0.15 (210) | 0.24 (195) | 0.24 (119) |
| RGBTDronePerson val | Thermal n | 0.32 (501) | 0.60 (7,850) | 0.64 (4,581) | 0.45 (1,406) |
| HIT-UAV test | Thermal n | 0.75 (16) | 0.88 (548) | 0.91 (1,045) | 0.92 (858) |
| NII-CU-MAPD thermal val | Thermal n | | 0.67 (36) | 0.97 (335) | 0.99 (413) |

The bracket is the number of people in the bin. On NII-CU-MAPD RGB val, where people are 8 to 15 px at 640, the first RGB nano had recall 0.80.

### Findings

High scores on a dataset's own splits say little about new places. Both RGB models trained on SARD and NII-CU-MAPD scored above 0.9 AP50 on SARD and then found 2 to 3% of the people at HERIDAL's held-out locations, at 8 to 16 px almost none, tiled or not. It wasn't the conversion: the labels sit on the people, the models skipped people standing in plain view on open grass, and recall at IoU 0.25 was still 0.03. SARD's people are mostly over 32 px, and NII-CU-MAPD's small people are all on one baseball field in winter, so neither showed the models a 10 px person in natural terrain. An earlier thermal model trained on HIT-UAV did the same on WiSARD (AP50 0.87 on its own test, 0.01 on WiSARD).

Adding HERIDAL's training locations raised AP50 on its unseen locations from 0.015 to 0.215 and tiled recall from 0.02 to 0.22, about the same at every size from under 8 px to 24 px. SARD stayed level (0.952 to 0.945) and NII-CU-MAPD rose (0.834 to 0.848). The model still misses about 78% of HERIDAL's people, and HERIDAL val (0.22, two other unseen locations) is no better, so the gap isn't down to which locations went into test. The combined val AP50 fell to 0.862 only because HERIDAL val is now part of it.

Tiling helps on HERIDAL: 0.215 tiled against 0.152 on whole frames, since whole 853×640 frames shrink to 640 and people shrink with them.

Most misses are real misses, not loose boxes. When a box only has to overlap a person by 25% (IoU 0.25), the current RGB model's tiled AP50 on HERIDAL test rises to 0.389 and recall to 0.30 at precision 0.76. About 70% of HERIDAL's people still get no box at all.

SARD and NII-CU-MAPD don't hold the model back on HERIDAL. Trained on HERIDAL alone, nano reached 0.195 AP50 and 0.20 recall on HERIDAL test, against 0.215 and 0.22 for the mixed model. With 582 test people, recall moves by about ±0.02 from sampling alone, so the two are level on HERIDAL. Without the other datasets, though, the model can't detect anyone in SARD (AP50 0.001), so it would be useless at the robot's close range.

Weighting HERIDAL up made things worse. Listing HERIDAL 3×, picking `best.pt` on HERIDAL val and narrowing the random rescale to ±25% gave 0.166 AP50 with `best.pt` and 0.122 with `last.pt`, and SARD fell from 0.945 to 0.832. The three changes went in together, so the run can't say which one hurt. Overfitting is the likely cause: HERIDAL val peaked at epoch 11 and never got back there (0.14 to 0.19 afterwards), which fits 1,090 frames from 9 locations being seen three times as often.

HERIDAL val is too small to pick an epoch. It has 174 people, and in the HERIDAL-only run its AP50 swung between 0.12 and 0.25 from one epoch to the next with no trend. Choosing `best.pt` on it picks noise (epoch 11 of 60 in the ×3 run). Keep picking on the combined val set.

Model size isn't the limit. Small beat nano by 1.6 AP50 on thermal, all of it on RGBTDronePerson, and lost on RGB (0.889 against 0.907, and 0.788 against 0.834 on NII-CU-MAPD). Nano stays the default.

Thermal overfits early. Both thermal models picked `best.pt` at epoch 28, and nano's val AP50 slid from 0.647 to 0.605 by epoch 100 while training loss kept dropping. The next thermal run should stop at 30 to 50 epochs.

Thermal is good on HIT-UAV and NII-CU-MAPD (recall 0.88 to 0.97 at 8 to 16 px) and weak on RGBTDronePerson (0.60), which has tiny people in dense street scenes and `crowd` boxes that are hard to match at IoU 0.5. HIT-UAV's numbers are optimistic because of its near-duplicates, and thermal has no held-out test, so we don't know how it does at a new site.

## Verdict

Neither model is ready for a real search. Both are good on the data they trained on and unproven or weak anywhere else.

The RGB model to use is YOLO26n + HERIDAL (`runs/rgb/yolo26n_e60_heridal`), run on 640 tiles. At locations it has never seen it finds about 22% of people in a single frame (30% if a rough box is enough), with about half its boxes correct at confidence 0.25. It keeps SARD (0.945) and NII-CU-MAPD (0.848) where they were. For an operator that's an aid that sometimes points at a person, not a detector to rely on. A hovering drone sees each person in many frames, which raises the chance of a hit over time, but misses tend to repeat on the same hard person, so per-frame recall is the honest number.

The thermal model to use is YOLO26n (`runs/thermal/yolo26n_e100`). It finds 88 to 97% of people at the drone's size on HIT-UAV and NII-CU-MAPD and 60% on RGBTDronePerson, but all three are its training sets' own splits. The last time a thermal model met a new site (HIT-UAV model on WiSARD), it fell to near zero, so its real performance is unknown.

What limits both is data, not the model or the training recipe. Neither a 3× larger model nor training on HERIDAL alone nor weighting HERIDAL up beat simply adding HERIDAL to the mix. The one change that moved RGB on unseen terrain was 1,090 frames of people at the drone's size in natural terrain, and those frames now seem used up: with or without the other datasets, HERIDAL takes nano to about 0.2 AP50 and no further.

## Next steps

In order. Score every RGB run on HERIDAL's test locations, tiled, against 0.215 AP50 and 0.22 recall, and keep picking `best.pt` on the combined val set.

1. More RGB data with people at the drone's size in natural terrain, one dataset per run so each one's effect is visible: NOMAD first (check its license), then a capped, re-split C2A sample.
2. Get a held-out thermal test. Without one, nothing says the thermal model works at a new site. WiSARD's thermal frames or AIResQ are the candidates.
3. Retrain thermal for 30 to 50 epochs; it peaked at epoch 28 in both runs.
4. If more RGB data still leaves 8 to 12 px recall low, try a P2 (stride-4) head for small objects, and download the HERIDAL original for scale augmentation from sharp frames.
5. On the operations side, flying at 30 m instead of 40 m makes a standing person about 13 px instead of 10 ([altitude table](#how-high-the-drone-can-fly)), and the current RGB model's recall is higher at 12 to 16 px than at 8 to 12 px (0.26 against 0.18).
6. Then run the [laptop test](#test-on-the-station-laptop) with the chosen models.

Don't repeat: weighting HERIDAL up, picking `best.pt` on HERIDAL val alone, or training RGB without SARD and NII-CU-MAPD.
