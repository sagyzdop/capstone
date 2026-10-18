# Research: Project State and Contribution Plan

> **Status:** Draft · **Updated:** 2026-10-18

What has been done so far, what stops teammates from contributing, and a plan to fix it. Based on a review of the repository and local working copy on 2026-10-18.

## 1. Repository state

- Remote: `https://github.com/sagyzdop/capstone.git`, single branch `main`.
- 4 commits (2026-10-04 to 2026-10-08), all by one author, all documentation.
- **Uncommitted work** (exists only on one laptop):

| Path | Change |
| --- | --- |
| `src/detection/` (`prepare.py`, `analyze.py`, `detect.py`, `README.md`) | New, untracked |
| `notebooks/train_colab.ipynb` | New, untracked |
| `station/detection-data-analysis.md`, `station/assets/` | New, untracked |
| `literature/datasets.md` | +27 lines (dataset shortlist) |
| `CHANGELOG.md`, `README.md`, `src/README.md`, `.gitignore` | Small edits |

- Local disk: ~14 GB, almost all in `data/` (git-ignored): raw C2A 9.3 GB, HIT-UAV 1.6 GB, WiSARD sample 1.9 GB, converted YOLO sets 61 MB. Weights (`*.pt`) and `runs/` are git-ignored.

## 2. What has been done

### Documentation and process

- README with system diagram, repository map, status checklist, contacts (team, supervisors, Robotics team) and conventions.
- `docs/`: overview with concept of operations, architecture, interfaces (links only, formats TBD), assumptions table, glossary.
- `CHANGELOG.md` with decisions; `open-questions.md` with 6 open and 1 resolved question.
- Templates for meeting notes and literature notes.
- `ground-robot/`: capabilities and requirements tables (mostly TBD).
- `paper/main.tex`: section skeleton, all sections TBD.
- `literature/references.bib`: 5 entries; reading list all "To read"; `literature/notes/` and `meeting-notes/` empty.

### Decisions logged (2026-10-04)

- Drone is stationary (hovers at one point), no processing on the drone.
- Station laptop is the orchestrator and the only compute node.
- Vehicle drives to a predefined location and stays there.
- Victim-location prior comes from carrier data (CDR / cell site analysis).
- Robot drop point is known; robot is a spherical "tumbleweed" built by the Robotics team.
- All links use WiFi.

Rationale for the first two decisions is still "_to be added by the team_".

### Datasets (2026-10-15)

16 aerial person-detection datasets reviewed in `literature/datasets.md`.

| Dataset | Modality | Role | Notes |
| --- | --- | --- | --- |
| HIT-UAV | Thermal | Train (thermal) | CC0, 2,898 imgs, 12,312 persons, campus/roads, not disaster |
| C2A | RGB | Train (RGB) | Synthetic humans on disaster scenes, 10,215 imgs, 360k+ persons, license unclear |
| WiSARD (sample) | RGB + thermal | Cross-dataset test | Real SAR, one flight, 264 frames per modality |
| HERIDAL | RGB | Real-world test | CC BY 3.0, 8.3 GB, not downloaded yet |
| NOMAD | RGB | Evaluating | Best real data, blocked on license and size |

Licenses marked `?` must be confirmed with authors before publishing models trained on them.

### Detection pipeline (`src/detection/`)

- `prepare.py`: converts YOLO or COCO labels to a single-class `person` YOLO dataset; images symlinked, negatives kept; writes `data/yolo/<name>.yaml`.
- `analyze.py`: person-size statistics and plots versus model input size.
- `detect.py`: runs a trained model on an image or folder and writes `[{"image", "bbox_xyxy", "conf"}]` JSON. This is the only defined inter-module format so far.
- `notebooks/train_colab.ipynb`: clone, download data (~6.7 GB), prepare, train HIT-UAV then C2A, evaluate on test splits and WiSARD, download results.

### Data analysis findings (`station/detection-data-analysis.md`)

- **Persons are tiny in every dataset.** HIT-UAV median 14.9 px (p5 9.9, p95 24.4); C2A median 12 px with 35% under 8 px even at full resolution.
- HIT-UAV person size drops with altitude: 16 px at 60 m to 11–12 px at 120–130 m.
- `imgsz=320` is ruled out (59% of HIT-UAV persons fall below 8 px). Train at 640; test 960.
- C2A recall will be capped by the 35% of persons under 8 px, regardless of imgsz.
- WiSARD 4K RGB frames shrink 6× at 640 (67 px persons become ~11 px). Tiling into 640 crops is worth testing if real RGB recall is low.
- HIT-UAV has no disaster scenes and no separate labels for lying or occluded people: expect a domain gap on rubble.
- HIT-UAV filename day/night flag meaning is unverified.

