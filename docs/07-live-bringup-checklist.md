# 07 — Live Bring-up Checklist

Two **independent** tracks. Do **A (Twitch)** first — it needs no game and closes the
Twitch unknown. Do **B (X4)** when the game finishes installing. Then **C** joins them.

Legend: `<X4>` = the X4 install dir (Steam Linux: usually
`~/.steam/steam/steamapps/common/X4 Foundations`). `<SAVE>` =
`~/.config/EgoSoft/X4/save`.

---

## Track A — Twitch half (no game needed)

- [ ] **Create a Twitch app:** https://dev.twitch.tv/console → *Register Your Application*.
      OAuth Redirect URL = **`http://localhost:17563`**. Copy the **Client ID** + **Client Secret**.
- [ ] **(Optional) Create the channel-point reward** titled exactly **`Pirate Attack`**
      (or edit `bridge/twitch_bridge/catalog.py` to match a reward you already have).
- [ ] **Install deps:** `cd bridge && pip install -r requirements.txt`
- [ ] **Set env:**
      ```bash
      export TWITCH_CLIENT_ID=xxxx TWITCH_CLIENT_SECRET=yyyy TWITCH_CHANNEL=yourlogin
      ```
- [ ] **First-run OAuth against the mock** (so no game needed):
      ```bash
      # terminal 1
      python tools/mock_x4.py --socket /tmp/x4_twitch.sock
      # terminal 2
      python -m twitch_bridge --source twitch --socket /tmp/x4_twitch.sock
      ```
      A browser opens → authorize the scopes → tokens saved to `~/.config/x4-twitch-bridge/`
      (auto-refreshed after this).
- [ ] **Verify read path:** type `!ping` in your Twitch chat → terminal 1 (mock) prints
      `{"t": "cmd", "id": "ping", ...}`. Try a raid/sub/cheer or redeem *Pirate Attack* too.
- [ ] **Verify send path:** in terminal 1 type `say hello from x4` → it appears in your
      Twitch chat (Helix). ✅ Twitch half done.

---

## Track B — X4 half (needs the game)

