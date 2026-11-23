# Communication

What the station can send, how fast, and how far, and how to set up the network. Radii and ranges
are estimates from link budgets; byte counts are measured from re-encoded SAR imagery, not from the
real camera.

## Network

A WiFi router on the vehicle is the access point. The station plugs into it by Ethernet, and each
module joins over WiFi with a fixed IP address. Recent macOS no longer creates ad-hoc networks, so
the station can't be the access point. On Ethernet, a module's traffic crosses the air once instead
of twice.

The current router, a Huawei HG658 V2, is temporary. Every source we found lists it as 2.4 GHz-only
802.11n (N300) with 10/100 Ethernet ports and a 12 V DC input. A 2.4 GHz 802.11n router delivers
roughly 30 to 60 Mbit/s in practice, shared by every client, so the streams are sized for about
20 Mbit/s in total.

## Streams

| Link | Payload | Rate | Bandwidth (estimate) |
| --- | --- | --- | --- |
| UAV module → station | RGB JPEG 1280×720, with pose | 3 to 5 FPS | about 13 Mbit/s at 5 FPS |
| UGV module → station | RGB JPEG 640×360 | 5 FPS | about 3 Mbit/s |
| UGV module ↔ station | Two-way audio, status, commands, heartbeat | Continuous | Under 1 Mbit/s |
| Station → rescue team | Victim locations and notes | On detection | Negligible |

Bytes per frame are scaled from a measured 454 KiB for a 1280×1024 JPEG. The pilot flies by the
drone's own video, so the UAV stream is only for detection and a few frames per second is enough.
If the link gets tight, H.264 cuts the bytes several times over at some cost to small people; the
Pi 5 has no hardware H.264 encoder but encodes 1080p30 in software.

## Coverage

Areas as square patches, since that is how a site gets talked about. RGB at 72° field of view,
4:3 sensor.

| Altitude | One frame | As a square | Person px @1280 | @4K | 2 min at 2 m/s |
| --- | --- | --- | --- | --- | --- |
| 20 m | 29 × 22 m | 25 × 25 m | 20 | 59 | 84 × 84 m |
| 30 m | 44 × 33 m | 38 × 38 m | 13 | 40 | 102 × 102 m |
| 40 m | 58 × 44 m | 50 × 50 m | 10 | 30 | 118 × 118 m |
| 49 m | 71 × 53 m | 62 × 62 m | 8 | 24 | 131 × 131 m |

