# Glossary

> **Status:** Draft · **Updated:** 2026-10-18

Every term used across the project, grouped by area. Measurement definitions that the analysis
scripts implement are written out in full; the rest are one line each.

## System

| Term | Meaning |
| --- | --- |
| Station | The laptop on the vehicle. The only compute node: detection, path planning, orchestration and the operator UI all run here. See [station/](station/). |
| Drone / UAV | Unmanned aerial vehicle. Flies to one point and hovers there, streaming video. Runs no processing. See [drone/](drone/). |
| Ground robot / UGV | Unmanned ground vehicle, built by the Robotics team. Follows the station's path, verifies the victim, talks to them. See [ground-robot/](ground-robot/). |
| Moving station | The vehicle carrying laptop, drone and robot. It drives to the site and then stays parked. Distinct from the station itself. |
| Orchestrator | The station component deciding what the system does next: which frames to process, when to plan a path, when to dispatch the robot. |
| Operator UI | The station's display: map, drone feed, detection boxes, robot state. |
| Dropping point | Where the robot is released. Assumed known in advance ([open-questions.md](open-questions.md)). |
| Tagging | Marking a detected victim's location and id on the station's map, so the robot can be sent to it. |
| Triage | Sorting victims by urgency and survivability. |
| START | Simple Triage And Rapid Treatment: Red immediate, Yellow delayed, Green minor, Black deceased or expectant. |
| Concept of operations (ConOps) | The ordered sequence of what the system does, from pre-mission to reporting out. Drawn in [README.md](README.md). |
| Waypoint | A point on the robot's path, sent from the station. |

## Victim location

| Term | Meaning |
| --- | --- |
| CDR | Call Detail Record. Carrier log of network events, including which cell tower a phone used. |
| Cell site analysis | Estimating a phone's location from the towers and sectors it attached to. Narrows the search area rather than pinpointing anyone. |
| Candidate zone | The area returned by carrier data before deployment. Where the vehicle drives. |

## Sensing and datasets

| Term | Meaning |
| --- | --- |
| RGB | Standard three-channel colour imagery. |
| Thermal / IR | Infrared imagery. Long-wave thermal reads body heat and works in darkness; "IR" and "thermal" are used interchangeably here. |
| Modality | Which kind of sensor produced an image: RGB or thermal. |
| SAR | Search and rescue. Also used in dataset names (WiSARD) for the application domain, not a sensor type. |
| HIT-UAV | Thermal dataset, 2,898 images of a drone at 60 to 130 m over campus and roads. CC0. Our thermal training set. |
| C2A | Synthetic RGB dataset: people pasted onto AIDER disaster scenes. 10,215 images. Our RGB candidate, but its val/test split leaks. |
| WiSARD | Real search-and-rescue dataset from a single flight: 264 frames, paired RGB 3840×2160 and thermal 640×512. Our domain-gap test. |
| AIDER | RGB disaster image set used as the background layer inside C2A. Image-level labels only. |
| COCO | Common Objects in Context. The 80-class pretraining set behind `yolo11n.pt`. |
| Leakage | A train image reappearing in val or test. C2A shares 98% of val/test scenes with train, so its metrics mean nothing. |
| Near-duplicate | A 64-bit difference hash within 4 bits of some train image. Found in 31% of HIT-UAV val/test. |
| Split | Train / val / test partition of a dataset. |
| Datasets and their licences | [research/datasets/datasets.md](research/datasets/datasets.md) |
| Literature review | [research/literature/UAV_SAR_Literature_Review.csv](research/literature/UAV_SAR_Literature_Review.csv) |

## Detection

| Term | Meaning |
| --- | --- |
| YOLO / YOLO11 | One-stage detector family from Ultralytics (AGPL-3.0). We use the detection variants. |
| YOLO11n/s/m/l/x | Size variants: nano, small, medium, large, xlarge. We use `n`. COCO mAP50-95 runs 39.5 to 54.7 across the range. |
| `imgsz` | Model input size in pixels. Images are resized to this square before inference. Not the camera resolution. |
| AP50 | Average precision at IoU ≥ 0.5. Our main accuracy number. |
| mAP | Mean average precision over several IoU thresholds (50 to 95). The usual COCO figure, unlike AP50. |
| IoU | Intersection over union between predicted and true box. How much two boxes must overlap to count as a match. |
| Precision | Of the detections made, the fraction that are real. |
| Recall | Of the real persons present, the fraction detected. Measured at confidence 0.25. |
| Confidence | Detector score for a box. Raised, it trades recall for precision. |
| Tiling | Splitting a large image into overlapping 640×640 crops and running the model on each. 20% overlap so a person on a seam appears whole in one tile. |
| Tiling count | A 3840×2160 frame yields 8 × 4 = 32 tiles, from the loop in `src/detection/eval_sizes.py:73`. |
| Inference | Running a trained model on new data. No weights change. |
| Fine-tuning / retraining | Continuing to train an existing model on new data. |
| Domain gap | The same nominal data looking different enough to break a model. Our thermal model drops from AP50 0.872 on HIT-UAV to 0.010 on WiSARD. |
| Baseline | The reference run a new model is compared against. |
| FPS | Frames per second. See [research/communication/](research/communication/). |
| Overlap (persons) | One person whose box intersects another's. Common in crowded frames. |
| DontCare | A COCO annotation marking a region to ignore. C2A uses it for background people. |
| Bounding box | The rectangle around a detected person, given as `[x1, y1, x2, y2]` in pixels. |
| Pose | Body position, e.g. standing, kneeling, lying. C2A includes these as a field we ignore. |

