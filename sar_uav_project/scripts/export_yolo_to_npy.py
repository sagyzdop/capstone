"""
Validate a prepared single-class YOLO dataset, letterbox-resize images,
and export image/label pairs as NumPy .npy files.

Input expected:
    ../data/yolo/<dataset>/
        images/{train,val,test}/
        labels/{train,val,test}/

Output created:
    processed_npy/<dataset>/<size>/
        images/{train,val,test}/*.npy
        labels/{train,val,test}/*.npy
        manifest.json
        export_report.json

Each label array has shape (N, 5), with rows:
    [class_id, x_center, y_center, width, height]

Coordinates remain YOLO-normalized after letterboxing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = PROJECT_ROOT.parent / "data" / "yolo"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "processed_npy"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def parse_sizes(values: list[str]) -> list[int]:
    sizes = []
    for value in values:
        size = int(value)
        if size <= 0:
            raise ValueError(f"Image size must be positive, got {size}.")
        sizes.append(size)

    if len(set(sizes)) != len(sizes):
        raise ValueError("Each requested size must appear only once.")

    return sizes


def read_yolo_labels(label_path: Path) -> np.ndarray:
    """
    Read class xc yc w h labels and validate every value.

    Empty label files are valid: they represent a negative/background image.
    """
    if not label_path.exists():
        raise ValueError("Missing label file")

    rows = []

    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        parts = line.split()

        if len(parts) != 5:
            raise ValueError(
                f"Malformed label at line {line_number}: expected 5 values, got {len(parts)}"
            )

        try:
            class_id, xc, yc, width, height = map(float, parts)
        except ValueError as error:
            raise ValueError(
                f"Non-numeric label value at line {line_number}"
            ) from error

        if not class_id.is_integer() or int(class_id) != 0:
            raise ValueError(
                f"Expected prepared person class 0 at line {line_number}, got {class_id}"
            )

        if not (0.0 <= xc <= 1.0 and 0.0 <= yc <= 1.0):
            raise ValueError(
                f"Center coordinate outside [0, 1] at line {line_number}"
            )

        if not (0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            raise ValueError(
                f"Box width/height outside (0, 1] at line {line_number}"
            )

        if xc - width / 2 < 0 or xc + width / 2 > 1:
            raise ValueError(
                f"Box extends beyond left/right image boundary at line {line_number}"
            )

        if yc - height / 2 < 0 or yc + height / 2 > 1:
            raise ValueError(
                f"Box extends beyond top/bottom image boundary at line {line_number}"
            )

        rows.append([0.0, xc, yc, width, height])

    if not rows:
        return np.empty((0, 5), dtype=np.float32)

    return np.asarray(rows, dtype=np.float32)


def open_image(image_path: Path) -> Image.Image:
    """Open, decode, and load image pixels; throws a useful error if corrupt."""
    try:
        with Image.open(image_path) as check:
            check.verify()

        with Image.open(image_path) as image:
            image.load()

            # Palette/RGBA/other uncommon formats become normal RGB.
            # L-mode grayscale images remain grayscale.
            if image.mode not in {"L", "RGB"}:
                image = image.convert("RGB")

            return image.copy()

    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError(f"Unreadable/corrupt image: {error}") from error


def letterbox_image_and_labels(
    image: Image.Image,
    labels: np.ndarray,
    target_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Resize without distortion and pad onto a target_size × target_size canvas.

    YOLO labels are transformed to match the resized-and-padded image.
    """
    original_width, original_height = image.size

    scale = min(target_size / original_width, target_size / original_height)
    resized_width = max(1, round(original_width * scale))
    resized_height = max(1, round(original_height * scale))

    # Actual scale after rounding is used for label transformation.
    scale_x = resized_width / original_width
    scale_y = resized_height / original_height

    resized = image.resize(
        (resized_width, resized_height),
        Image.Resampling.LANCZOS,
    )

    # Black padding. Thermal images stay grayscale if input was grayscale.
    canvas = Image.new(image.mode, (target_size, target_size), color=0)
    pad_left = (target_size - resized_width) // 2
    pad_top = (target_size - resized_height) // 2
    canvas.paste(resized, (pad_left, pad_top))

    transformed = labels.copy()

    if len(transformed):
        # Convert normalized source labels -> source pixels -> padded target pixels
        # -> normalized target labels.
        transformed[:, 1] = (
            transformed[:, 1] * original_width * scale_x + pad_left
        ) / target_size
        transformed[:, 2] = (
            transformed[:, 2] * original_height * scale_y + pad_top
        ) / target_size
        transformed[:, 3] = (
            transformed[:, 3] * original_width * scale_x
        ) / target_size
        transformed[:, 4] = (
            transformed[:, 4] * original_height * scale_y
        ) / target_size

    array = np.asarray(canvas)

    return array, transformed.astype(np.float32)


