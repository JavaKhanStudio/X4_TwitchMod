#!/usr/bin/env python3
"""MD lint: the x4-modding SKILL.md traps that neither md.xsd nor test_md_sync.py
catches cheaply. Each one loads fine in X4 and fails silently in game.

  1. <signal_cue> with a param or delay attribute: both are silently dropped
     (only signal_cue_instantly takes param; a delay lives on the target cue).
  2. A cue that reads event.param but is only ever reached by <signal_cue>:
     event.param is always null there (Twitch_RankWatch, fixed in r3/1c435ad).
  3. An MD file that differs from HEAD while Twitch_Say's $Build still equals
     HEAD's: an edit without a build bump, so chat cannot tell a stale script
     from a broken fix (#mod pack). Compared against HEAD, so a second edit
     before the commit is not caught.

`--self-test` plants each trap in a copy built in memory and checks the lint
fails on it.
"""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MD_FILES = sorted(REPO.glob("extensions/*/md/*.xml"))
BUILD_FILE = REPO / "extensions" / "twitch_integration" / "md" / "twitch_integration.xml"
BUILD_RE = re.compile(r"<set_value name=\"\$Build\" exact=\"'([^']*)'\"/>")


def short(ref: str) -> str:
    """'md.Twitch_Integration.Twitch_Say' and 'Twitch_Say' name the same cue."""
    return ref.rsplit(".", 1)[-1]


def own_elements(cue):
    """The cue's own conditions/delay/actions, not those of its sub-cues."""
    for child in cue:
        if child.tag != "cues":
            yield from child.iter()


def signal_param_or_delay(roots: dict[str, ET.Element]) -> list[str]:
    bad = []
    for name, root in roots.items():
        for e in root.iter("signal_cue"):
            for attr in ("param", "delay"):
                if attr in e.attrib:
                    bad.append(f"{name}: signal_cue cue={e.get('cue')!r} {attr}={e.get(attr)!r}")
    return bad


def param_never_sent(roots: dict[str, ET.Element]) -> list[str]:
    plain: dict[str, int] = {}
    instant: dict[str, int] = {}
    for root in roots.values():
        for tag, into in (("signal_cue", plain), ("signal_cue_instantly", instant)):
            for e in root.iter(tag):
                c = short(e.get("cue") or "")
                into[c] = into.get(c, 0) + 1
    bad = []
    for name, root in roots.items():
        for cue in root.iter("cue"):
            cname = cue.get("name")
            conds = cue.find("conditions")
            # Only a cue woken by a direct signal (<event_cue_signalled/>, no cue=)
            # gets its event.param from whoever signals it by name.
            direct = conds is not None and any(
                e.tag == "event_cue_signalled" and "cue" not in e.attrib for e in conds.iter())
            if not direct:
                continue
            reads = any("event.param" in v for e in own_elements(cue) for v in e.attrib.values())
            if reads and plain.get(cname) and not instant.get(cname):
                bad.append(f"{name}: {cname} reads event.param but is only reached by "
                           f"signal_cue ({plain[cname]}x), which carries no param")
    return bad


def head_text(path: Path) -> str | None:
    rel = path.relative_to(REPO).as_posix()
    p = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{rel}"],
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout if p.returncode == 0 else None


def norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def build_not_bumped(text: str, head: str | None) -> str | None:
    if head is None or norm(text) == norm(head):
        return None
    now, then = BUILD_RE.search(text), BUILD_RE.search(head)
    if now is None:
        return "no $Build in Twitch_Say"
    if then is not None and now.group(1) == then.group(1):
        return f"MD differs from HEAD but $Build is still {now.group(1)!r}"
    return None


ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


def lint(texts: dict[str, str], build_text: str, build_head: str | None, label: str = ""):
    roots = {n: ET.fromstring(t.encode("utf-8")) for n, t in texts.items()}
    bad = signal_param_or_delay(roots)
    check(not bad, f"{label}no signal_cue carries param or delay" + (f" {bad}" if bad else ""))
    bad = param_never_sent(roots)
    check(not bad, f"{label}no cue reads an event.param that only signal_cue sends"
          + (f" {bad}" if bad else ""))
    bad = build_not_bumped(build_text, build_head)
    check(bad is None, f"{label}$Build bumped since HEAD" + (f" ({bad})" if bad else ""))


def self_test(texts: dict[str, str], build_text: str):
    """Each planted trap must make the lint fail; the clean copy must pass."""
    global ok
    key = BUILD_FILE.name
    poll = ('<cue name="Lint_Poll" instantiate="true"><conditions><event_cue_signalled/>'
            '</conditions><actions><set_value name="$p" exact="event.param"/>'
            '<signal_cue cue="Lint_Poll"/></actions></cue>')
    planted = {
        "signal_cue param": build_text.replace(
            "</cues>", '<cue name="Lint_A"><actions><signal_cue cue="Twitch_Say" param="1"/>'
                       "</actions></cue></cues>", 1),
        "event.param via signal_cue": build_text.replace("</cues>", poll + "</cues>", 1),
    }
    for what, text in planted.items():
        saved, ok = ok, True
        print(f"-- self-test, planted: {what}")
        lint({**texts, key: text}, text, None, "  ")
        caught = not ok
        ok = saved
        check(caught, f"self-test: the lint catches a planted {what}")
    # an edit with the old $Build, and the same edit with a new one
    edited = build_text.replace("</cues>", "<!-- lint self-test edit --></cues>", 1)
    check(build_not_bumped(edited, build_text) is not None,
          "self-test: an edit without a $Build bump is caught")
    bumped = BUILD_RE.sub(lambda m: m.group(0).replace(m.group(1), m.group(1) + "-x"), edited, 1)
    check(build_not_bumped(bumped, build_text) is None,
          "self-test: the same edit with a bumped $Build passes")


texts = {p.name: p.read_text(encoding="utf-8") for p in MD_FILES}
check(BUILD_FILE.name in texts, f"found {len(texts)} MD files, including {BUILD_FILE.name}")
build_text = texts[BUILD_FILE.name]
lint(texts, build_text, head_text(BUILD_FILE))
if "--self-test" in sys.argv:
    self_test(texts, build_text)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
