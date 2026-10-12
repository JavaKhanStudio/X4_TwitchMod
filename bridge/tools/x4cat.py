#!/usr/bin/env python3
"""Read game files straight out of an X4 install's cat/dat archives — the shared
half of every gen_*.py.

The X4 cat format is text: '<path with spaces> <size> <timestamp> <hash>' per line;
the dat is those files concatenated in listing order. We compute each file's offset
from the running size sum and slice it out of the dat.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

DEFAULT_ROOT = r"E:\Steam\steamapps\common\X4 Foundations"


def cat_entries(cat: Path):
    """Yield (relpath_lower, offset, size) for a .cat, honoring space-containing paths."""
    offset = 0
    for line in cat.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(" ")
        if len(parts) < 4:
            continue
        try:
            size = int(parts[-3])
        except ValueError:
            continue
        path = " ".join(parts[:-3]).lower()
        yield path, offset, size
        offset += size


def extract(cat: Path, want: str) -> bytes | None:
    dat = cat.with_suffix(".dat")
    if not dat.exists():
        return None
    for path, off, size in cat_entries(cat):
        if path == want:
            with open(dat, "rb") as f:
                f.seek(off)
                return f.read(size)
    return None


def all_cats(root: Path) -> list[Path]:
    cats = sorted(c for c in root.glob("*.cat") if "_sig" not in c.name)
    for ext in sorted(root.glob("extensions/*")):
        cats += sorted(c for c in ext.glob("*.cat") if "_sig" not in c.name)
    return cats


def install_root() -> Path | None:
    """The X4 install named on the command line (or the default); None, said aloud,
    if it is not there."""
    root = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT)
    if not root.exists():
        print(f"X4 install not found: {root}")
        return None
    return root


def elements(root: Path, want: str, tag: str) -> Iterator[tuple[Path, ET.Element]]:
    """Yield (cat, element) for every <tag> in file `want`, across the base game and
    every DLC in load order. Each ships either the full document or a <diff> that
    adds to it; both shapes contain the elements, so this sees DLC additions too.
    An archive whose copy does not parse is skipped."""
    for cat in all_cats(root):
        blob = extract(cat, want)
        if not blob:
            continue
        try:
            doc = ET.fromstring(blob)
        except ET.ParseError:
            continue
        for el in doc.iter(tag):
            yield cat, el
