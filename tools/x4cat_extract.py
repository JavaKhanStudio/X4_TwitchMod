"""Extract files from X4's packed .cat/.dat archives (read-only, for modding refs).

An X4 `.cat` is a plaintext index; each line is:  <path> <size> <timestamp> <md5>
The paired `.dat` is every listed file's bytes concatenated in order, so a file's
offset is the sum of the sizes above it. Later catalogs override earlier ones, so
we scan NN.cat in order and the last match wins.

Usage:
    py tools/x4cat_extract.py <X4_DIR> <out_dir> <substr> [<substr> ...]
Example:
    py tools/x4cat_extract.py "E:\\steam\\steamapps\\common\\X4 Foundations" \\
        _ref maps/demo_universe/ libraries/gamestarts.xml
"""

from __future__ import annotations

import glob
import os
import sys


def _iter_index(cat_path: str):
    """Yield (path, offset, size) for each entry in one .cat, in dat order."""
    offset = 0
    with open(cat_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            # split from the right: md5, timestamp, size, then path (may hold spaces)
            parts = line.rsplit(" ", 3)
            if len(parts) != 4:
                continue
            path, size_s, _ts, _md5 = parts
            try:
                size = int(size_s)
            except ValueError:
                continue
            yield path, offset, size
            offset += size


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    x4_dir, out_dir, substrs = sys.argv[1], sys.argv[2], [s.lower() for s in sys.argv[3:]]

    # Later catalogs win: build a map path -> (cat, offset, size), overwriting.
    found: dict[str, tuple[str, int, int]] = {}
    cats = sorted(glob.glob(os.path.join(x4_dir, "*.cat")))
    for cat in cats:
        if cat.endswith("_sig.cat"):
            continue
        for path, offset, size in _iter_index(cat):
            if any(s in path.lower() for s in substrs):
                found[path] = (cat, offset, size)

    if not found:
        print("no matching files")
        return 1

    for path, (cat, offset, size) in sorted(found.items()):
        dat = cat[:-4] + ".dat"
        dest = os.path.join(out_dir, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dat, "rb") as f:
            f.seek(offset)
            data = f.read(size)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"{path}  ({size} bytes)  <- {os.path.basename(cat)}")
    print(f"\nextracted {len(found)} file(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
