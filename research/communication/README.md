# Communication

What the station can send, how fast, and how far. Radii and ranges are estimates from link
budgets; byte counts are measured.

> [!WARNING]
> The frame rates here (drone thermal 30 FPS, drone RGB 10 FPS, robot 5 FPS) are predictions, never measured end to end. They
> come from YOLO11n detector timings; the station now runs YOLO26, and the laptop test in
> [../datasets/](../datasets/README.md#test-on-the-station-laptop) replaces them. The robot's byte counts
> are scaled from the drone's, not measured.

**Streams.** Drone and robot carry the same cameras and send the same kind of stream: JPEG frames,
RGB and thermal separately. Drone: thermal 640×512 at a predicted 30 FPS, RGB 1280×1024 at a predicted
10 FPS, tiled to 640 on the station. Robot: both at 640×512 and 5 FPS, since its people are close and
large. Together about 82 Mbit/s of a 100 Mbit/s budget. Why each resolution: [SPEC.md](../../SPEC.md#streams).

**Range.** 100 Mbit/s holds to about 348 m and the working range is 20 to 120 m, so distance is not
the limit. Rubble is: one dense concrete wall costs 10 to 30 dB.

**Hardware.** The same Raspberry Pi, USB WiFi adapter and external antenna on the drone and the
robot. The Pi's onboard radio is not enough.

## Streams

| Stream | Bytes/frame | Send @100 Mb/s | Detect | FPS | Bandwidth |
| --- | --- | --- | --- | --- | --- |
| Drone thermal 640×512 | 139 KiB | 11 ms | 12.4 ms | 30 | 34 Mbit/s |
| Drone RGB 1280×1024 | 454 KiB | 37 ms | 6 tiles × 12.4 ms | 10 | 37 Mbit/s |
| Robot thermal 640×512 | 139 KiB | 11 ms | 12.4 ms | 5 | 6 Mbit/s |
| Robot RGB 640×512 | about 114 KiB (¼ of 1280) | 9 ms | 12.4 ms | 5 | 5 Mbit/s |

Byte counts come from re-encoding the repo's own SAR imagery at each resolution. Detect times are
the YOLO11n timings from the earlier [dataset audits](../datasets/README.md#input-size-and-tiling), measured on an
Apple Silicon laptop. FPS is set by the detector, not the link: 640 input is the AP50 peak on thermal at 0.872, and going
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

Thermal at 40 m is 29 × 23 m (26 × 26 m as a square): half as wide as RGB, because its 40° field
of view is half as wide, and about a quarter of the area. The thermal view sits inside the RGB view,
so the RGB edges are covered by one camera only.

**49 m is the ceiling** with these cameras, set by the 8 px detection floor for a standing person
(10 px, the safer floor, is at 40 m). Thermal and RGB reach it at the same altitude. A lying person
is about twice as large from above, so thermal still sees them to about 80 m. A narrower lens raises
the ceiling but covers less ground. Real SAR datasets fly at 40 to 65 m; the comparison with each
dataset is in [../datasets/](../datasets/README.md#how-high-the-drone-can-fly).

One hover at 40 m covers about 0.0025 km² and never grows. An urban cell sector is roughly 28 km²,
so hover only works once an operator narrows the sector to a specific building, and the station
searches nothing. That is the current [spec](../../SPEC.md#system); a vehicle that keeps moving until
the drone finds the victims is proposed in [QUESTIONS.md](../../QUESTIONS.md).

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
| Robot → station | Thermal JPEG 640×512 | 5 FPS | 6 Mbit/s |
| Robot → station | RGB JPEG 640×512 | 5 FPS | 5 Mbit/s |
| Robot ↔ station | Two-way audio, telemetry | Continuous | Under 1 Mbit/s |
| Station → robot | Drive commands from the operator | While driving | Negligible |
| Station → rescue team | Victim location and status | On detection | Negligible |

Both platforms send JPEG frames because every frame goes to a detector. If the link gets tight, the
robot can switch to H.264 (a 720p30 stream with audio and telemetry is about 2.6 Mbit/s) at some cost
to detection.

Total load is about 82 Mbit/s, leaving roughly 18 Mbit/s of headroom. The operator UI is rendered on
the station's own screen and costs nothing on the network; the headroom covers reassociation overhead
and margin for a degraded link.

## Hardware

| Option | Real 5 GHz | Margin over the drone's 71 Mbit/s | Verdict |
| --- | --- | --- | --- |
| Pi Zero 2W onboard | 2.4 GHz only | — | Out |
| Pi 4 / 5 onboard | 80–110 Mbit/s | 1.1–1.5× | Too tight |
| Pi + USB RTL8812AU | ~140 Mbit/s | 2.0× | Works, needs a DKMS driver |
| Pi + USB MT7921AUN | ~350 Mbit/s | 4.9× | Recommended |
| Pi 5 + M.2 AX210 | ~650 Mbit/s | 9.2× | Best, native driver |

**A Pi 5 with an MT7921AUN and a 5 GHz antenna on the airframe.** About $110–135 and 80 g mounted.
The Robotics team confirmed a Pi for the robot, so both endpoints share a bill of materials.

The onboard radio fails on margin: the drone's 71 Mbit/s of load against 80 to 110 measured is most of the
capacity gone before any range loss, and throughput falls off a cliff below the top MCS. An ESP32 on
the flight controller is out on two counts, being 2.4 GHz only at 11 to 20 Mbit/s, and unable to
JPEG-encode at 30 FPS while flying. The Pi also records to SD, so a dropped link loses no frames.

## Setup

The station laptop is the access point. Drone and robot are its clients, well inside macOS's roughly
ten-device limit. 5 GHz, 80 MHz, non-DFS, since a mid-flight radar check would drop the link. 2.4 GHz
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
| Frame container | Agreed: one JPEG per frame, with a timestamp and GPS / heading ([SPEC.md](../../SPEC.md#streams)) |
| Coordinate frame | Open: `bbox_xyxy` is image pixels today, ground metres wanted |
| Transport | Open: none exists. `detect.py` writes a file, not a socket |
| Timing | Open: where the timestamp and GPS travel (filename, JPEG header or a sidecar message), and clock sync between the Pis and the station |
| Loss behaviour | Open: what the station does with a dropped frame |

Robot links need Robotics team review.

## Open

All open questions, including the link ones, are in [QUESTIONS.md](../../QUESTIONS.md).

## Measuring

```bash
iperf3 -c <drone-ip> -t 60 -i 1        # drone runs iperf3 -s, at hover altitude
sips -z 512 640 research/datasets/assets/wisard_pair.jpg --out /tmp/t.jpg && stat -f%z /tmp/t.jpg
```

Throughput at 20, 50, 100, 200 m, then again through one and two rubble walls.

- [ ] Real camera JPEG size: `?` bytes
- [ ] Throughput at hover altitude: `?` Mbit/s
- [ ] Range through one rubble wall: `?` m
- [ ] End-to-end latency: `?` ms

## Sources

- YOLO26 replaces YOLO11; its specs are in [SPEC.md](../../SPEC.md#detection).
- Throughput against RSSI, 802.11ax 5 GHz 80 MHz: [Candela Wi-Fi station test report](https://reports.candelatech.com/reports/Wi-Fi%20Station%20Testing/Candela%20Wi-Fi%20Station%20Test%20Solution.pdf).
- Real-world rates by band: [HP knowledge base](https://h30434.www3.hp.com/t5/Laptops-Knowledge-Base/Real-world-WiFi-speed-and-flex-repeater-booster-system/ta-p/9110464), [Cisco](https://www.cisco.com/c/en/us/support/docs/wireless-mobility/wireless-lan-wlan/212892-802-11ac-wireless-throughput-testing-and.html).
- YOLO11 variant specs: [Ultralytics](https://docs.ultralytics.com/models/yolo11/).
- Internet Sharing needs an upstream interface: [Ask Different](https://apple.stackexchange.com/questions/464557/how-to-create-computer-to-computer-network-on-macos-sonoma-2023).
