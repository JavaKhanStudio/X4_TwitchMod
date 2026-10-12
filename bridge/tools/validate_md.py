#!/usr/bin/env python3
"""Validate every extensions/*/md/*.xml against the game's own md.xsd.

Given file or directory paths (a directory means every *.xml in an md/ folder
under it), it validates those instead, so another extension can check its own MD:

  py.exe bridge/tools/validate_md.py ../X4_Questline/extensions/*/md/*.xml

Windows Python reads paths relative to the current directory; a WSL absolute
path (/mnt/c/...) means nothing to it, so pass relative ones.

Needs lxml, which WSL's python3 does not have: run it with Windows Python,
`py.exe bridge/tools/validate_md.py` from the repo root under WSL.

md.xsd + common.xsd are extracted from the X4 install into _scratch/ on first
use (extract_x4.py). Compiling them takes ~2 min (127 s measured 2026-10-12;
validating a file then takes milliseconds). The cost is common.xsd's 1.7 MB
content model, not its xs:pattern facets (removing them saved nothing), and
lxml cannot pickle a compiled XMLSchema. So the only cache is a process that
keeps it:

  py.exe bridge/tools/validate_md.py --serve   # compile once, stay up
  py.exe bridge/tools/validate_md.py           # uses the server if it is up,
                                               # else compiles in-process
  py.exe bridge/tools/validate_md.py --stop    # stop the server

The server listens on 127.0.0.1 only and recompiles when the .xsd files change.
Files are sent by content, so any checkout can use it. Add `--plant` to also
validate a copy of twitch_integration.xml with a `<signal_cue param=>` planted:
it must FAIL, which proves the schema is really checking.
"""
import subprocess
import sys
from multiprocessing.connection import Client, Listener
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRATCH = REPO / "_scratch"
XSD = SCRATCH / "md.xsd"
DEPS = (XSD, SCRATCH / "common.xsd")
EXTRACT = REPO / ".claude" / "skills" / "x4-modding" / "extract_x4.py"
ADDRESS = ("127.0.0.1", 17565)
AUTHKEY = b"x4-twitchmod-validate-md"


def ensure_xsd() -> None:
    if all(p.exists() for p in DEPS):
        return
    print("extracting md.xsd + common.xsd into _scratch/ ...", flush=True)
    subprocess.run([sys.executable, str(EXTRACT), "libraries/md.xsd", "libraries/common.xsd",
                    "--out", str(SCRATCH)], check=True)


def stamp() -> tuple:
    return tuple(p.stat().st_mtime_ns for p in DEPS)


def compile_schema():
    from lxml import etree
    print("compiling md.xsd (~2 min) ...", flush=True)
    return etree.XMLSchema(etree.parse(str(XSD)))


def validate(schema, name: str, data: bytes) -> list[str]:
    from lxml import etree
    try:
        doc = etree.fromstring(data, etree.XMLParser(remove_blank_text=False)).getroottree()
    except etree.XMLSyntaxError as e:
        return [f"{name}: not well-formed: {e}"]
    if schema.validate(doc):
        return []
    return [f"{name}:{e.line}: {e.message}" for e in schema.error_log]


def serve() -> None:
    ensure_xsd()
    schema, seen = compile_schema(), stamp()
    print(f"validate_md server up on {ADDRESS[0]}:{ADDRESS[1]}", flush=True)
    with Listener(ADDRESS, authkey=AUTHKEY) as listener:
        while True:
            with listener.accept() as conn:
                req = conn.recv()
                if req == "stop":
                    conn.send("stopped")
                    return
                if stamp() != seen:
                    schema, seen = compile_schema(), stamp()
                conn.send({name: validate(schema, name, data) for name, data in req})


def md_paths(args: list[str]) -> list[Path]:
    """The paths given (a directory: the *.xml in md/ folders under it), else the repo's."""
    if not args:
        return sorted(REPO.glob("extensions/*/md/*.xml"))
    out = []
    for a in args:
        p = Path(a).resolve()
        if p.is_dir():
            out += sorted(f for f in p.rglob("*.xml") if f.parent.name == "md")
        elif p.is_file():
            out.append(p)
        else:
            sys.exit(f"no such file or directory: {a}")
    return out


def files(args: list[str], plant: bool) -> list[tuple[str, bytes]]:
    out = [(p.relative_to(REPO).as_posix() if p.is_relative_to(REPO) else str(p), p.read_bytes())
           for p in md_paths(args)]
    if not out:
        sys.exit("no MD files in the paths given")
    if plant:
        # planted into this repo's twitch_integration.xml, whatever the paths
        plant_file = REPO / "extensions" / "twitch_integration" / "md" / "twitch_integration.xml"
        name, data = plant_file.relative_to(REPO).as_posix(), plant_file.read_bytes()
        bad = data.replace(b"</cues>", b'<cue name="Plant"><actions>'
                           b'<signal_cue cue="Plant" param="1"/></actions></cue></cues>', 1)
        out.append((name + " (planted signal_cue param)", bad))
    return out


def run(args: list[str], plant: bool) -> int:
    req = files(args, plant)
    try:
        with Client(ADDRESS, authkey=AUTHKEY) as conn:
            conn.send(req)
            results = conn.recv()
        print("(validated by the running server)")
    except OSError:
        ensure_xsd()
        schema = compile_schema()
        results = {name: validate(schema, name, data) for name, data in req}
    ok = True
    for name, errors in results.items():
        expect_fail = name.endswith("(planted signal_cue param)")
        good = bool(errors) if expect_fail else not errors
        verdict = ("FAILS, as it must" if expect_fail else "INVALID") if errors else "OK"
        print(f"{'PASS' if good else 'FAIL'}: {name}: {verdict}")
        for e in errors:
            print("   ", e)
        ok = ok and good
    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    elif "--stop" in sys.argv:
        try:
            with Client(ADDRESS, authkey=AUTHKEY) as conn:
                conn.send("stop")
                print(conn.recv())
        except OSError:
            print("no server running")
    else:
        sys.exit(run([a for a in sys.argv[1:] if not a.startswith("--")], "--plant" in sys.argv))
