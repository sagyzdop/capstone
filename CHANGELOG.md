# Changelog

> **Status:** Draft · **Updated:** 2026-10-15

All decisions and notable changes are recorded here, newest first. Answers to questions from [open-questions.md](open-questions.md) are recorded here too. Categories: **Decided**, **Changed**, **Added**, **Removed**.

<!--
Entry template:
## YYYY-MM-DD — Short title
### Decided
- **Decision.** What was decided. Rationale: why.
### Changed / Added / Removed
- ...
-->

## [Unreleased]

### Added
- Per-dataset profiles in [station/dataset-profiles.md](station/dataset-profiles.md): size, distinct backgrounds (`src/detection/backgrounds.py`), persons per image, pixels per person, contrast, sharpness and crowding, each as mean + percentiles.
- Dataset suitability audit in [station/dataset-suitability.md](station/dataset-suitability.md) (`src/detection/audit.py`, `src/detection/eval_sizes.py`). Findings: C2A val/test leak (98% of scenes shared with train), HIT-UAV flag 1 = night, thermal model does not transfer to WiSARD IR (AP50 0.87 → 0.01), tiling is required for 4K RGB, RGB↔IR alignment supports late fusion only.

## 2026-10-15 — Detection datasets shortlisted

### Decided
- **Detector targets RGB and thermal.** RGB is the main path; thermal (HIT-UAV) is analysed first because it is the smallest download.

### Added
- Dataset shortlist in [literature/datasets.md](literature/datasets.md).
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
