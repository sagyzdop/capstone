# Communication

> **Status:** Draft · **Updated:** 2026-10-18

What the station can send, how fast, and how far. Radii and ranges are estimates from link
budgets; byte counts and detector times are measured.

**Streams.** Thermal 640×512 at 30 FPS, RGB 1280×1024 at 10 FPS, both through YOLO11n at 640 input.
Together 71 Mbit/s of a 100 Mbit/s budget.

**Range.** 100 Mbit/s holds to about 348 m and the working range is 20 to 120 m, so distance is not
the limit. Rubble is: one dense concrete wall costs 10 to 30 dB.

**Hardware.** A Raspberry Pi on both endpoints with a USB WiFi adapter and an antenna on the
airframe. The Pi's onboard radio is not enough.

## Streams

| Stream | Bytes/frame | Send @100 Mb/s | Detect | FPS | Bandwidth |
| --- | --- | --- | --- | --- | --- |
| Thermal 640×512 | 139 KiB | 11 ms | 12.4 ms | 30 | 34 Mbit/s |
| RGB 1280×1024 | 454 KiB | 37 ms | 12.4 ms | 10 | 37 Mbit/s |

Byte counts come from re-encoding the repo's own SAR imagery at each resolution. Detect times are
`ms_per_image_median` from [assets/audit/eval/](../datasets/assets/audit/eval/), measured on an M4.
FPS is set by the detector, not the link: 640 input is the AP50 peak on thermal at 0.872, and going
to 1280 loses 12 points because the model has not seen people that large.

Anything above 1280 transmits fine and buys nothing. Coverage is `2·altitude·tan(HFOV/2)`, which has
no sensor width in it, so a bigger sensor only reaches a higher altitude. 4K cost 4× the bytes and
40× the detector time to clear a ceiling the drone was never going to fly. Tiling the native frame
was the only reason 4K was ever worth sending, and tiling belongs on the station, which has the
headroom.

## Coverage

Areas as square patches, since that is how a site gets talked about. RGB at 72° field of view,
4:3 sensor.

| Altitude | One frame | As a square | Person px @1280 | @4K | 2 min at 2 m/s |
| --- | --- | --- | --- | --- | --- |
| 20 m | 29 × 22 m | 25 × 25 m | 20 | 59 | 84 × 84 m |
| 30 m | 44 × 33 m | 38 × 38 m | 13 | 40 | 102 × 102 m |
| 40 m | 58 × 44 m | 50 × 50 m | 10 | 30 | 118 × 118 m |
| 49 m | 71 × 53 m | 62 × 62 m | 8 | 24 | 131 × 131 m |

Thermal at 40 m is 26 × 26 m, half the RGB footprint, because its 40° field of view is half as wide.
Both see the same ground.

**49 m is the ceiling**, set by the 8 px detection floor for a standing person. Thermal and RGB reach
it at the same altitude. Above it nobody is detected whatever the sensor.

One hover at 40 m covers about 0.0025 km² and never grows. An urban cell sector is roughly 28 km²,
so hover only works once an operator narrows the sector to a specific building. That is the
assumption in [open-questions.md](../../open-questions.md): the station searches nothing.

## Link

Throughput against range, from a measured 802.11ax 5 GHz 80 MHz curve through a free-space budget at
20 dBm and 2 dBi antennas:

| Sustained | RSSI | Range |
| --- | --- | --- |
| 400 Mbit/s | −59 dBm | 49 m |
| 200 Mbit/s | −69 dBm | 157 m |
| **100 Mbit/s** | −76 dBm | **348 m** |
| 50 Mbit/s | −82 dBm | 678 m |
| 10 Mbit/s | −90 dBm | 1629 m |

The 100 Mbit/s design figure is half a pessimistic 200 Mbit/s client rate. Real 5 GHz reaches 200 to
600 Mbit/s, but we are a client with an unknown radio rather than the access point, so the pessimistic
figure is the one to design against.

| Link | Payload | Rate | Bandwidth |
| --- | --- | --- | --- |
| Drone → station | Thermal JPEG 640×512 | 30 FPS | 34 Mbit/s |
| Drone → station | RGB JPEG 1280×1024 | 10 FPS | 37 Mbit/s |
| Robot → station | 720p30 H.264, audio, telemetry | ~10 FPS | 2.6 Mbit/s |
| Station → robot | Path / waypoints | On change | Negligible |
| Station → rescue team | Victim location and status | On detection | Negligible |

The drone's video goes to a detector as JPEG frames. The robot's goes to a human, so H.264 carries it
in 2.6 Mbit/s. That leaves 26 Mbit/s for the operator UI.

## Hardware

