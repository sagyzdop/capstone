# Communication

> **Status:** Draft · **Updated:** 2026-10-18

What the station can send, how fast, and how far, with numbers the team can design against.

Two streams: 640×512 thermal at 30 FPS and 1280×1024 RGB at 10 FPS, both run through YOLO11n at
640 input. Higher resolutions transmit fine and buy nothing, because coverage is set by field of
view and altitude rather than sensor width. The station is the access point, so the operator's
phone joins as a third client without extra hardware.

Radiation is not the limiting factor: 100 Mbit/s holds to about 348 m, and the working range is 20
to 120 m. Rubble is what ends the link, costing 10 to 30 dB for one dense concrete wall.

## Numbers

**Bandwidth.** 100 Mbit/s per link is the design figure. Real 5 GHz throughput is 200 to 600
Mbit/s, we are a client with an unknown radio rather than the access point, and halving the
pessimistic number leaves room for a degraded link.

**Resolution and rate.** Re-encoding `wisard_pair.jpg`, the SAR imagery already in
[assets/audit/](../datasets/assets/audit/), at each resolution gives the byte counts. Detector
times are `ms_per_image_median` from [assets/audit/eval/](../datasets/assets/audit/eval/), measured
on an M4.

| Resolution | Bytes | Send @100 Mb/s | FPS ceiling | Verdict |
| --- | --- | --- | --- | --- |
| 640×512 thermal | 139 KiB | 11 ms | ~43 | **Send this.** AP50 0.872 at 640 input |
| 1280×1024 RGB | 454 KiB | 37 ms | ~20 | **Send this.** Same 49 m ceiling as thermal |
| Anything higher | 677 KiB and up | 55 ms and up | ~14 and down | No gain. Coverage has no sensor width in it, so a bigger sensor only reaches an altitude the drone cannot use |

4K was cut for that reason: 1.8 MiB a frame and 40× the detector time to reach an altitude above
the 49 m detection floor. Tiling the native frame is the only thing that made 4K worth sending, and
tiling belongs on the station, which already has the headroom.

FPS ceiling is 1000 ÷ (send + detect), since the pipeline cannot overlap them yet.

**Distance.** The throughput-to-RSSI curve is measured 802.11ax 5 GHz 80 MHz data; converting
through a free-space budget at 20 dBm and 2 dBi antennas gives range:

| Sustained | RSSI needed | Range |
| --- | --- | --- |
| 400 Mbit/s | −59 dBm | 49 m |
| 200 Mbit/s | −69 dBm | 157 m |
| **100 Mbit/s** | −76 dBm | **348 m** |
| 50 Mbit/s | −82 dBm | 678 m |
| 25 Mbit/s | −85 dBm | 920 m |
| 10 Mbit/s | −90 dBm | 1629 m |

The working range is 20 to 120 m, well inside the 348 m the design figure supports, so distance
does not constrain us at the intended geometry. Rubble does. A dense concrete wall costs 10 to
30 dB, enough to end the link on its own, so plan for total link loss.

**Models.** YOLO11n at 640 input, for both modalities. COCO figures for scale:

| Model | mAP50-95 | Params | FLOPs | T4 TensorRT |
| --- | --- | --- | --- | --- |
| YOLO11n | 39.5 | 2.6 M | 6.5 B | 1.5 ms |
| YOLO11s | 47.0 | 9.4 M | 21.6 B | 2.5 ms |
| YOLO11m | 51.5 | 20.1 M | 68.1 B | 4.7 ms |
| YOLO11l | 53.4 | 25.3 M | 87.2 B | 6.2 ms |
| YOLO11x | 54.7 | 56.9 M | 195.3 B | 11.3 ms |

s buys 7.5 mAP points for 3.3× the FLOPs, and the tiled RGB path is already the slowest thing we
run. The gap worth closing is training data, not capacity.

## Coverage

Coverage is set by field of view and altitude. Sensor width is not in the formula, so a 1280
camera and a 4K camera with the same lens see identical ground. Resolution decides how high the
drone can hover before a person falls under the 8 px detection floor, not how much it can see.

Swath is `2·altitude·tan(HFOV/2)` and does not depend on sensor width. Frame height depends on the
sensor's aspect ratio, which is not decided yet; the table uses the 4:3 RGB and 5:4 thermal
cameras assumed in [detection-data-analysis.md](../datasets/detection-data-analysis.md) §8.

| Altitude | RGB 72°, one frame | Person px @1280 | @4K | Sweep in 2 min @2 m/s |
| --- | --- | --- | --- | --- |
| 20 m | 29 × 22 m | 20 | 59 | 0.0070 km² |
| 30 m | 44 × 33 m | 13 | 40 | 0.0105 km² |
| 40 m | 58 × 43 m | 10 | 30 | 0.0139 km² |
| 49 m | 71 × 53 m | 8 | 24 | 0.0171 km² |

