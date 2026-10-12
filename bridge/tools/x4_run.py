#!/usr/bin/env python3
"""The old path of x4_run.py, kept working: the runner itself moved to
../X4_Mods/tools/x4_run.py (board x4 r2), which every X4 board shares.

This shim loads it with this checkout's deploy.ps1, so `py.exe bridge/tools/x4_run.py
run` still deploys the Twitch mod before the --deploy-extra folders, and stands in
for it under the name x4_run, so `import x4_run` (the tests here) gets the runner
itself: setting x4_run.X4_CANDIDATES reaches the code that reads it.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO.parent / "X4_Mods" / "tools" / "x4_run.py"
if not CORE.is_file():
    sys.exit(f"[x4_run] the runner moved to {CORE}, which is not there: clone X4_Mods "
             "next to this checkout")
spec = importlib.util.spec_from_file_location("x4_run", CORE)
x4_run = importlib.util.module_from_spec(spec)
sys.modules["x4_run"] = x4_run
spec.loader.exec_module(x4_run)
x4_run.DEPLOY = REPO / "deploy.ps1"
# deploy.ps1 mirrors these with its own rules (twitch_integration keeps companion/).
x4_run.OWN_EXTENSIONS = {"twitch_integration", "twitch_arena"}
x4_run.REPO = REPO

if __name__ == "__main__":
    sys.exit(x4_run.main())
