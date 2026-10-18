# Changelog

> **Status:** Draft · **Updated:** 2026-10-18

Decisions and notable changes, newest first. Answers to questions from [open-questions.md](open-questions.md) are recorded here too. Categories: **Decided**, **Changed**, **Added**, **Removed**.

Superseded decisions are replaced rather than kept, so an older entry here always still holds. The
rationale and the numbers behind each one live in the linked document.

<!--
Entry template:
## YYYY-MM-DD — Short title
### Decided
- **Decision.** What was decided. Rationale: why.
### Changed / Added / Removed
- ...
-->

## 2026-10-18 — Detector and streams

### Decided
- **The station runs YOLO11n at 640 input for both modalities.** Rationale: YOLO11s buys 7.5 COCO mAP points for 3.3× the FLOPs, and the gap worth closing is training data, not capacity. 640 is the AP50 peak on HIT-UAV at 0.872; 1280 loses 12 points because the model has not seen people that large.
- **Two streams: thermal 640×512 at 30 FPS, RGB 1280×1024 at 10 FPS.** Rationale: 640×512 thermal is the best result we have, and RGB tiling beats resizing to 640 by 10× on AP50. Frame rates come from measured detector times (12.4 ms thermal, 494 ms tiled RGB), not from the link.
- **RGB drops to 1280×1024.** Rationale: coverage is 2·altitude·tan(HFOV/2), which has no sensor width in it, so a 1280 camera sees what a 4K camera sees. Resolution buys hover altitude, and 1280 already reaches the 8 px detection floor at 49 m, the same as thermal.
- **The drone sends full frames and the station does the tiling.** Rationale: tiling on the drone costs 4.3 MiB per frame instead of 1.8 MiB, and the station has the headroom.
- **Frames are JPEG over the station-hosted network.** Rationale: byte counts are known at every resolution, so one format covers both modalities. The detection output stays as `[{"image", "bbox_xyxy", "conf"}]`, which `src/detection/detect.py` already writes.

### Added to open questions
- The thermal model scores AP50 0.010 on real SAR footage against 0.872 on HIT-UAV. Retraining on HIT-UAV plus WiSARD is the highest-value experiment available. Blocking.
- No drone or camera has been chosen, so every image size, frame rate and range number is provisional. Blocking.

## 2026-10-18 — Link and coverage

### Decided
- **The station laptop is the access point.** Drone, robot and the operator's phone are clients on one network. Rationale: the station is already the orchestrator and the only compute node, so this avoids a second device to power or configure in rubble.
- **No separate access point for the phone.** Rationale: macOS caps Internet Sharing near 10 devices and we plan three. Worth revisiting only if the phone ever needs its own channel or VLAN.
- **5 GHz, 80 MHz, non-DFS, with 2.4 GHz as a rubble fallback.** Rationale: about 3× the throughput of 2.4 GHz and 3.5× the Fresnel range per metre of antenna height. Non-DFS because a mid-flight radar check would drop a safety link.
- **Design against 100 Mbit/s per link, not the 200 to 600 Mbit/s real-world maximum.** Rationale: we are a client with an unknown radio rather than an access-point vendor, and halving the pessimistic figure leaves headroom for a degraded link.
- **100 Mbit/s sustains to about 348 m.** Rationale: a measured 802.11ax throughput-against-RSSI curve through a free-space budget puts it at −76 dBm. The working range is 20 to 120 m, so rubble rather than distance is the limit.

### Added
- Link budget in [research/communication/](research/communication/). Image sizes are measured by re-encoding the repo's own SAR imagery; detector timings and AP50 figures come from the committed eval JSONs; range is calculated from a measured throughput curve. Radio numbers remain estimates, marked `?` pending measurement.

### Added to open questions
- Link loss is unimplemented. The station must keep working from its last detections and the drone must be able to return. Blocking.
- The two drone streams take 71 Mbit/s of the 100 Mbit/s budget, and the robot's contribution is unbudgeted. How the remaining 29 Mbit/s splits between the robot stream and the operator UI is undecided. Blocking.
- Handed a whole cell sector rather than a building, does the robot search the rest or does the drone sweep? Both change the architecture. Blocking.

## 2026-10-18 — Hardware: a Raspberry Pi on both endpoints

