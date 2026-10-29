# Spec

What the team has agreed to build. Anything still under discussion is in [QUESTIONS.md](QUESTIONS.md), and moves here once it is settled. The numbers behind each decision are in [research/](research/), and git history keeps the older versions.

## Scope

In scope:

- victim detection on the station, from the drone's and the robot's RGB and thermal streams;
- the operator map;
- the operator driving the robot from the station, steering by the robot's GPS position drawn on the drone footage (the robot's own camera is optional for this), and receiving its streams;
- two-way audio between the operator and the victim, through the robot;
- decision-making by an agent (RL or decision-theoretic planning), built on top of operator control. How is still open (QUESTIONS.md);
- evaluation as a live demo with the Robotics team, plus detection scores against a baseline.

Out of scope:

- path planning and autonomous navigation, for both the vehicle and the robot, until detection works. A person drives the vehicle and the operator drives the robot. Supervisors still have to agree (QUESTIONS.md item 2);
- robot locomotion and hardware design, which belong to the Robotics team;
- carrier-side location services, which we assume are available.

## System

| Decision | Why |
| --- | --- |
| A vehicle carries the station laptop, drone and robot to a predefined site and parks there. | Defines a fixed station. A moving vehicle is proposed in QUESTIONS.md. |
| The site is a known collapse site, chosen before deployment. Rescue teams get last-known phone locations from mobile carriers, which gives a cell sector, and an operator narrows that to one building. | One hover at 40 m images about 58 × 43 m (0.0025 km²) and never grows. An urban cell sector is about 28 km², roughly 11,000 times larger, so the drone cannot search it. |
| The drone flies to one point and hovers. | Follows from the line above. |
| No processing runs on the drone. It captures and streams. | The station has the compute. |
| The station is the only compute node and the orchestrator: detection, fusion, tracking, the map and the robot's remote control all run there. | One machine to power and configure on site. |
| The ground robot is a spherical "tumbleweed" rolling robot built by the Robotics team. | Their design. |
| Drone and robot each run a Raspberry Pi. The Robotics team confirmed this for the robot on 2026-10-18. | One bill of materials, one setup process, shared spares. A Pi also records to SD, so a dropped link loses no frames. |
| The Pi's onboard WiFi is not enough; it needs a USB adapter and an external 5 GHz antenna. | The drone's load is about 71 Mbit/s against a measured 80 to 110 Mbit/s for the onboard 1×1 trace antenna, so the margin is spent before any range loss. Recommended: Pi 5 + MT7921AUN adapter, about $110 to 135 and 80 g mounted. Pi Zero 2W is out (no 5 GHz). An ESP32 is out (2.4 GHz only, 11 to 20 Mbit/s, cannot JPEG-encode at 30 FPS while flying). |
| The station laptop is the WiFi access point; drone and robot join as clients. | No extra powered device on site. Sharing costs 30 to 40% throughput, and macOS allows about ten clients. |
| 5 GHz, 80 MHz, non-DFS channel. 2.4 GHz is the fallback in rubble. | About 3× the throughput of 2.4 GHz. A DFS radar check mid-flight would drop the link. |
| Design against 100 Mbit/s per link. | Half of a pessimistic 200 Mbit/s client rate. A measured 802.11ax curve puts 100 Mbit/s at about 348 m in free space; the working range is 20 to 120 m, so rubble, at 10 to 30 dB per dense wall, is the real limit. |
| The hover ceiling is 49 m with the assumed cameras; 40 m is the safe working height. | Below 8 px a standing person is mostly missed; thermal at 640×512 and RGB at 1280×1024 tiled both reach 8 px at 49 m and 10 px at 40 m. Lying people stay visible in thermal to about 80 m. Real SAR datasets fly at 40 to 65 m ([comparison](research/datasets/README.md#how-high-the-drone-can-fly)). |

Setup commands, coverage tables and the full link budget: [research/communication/](research/communication/).

## Streams

The drone and the robot carry the same modules: the same RGB camera, thermal camera, Raspberry Pi and WiFi adapter, and the same streamer software. Each sends RGB and thermal as two separate streams of JPEG frames, each frame with a timestamp and the platform's GPS position and heading (the drone adds altitude and camera angle). The streams differ only in resolution and frame rate, because the people they look at differ in size.

What `imgsz=640` needs: the model sees at most 640 px across per pass, and people must be at least 8 px (ideally 10) at that input. A frame wider than 640 only helps if the station cuts it into 640×640 tiles (20% overlap) and runs the model on each, which costs one detector pass per tile.

| Stream | Sent as | At the model | Person size | FPS (predicted) | Bandwidth |
| --- | --- | --- | --- | --- | --- |
| Drone thermal | 640×512, native | as is, 1 pass | 10 px standing at 40 m, 8 px at 49 m | 30 | 34 Mbit/s |
| Drone RGB | 1280×1024 | 6 tiles of 640×640 | 10 px at 40 m, 8 px at 49 m | 10 | 37 Mbit/s |
| Robot thermal | 640×512, native | as is, 1 pass | large: people are metres away | 5 | about 6 Mbit/s |
| Robot RGB | 640×512, resized on the Pi | as is, 1 pass | large | 5 | about 5 Mbit/s (estimate) |

Total about 82 of the 100 Mbit/s budget, plus audio and telemetry.

| Decision | Why |
| --- | --- |
| Drone RGB is sent at 1280×1024 and tiled on the station, not resized. | Resizing to 640 halves every person, to 5 px at 40 m, so RGB would only work below about 25 m. A 4K camera would cover the same ground (coverage is 2·altitude·tan(HFOV/2), with no sensor width in it) for 4× the bytes. On 4K RGB, tiling scored AP50 0.324 against 0.030 for resizing to 640. |
| Tiling happens on the station. | Tiling on the drone sends 4.3 MiB per frame instead of 1.8 MiB. |
| The robot sends 640×512 at 5 FPS. | At ground level people are metres away and large, so no tiling. A slow robot needs no more than 5 FPS, and it keeps the robot's share of the link small. |

All four streams go through the same two detectors and the same late fusion. Frame rates are predictions from YOLO11n timings until the [laptop test](research/datasets/README.md#test-on-the-station-laptop) replaces them, and the robot's bandwidth is scaled from the drone's frames. The detectors were trained only on drone footage, so how well they work from the robot's ground-level view is open (QUESTIONS.md).

## Detection

| Decision | Why |
| --- | --- |
| YOLO26 (Ultralytics), nano first, then small. | Nano: 2.4M parameters, 5.5 GFLOPs, 40.9 COCO mAP50-95. Small: 9.5M, 20.9 GFLOPs, 48.6. Small is the step up if nano's accuracy falls short and the laptop has headroom. |
| Two separate models, one RGB and one thermal, each trained only on its own modality. Datasets with both modalities are split by modality before training. | Late fusion: the models run independently on their own streams. |
| Trained on the raw datasets with `imgsz=640`. | Ultralytics resizes on load, so no preprocessing step. |
| Training sets: SARD (RGB), NII-CU-MAPD (RGB + thermal), RGBTDronePerson (RGB + thermal). | Details, caveats and results: [research/datasets/](research/datasets/README.md). |
| Detector output is JSON, one record per box: `{"image", "bbox_xyxy", "conf"}`. | Already written by `src/detection/detect.py`. |

### Late fusion

1. Each model produces boxes in its own image.
2. Thermal boxes are mapped into RGB pixels with a homography calibrated once for the real camera pair. The two cameras have different fields of view: on WiSARD, thermal covers 64% of the RGB frame, with a median error of 7.7 thermal pixels after a linear fit. That is good enough for matching boxes, not for merging pixels.
3. Boxes from the two modalities that overlap (IoU above a threshold, to be tuned) are one person. Their combined confidence is `1 − (1 − p_rgb)(1 − p_thermal)`, so agreement raises it.
4. A box seen by only one model is kept with its own confidence, tagged with that modality.
5. Across frames, a tracker links boxes into one victim. Each victim becomes one map marker, placed on the ground using the telemetry of the drone or robot that saw it.

## Operator map

On the station screen, so it costs nothing on the network.

- Satellite basemap, downloaded before the mission, since there may be no internet on site. It shows the area before the quake, so live imagery is drawn over it.
- The latest drone frame, projected onto the map from the drone's GPS, altitude, heading and camera angle. For the demo, only the latest frame. Stitching frames into a mosaic is a later step.
- The drone's current footprint outlined, plus a layer showing how long ago each area was last in view.
- Victim markers, which stay after the person leaves the frame. Each shows last-seen time, modality (RGB, thermal or both) and confidence.
- Confirm and reject on every marker, so a false positive never sends the robot.
- Robot position from its GPS, its track, battery and link state.
- Victim status from the marker lifecycle in the README: detected, confirmed, dispatched, verified, then a START colour.
- Link health for every stream, so a frozen feed is not mistaken for an empty scene. Audio failure in particular must be visible: two-way conversation needs under 300 ms round trip, and WiFi reassociation takes seconds.

## Robot interface

What we need from the Robotics team. They have not reviewed it yet.

| Requirement | Status |
| --- | --- |
| Accept drive commands (speed and turn) from the station over WiFi | Proposed |
| Stop on its own when commands stop arriving, for example after a dropped link | Proposed |
| Stream RGB and thermal as JPEG frames, 640×512 at 5 FPS each ([Streams](#streams)). If the operator drives by this video, camera-to-screen plus command delay should stay under about 300 ms | Proposed |
| Two-way audio with the victim | Proposed |
| Carry the same cameras, Pi and WiFi adapter as the drone, plus a microphone, speaker and GPS module | Proposed |
| Report its GPS position, battery and health | Proposed |

The robot does not talk to the drone. Both report to the station, which draws the robot's GPS position on the drone footage and the map. That is enough to steer by; the robot's video helps up close.

Known robot facts, with source and date:

| Attribute | Value | Source |
| --- | --- | --- |
| Platform | Spherical "tumbleweed" rolling robot | Robotics team, 2026-10-04 |
| Onboard computer | Raspberry Pi, same as the drone | Robotics team, 2026-10-18 |
| GPS module | Can be carried | Our team, 2026-10-29 |

We assume the same Pi 5 and MT7921AUN adapter as the drone until they confirm. Antenna placement, size and weight are unknown (QUESTIONS.md).

## Assumptions

Things we treat as true without having checked. They mark the edge of what we build; if one turns out false, the design changes.

| Assumption | If false |
| --- | --- |
| Rescue teams can get last-known phone locations from carriers (CDR / cell site analysis), and an operator can narrow the sector to one building. For the demo, the carrier data and the collapse site are simply given. | We don't know where to go. |
| The vehicle can reach the site and park. | The station's position and coverage change. |
| The robot's drop point is known. | The robot has to locate itself from scratch. |
| WiFi connects station, drone and robot, on one network run by the station laptop. | Video and control links fail. |
| Each link sustains 100 Mbit/s. | Every image size and frame rate scales down with it. |
| Rubble costs no more than one wall's attenuation on the drone's line of sight. | The link drops, and no return behaviour exists yet. |

## Terms

| Term | Meaning |
| --- | --- |
| Station | The laptop on the vehicle. |
| Vehicle | Carries the station, drone and robot. Previously called the "moving station". |
| Operator | The person at the station. |
| CDR | Call detail record: the carrier's log of which tower a phone used. |
| Candidate zone | The cell sector the carrier data gives; hundreds of metres to kilometres across. |
| Tagging | Placing a victim marker on the map so the operator can send the robot to it. |
| START | Simple Triage And Rapid Treatment: red immediate, yellow delayed, green minor, black deceased or expectant. |
| `imgsz` | Model input size in pixels. Not the camera resolution. |
| Tiling | Splitting a large frame into overlapping 640×640 crops (20% overlap) and running the model on each. |
| AP50 | Average precision at IoU ≥ 0.5. Our main accuracy number. |
| Late fusion | Combining the RGB and thermal models' boxes, rather than their pixels or features. |
| GSD | Ground sampling distance, metres of ground per pixel: 2·altitude·tan(HFOV/2) ÷ image width. |

Image measurement terms (person size, contrast, sharpness, crowding) are defined in [research/datasets/](research/datasets/README.md#measures).
