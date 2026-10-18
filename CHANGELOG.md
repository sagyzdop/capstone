# Changelog

> **Status:** Draft · **Updated:** 2026-10-18

All decisions and notable changes are recorded here, newest first. Answers to questions from [open-questions.md](open-questions.md) are recorded here too. Categories: **Decided**, **Changed**, **Added**, **Removed**.

<!--
Entry template:
## YYYY-MM-DD — Short title
### Decided
- **Decision.** What was decided. Rationale: why.
### Changed / Added / Removed
- ...
-->

## 2026-10-18 — Interfaces, and the bandwidth that does not fit

### Decided
- **Drone frames are JPEG over the station-hosted network.** Rationale: every resolution from 128×128 to 4K transmits at known byte counts, so one format covers both modalities.
- **Detection output stays as it is.** `[{"image", "bbox_xyxy", "conf"}]`, already written by `src/detection/detect.py:16`.

### Added
- Rates and message formats in [docs/interfaces.md](docs/interfaces.md), replacing "TBD". Frame rates are the measured detector limits, byte counts come from the re-encoded SAR imagery.

### Added to open questions
- The drone streams exceed the link. Thermal at 30 FPS is 34 Mbit/s and RGB at 10 FPS is 37; adding 4K reaches 101, the whole 100 Mbit/s budget, leaving nothing for the robot or the operator. Three options are set out in the interfaces doc. Blocking, since the team picks the streams.

## 2026-10-18 — Communication link budget

### Decided
- **The station laptop is the access point.** Drone and robot join one network hosted by the station. Rationale: the station is already the orchestrator and the only compute node, so this keeps every network decision in one place with no second device to power or configure in rubble.
- **5 GHz, 80 MHz, non-DFS channel.** Rationale: ~3× the throughput of 2.4 GHz and 3.5× the Fresnel range per metre of antenna height. Non-DFS because a mid-flight radar check would drop a safety link. 2.4 GHz kept as a fallback for range through rubble.
- **Design against 100 Mbit/s per link, not the 200–600 Mbit/s real-world maximum.** Rationale: we are a WiFi client with an unknown radio, not an AP vendor, and we halve the pessimistic figure to leave headroom for a degraded link.
- **No separate access point for the operator's phone.** The station is already the AP, so the phone is simply a third client on the same SSID. Rationale: macOS caps Internet Sharing near 10 devices and we plan three; a dedicated AP is only worth buying if we later want the phone on a different VLAN or channel.
- **Thermal at 640 input, 30 FPS; RGB at 640 tiles, 10 FPS.** Rationale: 640 is the AP50 peak for thermal (0.872) and going to 1280 loses 12 AP points because the model has not seen people that large; RGB tiling is 10× better than resizing to 640. Frame rates are set by the measured detector time (12.4 ms thermal, 494 ms tiled RGB), not by the link.
- **Do not use a larger YOLO variant.** Rationale: YOLO11s buys 7.5 COCO mAP points for 3.3× the FLOPs, and the gap we need to close is training data, not capacity. The tiled RGB path is already the slowest thing we run.
- **The drone sends full frames; the station tiles.** Rationale: tiling 4K into 32 tiles costs 4.3 MiB instead of 1.8 MiB, and the station has the headroom to do it.
- **Supported resolutions run from 128×128 to 3840×2160, and every one of them transmits.** Rationale: the link carries all of them; what changes with resolution is detector throughput, not the radio. 640×512 thermal is the working stream.
- **The 100 Mbit/s figure sustains to about 348 m.** Rationale: converting a measured 802.11ax throughput-against-RSSI curve through a free-space budget puts 100 Mbit/s at −76 dBm, or 348 m at 20 dBm with 2 dBi antennas. At the 20 to 120 m working range the link has more headroom than the stream needs, so rubble, not distance, is what limits us.

### Added
- Link budget in [research/communication/](research/communication/): supported resolutions, frame rates, distance, and model choice. Image sizes are measured by re-encoding the repo's own SAR imagery; detector timings and AP50 figures come from the committed eval JSONs; range is calculated from a measured throughput-against-RSSI curve. Radio numbers remain estimates and are marked `?` pending measurement.

### Added to open questions
- Link loss is unimplemented: the station must survive on last detections and the drone must be able to return. Blocking.
- The detector scores AP50 0.010 on real SAR footage versus 0.872 on HIT-UAV. Retraining on HIT-UAV + WiSARD is the highest-value experiment available. Blocking.
- No drone or camera has been chosen, so every image size, frame rate and range number is provisional. Blocking.

## [Unreleased]

### Added
- HERIDAL profile in [station/heridal-profile.md](station/heridal-profile.md) (`src/detection/heridal_profile.py`), on the Roboflow 640×640 export. Same eight points as the other profiles, with an at-a-glance row in the audit.py metric definitions. Findings: 44 of 101 test images have a near-duplicate in train/valid, people are the smallest of all sets (median 126 px²), 70% are low-contrast in grey level, 35.5% of frames are empty, 11 scene types.
- Per-dataset profiles in [research/datasets/dataset-profiles.md](research/datasets/dataset-profiles.md): size, distinct backgrounds (`src/detection/backgrounds.py`), persons per image, pixels per person, contrast, sharpness and crowding, each as mean + percentiles.
- Dataset suitability audit in [research/datasets/dataset-suitability.md](research/datasets/dataset-suitability.md) (`src/detection/audit.py`, `src/detection/eval_sizes.py`). Findings: C2A val/test leak (98% of scenes shared with train), HIT-UAV flag 1 = night, thermal model does not transfer to WiSARD IR (AP50 0.87 → 0.01), tiling is required for 4K RGB, RGB↔IR alignment supports late fusion only.

## 2026-10-15 — Detection datasets shortlisted

### Decided
- **Detector targets RGB and thermal.** RGB is the main path; thermal (HIT-UAV) is analysed first because it is the smallest download.

### Added
- Dataset shortlist in [research/datasets/datasets.md](research/datasets/datasets.md).
- `src/detection/analyze.py`: person-size vs model input resolution analysis.

## 2026-10-04 — Pivot to a stationary, station-centric architecture

### Decided
- **The drone is stationary.** It flies to a point and hovers there instead of sweeping the area. Rationale: _to be added by the team_.
- **The station is the orchestrator and the only compute node.** All processing (detection, path planning, orchestration) runs on the station laptop. Rationale: _to be added by the team_.
- **No processing runs on the drone.** It only senses and streams. The "processes the data, locates and tags a victim" step in the scenario diagram happens on the station.
- **The station is also stationary.** "Moving station" means a vehicle carrying laptop, drone and robot drives to a predefined location, then stays there.
- **Victim-location prior comes from cellular data.** Rescue teams request last-known-location data of phones in the area from mobile carriers (CDR / cell site analysis) to choose where to go. See [docs/assumptions.md](docs/assumptions.md).
- **The robot's drop point is known** in advance.
- **The ground robot is a spherical "tumbleweed" rolling robot**, built by the Robotics team.

### Changed
- Orchestration moved from the UAV to the station.
- Drone–station and robot–station communication is WiFi (video and images).

### Added
- Repository structure and templates.
- Initial [open questions](open-questions.md).
