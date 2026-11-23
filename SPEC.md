# Spec

What the team has agreed to build. Anything still under discussion is in [QUESTIONS.md](QUESTIONS.md), and moves here once it is settled. The numbers behind each decision are in [research/](research/), and git history keeps the older versions.

## Scope

In scope:

- two sensor modules that work on any platform of their kind: a UAV module for drones and a UGV module for ground robots ([Modules](#modules));
- victim detection on the station, from the UAV module's RGB stream;
- the operator map;
- controlling the ground robot from the station: the operator drives it, or sends it to a victim's coordinates and it drives there itself, and can take over at any moment;
- two-way audio between the operator and the victim, through the UGV module;
- decision-making by an agent (RL or decision-theoretic planning), built on top of operator control. How is still open (QUESTIONS.md);
- evaluation as a live demo with the Robotics team, plus detection scores against a baseline.

Out of scope:

- thermal imaging. Drone thermal cameras that resolve a person at working altitude (640×512) cost thousands of dollars, and our thermal model was never tested on a site it didn't train on. The thermal runs stay in [research/datasets/](research/datasets/README.md) as a record;
- triage (START colours). A robot can check only 2 of START's 5 steps; the operator keeps a free-text note per victim instead;
- flying the drone. A pilot flies it with its own controller, and the drone's own failsafes (return-to-home on signal loss) apply;
- path planning beyond "drive to a GPS point", and the vehicle driving itself. A person drives the vehicle;
- robot locomotion, hardware, go-to-point driving and collision handling, which belong to the Robotics team;
- carrier-side location services, which we assume are available.

## System

| Decision | Why |
| --- | --- |
| A vehicle carries the station laptop, the WiFi router, the drone and the robot to the site and parks there. | Defines a fixed station. |
| The site is a known collapse site, chosen before deployment. Rescue teams get last-known phone locations from mobile carriers, which gives a cell sector, and an operator narrows that to one building. | One frame at 40 m images about 58 × 43 m (0.0025 km²). An urban cell sector is about 28 km², roughly 11,000 times larger, so the drone can't search it. |
| A pilot flies the drone with its own controller. Nothing on the station flies it. | No flight logic to build, and it works with any drone. |
| The station is the only compute node and the orchestrator: detection, the map and the robot's control all run there. Modules capture and stream. | One machine to power and configure on site. |
| The ground robot is a spherical "tumbleweed" rolling robot built by the Robotics team. | Their design. |
| A WiFi router on the vehicle is the access point. The station plugs into it by Ethernet; modules join over WiFi with fixed IP addresses. | Recent macOS no longer creates ad-hoc networks. On Ethernet, the station's traffic crosses the air once instead of twice. |
| The current router (Huawei HG658 V2) is temporary. It is 2.4 GHz only, so streams are sized to fit about 20 Mbit/s in total. | A dual-band router would allow more; see QUESTIONS.md. |
| The drone's ceiling is 49 m; 40 m is the safe working height. | Below 8 px a standing person is mostly missed; 1280 px RGB, tiled, reaches 8 px at 49 m and 10 px at 40 m. Lying people are about twice as large. Real SAR datasets fly at 40 to 65 m ([comparison](research/datasets/README.md#how-high-the-drone-can-fly)). |

Setup and the link budget: [research/communication/](research/communication/).

## Modules

A module is a Raspberry Pi with sensors that bolts onto a platform and talks only to the station. It can't read the platform's own telemetry, so it carries its own GPS and attitude sensor. Two types are built now; others can follow on the same core, for example a wearable module that shows rescuers on the map.

| | UAV module | UGV module |
| --- | --- | --- |
| Goes on | Any drone that can lift about 300 g and has a mount point | Any ground robot that accepts the [control commands](#ugv-module-interface) |
| Camera | RGB, pointing down | RGB, forward |
| Sends | Frames for detection, with pose | Video for the operator, position, battery, robot status |
| Receives | Nothing | Mode, drive and go-to commands, heartbeat |
| Audio | No | Two-way, with echo cancellation |
| Link to the platform | None; powered by its own battery | Serial or USB to the robot's controller |

Shared parts. Example parts fit the spec but haven't been bought or tested.

| Item | Spec we need | Example part |
| --- | --- | --- |
| Computer | Raspberry Pi 5. No detection runs on it; it encodes JPEG and streams, and records to SD so a dropped link loses no frames. | Raspberry Pi 5, 4 GB |
| RGB camera | At least 1280 px wide, about 66 to 72° HFOV, CSI or USB | Raspberry Pi Camera Module 3, standard lens (66° HFOV, 4608×2592), streamed as 1280×720 |
| GPS and compass | GPS module with a built-in compass, UART. About 2 to 5 m accuracy | u-blox NEO-M8N or M9N drone GPS module |
| Attitude | IMU giving roll, pitch and yaw, so each frame can be placed on the ground. At 40 m, 5° of tilt moves a victim about 3.5 m | BNO085 breakout |
| WiFi | USB adapter with an external antenna; the onboard trace antenna loses range next to batteries and motors | MT7921AUN adapter, for example the Alfa AWUS036AXML |
| Microphone and speaker (UGV only) | One USB speakerphone with echo cancellation | Any USB conference speakerphone |

## Streams

What `imgsz=640` needs: the model sees at most 640 px across per pass, and people must be at least 8 px (ideally 10) at that input. A frame wider than 640 only helps if the station cuts it into 640×640 tiles (20% overlap) and runs the model on each.

| Stream | Sent as | Used for | FPS | Bandwidth (estimate) |
| --- | --- | --- | --- | --- |
| UAV RGB | 1280×720 JPEG, tiled on the station | Detection: 10 px standing at 40 m | 3 to 5 | about 13 Mbit/s at 5 FPS |
| UGV RGB | 640×360 JPEG | The operator only; no detection | 5 | about 3 Mbit/s |

Each frame carries a sequence number, GPS time, and the module's position and attitude. Audio, telemetry and commands add under 1 Mbit/s.

| Decision | Why |
| --- | --- |
| UAV RGB is sent at 1280 px and tiled on the station, not resized. | Resizing to 640 halves every person, to 5 px at 40 m. A 4K camera covers the same ground for 4× the bytes. On 4K RGB, tiling scored AP50 0.324 against 0.030 for resizing to 640. |
| 3 to 5 FPS is enough. | The pilot flies by the drone's own video; the module's stream is only for detection, and each person stays in view for many frames. |
| The UGV stream isn't run through the detector. | The detector was trained on drone footage looking down. Up close, the operator sees the victim directly. |

Frame rates and bandwidth are estimates until the [laptop test](research/datasets/README.md#test-on-the-station-laptop) and a link test on the real router replace them.

## Detection

| Decision | Why |
| --- | --- |
| YOLO26 (Ultralytics), nano first, then small. | Nano: 2.4M parameters, 5.5 GFLOPs, 40.9 COCO mAP50-95. Small: 9.5M, 20.9 GFLOPs, 48.6. Small is the step up if nano's accuracy falls short and the laptop has headroom. |
| One RGB model, trained with `imgsz=640` on SARD, NII-CU-MAPD (RGB), HERIDAL (its training locations) and NOMAD (its training actors). | Details, caveats and results: [research/datasets/](research/datasets/README.md). |
| Detector output is JSON, one record per box: `{"image", "bbox_xyxy", "conf"}`. | Already written by `src/detection/detect.py`. |
| Each box is placed on the ground from the UAV module's position, altitude and attitude, and boxes from many frames that land on the same spot become one victim marker. | How close counts as "the same spot" is open (QUESTIONS.md). |

## Operator map

On the station screen, so it costs nothing on the network.

- Satellite basemap, downloaded before the mission, since there may be no internet on site. It shows the area before the quake, so live imagery is drawn over it.
- The latest drone frame, projected onto the map from the UAV module's pose. For the demo, only the latest frame. Stitching frames into a mosaic is a later step.
- The drone's current footprint outlined, plus a layer showing how long ago each area was last in view.
- Victim markers, which stay after the person leaves the frame. Each shows last-seen time and confidence.
- Confirm and reject on every marker, so a false positive never sends the robot.
- Robot position from its GPS, its track, battery, mode and link state.
- Victim status from the marker lifecycle in the README: detected, confirmed, dispatched, reached. A reached victim gets the operator's free-text note.
- Link health for every stream, so a frozen feed is not mistaken for an empty scene. Audio failure in particular must be visible: two-way conversation needs under 300 ms round trip, and WiFi reassociation takes seconds.

## UGV module interface

What we need from the Robotics team's robot. They have not reviewed it yet.

| Requirement | Status |
| --- | --- |
| Three modes set from the station: MANUAL (follow speed and turn commands), AUTO (drive to a given GPS point on its own) and HOLD (stop). Any manual command from the operator switches it to MANUAL | Proposed |
| In AUTO, report progress: driving, arrived (within about 5 m, GPS accuracy) or blocked (collision detected) | Proposed |
| Stop on its own when the station's heartbeat stops arriving for 1 s, in every mode | Proposed |
| Carry the UGV module and power it | Proposed |
| Report battery and health to the module | Proposed |

If the operator drives by the module's video, camera-to-screen plus command delay should stay under about 300 ms.

The robot doesn't talk to the drone. Both modules report to the station, which draws the robot's position on the drone footage and the map.

Known robot facts, with source and date:

| Attribute | Value | Source |
| --- | --- | --- |
| Platform | Spherical "tumbleweed" rolling robot | Robotics team, 2026-10-04 |
| Onboard computer | Raspberry Pi | Robotics team, 2026-10-18 |
| GPS module | Can be carried | Our team, 2026-10-29 |
| Autonomy | Can drive to a point, detecting collisions from motor voltage spikes | Robotics team, 2026-11 |

Antenna placement, size and payload are unknown (QUESTIONS.md).

## Assumptions

Things we treat as true without having checked. They mark the edge of what we build; if one turns out false, the design changes.

| Assumption | If false |
| --- | --- |
| Rescue teams can get last-known phone locations from carriers (CDR / cell site analysis), and an operator can narrow the sector to one building. For the demo, the carrier data and the collapse site are simply given. | We don't know where to go. |
| The vehicle can reach the site and park. | The station's position and coverage change. |
| The robot's drop point is known. | The robot has to locate itself from scratch. |
| WiFi connects the station and every module, on one network run by the router on the vehicle. | Video and control links fail. |
| The router carries about 20 Mbit/s for all streams together. | Frame rates scale down with it. |
| Rubble costs no more than one wall's attenuation on the line of sight to a module. | The link drops. |

## Terms

| Term | Meaning |
| --- | --- |
| Station | The laptop on the vehicle. |
| Vehicle | Carries the station, router, drone and robot. |
| Operator | The person at the station. |
| Pilot | The person flying the drone with its own controller. |
| Module | A Raspberry Pi with sensors that bolts onto a platform and streams to the station. UAV module for drones, UGV module for ground robots. |
| CDR | Call detail record: the carrier's log of which tower a phone used. |
| Candidate zone | The cell sector the carrier data gives; hundreds of metres to kilometres across. |
| Tagging | Placing a victim marker on the map so the operator can send the robot to it. |
| `imgsz` | Model input size in pixels. Not the camera resolution. |
| Tiling | Splitting a large frame into overlapping 640×640 crops (20% overlap) and running the model on each. |
| AP50 | Average precision at IoU ≥ 0.5. Our main accuracy number. |
| GSD | Ground sampling distance, metres of ground per pixel: 2·altitude·tan(HFOV/2) ÷ image width. |

Image measurement terms (person size, contrast, sharpness, crowding) are defined in [research/datasets/](research/datasets/README.md#measures).