## Image measurements

How the analysis scripts compute these, from
[research/datasets/detection-data-analysis.md](research/datasets/detection-data-analysis.md) §1:

| Term | Meaning |
| --- | --- |
| Person size | √(box width × box height) in native pixels. |
| Small / tiny | Under 8 px. Below this, detectors mostly miss persons. |
| Contrast | (mean grey inside box − mean grey of a ring one box-size wide around it) ÷ image grey std. \|value\| < 0.5 counts as low contrast. Strong signal on thermal; only a proxy on RGB, where colour also separates people. |
| Sharpness | Variance of the Laplacian, after resizing to a 640 px long side so datasets compare. |
| Crowding | Distance from a person's centre to the nearest other centre, in units of that person's size. |
| Brightness | Mean grey level, 0 to 255. |
| Dynamic range | Brightness spread between the 1st and 99th percentile. |
| Density | Number of persons per image. |
| Pixels per person | Area of the person's box in pixels; the practical measure of detectability. |
| GSD | Ground sampling distance: 2 · altitude · tan(HFOV / 2) ÷ image width. Metres of ground per pixel. |
| HFOV | Horizontal field of view, the camera's angular width. |
| Altitude | Height above ground (AGL) while hovering. |
| JPEG | Lossy image compression. Our transmitted format; quality 85 throughout. |
| Tiling vs resize | Resizing throws away detail; tiling keeps native pixels. On 4K RGB, tiling scores AP50 0.324 against 0.030 for resizing to 640. |

## Radio and networking

| Term | Meaning |
| --- | --- |
| WiFi | 802.11 wireless. We use 5 GHz for both drone and robot links. |
| Access point (AP) | The device broadcasting the network. Here, the station laptop. |
| Station-hosted network | Drone, robot and phone as clients on one network run by the station. No separate router. |
| SSID | Network name. Ours is `capstone-sar`. |
| Client / station | A device that joins the network. Drone, robot and phone are clients. |
| Internet Sharing | The macOS feature that makes the station an access point. Needs a dummy upstream interface on `lo0` to start. |
| AdHoc | The dummy network service created on the loopback so Internet Sharing has something to share. |
| Non-DFS channel | A 5 GHz channel with no radar detection. Avoided DFS because a mid-flight radar check drops the link. |
| Band | 2.4 GHz or 5 GHz. 5 GHz carries more; 2.4 GHz penetrates rubble better and is our fallback. |
| Channel width | 20, 40, 80 or 160 MHz. Wider is faster. We use 80 MHz. |
| Mbit/s | Megabits per second. `MiB` and `KiB` are bytes; the two are not interchangeable. |
| RSSI | Received signal strength, in dBm. Negative; closer to zero is stronger. |
| FSPL | Free-space path loss: the signal loss over distance with nothing in the way. |
| Fresnel zone | The volume a radio signal effectively occupies. Roughly half of it must stay clear of terrain. |
| K-factor | Fresnel clearance requirement. 1.0 fully clear, 1.33 the usual standard, 1.6 conservative. |
| Range | Distance over which a given bitrate holds. At our link assumptions, 100 Mbit/s to about 348 m. |
| Rubble | Post-earthquake debris. Dense concrete costs 10 to 30 dB, which is more than free-space loss over our working range. |
| Link budget | Received power minus losses, compared against what the receiver needs. |
| NAT | Network address translation, the address rewriting the station's sharing does. |
| DHCP | Automatic address assignment to joining clients. |
| `iperf3` | Throughput test tool. Both ends need it; the station runs `-s`, the drone connects. |

## Process

| Term | Meaning |
| --- | --- |
| Status line | The `> **Status:** … · **Updated:** …` header every document opens with. Values: Draft, In review, Agreed. |
| Changelog | [CHANGELOG.md](CHANGELOG.md). Every decision and answer, newest first. Categories: Decided, Changed, Added, Removed. |
| Rationale | The "why" recorded alongside a decision in the changelog. |
| Open question | An unresolved question in [open-questions.md](open-questions.md), with a Blocking? flag. |
| Blocking | An open question that stops other work from proceeding. |
| Assumption | Something we treat as true but have not verified, listed in [open-questions.md](open-questions.md) with the risk if it is false. |
| Citekey | The BibTeX key for a paper. Only keys in [research/literature/references.bib](research/literature/references.bib) may be cited. |
| Robotics team | The group building the ground robot. Their internals are not copied; facts are recorded with a source and date in [ground-robot/capabilities.md](ground-robot/capabilities.md). |
| Baseline run | The evaluation every model is compared against. |
