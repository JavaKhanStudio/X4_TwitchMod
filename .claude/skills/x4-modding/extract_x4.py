#!/usr/bin/env python3
"""The old path of extract_x4.py, kept working: the extractor moved with the shared
x4-modding guide to ../X4_Mods/.claude/skills/x4-modding/extract_x4.py (board x4 r5).

Run, it runs that file with the same arguments. Imported (`from extract_x4 import
build_index`, or loaded by path), it carries the same names: build_index, DEFAULT_X4, main.
"""
import importlib.util
import sys
from pathlib import Path

CORE = (Path(__file__).resolve().parents[4] / "X4_Mods" / ".claude" / "skills" / "x4-modding"
        / "extract_x4.py")
if not CORE.is_file():
    sys.exit(f"extract_x4.py moved to {CORE}, which is not there: clone X4_Mods next to "
             "this checkout")
_spec = importlib.util.spec_from_file_location("x4mods_extract_x4", CORE)
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})

if __name__ == "__main__":
    sys.exit(_core.main())
