"""The old path of x4cat_extract.py, kept working: the extractor moved to
../X4_Mods/tools/x4cat_extract.py (board x4 r4), which every X4 board shares.
This shim runs it with the same arguments.

    py tools/x4cat_extract.py <X4_DIR> <out_dir> <substr> [<substr> ...]
"""

import runpy
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "X4_Mods" / "tools" / "x4cat_extract.py"
if not CORE.is_file():
    sys.exit(f"x4cat_extract.py moved to {CORE}, which is not there: clone X4_Mods next to "
             "this checkout")
runpy.run_path(str(CORE), run_name="__main__")
