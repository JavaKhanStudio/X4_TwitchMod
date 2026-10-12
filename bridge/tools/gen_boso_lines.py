#!/usr/bin/env python3
"""Generate extensions/twitch_integration/md/twitch_boso_lines.xml — the pool of
Boso Ta voice lines `!boso random` draws from — straight from an X4 install.

    py -3 tools/gen_boso_lines.py "E:\\Steam\\steamapps\\common\\X4 Foundations"

WHY THE POOL LIVES IN MD AND NOT HERE. The bridge cannot send a line id: only
STRINGS marshal Lua->MD (numbers are dropped outright), MD has no string->number
conversion, and `<text line="…"/>` needs a number. So the bridge can only ever say
"play something random" and MD has to own the ids and do the picking. Hence a
GENERATED mdscript rather than a JSON file next to sectors.json/ships.json.

WHERE THE LINES COME FROM (verified against X4 8.00):
  * `t/0001-l044.xml` page 10201 — "Boron NPC 1 / Boron rep / Misc Plot Characters",
    voice="yes". This is the page Boso Ta's macro points at
    (libraries/character_macros.xml, `<identification … page="10201"/>`), so every
    id on it both renders as his subtitle and resolves to his recorded audio.
    It is a SHARED Boron voice page, not a Boso-only script: alongside his plot
    dialogue it carries generic Boron NPC chatter (mission offers, station
    security). All of it is in his voice, which is the point.
  * `voice-l044/10201/comm/<id>.ogg` — the recordings. An id with no file here
    plays SILENTLY, which in game is indistinguishable from the cue not firing,
    so presence in this folder is a hard requirement, not a nicety.

FILTERS (each one is a thing that looked wrong on screen):
  * id >= 99901 — below that the page holds names, menu strings and mission titles,
    not spoken lines.
  * no `(*  *)` section headers, no `{page,line}` redirects (they render literally).
  * no `$PLACEHOLDER$` — substituted by the mission that owns the line; we are not
    that mission, so it would show as raw text.
  * no parentheses left in the body — page 10201 keeps stage directions inline
    ("I recommend switching to EMPs.(pronounced Ee-Em-Pees)") and they are drawn
    in the subtitle. A leading "(annoyed)" tag is fine and is stripped by the game.
  * <= 120 chars, so it fits the comm popup.

Re-run after a game patch to pick up new lines. The result is a generated file:
edit this script, never the XML.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from x4cat import all_cats, cat_entries, elements, install_root

PAGE = "10201"                       # Boso Ta's voice/text page
MIN_ID = 99901                       # first spoken line; below this is UI text
MAX_LEN = 120                        # comm popup is not a paragraph
VOICE_DIR = f"voice-l044/{PAGE}/comm/"
# Keep each MD list literal comfortably inside proven territory: the largest list
# literal in vanilla MD is 8674 chars (story_paranid.xml), and the whole pool is
# ~14k. Four chunks puts each at ~3.5k, well under that, and MD picks a random
# chunk then a random line out of it.
CHUNKS = 4

OUT = (Path(__file__).resolve().parents[2] / "extensions" / "twitch_integration"
       / "md" / "twitch_boso_lines.xml")

HEADER = """<?xml version="1.0" encoding="utf-8"?>
<!--
  GENERATED FILE - DO NOT EDIT BY HAND.
  Regenerate with:  py -3 bridge/tools/gen_boso_lines.py "<X4 install path>"

  The pool of Boso Ta voice lines that `!boso random` draws from: every id on
  TextDB page {page} (his voice page) at {minid}+ that has a real recording in
  {voicedir}. See the generator for why the ids live in MD
  instead of in the bridge, and for what is filtered out.

  {count} lines, split into {chunks} lists purely to keep each expression near the
  size vanilla itself uses. Twitch_Integration calls RandomLine for the result.
-->
<mdscript name="Twitch_BosoLines" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <cues>
    <library name="RandomLine" purpose="run_actions">
      <actions>
"""

FOOTER = """        <set_value name="$pool" exact="[{chunknames}]"/>
        <set_value name="$chunk" exact="$pool.random"/>
        <return value="$chunk.random"/>
      </actions>
    </library>
  </cues>
</mdscript>
"""


def voiced_ids(root: Path) -> set[str]:
    """Every id that actually has audio. Reads the cat INDEXES only — the .dat blobs
    are gigabytes and we only need the file names."""
    have: set[str] = set()
    for cat in all_cats(root):
        for path, _off, _size in cat_entries(cat):
            if path.startswith(VOICE_DIR) and path.endswith(".ogg"):
                have.add(path[len(VOICE_DIR):-4])
    return have


def page_entries(root: Path) -> dict[str, str]:
    """The English TextDB's PAGE, id -> text. Later archives patch earlier ones, so
    merge in order."""
    entries: dict[str, str] = {}
    for _cat, pg in elements(root, "t/0001-l044.xml", "page"):
        if pg.get("id") != PAGE:
            continue
        for t in pg.iter("t"):
            if t.get("id"):
                entries[t.get("id")] = (t.text or "").strip()
    return entries


def spoken(txt: str) -> str | None:
    """The subtitle `txt` shows as, or None if it fails a FILTER (module docstring)."""
    if txt.startswith("(*") or "{" in txt or "$" in txt or "\\n" in txt:
        return None
    # A leading "(annoyed)" direction is stripped by the game; anything later in
    # the string is not, and would be drawn in the subtitle.
    body = re.sub(r"^(\([^)]*\))+", "", txt).strip()
    if not body or len(body) > MAX_LEN or "(" in body or ")" in body:
        return None
    return body


def collect(root: Path) -> list[tuple[str, str]]:
    have = voiced_ids(root)
    entries = page_entries(root)
    if not have or not entries:
        raise SystemExit(f"no data found under {root} "
                         f"(voice files: {len(have)}, page {PAGE} entries: {len(entries)})")

    kept: list[tuple[str, str]] = []
    for tid, txt in entries.items():
        if not tid.isdigit() or int(tid) < MIN_ID or tid not in have:
            continue
        body = spoken(txt)
        if body:
            kept.append((tid, body))

    kept.sort(key=lambda r: int(r[0]))
    return kept


def main() -> int:
    root = install_root()
    if root is None:
        return 1
    lines = collect(root)

    size = -(-len(lines) // CHUNKS)          # ceil, so the last chunk is the short one
    chunks = [lines[i:i + size] for i in range(0, len(lines), size)]

    body = []
    for n, chunk in enumerate(chunks, 1):
        ids = ", ".join(tid for tid, _ in chunk)
        body.append(f'        <set_value name="$c{n}" exact="[{ids}]"/>')
    names = ", ".join(f"$c{n}" for n in range(1, len(chunks) + 1))

    text = (HEADER.format(page=PAGE, minid=MIN_ID, voicedir=VOICE_DIR,
                          count=len(lines), chunks=len(chunks))
            + "\n".join(body) + "\n"
            + FOOTER.format(chunknames=names))
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(lines)} lines in {len(chunks)} chunks, "
          f"longest literal {max(len(b) for b in body)} chars)")
    print("  first:", lines[0][0], lines[0][1][:60])
    print("  last: ", lines[-1][0], lines[-1][1][:60])
    return 0


if __name__ == "__main__":
    sys.exit(main())
