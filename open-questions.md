# Open Questions

> **Status:** Draft · **Updated:** 2026-10-18

Unresolved questions live under **Open**. When a question is answered, move it to **Resolved** and record the answer in [CHANGELOG.md](CHANGELOG.md). Answers are **not** repeated here; the changelog is the single place to find them.

## Open

| Question | Blocking? |
| --- | --- |
| How does the station plan the robot's path from aerial imagery (robot localisation, obstacle and terrain handling, dynamic replanning)? | Yes |
| Which streams get the bandwidth? Thermal at 30 FPS plus RGB at 10 FPS is 71 Mbit/s, and 4K as well is 101, which is the entire 100 Mbit/s link with nothing left for the robot or the operator. Options are in [docs/interfaces.md](docs/interfaces.md). | Yes |
| What happens when the link is lost? The station must keep working from its last detections and the drone must return. Neither behaviour is implemented. | Yes |
| How do we handle the detector's failure on real footage (AP50 0.010 on WiSARD thermal against 0.872 on HIT-UAV)? Retrain on HIT-UAV + WiSARD, or ship a detector that only works on HIT-UAV? | Yes |
| Which drone and camera? Every resolution, frame rate and range number in [research/communication/](research/communication/) moves if the hardware differs from what we assumed. | Yes |
| Measured throughput and range in real rubble, rather than free space? [Estimated so far](research/communication/); the measurement plan is in that file. | No |
| With a stationary drone and a single station, what decisions remain for the orchestrator, and is RL / decision-theoretic planning still in scope? | No |
| Who can request carrier location data, how fast, and how accurate is it? What do we assume in the demo? | No |
| How do we evaluate: simulation, recorded data, or a live demo with the Robotics team? | No |
| Is the audio / dialogue module still in scope, and what structured signals does it output? | No |

## Resolved

| Question | Answer logged in changelog |
| --- | --- |
| The scenario diagram says the drone processes and tags victims. Does any processing happen on the drone? | [2026-10-04](CHANGELOG.md) |
| How do we use the WiFi, and what bandwidth do we design against? | [2026-10-18](CHANGELOG.md) |
| What photo resolutions, frame rates and distances can the WiFi link support? | [2026-10-18](CHANGELOG.md) |
| Which YOLO models are suitable? | [2026-10-18](CHANGELOG.md) |
| Do we need a separate access point to connect the operator's phone to the laptop? | [2026-10-18](CHANGELOG.md) |
