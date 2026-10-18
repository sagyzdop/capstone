# Detection Data Analysis

> **Status:** Draft · **Updated:** 2026-10-15

How big victims look in the training data, and which model input size (`imgsz`) keeps them detectable. Generated with `src/detection/analyze.py`; prepared with `src/detection/prepare.py` (single class `person`, images without persons kept as negatives). Full audit (quality, coverage, leakage, measured recall vs imgsz, RGB + IR): [dataset-suitability.md](dataset-suitability.md). Note: the imgsz tables below assume no upscaling; YOLO's letterbox does upscale small images (most of C2A), adding pixels but not detail.

## HIT-UAV (thermal)

| Split | Images | Persons |
| --- | --- | --- |
| train | 2,029 | 8,533 |
| val | 290 | 1,168 |
| test | 579 | 2,611 |
| **total** | **2,898** (1,691 with persons) | **12,312** |

- All images are 640×512, 8-bit thermal (grey).
- Person size (√ of box area): p5 9.9 px, median 14.9 px, p95 24.4 px. Almost all persons are 8–30 px: a **tiny-object** problem.
- Size drops with altitude: median 16 px at 60 m → 11–12 px at 120–130 m.
- Persons per filename flag: 9,573 with flag `1`, 2,739 with flag `0`. The README does not say which flag is night (unverified).

![Person size histogram](assets/hit-uav-analysis/person_sizes.png)

### Model input size

| imgsz | Median person px | Persons < 8 px |
| --- | --- | --- |
| 320 | 7.4 | 59% |
| 640 (native) | 14.9 | 1% |
| 960 / 1280 | 14.9 (+ upscaling) | 1% |

![Same image at each imgsz](assets/hit-uav-analysis/imgsz_examples.png)

**Takeaways**

- `imgsz=320` is ruled out: it shrinks most persons below 8 px.
- Train and run at **640** (native). Try **960** too: YOLO upscales the image, which adds no detail but gives the tiny persons more feature-map cells. Measure the mAP gain against inference time on the laptop.
- No disaster scenes (campus, roads). Lying or occluded people are not labelled separately. Expect a domain gap on real rubble.

## C2A (RGB, synthetic disaster)

| Split | Images | Persons |
| --- | --- | --- |
| train | 6,129 | 215,821 |
| val | 2,043 | 72,123 |
| test | 2,043 | 72,523 |

- Every image has persons (no negatives). Average 35 persons per image.
- Image sizes vary widely: 80% of train images have a long side < 640 px, so YOLO upscales them at `imgsz=640`.
- Persons are even tinier than in HIT-UAV: median 12 px, p5 3.5 px. **35% are < 8 px even at full resolution**, so recall on C2A will be capped no matter the imgsz.

| imgsz | Median person px | Persons < 8 px |
| --- | --- | --- |
| 320 | 7.7 | 52% |
| 640 | 11.0 | 38% |
| 960 / 1280 / full | 11.6–12.0 | 35–36% |

![C2A person sizes](assets/c2a-analysis/person_sizes.png)

## WiSARD sample (real SAR, evaluation only)

One flight (Mt Erie, 2021-04-17), 264 RGB frames at 3840×2160 and 264 thermal frames at 640×512, 1 class (human). Labels ship in YOLO format.

| Modality | Persons | Median person px (full res) | Persons < 8 px at imgsz 640 |
| --- | --- | --- | --- |
| RGB | 1,022 | 66.7 | 4% (11 px median) |
| Thermal | 1,006 | 17.2 | 0% |

- 4K RGB frames shrink 6× at `imgsz=640`: the 67 px persons become ~11 px. `imgsz=960` gives 17 px with 0% < 8 px. **Tiling** the 4K frame into 640 crops would keep full detail; worth testing if recall on real RGB is low.
- The sample is one flight in one place, so treat its numbers as a sanity check, not a benchmark.