### Decided
- **Both the drone and the robot run a Raspberry Pi.** The Robotics team confirmed this for the robot. One bill of materials, one provisioning process and shared spares.
- **The Pi's onboard radio is not good enough.** We need 74 Mbit/s (71.4 for the two drone streams, 2.6 for the robot) against a measured 80 to 110 Mbit/s for the onboard 1×1 trace antenna. That is 1.1 to 1.5× margin, spent before any range loss, and throughput falls off a cliff below the top MCS. Recommend a Pi 5 with an MT7921AUN USB adapter and a 5 GHz antenna on the airframe, about $110–135 and 80 g. A Pi 4 is acceptable if weight is tight; a Jetson Orin Nano is wasted, since detection is forbidden on the drone.
- **A companion computer, not a flight-controller radio.** An ESP32 is 2.4 GHz only at 11 to 20 Mbit/s, three and a half times short, and an MCU cannot JPEG-encode at 30 FPS alongside flight control. The Pi also lets the drone record to SD, so a dropped link does not lose frames.

### Changed
- Robot capabilities in [ground-robot/capabilities.md](ground-robot/capabilities.md) record the Raspberry Pi with source and date, and list the Pi model, radio and antenna as still open.

### Added to open questions
- Which Pi model, and which radio? A Pi Zero 2W has no 5 GHz and is ruled out.

## 2026-10-18 — Hover over a known collapse site

### Decided
- **The drone hovers over a known collapse site, not over a cell sector.** Rationale: one hover images 0.0025 km² at 40 m and never grows, against a candidate zone of about 28 km². An operator narrows the carrier sector to a building before deployment and the station searches nothing. Coverage is a human problem, not an autonomy problem.
- **The hover ceiling is 49 m.** Rationale: set by the 8 px detection floor for a standing person, which thermal at 640×512 and RGB at 1280×1024 reach at the same altitude.

## 2026-10-18 — Repository structure

### Changed
- **`docs/` removed.** The overview moved to [README.md](README.md), the station-internal diagram to [station/README.md](station/README.md), the link budget and rates to [research/communication/](research/communication/), and the assumptions to [open-questions.md](open-questions.md).
- **Dataset work moved to [research/datasets/](research/datasets/).** It had accumulated under `station/`, which is a subsystem rather than a research folder.
- **[GLOSSARY.md](GLOSSARY.md) added at the root**, superseding `docs/glossary.md`. New terms go there rather than being explained inline in several places.
- Conventions: unverified assumptions are logged in [open-questions.md](open-questions.md) alongside open questions, each with the risk if it turns out false.

## 2026-10-18 — Dataset analysis

### Added
- Per-dataset profiles in [research/datasets/dataset-profiles.md](research/datasets/dataset-profiles.md): size, distinct backgrounds, persons per image, pixels per person, contrast, sharpness and crowding, each as mean plus percentiles, for HIT-UAV, C2A, both WiSARD modalities and HERIDAL.
- Dataset suitability audit in [research/datasets/dataset-suitability.md](research/datasets/dataset-suitability.md). Findings: C2A val/test leak (98% of scenes shared with train), HIT-UAV flag 1 is night, the thermal model does not transfer to WiSARD IR (AP50 0.87 to 0.01), tiling is required for 4K RGB, RGB–IR alignment supports late fusion only.
- HERIDAL profile, on the Roboflow 640×640 export (`src/detection/heridal_profile.py`). Findings: 44 of 101 test images have a near-duplicate in train or valid, its people are the smallest of any set at a median 126 px², 70% are low-contrast in grey level, 35.5% of frames are empty, 11 scene types. Verdicts in the suitability audit.

## 2026-10-15 — Detection datasets shortlisted

### Decided
- **Detector targets RGB and thermal.** RGB is the main path; thermal (HIT-UAV) is analysed first because it is the smallest download.

### Added
- Dataset shortlist in [research/datasets/datasets.md](research/datasets/datasets.md).
- `src/detection/analyze.py`: person-size versus model input resolution.

## 2026-10-04 — Pivot to a stationary, station-centric architecture

### Decided
- **The drone is stationary.** It flies to a point and hovers there instead of sweeping the area.
- **The station is the orchestrator and the only compute node.** All processing runs on the station laptop.
- **No processing runs on the drone.** It only senses and streams. The "processes the data, locates and tags a victim" step in the scenario diagram happens on the station.
- **The station is also stationary.** "Moving station" means a vehicle carrying laptop, drone and robot drives to a predefined location, then stays there.
- **Victim-location prior comes from cellular data.** Rescue teams request last-known-location data from mobile carriers to choose where to go.
- **The robot's drop point is known** in advance.
- **The ground robot is a spherical "tumbleweed" rolling robot**, built by the Robotics team.

### Changed
- Orchestration moved from the UAV to the station.
- Drone–station and robot–station communication is WiFi.

### Added
- Repository structure and templates.
- Initial [open questions](open-questions.md).
