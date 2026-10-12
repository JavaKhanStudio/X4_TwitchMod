#!/usr/bin/env python3
"""--deploy-extra mirrors a sibling checkout's extension into <X4>/extensions/<name>
(r81): X4_Questline deploys extensions/x4_questline under x4_run.py's lock.

Windows py only (robocopy): `py.exe bridge/tools/test_x4_run_extra.py`. It never
touches the real game: X4_CANDIDATES points at a temp folder with a stub X4.exe.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "x4_run.py"


def main() -> int:
    sys.path.insert(0, str(HERE))
    import x4_run
    fails = 0

    def check(ok, what, out=""):
        nonlocal fails
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            print("   " + str(out).replace("\n", "\n   "))
            fails += 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        game = tmp / "X4 Foundations"
        (game / "extensions").mkdir(parents=True)
        (game / "X4.exe").write_bytes(b"")
        x4_run.X4_CANDIDATES[:] = [str(game)]
        ext = tmp / "sibling" / "extensions" / "my_ext"
        (ext / "md").mkdir(parents=True)
        (ext / "content.xml").write_text("<content/>", encoding="utf-8")
        (ext / "md" / "a.xml").write_text("<mdscript/>", encoding="utf-8")
        dst = game / "extensions" / "my_ext"
        (dst / "md").mkdir(parents=True)
        (dst / "md" / "stale.xml").write_text("old", encoding="utf-8")

        x4_run.mirror(ext, x4_run.x4_dir(), dry=True)
        check(not (dst / "content.xml").exists() and (dst / "md" / "stale.xml").exists(),
              "dry run copies and deletes nothing")
        x4_run.mirror(ext, x4_run.x4_dir())
        check((dst / "content.xml").exists() and (dst / "md" / "a.xml").exists(),
              "the extension is copied into <X4>/extensions/<name>")
        check(not (dst / "md" / "stale.xml").exists(), "/MIR removes what the source dropped")

        os.chdir(tmp / "sibling")
        check(x4_run.extras(["extensions/my_ext"]) == [ext.resolve()],
              "DIR resolves against the current directory")
        for bad, why in (("extensions", "not an extension"),
                         ("twitch_integration", "deploy.ps1 already deploys")):
            if bad == "twitch_integration":
                (tmp / "sibling" / bad).mkdir()
                (tmp / "sibling" / bad / "content.xml").write_text("<content/>")
            p = subprocess.run([sys.executable, str(RUN), "run", "--dry-run",
                                "--deploy-extra", bad], capture_output=True, text=True)
            check(p.returncode != 0 and why in p.stderr, f"--deploy-extra {bad} is refused",
                  p.stdout + p.stderr)
        os.chdir(HERE)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
