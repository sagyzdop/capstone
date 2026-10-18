# Robot Capabilities

> **Status:** Draft · **Updated:** 2026-10-18

Facts as reported by the Robotics team. Always record the source and date.

| Attribute | Value | Source | Date |
| --- | --- | --- | --- |
| Platform / locomotion | Spherical "tumbleweed" rolling robot | Team | 2026-10-04 |
| Onboard compute | Raspberry Pi, same hardware as the drone | Team | 2026-10-18 |
| Pi model | TBD | — | — |
| WiFi radio | TBD | — | — |
| External antenna | TBD | — | — |
| Dimensions and mass | TBD | TBD | TBD |
| Battery life | TBD | TBD | TBD |
| Thermal camera | TBD | TBD | TBD |
| Microphone / speaker | TBD | TBD | TBD |
| WiFi range | TBD | TBD | TBD |
| Terrain limits | TBD | TBD | TBD |

## What we still need from them

Using the same computer as the drone means one bill of materials, one provisioning process and shared
spares. Three things decide whether the radio works:

1. **Which Pi model?** A Pi Zero 2W is ruled out: 2.4 GHz only, no 5 GHz. Pi 4 and Pi 5 are both
   dual-band 802.11ac. See [research/communication/](../research/communication/).
2. **Onboard WiFi or a USB adapter?** The onboard radio is 1×1 with a PCB trace antenna and measures
   80 to 110 Mbit/s in the lab. Our two streams plus a robot feed want about 74 Mbit/s, so that is
   most of the capacity spent before any range loss.
3. **Antenna on the airframe, or on the body?** A trace antenna next to a battery and a motor will
   detune. This matters more for the robot than the drone, since it works at ground level among walls.

## Link requirement

Bandwidth is not the robot's constraint. A 720p30 H.264 feed with two-way audio and telemetry is
about 2.6 Mbit/s. What the robot needs is that audio survives a contended or dropped link: two-way
conversation needs under 300 ms round trip, and reassociation takes seconds.

The station must therefore make audio failure visible rather than silent, whatever radio the robot
carries.
