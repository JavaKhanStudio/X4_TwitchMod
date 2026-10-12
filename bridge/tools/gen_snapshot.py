#!/usr/bin/env python3
"""Run every gen_*.py against an X4 install and copy what each wrote into OUTDIR,
then put the checked-in outputs back untouched. Snapshot before and after a change
to a generator and `diff -r` the two: a refactor must leave them byte-identical.

    python3 tools/gen_snapshot.py "/mnt/e/Steam/steamapps/common/X4 Foundations" /tmp/before
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
# generator -> the file it (over)writes
OUTPUTS = {
    "gen_ships.py": "bridge/twitch_bridge/ships.json",
    "gen_sectors.py": "bridge/twitch_bridge/sectors.json",
    "gen_characters.py": "extensions/twitch_integration/libraries/characters.xml",
    "gen_ware_owners.py": "extensions/twitch_integration/libraries/wares.xml",
    "gen_boso_lines.py": "extensions/twitch_integration/md/twitch_boso_lines.xml",
}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    root, outdir = sys.argv[1], Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for gen, rel in OUTPUTS.items():
        target = REPO / rel
        saved = target.read_bytes()
        try:
            r = subprocess.run([sys.executable, str(TOOLS / gen), root],
                               capture_output=True, text=True, check=False)
            print(f"{gen}: exit {r.returncode} {r.stdout.strip().splitlines()[:1]}")
            if r.returncode:
                print(r.stderr, file=sys.stderr)
                failed += 1
            shutil.copyfile(target, outdir / target.name)
        finally:
            target.write_bytes(saved)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
