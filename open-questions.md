# Open Questions and Assumptions

> **Status:** Draft · **Updated:** 2026-10-18

Two kinds of uncertainty live here. **Questions** are things we do not know and should find out.
**Assumptions** are things we are treating as true without having verified them; they are not
modelled in the system, they define its boundary, and if one turns out false we log that in
[CHANGELOG.md](CHANGELOG.md).

Answers are not repeated here. The changelog is the single place to find them.

## Open questions

| Question | Blocking? |
| --- | --- |
| How does the station plan the robot's path from aerial imagery (robot localisation, obstacle and terrain handling, dynamic replanning)? | Yes |
| What happens when the link is lost? The station must keep working from its last detections and the drone must return. Neither behaviour is implemented. | Yes |
| How do we handle the detector's failure on real footage (AP50 0.010 on WiSARD thermal against 0.872 on HIT-UAV)? Retrain on HIT-UAV + WiSARD, or ship a detector that only works on HIT-UAV? | Yes |
| Which drone and camera? Every resolution, frame rate and range number in [research/communication/](research/communication/) moves if the hardware differs from what we assumed. The computer is settled: a Raspberry Pi on both the drone and the robot. The radio and camera are not. | Yes |
| The drone hovers over a known collapse site, so it never searches. If the team is handed a whole cell sector instead, does the robot search the rest, or does the drone sweep? Both change the architecture and neither is built. | Yes |
| How is the remaining 29 Mbit/s split between the robot stream and the operator UI, given that the robot's contribution is unbudgeted? | Yes |
| Measured throughput and range in real rubble, rather than free space? [Estimated so far](research/communication/); the measurement plan is in that file. | No |
| With a stationary drone and a single station, what decisions remain for the orchestrator, and is RL / decision-theoretic planning still in scope? | No |
| Who can request carrier location data, how fast, and how accurate is it? What do we assume in the demo? | No |
| How do we evaluate: simulation, recorded data, or a live demo with the Robotics team? | No |
| Is the audio / dialogue module still in scope, and what structured signals does it output? | No |

## Assumptions

> [!IMPORTANT]
> These are **not** modeled in the system. They define the boundary of what we build.

| Assumption | Rationale | Risk if false | Status |
| --- | --- | --- | --- |
| Rescue teams can request last-known-location data of phones in the area from mobile carriers (CDR / cell site analysis), giving a candidate zone, which an operator narrows to a specific collapse site before deployment. | Used operationally in search and rescue elsewhere. | We do not know where to deploy. | Open |
| The drone and the robot both run a Raspberry Pi and join the station's network as clients. | One bill of materials, one provisioning process, shared spares. The Robotics team confirmed the robot side. | A Pi Zero 2W would be ruled out, since it has no 5 GHz radio. | Open |
| The vehicle drives to a predefined location and stays there. | Defines a stationary station. | Station must move; coverage changes. | Agreed |
| The ground robot's drop point is known. | Needed for path planning. | Robot localisation becomes harder. | Agreed |
| The vehicle drives to a **known collapse site** and the drone hovers over it. | Core of the pivot. The operator narrows the CDR cell sector down to a specific building before deployment; the drone then hovers over that building rather than searching it. | A hover covers 58 × 43 m at 40 m, 0.0025 km², and never grows. An urban cell sector is about 28 km², so one hover is roughly 11,000 times short. If the team is handed a sector rather than a building, the station has nothing to do. | Agreed |
| WiFi connects the station to both the drone and the robot. | Diagram shows WiFi links. | Video and control links fail. | Open |
| The station laptop is the WiFi access point; drone and robot are clients on one network. | Avoids a second powered device at the site; the station is already the only compute node. | Sharing WiFi over WiFi costs 30 to 40% throughput, and a client limit may be reached. | Open |
| Each link sustains at least 100 Mbit/s, halved from a pessimistic 200 Mbit/s real-world 5 GHz client rate. | Half the realistic maximum leaves headroom for a degraded link. | Every image size and frame rate in [research/communication/](research/communication/) scales with this. | Open |
| Rubble attenuates the link by no more than one wall's worth on the flight path. | Post-earthquake rubble is the main non-free-space loss. | The link drops and the drone must return; no return behaviour is implemented. | Open |

> [!NOTE]
> Carrier location data is typically accurate to a cell sector, so it narrows the search area rather than pinpointing a person. A fixed-point hover only works once a human narrows that sector to a specific collapse site; the station does not search.

## Resolved

| Question | Answer logged in changelog |
| --- | --- |
| The scenario diagram says the drone processes and tags victims. Does any processing happen on the drone? | [2026-10-04](CHANGELOG.md) |
| How do we use the WiFi, and what bandwidth do we design against? | [2026-10-18](CHANGELOG.md) |
| What photo resolutions, frame rates and distances can the WiFi link support? | [2026-10-18](CHANGELOG.md) |
| Which YOLO models are suitable? | [2026-10-18](CHANGELOG.md) |
