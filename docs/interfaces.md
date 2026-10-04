# Interfaces

> **Status:** Draft · **Updated:** 2026-10-04

Every link between components in one diagram. Links involving the robot must be reviewed by the Robotics team. Rates and message formats are TBD.

```mermaid
flowchart LR
    D["Drone"] -- "video + images<br/>WiFi" --> S["Station"]
    S -- "path / waypoints<br/>WiFi" --> R["Ground robot"]
    R -- "video, thermal, audio, status<br/>WiFi" --> S
    R <-. "two-way audio<br/>mic / speaker" .-> V(("Victim"))
    S -- "victim location + status<br/>operator UI" --> T["Rescue team"]
```

## Agreed details

_Add notes on message format, rate, units and coordinate frame for each link once agreed._
