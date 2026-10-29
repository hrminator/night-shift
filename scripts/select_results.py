"""Copy only the front-door comparison inputs out of results/.

The deployed image needs the results/*/results.json files (the k-of-n
counts behind the Night B comparison sentence) and the report.md files,
not the raw per-run exports (which carry encrypted reasoning blobs).
Keeps the results/<folder>/ layout so
``app.night_b.night_b_results_dir()`` works unchanged.

Usage:
  python scripts/select_results.py <src-results-dir> <dst-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The only files each results folder contributes to the image.
WANTED = ("results.json", "report.md")


def select(src: Path, dst: Path) -> dict[str, int]:
    """Copy wanted files, mirroring the per-folder layout.

    Returns {"folders": n, "files": m, "bytes": b}. Folders holding
    neither wanted file (e.g. grounding probe folders) are skipped.
    """
    folders = 0
    files = 0
    size = 0
    for folder in sorted(src.iterdir()):
        if not folder.is_dir():
            continue
        hits = [name for name in WANTED
                if (folder / name).is_file()]
        if not hits:
            continue
        target = dst / folder.name
        target.mkdir(parents=True, exist_ok=True)
        for name in hits:
            data = (folder / name).read_bytes()
            (target / name).write_bytes(data)
            files += 1
            size += len(data)
        folders += 1
    return {"folders": folders, "files": files, "bytes": size}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: select_results.py <src-results-dir> <dst-dir>",
              file=sys.stderr)
        return 2
    src = Path(argv[1])
    if not src.is_dir():
        print(f"no such directory: {src}", file=sys.stderr)
        return 2
    dst = Path(argv[2])
    counts = select(src, dst)
    print(f"selected {counts['files']} files from {counts['folders']} "
          f"folders ({counts['bytes'] / 1024:.1f} KB) into {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
