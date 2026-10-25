import argparse
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Folder to archive")
    parser.add_argument("output", type=Path, help="Output .zip file")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()

    if not source.is_dir():
        raise SystemExit(f"Source folder does not exist: {source}")

    if output.exists():
        output.unlink()

    files = [path for path in source.rglob("*") if path.is_file()]
    print(f"Adding {len(files)} files...")

    # ZIP_STORED is intentional: .npy image arrays usually do not shrink much,
    # and this makes archive creation substantially faster.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as zf:
        for index, path in enumerate(files, start=1):
            # as_posix() guarantees /, never Windows \
            archive_name = (Path(source.name) / path.relative_to(source)).as_posix()
            zf.write(path, archive_name)

            if index % 1000 == 0 or index == len(files):
                print(f"{index}/{len(files)}")

    print(f"Created: {output}")


if __name__ == "__main__":
    main()