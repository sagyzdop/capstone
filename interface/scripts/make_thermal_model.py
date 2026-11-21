"""Write the MLX90640 person model for the station UI: models/thermal.onnx + models/thermal.json.

Usage (from interface/, in the capstone conda env):
    conda activate capstone
    python scripts/make_thermal_model.py [--lo 28 --hi 40 --soft 0.5]

There is no labelled MLX90640 data yet, so this is not trained. It is a fixed-weight graph:
a soft body-temperature band, sigmoid((T-lo)/soft) * sigmoid((hi-T)/soft), then a 3x3 mean filter.
Contract, which a trained model must keep to drop in:
    input  "temps"  [1, 1, 24, 32] float32, degrees C, row 0 = sensor top
    output "person" [1, 1, 24, 32] float32, per-pixel person probability 0..1
lib/thermal.ts thresholds the map and turns connected blobs into boxes. Needs `onnx`.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from onnx.reference import ReferenceEvaluator

HERE = Path(__file__).resolve().parent.parent
H, W = 24, 32


def build(lo: float, hi: float, soft: float) -> onnx.ModelProto:
    c = lambda name, v: numpy_helper.from_array(np.array(v, dtype=np.float32), name)
    nodes = [
        helper.make_node("Sub", ["temps", "lo"], ["d_lo"]),
        helper.make_node("Div", ["d_lo", "soft"], ["z_lo"]),
        helper.make_node("Sigmoid", ["z_lo"], ["above"]),
        helper.make_node("Sub", ["hi", "temps"], ["d_hi"]),
        helper.make_node("Div", ["d_hi", "soft"], ["z_hi"]),
        helper.make_node("Sigmoid", ["z_hi"], ["below"]),
        helper.make_node("Mul", ["above", "below"], ["band"]),
        # smooth the probability, not the temperatures: a smoothed kettle edge would read as 39 degC
        helper.make_node("AveragePool", ["band"], ["person"], kernel_shape=[3, 3], pads=[1, 1, 1, 1], count_include_pad=0),
    ]
    graph = helper.make_graph(
        nodes,
        "mlx90640_person_band",
        [helper.make_tensor_value_info("temps", TensorProto.FLOAT, [1, 1, H, W])],
        [helper.make_tensor_value_info("person", TensorProto.FLOAT, [1, 1, H, W])],
        [c("lo", lo), c("hi", hi), c("soft", soft)],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], producer_name="make_thermal_model.py")
    model.ir_version = 8  # readable by onnxruntime-node 1.30
    onnx.checker.check_model(model)
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=float, default=28.0, help="degC where a pixel starts to count as a person")
    ap.add_argument("--hi", type=float, default=40.0, help="degC above which it is a hot object, not a person")
    ap.add_argument("--soft", type=float, default=0.5, help="degC width of both band edges")
    args = ap.parse_args()

    model = build(args.lo, args.hi, args.soft)

    # self-check: 22 degC room, a 6x4 px 33 degC person, a 2x2 px 60 degC kettle
    t = np.full((1, 1, H, W), 22.0, np.float32)
    t[0, 0, 8:14, 10:14] = 33.0
    t[0, 0, 2:4, 26:28] = 60.0
    (p,) = ReferenceEvaluator(model).run(None, {"temps": t})
    assert p[0, 0, 10, 11] > 0.9 and p[0, 0, 0, 0] < 0.01 and p[0, 0, 2, 26] < 0.5, "band check failed"

    out = HERE / "models"
    out.mkdir(exist_ok=True)
    onnx.save(model, out / "thermal.onnx")
    meta = {
        "weights": "thermal.onnx",
        "kind": "heatmap",
        "trained": None,
        "note": f"fixed body-temperature band {args.lo}-{args.hi} degC, not trained",
        "input": [1, 1, H, W],
        "band_c": [args.lo, args.hi, args.soft],
        "threshold": 0.5,  # pixel counts as person above this
        "min_pixels": 3,  # smaller blobs are dropped
        "names": {0: "person"},
    }
    (out / "thermal.json").write_text(json.dumps(meta, indent=1))
    print(f"self-check ok: person px {p[0, 0, 10, 11]:.3f}, room px {p[0, 0, 0, 0]:.4f}, kettle px {p[0, 0, 2, 26]:.3f}")
    print(f"-> {out / 'thermal.onnx'}, {out / 'thermal.json'}")


if __name__ == "__main__":
    main()
