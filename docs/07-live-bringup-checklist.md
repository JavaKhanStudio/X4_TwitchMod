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

- [ ] **Install X4** via Steam. Properties → Compatibility: **NOT** forced to Proton
      (native Linux). Launch once so `~/.config/EgoSoft/X4/` is created.
- [ ] **Install LuaSocket for Lua 5.1:** `sudo dnf install lua5.1-socket`
      (must be **5.1**, not 5.4). Note where `core.so` + `unix.so` land (e.g.
      `/usr/lib64/lua/5.1/socket/`).
- [ ] **Install the bekopharm Mod Support APIs (linux-compat):**
      ```bash
      git clone -b linux-compat https://github.com/bekopharm/x4-projects
      cp -r x4-projects/extensions/sn_mod_support_apis "<X4>/extensions/"
      ```
      (SN API ≥ 1.93.)
- [ ] **Copy the socket `.so`s into the game lua path** — follow the fork's
      [Quick-manual](https://github.com/bekopharm/x4-projects/wiki/Quick-manual) for the exact
      target (`game/ui/core/lualibs/` *or*
      `extensions/sn_mod_support_apis/ui/c_library/socket/`). **Copy, do not symlink**
      (X4 ≥7.x rejects symlinks).
- [ ] **Install our mod:** `cp -r extensions/twitch_integration "<X4>/extensions/"`
- [ ] **In-game settings:** Extensions → **disable Protected UI Mode**; enable both
      extensions. In the Named Pipes API options set **"Pipe Prefix Linux"** to `<SAVE>/`.
- [ ] **Restart X4, load a save.** Confirm the socket appeared: `ls <SAVE>/` → a socket
      file for pipe name `twitch` (note its exact name).
- [ ] **Raw transport check (no bridge yet):** `nc -U <SAVE>/<socketfile>` — should connect.
- [ ] **Turn on script debug** so our `<debug_text>` shows: launch X4 with
      `-debug all -logfile debuglog.txt`, then `tail -f "<X4>/debuglog.txt"` (path varies).

---

## Track C — Join them (the moment of truth)

- [ ] **Point the bridge at the real socket:**
      ```bash
      python -m twitch_bridge --source twitch --socket <SAVE>/<socketfile>
      ```
      (If the fork's socket name ≠ our default `x4_twitch.xml`, either pass `--socket` to
      match, or change the pipe name `'twitch'` in `md/Twitch_Integration.xml`.)
- [ ] **End-to-end:** `!ping` in chat → debug log shows `[Twitch] ping: ...` **and** `pong`
      appears in your Twitch chat. 🎉
- [ ] **First real effect:** replace the `TODO` in `Twitch_OnSpawn` with an actual ship
      spawn, then `!spawn fighter` (as a mod) → ship appears.

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
