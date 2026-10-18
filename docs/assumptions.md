# Assumptions

> **Status:** Draft · **Updated:** 2026-10-18

> [!IMPORTANT]
> These assumptions are **not** modeled in the system. They define the boundary of what we build. If one turns out false, log it in [CHANGELOG.md](../CHANGELOG.md).

| Assumption | Rationale | Risk if false | Status |
| --- | --- | --- | --- |
| Rescue teams can request last-known-location data of phones in the area from mobile carriers (CDR / cell site analysis), giving a candidate zone. | Used operationally in search and rescue elsewhere. | We do not know where to deploy. | Open |
| The vehicle drives to a predefined location and stays there. | Defines a stationary station. | Station must move; coverage changes. | Agreed |
| The ground robot's drop point is known. | Needed for path planning. | Robot localisation becomes harder. | Agreed |
| The drone hovers at a fixed point with the victim area in view. | Core of the pivot. | Coverage gaps. | Agreed |
| WiFi connects the station to both the drone and the robot. | Diagram shows WiFi links. | Video and control links fail. | Open |
| The station laptop is the WiFi access point; drone, robot and the operator's phone are clients on one network. | Avoids a second powered device at the site; the station is already the only compute node. | Sharing WiFi over WiFi costs 30–40% throughput, and a client limit may be reached. | Open |
| Each link sustains at least 100 Mbit/s, halved from a pessimistic 200 Mbit/s real-world 5 GHz client rate. | Half the realistic maximum leaves headroom for a degraded link. | Every image size and frame rate in [research/communication/](../research/communication/) scales with this. | Open |
| Rubble attenuates the link by no more than one wall's worth on the flight path. | Post-earthquake rubble is the main non-free-space loss. | The link drops and the drone must return; no return behaviour is implemented. | Open |

> [!NOTE]
> Carrier location data is typically accurate to a cell sector, so it narrows the search area rather than pinpointing a person.