**49 m is the ceiling**, set by the 8 px detection floor for a standing person (10 px, the safer
floor, is at 40 m). A lying person is about twice as large from above. A narrower lens raises the
ceiling but covers less ground. Real SAR datasets fly at 40 to 65 m; the comparison with each
dataset is in [../datasets/](../datasets/README.md#how-high-the-drone-can-fly).

Anything above 1280 px transmits fine and buys nothing: coverage is `2·altitude·tan(HFOV/2)`, with
no sensor width in it, so a bigger sensor only reaches a higher altitude, for 4× the bytes at 4K.

## Range

Throughput against range, from a measured 802.11ax 5 GHz 80 MHz curve through a free-space budget at
20 dBm and 2 dBi antennas. It applies to a dual-band replacement router, not to the HG658:

| Sustained | RSSI | Range |
| --- | --- | --- |
| 400 Mbit/s | −59 dBm | 49 m |
| 200 Mbit/s | −69 dBm | 157 m |
| 100 Mbit/s | −76 dBm | 348 m |
| 50 Mbit/s | −82 dBm | 678 m |
| 10 Mbit/s | −90 dBm | 1629 m |

Distance is not the limit at a 20 to 120 m working range. Rubble is: one dense concrete wall costs
10 to 30 dB. Mount the router high on the vehicle.

Each module needs a USB WiFi adapter with an external antenna (an MT7921AUN, for example), because
the Pi's onboard trace antenna loses range next to batteries and motors. An ESP32 is out: 11 to
20 Mbit/s and too slow to JPEG-encode while flying.

## Setup

### Router

No reset needed. Use a fixed channel (1, 6 or 11) at 20 MHz width if the router's page allows it,
and make sure "AP isolation" is off, or the clients can't reach each other.

| Device | IP | How |
| --- | --- | --- |
| Station | 192.168.1.10 | Ethernet |
| UAV module | 192.168.1.20 | WiFi |
| UGV module | 192.168.1.30 | WiFi |

Pick addresses outside the router's DHCP pool. On a Pi:

```bash
sudo nmcli con mod "<ssid>" ipv4.method manual ipv4.addresses 192.168.1.20/24
sudo nmcli con up "<ssid>"
sudo iw wlan0 set power_save off    # otherwise latency spikes
```

Power: the HG658 takes 12 V DC. A car socket gives 12 to 14.4 V, so use a regulated 12 V
DC-DC cable or a power bank with 12 V output.

### Captive screen on the Mac

The router has no internet, so it answers every web request with its own page. macOS checks
connectivity by loading an Apple page, gets the router's page instead, and opens a login window.
Traffic between the devices isn't affected. Two fixes:

1. Connect the station by Ethernet. Wired connections don't get the window.
2. On Wi-Fi: System Settings → Wi-Fi → Details on the router's network. Under TCP/IP set
   "Configure IPv4" to Manually, IP 192.168.1.10, subnet 255.255.255.0, Router empty. Under DNS,
   remove the router and add 127.0.0.1. The check now fails outright, macOS shows "No internet
   connection", and no window opens. This only applies to that network.

If the window still opens, this switch worked on older macOS and may not on the newest:

```bash
sudo defaults write /Library/Preferences/SystemConfiguration/com.apple.captive.control Active -bool false
```

The Pis have no screen, so they never get the window.

## Message formats

| Field | State |
| --- | --- |
| Detection output | Agreed: JSON `[{"image", "bbox_xyxy", "conf"}]`, written by `src/detection/detect.py:16` |
| Frame container | Agreed: one JPEG per frame, with a timestamp, position and attitude ([SPEC.md](../../SPEC.md#streams)) |
| Coordinate frame | Open: `bbox_xyxy` is image pixels today, ground metres wanted |
| Transport | Open: none exists. `detect.py` writes a file, not a socket |
| Timing | Open: GPS time on each module would remove the need for clock sync |
| Loss behaviour | Open: what the station does with a dropped frame |

Proposals for the open rows are in [QUESTIONS.md](../../QUESTIONS.md#open).

## Measuring

```bash
iperf3 -c <module-ip> -t 60 -i 1        # module runs iperf3 -s
```

Throughput at 20, 50 and 100 m, then again through one and two rubble walls.

- [ ] Real camera JPEG size: `?` bytes
- [ ] Throughput on the HG658, module to station: `?` Mbit/s
- [ ] Range through one rubble wall: `?` m
- [ ] End-to-end latency: `?` ms

## Sources

- HG658 specs: [TechInfoDepot](https://techinfodepot.shoutwiki.com/wiki/Huawei_HG658), [HG658 V2 user manual](https://usermanual.wiki/Huawei-Technologies/HG658V2).
- Throughput against RSSI, 802.11ax 5 GHz 80 MHz: [Candela Wi-Fi station test report](https://reports.candelatech.com/reports/Wi-Fi%20Station%20Testing/Candela%20Wi-Fi%20Station%20Test%20Solution.pdf).
- Real-world rates by band: [HP knowledge base](https://h30434.www3.hp.com/t5/Laptops-Knowledge-Base/Real-world-WiFi-speed-and-flex-repeater-booster-system/ta-p/9110464), [Cisco](https://www.cisco.com/c/en/us/support/docs/wireless-mobility/wireless-lan-wlan/212892-802-11ac-wireless-throughput-testing-and.html).
- Pi 5 H.264 software encoding: [Raspberry Pi white paper](https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-010033-WP-1-H.264%20encoding%20performance%20on%20Raspberry%20Pi%205_series%20computers.pdf).
