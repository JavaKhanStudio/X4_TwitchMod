#!/usr/bin/env python3
"""Export the FULL catalog (all statuses, disabled included) to
docs/catalog/catalog.json — the static data behind the GitHub Pages
roadmap page (docs/catalog/index.html). Run after editing catalog.py
and commit the result."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twitch_bridge.catalog import catalog_view  # noqa: E402

out = Path(__file__).resolve().parents[2] / "docs" / "catalog" / "catalog.json"
data = catalog_view(enabled_only=False)
out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
print(f"wrote {out} ({len(data)} events)")