> **DONE on this machine (2026-06-09) — all filesystem prep complete.** Concrete facts:
> - `<X4>` = `<X4-install-dir>`. Confirmed
>   **native ELF, X4 8.00** (version.dat = `800`), not Proton.
> - `<SAVE>` = `~/.config/EgoSoft/X4/<id>/save/` (per-user numeric id — the fork
>   auto-detects it via `C.GetSaveFolderPath()`; the bridge globs for it).
> - Socket file will be **`<SAVE>/twitch.xml`** (pipe name in our MD is `twitch`; the fork
>   names the socket `<name>.xml`). The bridge default now resolves to exactly this.
> - LuaSocket libs were extracted **without root** (`dnf download lua5.1-socket` +
>   `rpm2cpio | cpio`) and copied to `<X4>/extensions/sn_mod_support_apis/ui/c_library/socket/`
>   (a `.gitkeep` there confirms that's the expected drop spot — `require("socket.core")`
>   resolves via the cpath the fork prepends).
> - bekopharm `sn_mod_support_apis` installed (its content id is **`ws_2042901274`**, ver 191).
> - Our mod installed. **Four bugs the real source exposed were fixed:** (1) bridge socket
>   filename `x4_twitch.xml` → `twitch.xml`; (2) save-dir hard-coded → autodiscovered;
>   (3) our `<dependency id="sn_mod_support_apis">` → **`ws_2042901274`** (deps match the
>   content *id*, not the folder — every SN companion mod uses this); (4) our `ui.xml` was at
>   `ui/ui.xml` with a bare `<file name="twitch_integration"/>` → moved to the extension
>   **root** with `<file name="ui/twitch_integration.lua"/>` (matches the fork's own ui.xml).
>
> **What's LEFT (needs the game running + your hands in the GUI):** the three steps below.

- [x] **Install X4** native (confirmed 8.00, not Proton).
- [x] **LuaSocket 5.1** extracted (no root) + dropped into `c_library/socket/`.
- [x] **bekopharm Mod Support APIs (linux-compat)** installed. **Our mod** installed.
- [ ] **In-game settings (YOU):** Extensions menu → **disable Protected UI Mode**; enable
      both `Mod Support APIs` and `Twitch Integration`. (No need to set "Pipe Prefix Linux" —
      the fork auto-points it at `<SAVE>`.)
- [ ] **Restart X4, load a save (YOU).** Then confirm the socket appeared:
      `ls -l ~/.config/EgoSoft/X4/<id>/save/twitch.xml`
- [ ] **Raw transport check (no bridge yet):**
      `nc -U ~/.config/EgoSoft/X4/<id>/save/twitch.xml` — should connect (Ctrl-C to exit).
- [ ] **Turn on script debug** so our `<debug_text>` shows: launch X4 with
      `-debug all -logfile debuglog.txt`, then `tail -f "<X4>/debuglog.txt"` (path varies).

---

## Track C — Join them (the moment of truth)  ✅ DONE 2026-06-09

**Milestone 1 COMPLETE — bidirectional socket round-trip proven on X4 8.00 native Linux.**
The probe `bridge/tools/socket_roundtrip.py` connected to the live `…/save/twitch.xml`, sent
`{"t":"cmd","id":"ping"}`, and the debug log showed the full chain:
```
New connection … for twitch          → X4 accepted the client
Read 40 characters from client        → X4 received the ping
Twitch_OnPing: [Twitch] ping: {…}     → JSON decoded, correct cue fired
Wrote 24 characters to client         → X4 sent {"t":"say","msg":"pong"} back
```
and the probe printed `<- {"t":"say","msg":"pong"}  RESULT: round-trip OK ✅`. **The entire
networking risk of the project is retired.** (Used a one-shot probe, not the real bridge, to
isolate the transport; the production bridge run is the next step below.)

- [x] Socket round-trips both directions via the Named Pipes MD API on native Linux.
- [ ] **Run the REAL bridge** against live X4 (confirm the production code path):
      ```bash
      cd bridge && python -m twitch_bridge --source stdin   # socket auto-discovered (config.py)
      ```
      then type a fake command; watch the debug log for `[Twitch] …`. (`--source twitch` once
      Twitch creds are set — see **doc 09** for the real onboarding/OAuth UX, not this console.)
- [ ] **First real effect:** replace the `TODO` in `Twitch_OnSpawn` with an actual ship spawn,
      then drive `!spawn fighter` → ship appears.
- [ ] **In-game "Enable Twitch" toggle + status panel** via Simple Menu API (doc 08 M4.3 /
      doc 09 §4) — the UI surface the streamer actually uses.

### Bug ledger — six issues only the live game exposed (all fixed)
1. Bridge socket filename `x4_twitch.xml` → **`twitch.xml`** + autodiscover the numeric save dir.
2. content.xml dependency `id="sn_mod_support_apis"` → **`ws_2042901274`** (deps match content
   *id*, not folder; every SN companion mod uses this).
3. `ui.xml` at `ui/ui.xml` → extension **root**, and `<file name="ui/twitch_integration.lua"/>`.
4. **Protected UI Mode** must be OFF (else `package` is nil + non-whitelisted `require` blocked).
5. MD filename `Twitch_Integration.xml` → **lowercase** `twitch_integration.xml` (X4's Linux
   VFS lowercases paths; capitalized files aren't found on a case-sensitive disk). *The unlock.*
6. Read started on `event_game_started` (too early) → **`md.Named_Pipes.Reloaded`**; and X4 pipe
   writes have **no trailing newline** → append `'\n'` in `Twitch_Say`.

---

## Likely snags (and the one-line fix)

| Symptom | Fix |
|---|---|
| LuaSocket not loading / `require` fails | Protected UI still on, or `.so`s in wrong path / wrong Lua version (need 5.1). |
| Mod doesn't load | Check debug log for `content.xml`/`ui.xml` parse errors (the schema `[VERIFY]` items). |
| No socket file in `<SAVE>/` | "Pipe Prefix Linux" not set, or SN API < 1.93, or extension disabled. |
| Bridge "waiting for X4 socket…" forever | `--socket` path ≠ the actual socket filename. `ls <SAVE>/` and match it. |
| Events arrive but MD cue never fires | `AddUITriggeredEvent`/`event.param3` mismatch — adjust `signal_md()` (lua) / `param3` (md). |
| `!spawn` denied | You're not a mod in your own chat? Use the broadcaster account, or lower `min_role` in `catalog.py`. |

## Recommended order
A (now) → B (on install) → C. A and B don't depend on each other; only C needs both.
