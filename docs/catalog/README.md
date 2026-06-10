# Catalog & Roadmap page

`index.html` is the viewer-facing **catalog + interactions roadmap** — one page, two homes:

1. **Live** — the companion dashboard serves this exact file at
   `http://127.0.0.1:17564/catalog`, fed by `/api/catalog?all=1` (live data).
2. **Static (GitHub Pages)** — the page falls back to `catalog.json` sitting next
   to it. Enable Pages with **Settings → Pages → Deploy from a branch → `main` /
   `docs`**; the page then lives at `https://<user>.github.io/X4_TwitchMod/catalog/`.

Both render the same single source of truth, `bridge/twitch_bridge/catalog.py`
(doc 08 §10: *no second catalog, ever*). Each event carries a `status` —
**live / wip / planned / suggested** — so the page doubles as the public
what's-done / what's-coming tracker.

Workflow:

```sh
# after editing catalog.py:
python bridge/tools/export_catalog.py   # regenerates catalog.json (commit it)
python bridge/tools/test_md_sync.py     # status must match the MD script (CI-honest roadmap)
```

Never edit `catalog.json` or data inside `index.html` by hand — only `catalog.py`.
