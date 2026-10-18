# Communication

> **Status:** Draft · **Updated:** 2026-10-18

What the station can send, how fast, and how far, with numbers the team can design against.

Every resolution from 128×128 to 3840×2160 transmits. What changes with resolution is detector
throughput rather than the radio, so the working streams are 640×512 thermal at 30 FPS and
1280×1024 RGB at 10 FPS. YOLO11n at 640 is the detector for both. The station is the access point,
so the operator's phone joins as a third client without extra hardware.

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

| Resolution | Bytes | Send @100 Mb/s | Detects at | FPS ceiling | Use it for |
| --- | --- | --- | --- | --- | --- |
| 128×128 | 7.3 KiB | 0.6 ms | below the 8 px floor | — | Thumbnails, no detection |
| 320×256 | 37 KiB | 3.0 ms | 320: AP50 0.664 | ~80 | Below the size floor, avoid |
| 640×512 | 139 KiB | 11 ms | 640: AP50 **0.872** | ~43 | **Thermal. The working stream.** |
| 1280×1024 | 454 KiB | 37 ms | 640 tiles | ~20 | **RGB. The working stream.** |
| 1920×1080 | 677 KiB | 55 ms | 640 tiles | ~14 | RGB if the link allows |
| 2560×1440 | 1.0 MiB | 85 ms | 640 tiles | ~9 | Link starts to hurt |
| 3840×2160 | 1.8 MiB | 149 ms | 640 tiles (32) | ~1.6 | Frame-accumulate |

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

## What this does not settle

Our thermal model scores AP50 0.872 on HIT-UAV and **0.010 on real WiSARD thermal footage**.
Persons there are larger and higher contrast, so this is not a resolution problem. Retraining on
HIT-UAV plus WiSARD is the highest-value experiment open to us.

Nothing handles link loss. The station should keep working from its last detections, and the drone
needs a return behaviour. Neither is implemented.

All three gaps are open questions in [open-questions.md](../../open-questions.md), along with the
hardware choice: every resolution, rate and range number above moves if the drone's camera and
radio differ from what we assumed.

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
