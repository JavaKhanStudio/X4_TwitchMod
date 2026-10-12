#!/usr/bin/env python3
"""X4 is one resource for the machine: a second x4_run.py is refused while a
first holds it, is told who, and gets it once the holder is gone (board r2).

Windows py only (msvcrt): `py.exe bridge/tools/test_x4_run_lock.py`. It never
launches X4: USERPROFILE points at an empty temp folder, so there is no away
mark and the gate refuses every run that gets past the lock.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "x4_run.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, USERPROFILE=home, ATELIER_AGENT="lock-holder-test")
        os.environ.update(env)
        sys.path.insert(0, str(HERE))
        import x4_run
        fails = 0

        def x4(*args):
            env2 = dict(env, ATELIER_AGENT="second")
            p = subprocess.run([sys.executable, str(RUN), *args], env=env2,
                               capture_output=True, text=True)
            return p.returncode, p.stdout + p.stderr

        def check(ok, what, out=""):
            nonlocal fails
            print(("PASS " if ok else "FAIL ") + what)
            if not ok:
                print("   " + out.replace("\n", "\n   "))
                fails += 1

        held = x4_run.take_lock()
        check(held is not None, "first holder takes the lock")
        rc, out = x4("run", "--no-deploy")
        check(rc == 2 and "another agent run holds X4" in out and "lock-holder-test" in out,
              "a second run is refused and told who holds X4", out)
        check("launching" not in out, "the refused run never launches", out)
        rc, out = x4("status")
        check(rc == 2 and "lock-holder-test" in out, "status names the holder", out)
        held.close()
        rc, out = x4("run", "--no-deploy")
        check("holds X4" not in out and "not marked away" in out and "launching" not in out,
              "once released, the next run gets past the lock (and the away gate stops it)", out)
        check(not (Path(home) / ".x4-agent-run.who").exists(),
              "the run that took the lock cleared its .who", out)
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
