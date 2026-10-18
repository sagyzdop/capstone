# Datasets

> **Status:** Draft · **Updated:** 2026-10-15

Candidate datasets for aerial person detection (RGB / thermal, disaster-relevant). "?" = not verified from the source page.

| Name | Modality | Disaster-relevant | License | Size | Link | Status |
| --- | --- | --- | --- | --- | --- | --- |
| C2A (2024) | RGB | Yes: synthetic humans (lying, kneeling, bent…) pasted on AIDER disaster scenes (rubble, flood, fire). 10,215 imgs, 360k+ persons, 47% < 10 px | ? (paper CC BY 4.0; data not stated) | ? | [GitHub](https://github.com/Ragib-Amin-Nihal/C2A), [Kaggle](https://www.kaggle.com/datasets/rgbnihal/c2a-dataset) | Selected (RGB train). 4.9 GB zip on Google Drive. YOLO + COCO labels, pose field ignored → `person` |
| HERIDAL (2019) | RGB | Partly: real SAR, wilderness, lying/hidden people, ~4000×3000 | CC BY 3.0 (Zenodo derivative) | 8.3 GB | [Zenodo 5662351](https://zenodo.org/records/5662351) | Selected (RGB real-world test). VOC format |
| NOMAD (2024) | RGB | Partly: real, 100 actors walking/lying/hiding, 10–90 m altitude, visibility levels. 42,825 frames | ? (data not stated) | ? | [GitHub](https://github.com/ArtRuss/NOMAD) | Evaluating: best real data, blocked on license and size |
| WiSARD (2022) | RGB + thermal (15,453 synced pairs) | Partly: real wilderness SAR, day/night | Permissive notice, not a named license | 40.5 GB (sample 0.97 GB) | [Project site](https://sites.google.com/uw.edu/wisard/) | Selected (sample only, cross-dataset test). Format ? |
| HIT-UAV (2023) | Thermal | No: campus/roads, 60–130 m, day + night. 2,898 imgs, 640×512 | CC0 (confirmed via Zenodo API; GitHub says CC BY 4.0) | 815 MB | [Zenodo 7633134](https://zenodo.org/record/7633134) | Selected (thermal train). Downloaded. v1.2.1 ships COCO json + VOC xml, no YOLO labels; 12,312 persons |
| VisDrone-DET (2018) | RGB | No: urban crowds | Academic use ? | 1.8 GB | [GitHub](https://github.com/VisDrone/VisDrone-Dataset) | Candidate: generic pretraining if needed |
| TinyPerson (2020) | RGB | No: beach/sea, < 20 px | ? | ? | [GitHub](https://github.com/ucas-vg/PointTinyBenchmark) | Candidate |
| BIRDSAI (2020) | Thermal | No: savanna anti-poaching, mostly night | CDLA-Permissive | 3.7 GB real | [LILA](https://lila.science/datasets/conservationdrones/) | Candidate: thermal backup |
| AIResQ (2025) | Thermal | Yes: SAR, 9,788 imgs | ? | ? | [Nature Sci. Data](https://www.nature.com/articles/s41597-026-07663-9) | Candidate: full set on request |
| SARD (2021) | RGB | Yes: actors, pose classes incl. lying | Not stated | 4.4 GB | [IEEE DataPort](https://ieee-dataport.org/documents/search-and-rescue-image-dataset-person-detection-sard) | Rejected: paid subscription |
| RGBTDronePerson (2023) | RGB + thermal | No: tiny persons | ? | ? | [code](https://github.com/NNNNerd/mmdet-rgbtdroneperson) | Candidate: data link not found |
| Okutama-Action (2017) | RGB video | No: actions on a field | Non-commercial ? | ? | [GitHub](https://github.com/miquelmarti/Okutama-Action) | Rejected: action labels, not SAR |
| AIDER (2019) | RGB | Yes | ? | ? | Zenodo 3888300 | Rejected: image-level labels, no person boxes (used inside C2A) |
| DroneVehicle | RGB + IR | No | ? | ? | — | Rejected: no person class |
| LLVIP (2021) | RGB + IR | No | ? | ? | [GitHub](https://github.com/bupt-ai-cz/LLVIP) | Rejected: street cameras, not aerial |
| Caltech Aerial RGB-T (2024) | RGB + thermal | No | ? | ? | [GitHub](https://github.com/aerorobotics/caltech-aerial-rgbt-dataset) | Rejected: segmentation only |

Status values: `Candidate` · `Evaluating` · `Selected` · `Rejected` (state the reason).

## Notes

- Licenses marked `?` must be confirmed (email authors) before anything trained on them is published.
- Train-on-synthetic (C2A), test-on-real (HERIDAL, WiSARD) measures the domain gap directly.
- Persons are tiny in all sets; downscaling to the model input size makes it worse. Step 2 measures this.
