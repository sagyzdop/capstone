# TODO

Start here. Tick a line when it's done, and delete it once nobody needs to see it.

## In the lab

- [x] Conversion and training scripts are in `src/detection/` (`convert.py`, `train.py`); commands, settings, SARD details and the NII-CU-MAPD variant are in [research/datasets/README.md](research/datasets/README.md#conversion-and-training).
- [x] Train YOLO26n RGB and fill its own-val results ([results](research/datasets/README.md#runs)).
- [x] Train YOLO26n thermal and fill its own-val results ([results](research/datasets/README.md#runs)).
- [ ] Retrain YOLO26n thermal for 30 to 50 epochs (or with early stopping): val AP50 peaked at epoch 28 and fell after.
- [x] Train YOLO26s RGB and thermal and compare with nano ([results](research/datasets/README.md#findings)): small barely helps, nano stays the default.
- [x] Score the RGB models on HERIDAL ([results](research/datasets/README.md#heridal)): AP50 about 0.01, both sizes, tiled or not.
- [x] Retrain YOLO26n RGB with HERIDAL (location split, `--tag heridal`): HERIDAL test AP50 0.015 to 0.215, SARD and NII-CU-MAPD unchanged ([findings](research/datasets/README.md#findings)).
- [x] Try HERIDAL only, and HERIDAL weighted 3× with `best.pt` picked on HERIDAL val: neither beats the mixed run ([findings](research/datasets/README.md#findings)).
- [ ] Add more RGB data like HERIDAL, one dataset per run, scored on HERIDAL's test locations: NOMAD (check its license), then a capped C2A sample ([more data](research/datasets/README.md#more-data)).
- [ ] Find a held-out thermal test (WiSARD thermal or AIResQ); see [next steps](research/datasets/README.md#next-steps).
- [ ] Score both models on WiSARD (download the WiSARD sample again; it was only kept in the dropped npz format).
- [x] Check whether the RGB model saw RGBTDronePerson's RGB images. The first one did, and scored AP50 0.06 on them; `train.py` now trains RGB without them ([why](research/datasets/README.md#rgbtdroneperson)).
- [ ] Test on WiSARD, which the models never trained on: convert it to `data/yolo/`, run `src/detection/eval_sizes.py` with and without `--tile 640`, fill the results table.
- [ ] Run the laptop test, nano then small ([steps](research/datasets/README.md#test-on-the-station-laptop)). Replace the predicted 30 / 10 FPS in [SPEC.md](SPEC.md#streams) with what you measure.

## Research

- [ ] The best parking point among the victims. Minimising the worst-case distance is the 1-center problem (minimax); minimising total distance is the 1-median (Fermat-Weber) problem. Find how each is solved for a few dozen points, whether a version exists that respects roads and obstacles, and recommend one for item 1 in [QUESTIONS.md](QUESTIONS.md#next-supervisors-meeting).
- [ ] Plan how operator control grows into agent decisions (RL or decision-theoretic planning): which decisions an agent would take over first (where to park, which victim next, where to move the drone), and what the station has to log now so that it can be trained or evaluated later. Start from GLIDE and Gemini in `paper/references.bib`.
- [ ] Read the Archangel paper's accuracy-by-altitude results and the RGBTDronePerson paper's flight altitude, and update the altitude table in [research/datasets/README.md](research/datasets/README.md#how-high-the-drone-can-fly).
- [ ] Set the detection target score from the held-out WiSARD and HERIDAL results, once they exist.

## Next supervisors' meeting

- [ ] Read and understand the two agenda items in [QUESTIONS.md](QUESTIONS.md#next-supervisors-meeting), and be ready to explain each.
- [ ] After the meeting, move whatever got decided from QUESTIONS.md into SPEC.md.

Questions to ask:

1. Instead of parking at a known site, can the vehicle keep moving while the drone looks for victims, then park at the best point among them and deploy the robots from there?
2. Is it fine to leave autonomy out for now, with a person driving the vehicle and the operator driving the robot remotely, and add agent decisions on top later?

Already answered, and recorded in SPEC.md: the evaluation is a live demo; RL / agent decisions are expected; the demo assumes the carrier data and collapse site are given; audio stays in scope.

## Robotics team

- [ ] Send them our requirements, the [robot interface](SPEC.md#robot-interface): the same cameras, Pi and WiFi adapter as the drone, drive commands over WiFi, stopping on a dropped link, GPS, microphone and speaker.

Questions to ask:

1. Will you use the same Pi 5 and MT7921AUN WiFi adapter as the drone?
2. Where does the antenna go on the sphere?
3. Size and weight.
