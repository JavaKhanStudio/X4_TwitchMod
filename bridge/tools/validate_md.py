#!/usr/bin/env python3
"""The old path of validate_md.py, kept working: the checker itself moved to
../X4_Mods/tools/validate_md.py (board x4 r3), which every X4 board shares.

This shim loads it with this repo as REPO (no path: this repo's extensions/*/md/*.xml),
this repo's _scratch/ (the md.xsd already extracted here) and twitch_integration.xml
as the --plant file, so `py.exe bridge/tools/validate_md.py [--plant|--serve|--stop]`
does what it always did. Its --help is the runner's docstring.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO.parent / "X4_Mods" / "tools" / "validate_md.py"
if not CORE.is_file():
    sys.exit(f"validate_md.py moved to {CORE}, which is not there: clone X4_Mods next to "
             "this checkout")
spec = importlib.util.spec_from_file_location("validate_md", CORE)
core = importlib.util.module_from_spec(spec)
sys.modules["validate_md"] = core
spec.loader.exec_module(core)
core.REPO = REPO
core.SCRATCH = REPO / "_scratch"
core.PLANT = REPO / "extensions" / "twitch_integration" / "md" / "twitch_integration.xml"

if __name__ == "__main__":
    sys.exit(core.main())
