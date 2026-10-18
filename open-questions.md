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
| Which drone and camera? Every resolution, frame rate and range number in [research/communication/](research/communication/) moves if the hardware differs from what we assumed. | Yes |
| Does the drone hover or sweep? [A hover covers 0.068 ha at 40 m](research/communication/) and never grows; a 2 m/s sweep covers 1.4 ha in two minutes. The pivot assumes a hover. | Yes |
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
| Rescue teams can request last-known-location data of phones in the area from mobile carriers (CDR / cell site analysis), giving a candidate zone. | Used operationally in search and rescue elsewhere. | We do not know where to deploy. | Open |
| The vehicle drives to a predefined location and stays there. | Defines a stationary station. | Station must move; coverage changes. | Agreed |
| The ground robot's drop point is known. | Needed for path planning. | Robot localisation becomes harder. | Agreed |
| The drone hovers at a fixed point with the victim area in view. | Core of the pivot. | Coverage gaps. A hover covers 0.068 ha at 40 m and never grows. | Agreed, now contested |
| WiFi connects the station to both the drone and the robot. | Diagram shows WiFi links. | Video and control links fail. | Open |
| The station laptop is the WiFi access point; drone, robot and the operator's phone are clients on one network. | Avoids a second powered device at the site; the station is already the only compute node. | Sharing WiFi over WiFi costs 30 to 40% throughput, and a client limit may be reached. | Open |
| Each link sustains at least 100 Mbit/s, halved from a pessimistic 200 Mbit/s real-world 5 GHz client rate. | Half the realistic maximum leaves headroom for a degraded link. | Every image size and frame rate in [research/communication/](research/communication/) scales with this. | Open |
| Rubble attenuates the link by no more than one wall's worth on the flight path. | Post-earthquake rubble is the main non-free-space loss. | The link drops and the drone must return; no return behaviour is implemented. | Open |

> [!NOTE]
> Carrier location data is typically accurate to a cell sector, so it narrows the search area rather than pinpointing a person.

## Resolved

| Question | Answer logged in changelog |
| --- | --- |
| The scenario diagram says the drone processes and tags victims. Does any processing happen on the drone? | [2026-10-04](CHANGELOG.md) |
| How do we use the WiFi, and what bandwidth do we design against? | [2026-10-18](CHANGELOG.md) |
| What photo resolutions, frame rates and distances can the WiFi link support? | [2026-10-18](CHANGELOG.md) |
| Which YOLO models are suitable? | [2026-10-18](CHANGELOG.md) |
| Do we need a separate access point to connect the operator's phone to the laptop? | [2026-10-18](CHANGELOG.md) |
