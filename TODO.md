# TODO

Start here. Tick a line when it's done, and delete it once nobody needs to see it.

## In the lab

- [x] Conversion and training scripts are in `src/detection/` (`convert.py`, `train.py`); commands, settings, SARD details and the NII-CU-MAPD variant are in [research/datasets/README.md](research/datasets/README.md#conversion-and-training).
- [x] Train YOLO26n RGB and fill its own-val results ([results](research/datasets/README.md#runs)).
- [x] Train YOLO26n thermal and fill its own-val results ([results](research/datasets/README.md#runs)).
- [x] Train YOLO26s RGB and thermal and compare with nano ([results](research/datasets/README.md#findings)): small barely helps, nano stays the default.
- [x] Score the RGB models on HERIDAL ([results](research/datasets/README.md#heridal)): AP50 about 0.01, both sizes, tiled or not.
- [x] Retrain YOLO26n RGB with HERIDAL (location split, `--tag heridal`): HERIDAL test AP50 0.015 to 0.215, SARD and NII-CU-MAPD unchanged ([findings](research/datasets/README.md#findings)).
- [x] Try HERIDAL only, and HERIDAL weighted 3× with `best.pt` picked on HERIDAL val: neither beats the mixed run ([findings](research/datasets/README.md#findings)).
- [x] Add NOMAD to RGB training (`--tag nomad`, saved as `best2.pt`): NOMAD test tiled AP50 0.086 to 0.300, HERIDAL test 0.215 to 0.192 ([findings](research/datasets/README.md#findings)).
- [ ] Check NOMAD's license before publishing anything trained on it.
- [ ] Next RGB data, one dataset per run, scored on HERIDAL and NOMAD test: a capped C2A sample ([more data](research/datasets/README.md#more-data)).
- [x] Check whether the RGB model saw RGBTDronePerson's RGB images. The first one did, and scored AP50 0.06 on them; `train.py` now trains RGB without them ([why](research/datasets/README.md#rgbtdroneperson)).
- [ ] Test the RGB model on WiSARD, which it never trained on: download the sample again (it was only kept in the dropped npz format), convert it to `data/yolo/`, run `src/detection/eval_sizes.py` with and without `--tile 640`, fill the results table.
- [ ] Run the laptop test, nano then small ([steps](research/datasets/README.md#test-on-the-station-laptop)). Replace the estimated frame rates in [SPEC.md](SPEC.md#streams) with what you measure.

## Research

- [ ] Plan how operator control grows into agent decisions (RL or decision-theoretic planning): which decisions an agent would take over first (which victim next, where the pilot should fly), and what the station has to log now so that it can be trained or evaluated later. Start from GLIDE and Gemini in `paper/references.bib`.
- [ ] Read the Archangel paper's accuracy-by-altitude results and update the altitude table in [research/datasets/README.md](research/datasets/README.md#how-high-the-drone-can-fly).
- [ ] Set the detection target score from the held-out WiSARD and HERIDAL results, once they exist.

## Next supervisors' meeting

- [ ] Be ready to explain the agenda in [QUESTIONS.md](QUESTIONS.md#next-supervisors-meeting).
- [ ] After the meeting, move whatever got decided from QUESTIONS.md into SPEC.md.

Already answered, and recorded in SPEC.md: the evaluation is a live demo; RL / agent decisions are expected; the demo assumes the carrier data and collapse site are given; audio stays in scope.

## Robotics team

- [ ] Send them the [UGV module interface](SPEC.md#ugv-module-interface) and the questions in [QUESTIONS.md](QUESTIONS.md#for-the-robotics-team).

## Network

- [ ] Set fixed IPs on the station and both modules, and run `iperf3` between them on the current router ([setup](research/communication/README.md#setup)).
