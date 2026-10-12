#!/usr/bin/env python3
"""gen_ships.py reads loose-file extensions (X4 Ship Forge's x4_shipforge) as well as
cat/dat archives: a fake install in a temp dir, no X4 needed."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_ships  # noqa: E402

ok = True


def check(c, m):
    global ok
    print(("PASS: " if c else "FAIL: ") + m)
    ok = ok and c


def ware(macro: str, price: int, name: str) -> str:
    return (f'<ware id="{macro}" name="{name}" transport="ship" tags="ship">'
            f'<price min="1" average="{price}" max="2"/><component ref="{macro}"/></ware>')


def pack(folder: Path, files: dict[str, bytes]) -> None:
    """Write files as one cat/dat pair in X4's format."""
    lines, dat = [], b""
    for path, blob in files.items():
        lines.append(f"{path} {len(blob)} 0 0")
        dat += blob
    (folder / "01.cat").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "01.dat").write_bytes(dat)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    pack(root, {
        "libraries/wares.xml": ("<wares>" + ware("ship_arg_m_corvette_01_a_macro", 900000, "{20101,1}")
                                + "</wares>").encode(),
        "t/0001-l044.xml": b'<language><page id="20101"><t id="1">Base</t><t id="2">Odd</t></page></language>',
    })
    ext = root / "extensions" / "x4_shipforge"
    (ext / "libraries").mkdir(parents=True)
    (ext / "t").mkdir()
    # loose, as Ship Forge ships it: a <diff> adding to /wares, and its own text page
    (ext / "libraries" / "wares.xml").write_text(
        '<diff><add sel="/wares">' + ware("ship_sf_l_destroyer_01_a_macro", 4713125, "{90001,1}")
        + "</add></diff>", encoding="utf-8")
    (ext / "t" / "0001-l044.xml").write_text(
        '<language><page id="90001"><t id="1">Forge</t></page></language>', encoding="utf-8")
    # a loose extension with mixed-case paths is found too (X4 is case-insensitive)
    odd = root / "extensions" / "zz_odd" / "Libraries"
    odd.mkdir(parents=True)
    (odd / "Wares.xml").write_text(
        "<wares>" + ware("ship_tel_s_fighter_01_a_macro", 150000, "{20101,2}") + "</wares>",
        encoding="utf-8")

    rows = {r["key"]: r for r in gen_ships.buyable(*gen_ships.load(root))}

check(rows.get("base", {}).get("macro") == "ship_arg_m_corvette_01_a_macro",
      "a ship from a cat/dat archive is still listed")
check(rows.get("forge") == {"key": "forge", "label": "Forge", "macro": "ship_sf_l_destroyer_01_a_macro",
                            "credits": 4713125, "size": "L", "role": "destroyer"},
      f"the loose extension's ship gets its row ({rows.get('forge')})")
check(rows.get("odd", {}).get("macro") == "ship_tel_s_fighter_01_a_macro",
      "loose paths match case-insensitively (Libraries/Wares.xml)")
check(len(rows) == 3, f"nothing else is listed ({sorted(rows)})")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