| Option | Real 5 GHz | Margin over 74 Mbit/s | Verdict |
| --- | --- | --- | --- |
| Pi Zero 2W onboard | 2.4 GHz only | — | Out |
| Pi 4 / 5 onboard | 80–110 Mbit/s | 1.1–1.5× | Too tight |
| Pi + USB RTL8812AU | ~140 Mbit/s | 1.9× | Works, needs a DKMS driver |
| Pi + USB MT7921AUN | ~350 Mbit/s | 4.7× | Recommended |
| Pi 5 + M.2 AX210 | ~650 Mbit/s | 8.8× | Best, native driver |

**A Pi 5 with an MT7921AUN and a 5 GHz antenna on the airframe.** About $110–135 and 80 g mounted.
The Robotics team confirmed a Pi for the robot, so both endpoints share a bill of materials.

The onboard radio fails on margin: 74 Mbit/s of load against 80 to 110 measured is most of the
capacity gone before any range loss, and throughput falls off a cliff below the top MCS. An ESP32 on
the flight controller is out on two counts, being 2.4 GHz only at 11 to 20 Mbit/s, and unable to
JPEG-encode at 30 FPS while flying. The Pi also records to SD, so a dropped link loses no frames.

## Setup

The station laptop is the access point. Drone, robot, phone and operator laptop are clients, four of
macOS's roughly ten. 5 GHz, 80 MHz, non-DFS, since a mid-flight radar check would drop the link. 2.4 GHz
is the rubble fallback.

```bash
# macOS needs a fake upstream interface before Internet Sharing will broadcast
sudo networksetup -createnetworkservice AdHoc lo0
sudo networksetup -setmanual AdHoc 127.0.0.1 255.255.255.255

# then System Settings > General > Sharing > Internet Sharing:
#   from AdHoc, to Wi-Fi, non-DFS channel 36, WPA3

# teardown: disable Internet Sharing, then
sudo networksetup -removenetworkservice AdHoc
```

Ubuntu: `nmcli device wifi hotspot ifname wlan0 ssid "capstone-sar" password "<password>"`.

## Message formats

| Field | State |
| --- | --- |
| Detection output | Agreed: JSON `[{"image", "bbox_xyxy", "conf"}]`, written by `src/detection/detect.py:16` |
| Frame container | Proposed: one JPEG per frame, timestamp in the filename |
| Coordinate frame | Open: `bbox_xyxy` is image pixels today, ground metres wanted |
| Transport | Open: none exists. `detect.py` writes a file, not a socket |
| Timing | Open: no timestamp in the payload, so latency is unmeasurable |
| Loss behaviour | Open: what the station does with a dropped frame |

Robot links need Robotics team review.

## Open

Blocking, and all in [open-questions.md](../../open-questions.md):

- The thermal model scores AP50 0.872 on HIT-UAV and **0.010 on real WiSARD thermal footage**.
  Persons there are larger and higher contrast, so this is not resolution. Retraining on HIT-UAV plus
  WiSARD is the most valuable experiment open to us.
- Link loss is unimplemented. The station should keep working from its last detections and the drone
  needs a return path.
- No drone or camera chosen. Which Pi, which radio, which field of view.
- Handed a cell sector instead of a building, the drone would have to search rather than hover.

Non-blocking: how the remaining 26 Mbit/s splits between robot and operator UI, measured throughput
through rubble, flight time at 20 to 40 m, whether audio is still in scope.

## Measuring

```bash
iperf3 -c <drone-ip> -t 60 -i 1        # drone runs iperf3 -s, at hover altitude
python3 -c "import json;print(json.load(open('research/datasets/assets/audit/eval/hituav-model_hituav-test.json'))[2])"
sips -z 512 640 research/datasets/assets/audit/wisard_pair.jpg --out /tmp/t.jpg && stat -f%z /tmp/t.jpg
```

Throughput at 20, 50, 100, 200 m, then again through one and two rubble walls.

- [ ] Real camera JPEG size: `?` bytes
- [ ] Throughput at hover altitude: `?` Mbit/s
- [ ] Range through one rubble wall: `?` m
- [ ] End-to-end latency: `?` ms

## Sources

- Throughput against RSSI, 802.11ax 5 GHz 80 MHz: [Candela Wi-Fi station test report](https://reports.candelatech.com/reports/Wi-Fi%20Station%20Testing/Candela%20Wi-Fi%20Station%20Test%20Solution.pdf).
- Real-world rates by band: [HP knowledge base](https://h30434.www3.hp.com/t5/Laptops-Knowledge-Base/Real-world-WiFi-speed-and-flex-repeater-booster-system/ta-p/9110464), [Cisco](https://www.cisco.com/c/en/us/support/docs/wireless-mobility/wireless-lan-wlan/212892-802-11ac-wireless-throughput-testing-and.html).
- YOLO11 variant specs: [Ultralytics](https://docs.ultralytics.com/models/yolo11/).
- Internet Sharing needs an upstream interface: [Ask Different](https://apple.stackexchange.com/questions/464557/how-to-create-computer-to-computer-network-on-macos-sonoma-2023).