### First training run

YOLO11n, HIT-UAV, `imgsz=640`, `batch=16`, `device=mps`, 50 epochs planned (patience 15). Stopped during epoch 15 when training moved to Colab. Weights at `runs/runs/hituav-n-640/weights/best.pt` (local only).

| Epoch | mAP50 (val) | mAP50-95 (val) |
| --- | --- | --- |
| 1 | 0.638 | 0.272 |
| 6 | 0.821 | 0.393 |
| 9 | 0.830 | 0.409 |
| 14 (last) | **0.848** | **0.430** |

Epoch 14 precision 0.847, recall 0.808. Validation mAP is noisy between epochs (0.43–0.85) and the run did not converge. No test-split or WiSARD evaluation yet. About 100 s per epoch on Apple MPS.

### Not started

Path planning, orchestrator, operator UI, drone stream ingest, robot interface, message formats in `docs/interfaces.md`, paper text, literature notes, meeting notes.

## 3. Blockers for contributors

1. **Detection work is not pushed.** Teammates only see documentation. The Colab notebook clones the repo, so it fails for everyone else because `src/detection/` does not exist on GitHub.
2. **Access is unclear.** The notebook hints the repo is private (token in the clone URL). Collaborator list not verified.
3. **No shared storage for data, weights or results.** Data and weights are correctly kept out of git, but nothing replaces them. Each Colab session re-downloads ~6.7 GB; `best.pt` exists only on one disk.
4. **Setup is not reproducible.** No `requirements.txt`; versions not pinned; the README hardcodes `device=mps` (Mac only), while the notebook uses `batch=32` on CUDA.
5. **No ownership.** Six planned modules, five people, every role in the README is "-". No issues, board or workflow.
6. **Interfaces are undefined.** Message format, rate, units and coordinate frame are TBD for every link, so modules cannot be built in parallel.
7. **Robotics team inputs missing.** Robot capabilities and their requirements from us are all TBD.

Minor: README status checklist still shows "Detection baseline running" unchecked; typos "architecure", "tumblweed" in the README.

## 4. Plan

### Phase 0: unblock (one person, ~1 hour)

- [ ] Commit pending work in logical commits (dataset docs; detection code and analysis; Colab notebook) and push.
- [ ] Add a pinned `requirements.txt` (`ultralytics`, `gdown`); make `device` a parameter in the docs.
- [ ] Add all teammates as GitHub collaborators.
- [ ] Run the notebook from a fresh clone in Colab to confirm it works end to end.

### Phase 1: workflow (one team meeting)

- [ ] Rule: feature branch → pull request → 1 review → merge. Enable branch protection on `main`.
- [ ] Keep the existing conventional commit style (`feat(detection): ...`, `docs(...): ...`).
- [ ] Add a short `CONTRIBUTING.md`: setup, branch/PR rule, link to the README conventions.
- [ ] Create GitHub Issues from the `src/README.md` module table and `open-questions.md`; labels `module:*`, `blocking`; one GitHub Projects board.

### Phase 2: one owner per workstream

Fill the Role column in the README.

| Workstream | Starting point |
| --- | --- |
| Detection | Finish HIT-UAV run, train C2A, evaluate on test and WiSARD, try `imgsz=960` and tiling |
| Path planning | Open question #1; input is the detection JSON plus the known drop point |
| Orchestrator + operator UI | Mission state machine; map and feed view |
| Drone ingest + drone specs | `drone/README.md` TBDs; stream frames into `detect.py` |
| Robot interface + Robotics liaison | `ground-robot/requirements.md`; agree waypoint and status format |
| Literature + paper (shared) | Reading list, one note per paper, `paper/main.tex` (Overleaf GitHub sync) |

### Phase 3: shared artifacts

- [ ] Shared Google Drive folder for raw dataset zips and weights; the Colab notebook mounts it instead of re-downloading.
- [ ] Publish weights as GitHub Release assets (or Drive links) referenced from `src/detection/README.md`.
- [ ] Experiment log table (run, data, imgsz, mAP50, mAP50-95, weights link); every training PR adds a row.

### Phase 4: agree interfaces before more code

- [ ] Fill `docs/interfaces.md` per link: format, rate, units, coordinate frame. Robotics team reviews robot links.
- [ ] Each module ships a mock input (recorded frames, fake detection JSON, fake robot status) so nobody waits on another module.

## 5. Open items to resolve with the team

- Rationale for the stationary-drone and station-only-compute decisions (CHANGELOG placeholders).
- Evaluation method: simulation, recorded data, or live demo with the Robotics team.
- Whether the audio / dialogue module and RL-based orchestration stay in scope.
- Dataset licenses marked `?` (C2A, NOMAD, WiSARD).
