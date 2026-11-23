# Agentic Aerial-Ground Robot Collaboration for Victim Detection and Triage

CSCI 408 senior project, Group 19.

After an earthquake, roads, buildings and phone networks are damaged, and sending people into an unassessed area is slow and dangerous. A vehicle carries a laptop (the station), a WiFi router, a drone and a ground robot to a collapse site. A pilot flies the drone; a UAV module on it streams RGB video to the station, which finds victims and shows them on a map. A UGV module on the robot lets the operator send it to a victim, drive it, and talk to the victim. Both modules work on any drone or robot of their kind.

| File | What's in it |
| --- | --- |
| [TODO.md](TODO.md) | What to do next. Start here |
| [SPEC.md](SPEC.md) | What we are building: agreed decisions, modules, interfaces, operator map |
| [QUESTIONS.md](QUESTIONS.md) | Everything not settled, with the agenda for the next supervisors' meeting on top |
| [research/datasets/](research/datasets/) | Training and test data, results, laptop test plan, earlier dataset audits |
| [research/communication/](research/communication/) | Link budget and network setup |
| [research/literature/](research/literature/) | Literature review (CSV) |
| [src/detection/](src/detection/) | Detector training and scoring code |
| [interface/](interface/) | Operator UI |
| [paper/](paper/) | Final report (LaTeX) and `references.bib` |

## Deployment diagram

What runs where, and what each WiFi link carries. Mermaid has no UML deployment syntax, so this is a flowchart drawn in that style.

```mermaid
flowchart LR
    subgraph DR["Drone, flown by a pilot"]
        subgraph UAV["UAV module: Raspberry Pi"]
            DC["RGB camera"]
            DT["GPS, compass, IMU"]
            DS["Frame streamer<br/>(+ SD recording)"]
            DC --> DS
            DT --> DS
        end
    end
    subgraph VE["Vehicle"]
        RT["WiFi router"]
        subgraph ST["Station laptop"]
            RGB["RGB detector<br/>YOLO26"]
            MAP["Operator map"]
            CTL["Robot control"]
            RGB --> MAP
        end
        RT ---|"Ethernet"| ST
    end
    subgraph RO["Ground robot"]
        subgraph UGV["UGV module: Raspberry Pi"]
            RC["RGB camera"]
            RG["GPS, compass, IMU"]
            RA["Microphone, speaker"]
        end
        RN["Robot controller<br/>(Robotics team)"]
        UGV <-->|"serial"| RN
    end
    UAV -->|"RGB frames + pose (WiFi)"| RT
    UGV <-->|"video, status, audio /<br/>modes, commands, audio (WiFi)"| RT
```

## Sequence diagram: one mission

```mermaid
sequenceDiagram
    participant T as Rescue team
    participant C as Mobile carrier
    participant O as Operator + station
    participant P as Pilot + drone
    participant R as Ground robot
    participant V as Victim
    T->>C: Request last known phone locations
    C-->>T: Candidate zone (a cell sector)
    T->>O: Narrow it to one collapse site, drive there, park
    O->>P: Fly over the site
    loop Every frame
        P->>O: RGB frame, GPS, altitude, attitude
        O->>O: Detect, place boxes on the ground, update map
    end
    O->>O: Operator confirms a victim marker
    O->>R: AUTO: go to the victim's coordinates
    loop Until the robot reaches the victim
        R->>O: Video, position, status
        O-->>R: Operator takes over (MANUAL) when needed
    end
    R-->>V: Two-way audio with the operator
    O->>O: Operator marks the victim reached, adds a note
    O->>T: Victim locations and notes
```

## State diagram: a victim marker

What the station tracks for each victim. A marker stays on the map after the person leaves the drone's frame, with the time they were last seen.

```mermaid
stateDiagram-v2
    [*] --> Detected: box from the RGB detector
    Detected --> Rejected: operator says false positive
    Detected --> Confirmed: operator confirms
    Confirmed --> Dispatched: robot sent there
    Dispatched --> Reached: robot reaches the victim
    Rejected --> [*]
    Reached --> [*]
```

## Team

| Name | Email |
| --- | --- |
| Askar Matayev | askar.matayev@nu.edu.kz |
| Ruslan Nagimov | ruslan.nagimov@nu.edu.kz |
| Yelzhan Rakhimzhanov | yelzhan.rakhimzhanov@nu.edu.kz |
| Bakhtiyar Yesbolsyn | bakhtiyar.yesbolsyn@nu.edu.kz |
| Nurbek Baktygali | nurbek.baktygali@nu.edu.kz |

Supervisors: Adnan Yazici (main, adnan.yazici@nu.edu.kz), Enver Ever (enverevermetu@gmail.com), Muhammad Toaha Khan (khan@metu.edu.tr).

Robotics team, who build the ground robot: Gourav Devappa (supervisor, gourav.devappa@nu.edu.kz), Mirat Serik (mirat.serik@nu.edu.kz), Adil Ismagambetov (adil.ismagambetov@nu.edu.kz), Yevgeniy Dikun (yevgeniy.dikun@nu.edu.kz).
