"""Package a deterministic target-marked release artifact."""

from __future__ import annotations

import argparse
import io
import tarfile
from pathlib import Path


def package(source: Path, output: Path, target: str) -> None:
    if not source.exists():
        raise ValueError(f"artifact source does not exist: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w") as archive:
        marker = tarfile.TarInfo(".tradvisor-target")
        marker_data = target.encode("utf-8")
        marker.size = len(marker_data)
        marker.mtime = 0
        archive.addfile(marker, io.BytesIO(marker_data))
        paths = [source] if source.is_file() else sorted(path for path in source.rglob("*") if path.is_file())
        for path in paths:
            entry = tarfile.TarInfo(path.name if source.is_file() else str(path.relative_to(source)))
            entry.size = path.stat().st_size
            entry.mtime = 0
            entry.mode = 0o644
            with path.open("rb") as content:
                archive.addfile(entry, content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    package(args.source, args.output, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
