# Assumptions

> **Status:** Draft · **Updated:** 2026-10-04

> [!IMPORTANT]
> These assumptions are **not** modeled in the system. They define the boundary of what we build. If one turns out false, log it in [CHANGELOG.md](../CHANGELOG.md).

| Assumption | Rationale | Risk if false | Status |
| --- | --- | --- | --- |
| Rescue teams can request last-known-location data of phones in the area from mobile carriers (CDR / cell site analysis), giving a candidate zone. | Used operationally in search and rescue elsewhere. | We do not know where to deploy. | Open |
| The vehicle drives to a predefined location and stays there. | Defines a stationary station. | Station must move; coverage changes. | Agreed |
| The ground robot's drop point is known. | Needed for path planning. | Robot localisation becomes harder. | Agreed |
| The drone hovers at a fixed point with the victim area in view. | Core of the pivot. | Coverage gaps. | Agreed |
| WiFi connects the station to both the drone and the robot. | Diagram shows WiFi links. | Video and control links fail. | Open |

> [!NOTE]
> Carrier location data is typically accurate to a cell sector, so it narrows the search area rather than pinpointing a person.