These are small numbers, and that is the point. At 40 m a two-minute sweep covers 0.014 km²,
which is a football pitch and a half, with persons still at 10 px. A single hover is 0.0025 km²
and never grows. An urban cell sector is roughly 28 km², so one hover is about 11,000 times short of
the area carrier data narrows the search to.

For scale in everyday terms, since the km² figures are small: a tennis court is 260 m², a car park
1,000 m², a small building 2,000 m², a football pitch 7,100 m².

Thermal at 40 m is 29 × 23 m, or 0.0007 km², because its 40° field of view is half the RGB one.
Both modalities see the same ground; thermal just slows the sweep by roughly half.

This is why 4K is not worth sending: it costs 4× the bytes and 40× the detector time to reach an
altitude the drone was never going to use.

## Rates

Design against 100 Mbit/s per link. Every link in the system shares the station's channel.

| Link | Payload | Rate | Bytes/frame | Bandwidth |
| --- | --- | --- | --- | --- |
| Drone → station | Thermal JPEG 640×512 | 30 FPS | 139 KiB | 34 Mbit/s |
| Drone → station | RGB JPEG 1280×1024 | 10 FPS | 454 KiB | 37 Mbit/s |
| Station → robot | Path / waypoints | On change | JSON | Negligible |
| Robot → station | Video, thermal, audio, status | TBD | TBD | **Unbudgeted** |
| Station → rescue team | Victim location and status | On detection | JSON | Negligible |

Those two drone streams come to 71 Mbit/s, leaving 29 for the robot and the operator UI. That fits,
but only just, and the robot's contribution is still unknown.

## Message formats

| Field | State | Note |
| --- | --- | --- |
| Frame container | Proposed | One JPEG per frame, filename carrying the timestamp. |
| Detection output | Agreed | JSON, `[{"image", "bbox_xyxy", "conf"}]`, as written by `src/detection/detect.py:16`. |
| Coordinate frame | Open | Whether `bbox_xyxy` is in image pixels or in ground metres. Pixels today. |
| Transport | Open | Plain TCP, HTTP, or a stream protocol. |
| Timing | Open | No frame timestamp in the payload, so latency is unmeasurable. |
| Loss behaviour | Open | What the station does with a dropped frame. |

Nothing carries a timestamp yet, and `detect.py` writes results to a file rather than a socket, so
no transport exists. This starts when the drone is chosen. Links involving the robot must be
reviewed by the Robotics team.

## Setup

The station laptop is the access point. Drone, robot and the operator's phone are clients on one
network, so no separate AP is needed and macOS's roughly 10-device limit leaves room for four.

5 GHz, 80 MHz, non-DFS channel. 2.4 GHz stays as a fallback, since it penetrates rubble better.

```bash
# macOS has no -createautohotspot, and Internet Sharing needs an upstream
# interface to exist, so fake one on the loopback first
sudo networksetup -createnetworkservice AdHoc lo0
sudo networksetup -setmanual AdHoc 127.0.0.1 255.255.255.255

# then System Settings > General > Sharing > Internet Sharing:
#   Share your connection from: AdHoc
#   To devices using: Wi-Fi
#   Wi-Fi Options: SSID, non-DFS channel 36, WPA3

# tear down: disable Internet Sharing, then
sudo networksetup -removenetworkservice AdHoc
```

On Ubuntu the equivalent is one line:

```bash
nmcli device wifi hotspot ifname wlan0 ssid "capstone-sar" password "<password>"
```

Sharing WiFi over WiFi costs 30 to 40% throughput on some adapters, which is one of the reasons the
design figure is halved.

## Hardware

Both endpoints run a Raspberry Pi. The Robotics team confirmed this for the robot, and using the
same computer on both sides means one bill of materials, one provisioning process and shared
spares.

| Option | Band | Real 5 GHz | Margin over 74 Mbit/s | Verdict |
| --- | --- | --- | --- | --- |
| Pi Zero 2W onboard | 2.4 GHz only | — | — | Out, no 5 GHz |
| Pi 4 / 5 onboard | 802.11ac 5 GHz, 1×1, PCB trace | 80–110 Mbit/s | 1.1–1.5× | **Too tight** |
| Pi + USB RTL8812AU | ac 2×2, external SMA | ~140 Mbit/s | 1.9× | Works, needs a DKMS driver |
| Pi + USB MT7921AUN | ax WiFi 6 | ~350 Mbit/s | 4.7× | Recommended |
| Pi 5 + M.2 AX210 | ax WiFi 6E | ~650 Mbit/s | 8.8× | Best, native driver |

**Recommendation: a Pi 5 with an MT7921AUN USB adapter and a 5 GHz antenna on the airframe.**
Roughly $110–135 and about 80 g mounted. A Pi 4 is acceptable if weight is tight. A Jetson Orin Nano
at 140 g is wasted here, since the architecture forbids running detection on the drone.

