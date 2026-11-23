# Questions

Everything not yet settled. When something is decided, move it to [SPEC.md](SPEC.md) and delete it here.

## Next supervisors' meeting

1. Thermal and triage are now out of scope, though the project title still says "Triage". Is that acceptable?
2. Does "the station proposes which victim is next, and the robot drives there itself" count as the agent decision-making they expect?

## For the Robotics team

We send them the [UGV module interface](SPEC.md#ugv-module-interface) and ask:

- Does their controller speak MAVLink (ArduPilot Rover, PX4)? If yes, we use it as is. If not, we agree a small serial protocol between the module and their controller.
- Does go-to-a-point run on their controller or on the module?
- How does the sphere know its heading? A compass inside a rolling shell needs a stabilised inner platform.
- Where does the module's antenna go, and how much weight can the robot carry?

## Open

| #   | Question | Recommendation | Blocking? |
| --- | --- | --- | --- |
| 1   | Which drone carries the UAV module, and how is it mounted and powered? | Any drone that lifts about 300 g, with the module on its own battery. | Yes |
| 2   | Which router replaces the HG658? | A dual-band Wi-Fi 6 travel router powered over USB-C, so it runs from a power bank. | No |
| 3   | Link loss on the station and robot side. | Station keeps markers and marks the feed stale; module records to SD and reconnects; robot holds after 1 s without a heartbeat. | No |
| 4   | When are two detections the same victim? | Within about 3 m on the map. An image tracker loses track when the pilot moves the camera. | No |
| 5   | Message formats. | One WebSocket per module. Each frame is a JSON header (sequence, GPS time, position, attitude) plus the JPEG; the station uses the newest frame and drops the rest. Robot commands and status as JSON on the same socket, with a 5 Hz heartbeat. Audio over WebRTC. | No |
| 6   | Agent decisions. | The station ranks confirmed victims by distance and proposes the next one; the operator approves. Log every operator choice from now on. | No |
| 7   | Pointing the operator at the victim on the robot's video. | A bearing arrow and distance, not a box: GPS is 2 to 5 m off on each end. | No |