def find_images(images_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def process_dataset(
    dataset: str,
    input_root: Path,
    output_root: Path,
    sizes: list[int],
    dry_run: bool,
) -> dict:
    dataset_root = input_root / dataset
    images_root = dataset_root / "images"
    labels_root = dataset_root / "labels"

    if not images_root.exists() or not labels_root.exists():
        raise FileNotFoundError(
            f"Cannot find prepared dataset '{dataset}' under:\n"
            f"  images: {images_root}\n"
            f"  labels: {labels_root}"
        )

    report = {
        "dataset": dataset,
        "input_root": str(dataset_root.resolve()),
        "output_root": str((output_root / dataset).resolve()),
        "requested_sizes": sizes,
        "dry_run": dry_run,
        "splits": {},
        "invalid_files": [],
    }

    split_dirs = sorted(path for path in images_root.iterdir() if path.is_dir())

    if not split_dirs:
        raise ValueError(f"No split folders found in {images_root}")

    for split_dir in split_dirs:
        split = split_dir.name
        label_dir = labels_root / split
        images = find_images(split_dir)

        split_summary = {
            "images_found": len(images),
            "kept": 0,
            "negative_images": 0,
            "person_boxes": 0,
            "skipped_invalid": 0,
        }

        if not label_dir.exists():
            raise FileNotFoundError(f"Missing label directory: {label_dir}")

        for image_path in images:
            label_path = label_dir / f"{image_path.stem}.txt"

            try:
                image = open_image(image_path)
                labels = read_yolo_labels(label_path)

            except ValueError as error:
                split_summary["skipped_invalid"] += 1
                report["invalid_files"].append(
                    {
                        "split": split,
                        "image": str(image_path),
                        "label": str(label_path),
                        "reason": str(error),
                    }
                )
                continue

            split_summary["kept"] += 1
            split_summary["person_boxes"] += int(len(labels))

            if len(labels) == 0:
                split_summary["negative_images"] += 1

            if dry_run:
                continue

            for size in sizes:
                image_array, transformed_labels = letterbox_image_and_labels(
                    image=image,
                    labels=labels,
                    target_size=size,
                )

                image_out = (
                    output_root
                    / dataset
                    / str(size)
                    / "images"
                    / split
                    / f"{image_path.stem}.npy"
                )
                label_out = (
                    output_root
                    / dataset
                    / str(size)
                    / "labels"
                    / split
                    / f"{image_path.stem}.npy"
                )

                image_out.parent.mkdir(parents=True, exist_ok=True)
                label_out.parent.mkdir(parents=True, exist_ok=True)

                np.save(image_out, image_array)
                np.save(label_out, transformed_labels)

        report["splits"][split] = split_summary

    if not dry_run:
        dataset_output = output_root / dataset

        manifest = {
            "dataset": dataset,
            "class_names": {"0": "person"},
            "sizes": sizes,
            "resize_method": "letterbox",
            "padding_value": 0,
            "label_format": "[class_id, x_center, y_center, width, height]",
            "label_coordinates": "YOLO normalized coordinates after letterboxing",
            "image_layout": (
                "H,W for grayscale images; H,W,C for RGB images. "
                "Inspect arrays before assuming a channel layout."
            ),
            "splits": report["splits"],
        }

        (dataset_output / "manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        (dataset_output / "export_report.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate prepared YOLO data and export letterboxed .npy files."
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        required=True,
        help="Prepared dataset names, for example: hit-uav sard",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        default=["128", "640", "1280"],
        help="Square output sizes. Default: 128 640 1280",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=f"Default: {DEFAULT_INPUT_ROOT}",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; do not create .npy outputs.",
    )
    args = parser.parse_args()

    sizes = parse_sizes(args.sizes)
    all_reports = []

    for dataset in args.datasets:
        print(f"\nProcessing {dataset} ...")
        report = process_dataset(
            dataset=dataset,
            input_root=args.input_root,
            output_root=args.output_root,
            sizes=sizes,
            dry_run=args.dry_run,
        )
        all_reports.append(report)

        for split, summary in report["splits"].items():
            print(
                f"  {split}: "
                f"found={summary['images_found']}, "
                f"kept={summary['kept']}, "
                f"persons={summary['person_boxes']}, "
                f"negatives={summary['negative_images']}, "
                f"invalid={summary['skipped_invalid']}"
            )

        print(f"  Total invalid files: {len(report['invalid_files'])}")

    if args.dry_run:
        print("\nDry run complete: no .npy files were written.")
    else:
        print(f"\nExport complete. Output: {args.output_root.resolve()}")


if __name__ == "__main__":
    main()