The onboard radio is the problem, not the Pi. It is 1×1 with a PCB trace antenna and measures 80 to
110 Mbit/s in the lab, while the two drone streams plus a robot feed want 74 Mbit/s. That is most of
the capacity spent before any range loss, and throughput falls off a cliff once the link drops to a
lower MCS. The robot needs the same adapter, and its antenna matters more than the drone's, since it
works at ground level among walls.

A companion computer also buys two things the flight controller cannot: the drone can JPEG-encode
rather than send raw frames, and it can record to SD so a dropped link does not lose data.

## What the drone covers

The drone hovers over a **known collapse site** rather than searching one. A cell sector from
carrier data is far larger than any single hover, so an operator narrows it to a building first.
That is what makes fixed-point hover viable, and it is why coverage per frame never has to grow.

At the 8 px detection floor for a standing person, the usable ceiling is 49 m, which matches
thermal at 640×512 and RGB at 1280×1024. Higher than that and nobody is detected regardless of
sensor. Lower than 20 m and one frame is 0.0006 km² of ground, which only suits a small site.

## What this does not settle

Our thermal model scores AP50 0.872 on HIT-UAV and **0.010 on real WiSARD thermal footage**.
Persons there are larger and higher contrast, so this is not a resolution problem. Retraining on
HIT-UAV plus WiSARD is the highest-value experiment open to us.

Nothing handles link loss. The station should keep working from its last detections, and the drone
needs a return behaviour. Neither is implemented.

All three gaps are open questions in [open-questions.md](../../open-questions.md), along with the
hardware choice: every resolution, rate and range number above moves if the drone's camera and
radio differ from what we assumed. So does the case where the team is handed a whole cell sector
instead of a building, since the drone would then have to search rather than hover.

## Still unanswered

These are the questions this analysis raised but could not settle. Each belongs in
[open-questions.md](../../open-questions.md) once the team has agreed it matters.

**About the mission**
- What is the target site? A single building fixes the hover. A cell sector does not.
- Who narrows the carrier sector to a building, and how long before the drone launches?
- If the team is handed a sector rather than a building, does the robot search the rest, or does the
  drone sweep? The second needs pose tracking, frame stitching and detection de-duplication, since
  the same victim appears in every overlapping frame.

**About the hardware**
- Which drone and camera? Every number above moves with it.
- What are the frame aspect ratio and field of view? The heights in the coverage table assume 4:3 RGB
  and 5:4 thermal.
- What is the drone's flight time, and does hovering at 20 to 40 m fit inside it?
- Does the drone's autopilot release the WiFi interface for client use?

**About the link**
- How is the remaining 29 Mbit/s split between the robot stream and the operator UI?
- Measured throughput and range through real rubble, not free space?
- What happens on link loss? The station needs to keep working from its last detections and the
  drone needs a return path. Neither is implemented.
- Does the operator UI need video at all, or would downscaled keyframes at 1 FPS do?

**About the detector**
- Retrain thermal on HIT-UAV plus WiSARD, or ship a detector that only works on HIT-UAV? AP50 is
  0.010 on real WiSARD thermal against 0.872 on HIT-UAV.
- Should the RGB path wait for the domain gap to close, or ship as COCO zero-shot with a stated
  caveat?

**About scope**
- Is audio still in scope, and what structured signal does it output?
- Does the tumbling robot ever search, or only verify?

## Measuring it

```bash
# throughput at the hover altitude, drone running iperf3 -s
iperf3 -c <drone-ip> -t 60 -i 1

# detector timing, from the committed eval JSONs
python3 -c "import json;print(json.load(open('research/datasets/assets/audit/eval/hituav-model_hituav-test.json'))[2])"

# image bytes at a given resolution
sips -z 512 640 research/datasets/assets/audit/wisard_pair.jpg --out /tmp/t.jpg && stat -f%z /tmp/t.jpg
```

Record throughput at 20, 50, 100, 200 m and again through one and two rubble walls.

- [ ] Real camera JPEG size: `?` bytes
- [ ] Measured throughput at hover altitude: `?` Mbit/s
- [ ] Measured range through one rubble wall: `?` m
- [ ] End-to-end latency, not just transfer: `?` ms

## Sources

- Throughput against RSSI for 802.11ax 5 GHz 80 MHz: [Candela Wi-Fi station test report](https://reports.candelatech.com/reports/Wi-Fi%20Station%20Testing/Candela%20Wi-Fi%20Station%20Test%20Solution.pdf).
- Real-world rates by band and standard: [HP knowledge base](https://h30434.www3.hp.com/t5/Laptops-Knowledge-Base/Real-world-WiFi-speed-and-flex-repeater-booster-system/ta-p/9110464), [Cisco](https://www.cisco.com/c/en/us/support/docs/wireless-mobility/wireless-lan-wlan/212892-802-11ac-wireless-throughput-testing-and.html).
- YOLO11 variant specs: [Ultralytics docs](https://docs.ultralytics.com/models/yolo11/).
- Internet Sharing needs an upstream interface: [Ask Different](https://apple.stackexchange.com/questions/464557/how-to-create-computer-to-computer-network-on-macos-sonoma-2023).
