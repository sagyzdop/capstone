# Victim Detection

> **Status:** Draft · **Updated:** 2026-10-15

Person detector for the station. YOLO11 ([ultralytics](https://docs.ultralytics.com), AGPL-3.0), trained per modality: thermal on HIT-UAV, RGB on C2A. Data and analysis: [station/detection-data-analysis.md](../../station/detection-data-analysis.md).

## Setup

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install ultralytics
```

Raw data goes in `data/raw/<dataset>/`, converted data in `data/yolo/` (both git-ignored). Download links: [literature/datasets.md](../../literature/datasets.md).

## Pipeline

| Step | Command |
| --- | --- |
| Convert to single-class `person` YOLO | `python src/detection/prepare.py hit-uav --person-ids 0 --split train=IMG_DIR:COCO.json ...` |
| Analyse person sizes | `python src/detection/analyze.py data/yolo/hit-uav/images data/yolo/hit-uav/labels --out station/assets/hit-uav-analysis` |
| Dataset audit (all sets) | `python src/detection/audit.py --out station/assets/audit` |
| HERIDAL profile (Roboflow export in `data/raw/heridal-roboflow/`, also needs `scikit-learn scipy`) | `python src/detection/heridal_profile.py && python src/detection/heridal_cluster_sheets.py && python src/detection/heridal_scenes.py` |
| Recall per size vs imgsz / tiling (inference only) | `python src/detection/eval_sizes.py MODEL.pt wisard-vis val --imgsz 640 1280 --tile 640 --out OUT.json` |
| Train | `yolo detect train model=yolo11n.pt data=data/yolo/hit-uav.yaml epochs=50 patience=15 imgsz=640 batch=16 device=mps cache=ram` |
| Evaluate on test | `yolo detect val model=runs/.../weights/best.pt data=data/yolo/hit-uav.yaml split=test device=mps` |
| Detect (station) | `python src/detection/detect.py best.pt FOLDER_OR_IMAGE --out detections.json` |

HIT-UAV split arguments (COCO json from the `normal_json` folder):

```bash
R=data/raw/hit-uav/extracted/suojiashun-HIT-UAV-Infrared-Thermal-Dataset-b53106c/normal_json
python src/detection/prepare.py hit-uav --person-ids 0 \
  --split train=$R/train:$R/annotations/train.json \
  --split val=$R/val:$R/annotations/val.json \
  --split test=$R/test:$R/annotations/test.json
```

## Output format

`detect.py` writes a JSON list with one entry per detected person:

```json
[{"image": "frame_0001.jpg", "bbox_xyxy": [264.0, 319.0, 274.0, 331.0], "conf": 0.87}]
```
