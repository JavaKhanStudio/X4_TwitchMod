#!/usr/bin/env python3
"""The old path of test_md_lint.py, kept working: the lint itself moved to
../X4_Mods/tools/test_md_lint.py (board x4 r3), which every X4 board shares.

This shim loads it with this repo as REPO (no path: this repo's extensions/*/md/*.xml)
and twitch_integration.xml as BUILD_FILE (Twitch_Say's $Build: it must be among the
default files, and --self-test plants into it), so `python3
bridge/tools/test_md_lint.py [--self-test] [paths]` does what it always did.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO.parent / "X4_Mods" / "tools" / "test_md_lint.py"
if not CORE.is_file():
    sys.exit(f"test_md_lint.py moved to {CORE}, which is not there: clone X4_Mods next to "
             "this checkout")
spec = importlib.util.spec_from_file_location("test_md_lint", CORE)
core = importlib.util.module_from_spec(spec)
sys.modules["test_md_lint"] = core
spec.loader.exec_module(core)
core.REPO = REPO
core.BUILD_FILE = REPO / "extensions" / "twitch_integration" / "md" / "twitch_integration.xml"

if __name__ == "__main__":
    sys.exit(core.main())
