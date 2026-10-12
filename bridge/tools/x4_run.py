#!/usr/bin/env python3
"""Run X4 for an agent test: only while Simon is marked away, minimized and
silent, and ALWAYS killed at the end (board r24/r46, docs/11-agent-testing.md).

Windows Python only (it drives X4.exe, Steam and the Windows profile folder):
from WSL, `py.exe bridge/tools/x4_run.py ...`.

  away [HOURS]    Simon: "agents may run X4 for the next HOURS" (default 2).
  back            Simon: clear it now.
  status          what the gate says, and why.
  run [--expect REGEX] [--timeout S] [--no-deploy] [--deploy-extra DIR]... [--dry-run]
                  gate -> deploy.ps1 -> extras -> launch -> wait for REGEX in the log -> kill.

--deploy-extra DIR (repeatable) mirrors another checkout's extension folder into
<X4>/extensions/<DIR's name> after deploy.ps1, inside the lock, so a sibling board
(X4_Questline: --deploy-extra extensions/x4_questline from its root) deploys its own
without racing another run. DIR is relative to the current directory and must hold a
content.xml. --no-deploy skips deploy.ps1 only; the extras are still mirrored.
--dry-run takes no lock, checks no gate and launches nothing: it prints what would
be deployed and lists what robocopy would copy (/L).

tools/x4-away.cmd wraps away/back for a double-click.

The away flag lives OUTSIDE the repo (%USERPROFILE%\\.x4-agent-away, an expiry
time in ISO format), so every checkout and session sees the same one and nothing
can commit it. The gate also refuses when X4 is already running (Simon is playing,
or a run leaked) and when Steam is not.

X4 is ONE resource for the whole machine: every board and checkout shares the
game, its extensions folder and the profile. `run` holds an exclusive lock
(%USERPROFILE%\\.x4-agent-run.lock, an OS file lock, so it frees itself when the
holder dies) from before deploy.ps1 until X4 is killed; a second `run` is refused
at once and told who holds it (.x4-agent-run.who), never queued behind it.

The log is <PROFILE>\\agent_x4.txt, written by X4 itself (-logfile). It is deleted
before each run, so a match always comes from this launch.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOME = Path(os.environ.get("USERPROFILE", str(Path.home())))
AWAY = HOME / ".x4-agent-away"
LOCK = HOME / ".x4-agent-run.lock"
WHO = HOME / ".x4-agent-run.who"
LOGNAME = "agent_x4.txt"
X4_CANDIDATES = [
    r"E:\steam\steamapps\common\X4 Foundations",
    r"C:\Program Files (x86)\Steam\steamapps\common\X4 Foundations",
    r"D:\steam\steamapps\common\X4 Foundations",
]
FLAGS = ["-skipintro", "-disablesound", "-disablemusic", "-nosoundthrottle", "-nocputhrottle",
         "-dontsaveconfig", "-debug", "all", "-logfile", LOGNAME]
# X4.exe prints this once the start menu fades in (string in X4.exe; unverified
# in a log until the first real run, which records what it actually saw).
DEFAULT_EXPECT = r"start menu"


def say(msg: str) -> None:
    print(f"[x4_run] {msg}", flush=True)


def running(image: str) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                         capture_output=True, text=True, check=False).stdout
    return image.lower() in out.lower()


def away_until() -> datetime | None:
    try:
        # .astimezone() reads a mark written before it carried an offset as local time.
        return datetime.fromisoformat(AWAY.read_text(encoding="utf-8").strip()).astimezone()
    except (OSError, ValueError):
        return None


def gate(locked: bool = False) -> list[str]:
    """Every reason not to launch; empty means go."""
    why = []
    until = away_until()
    if until is None:
        why.append(f"Simon is not marked away (no {AWAY}; he runs tools/x4-away.cmd)")
    elif until < datetime.now().astimezone():
        why.append(f"Simon's away mark expired at {until:%Y-%m-%d %H:%M}")
    if not locked and not lock_free():
        why.append(f"another agent run holds X4: {holder()}")
    elif running("X4.exe"):
        why.append("X4.exe is already running (Simon playing, or a leaked run)")
    if not running("steam.exe"):
        why.append("Steam is not running")
    return why


def take_lock():
    """The open lock file if this process now holds X4, else None.

    msvcrt.locking is released by Windows when the process exits, so a run that
    crashes or is killed never leaves the game locked."""
    import msvcrt
    f = open(LOCK, "a+b")
    f.seek(0)
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    who = os.environ.get("ATELIER_AGENT") or os.environ.get("USERNAME") or "?"
    WHO.write_text(f"{who} pid {os.getpid()} since {datetime.now():%H:%M:%S} in {REPO}",
                   encoding="utf-8")
    return f


def holder() -> str:
    try:
        return WHO.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def lock_free() -> bool:
    f = take_lock()
    if f is None:
        return False
    f.close()
    return True


def x4_dir() -> Path:
    for c in X4_CANDIDATES:
        if (Path(c) / "X4.exe").exists():
            return Path(c)
    sys.exit("[x4_run] X4.exe not found in " + ", ".join(X4_CANDIDATES))


def profile_dir() -> Path:
    base = HOME / "Documents" / "Egosoft" / "X4"
    ids = [d for d in base.iterdir() if d.is_dir() and d.name.isdigit()]
    if len(ids) != 1:
        sys.exit(f"[x4_run] expected one numeric profile folder under {base}, found {len(ids)}")
    return ids[0]


def kill_x4() -> None:
    if running("X4.exe"):
        subprocess.run(["taskkill", "/IM", "X4.exe", "/F", "/T"], capture_output=True,
                       check=False)
        say("X4 killed")


def launch(x4: Path) -> subprocess.Popen:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7          # SW_SHOWMINNOACTIVE: minimized, focus stays where it was
    return subprocess.Popen([str(x4 / "X4.exe"), *FLAGS], cwd=str(x4), startupinfo=si)


# deploy.ps1 mirrors these with its own rules (twitch_integration keeps companion/).
OWN_EXTENSIONS = {"twitch_integration", "twitch_arena"}


def extras(dirs: list[str]) -> list[Path]:
    """The --deploy-extra folders, resolved; exits naming the first bad one."""
    out = []
    for d in dirs:
        src = Path(d).resolve()
        if not (src / "content.xml").is_file():
            sys.exit(f"[x4_run] --deploy-extra {d}: no content.xml in {src}, not an extension")
        if src.name in OWN_EXTENSIONS:
            sys.exit(f"[x4_run] --deploy-extra {d}: deploy.ps1 already deploys {src.name}")
        out.append(src)
    return out


def mirror(src: Path, x4: Path, dry: bool = False) -> None:
    """robocopy /MIR src into <X4>/extensions/<name>; /L only lists when dry."""
    dst = x4 / "extensions" / src.name
    cmd = ["robocopy", str(src), str(dst), "/MIR", "/NDL", "/NJH", "/NP", "/R:1", "/W:1"]
    cmd.append("/L" if dry else "/NFL")
    rc = subprocess.run(cmd, capture_output=True, text=True, encoding="oem", errors="replace",
                        check=False)
    if dry:
        print(rc.stdout, end="")
    if rc.returncode >= 8:
        sys.exit(f"[x4_run] robocopy failed for {src.name} (code {rc.returncode})")
    say(f"{'would deploy' if dry else 'deployed'} {src} -> {dst} (robocopy code {rc.returncode})")


def dry_run(args) -> int:
    x4, extra = x4_dir(), extras(args.deploy_extra)
    say("DRY RUN: no lock, no gate, no launch")
    say("would run deploy.ps1" if not args.no_deploy else "would skip deploy.ps1 (--no-deploy)")
    for src in extra:
        mirror(src, x4, dry=True)
    return 0


def cmd_run(args) -> int:
    if args.dry_run:
        return dry_run(args)
    extra = extras(args.deploy_extra)   # a bad folder fails before the lock
    lock = take_lock()
    if lock is None:
        say(f"REFUSED: another agent run holds X4: {holder()}")
        return 2
    try:
        return run_locked(args, extra)
    finally:
        WHO.unlink(missing_ok=True)
        lock.close()


def run_locked(args, extra: list[Path]) -> int:
    why = gate(locked=True)
    if why:
        for w in why:
            say("REFUSED: " + w)
        return 2
    x4, prof = x4_dir(), profile_dir()
    log = prof / LOGNAME
    if not args.no_deploy:
        say("deploy.ps1 ...")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(REPO / "deploy.ps1")], check=True)
    for src in extra:
        mirror(src, x4)
    log.unlink(missing_ok=True)
    expect = re.compile(args.expect, re.IGNORECASE)
    t0 = time.monotonic()
    say(f"launching {x4 / 'X4.exe'} {' '.join(FLAGS)}")
    try:
        launch(x4)
        while time.monotonic() - t0 < args.timeout:
            time.sleep(2)
            if not log.exists():
                continue
            text = log.read_text(encoding="utf-8", errors="replace")
            hit = next((ln for ln in text.splitlines() if expect.search(ln)), None)
            if hit:
                say(f"MATCH after {time.monotonic() - t0:.0f}s: {hit.strip()}")
                return 0
        say(f"TIMEOUT after {args.timeout}s: no line matching {args.expect!r} in {log}"
            + ("" if log.exists() else " (the log was never created)"))
        return 1
    finally:
        kill_x4()
        say(f"X4 ran {time.monotonic() - t0:.0f}s; log kept at {log}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("away")
    a.add_argument("hours", nargs="?", type=float, default=2.0)
    sub.add_parser("back")
    sub.add_parser("status")
    r = sub.add_parser("run")
    r.add_argument("--expect", default=DEFAULT_EXPECT)
    r.add_argument("--timeout", type=int, default=300)
    r.add_argument("--no-deploy", action="store_true", help="skip deploy.ps1 (extras still go)")
    r.add_argument("--deploy-extra", action="append", default=[], metavar="DIR",
                   help="also mirror this extension folder into <X4>/extensions (repeatable)")
    r.add_argument("--dry-run", action="store_true",
                   help="print what would be deployed; no lock, gate or launch")
    args = ap.parse_args()

    if args.cmd == "away":
        until = datetime.now().astimezone() + timedelta(hours=args.hours)
        AWAY.write_text(until.isoformat(timespec="minutes"), encoding="utf-8")
        say(f"agents may run X4 until {until:%Y-%m-%d %H:%M}")
        return 0
    if args.cmd == "back":
        AWAY.unlink(missing_ok=True)
        say("agents may NOT run X4 (away mark cleared)")
        return 0
    if args.cmd == "status":
        why = gate()
        say("GO: an agent may launch X4 now" if not why else "NO: " + "; ".join(why))
        return 0 if not why else 2
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
