# 11 — How far can an agent test without Simon?

The question (board r24): can an agent test a mod change without Simon starting the
whole game? Or can it run X4 in the background and drive it from start to finish? It
has to stay inside the rule in r2: no agent opens X4 or a window on Simon's screen
without his go.

Legend: `<X4>` = the X4 install dir. `<PROFILE>` = `<HOME>\Documents\Egosoft\X4\<id>`.
These are placeholders, not real paths (SECURITY.md).

## Tier 0 — no game at all (an agent can do this today)

| Check | Catches | Status |
|---|---|---|
| `ET.parse` of the MD | `--` in a comment, broken XML: the whole file fails to load | in the #mod pack |
| `bridge/tools/test_md_sync.py` | a cue under an instantiated cue with no event condition (dropped at load); catalog ↔ MD drift | in the #mod pack |
| `py.exe bridge/tools/validate_md.py` (md.xsd, Windows `py` + lxml) | unknown attributes, e.g. `signal_cue param=` and `delay=`; a missing required `reason` | ~2 min, or 0.2 s with `--serve` up (r43) |
| `bridge/tools/test_lua_decode.py` (lupa) | the Lua JSON decode and the argv joining | in the #companion pack, run with `py.exe`; FAILS without lupa (r37) |
| `mock_x4.py` + the smoke test | the bridge ↔ pipe protocol, with the game faked | in the #companion pack |

What tier 0 can NEVER prove: that a cue fires, that `$x?` meant what you thought, that
a ship spawns, that chat shows the line. Those are runtime facts, and today they cost one
round with Simon each.

Cheap wins left in tier 0:
- Done in r42: `bridge/tools/test_md_lint.py`, an MD lint for the SKILL.md traps that
  neither the schema nor the sync test sees ($Build not bumped, `signal_cue` param or delay,
  and `event.param` on a cue only `signal_cue` reaches).
- Done in r43: the md.xsd recipe as one script, `bridge/tools/validate_md.py`.

## Tier 1 — X4 runs, driven by the agent (needs Simon's go, see r2)

Verified on this machine from the strings in `<X4>\X4.exe` (2026-10-12):

- Launch flags that exist: `-skipintro`, `-disablesound`, `-disablemusic`,
  `-nosoundthrottle`, `-nocputhrottle` (keep running at full speed while unfocused),
  `-logfile <name>`, `-debug <filter>`, `-scriptlogfiles`, `-enablexmlvalidation`,
  `-dontsaveconfig`, `-pauseonload`, `-prefersinglefiles`.
- No load-a-save flag. The binary has the `loadSave` UI event, but no command-line
  parameter that names a save (inferred: none found among the config keys around
  `skipintro`).
- The UI Lua has globals for the whole lifecycle. Vanilla
  `ui/addons/ego_gameoptions/gameoptions.lua` calls them:
  - `LoadGame(filename)` at :2963 and :8045;
  - `NewGame(gamestartid)` at :8099 and :13428;
  - `SaveGame(filename, name)` at :9296;
  - `QuitGame()` at :8125;
  - `C.IsStartmenu()` at :418.

So a run from start to finish is feasible:

1. The agent runs `deploy.ps1`, then starts `X4.exe -skipintro -disablesound
   -nocputhrottle -debug all -logfile agent.txt` through `powershell.exe`. Steam must be
   running. One X4 at a time: it cannot run while Simon plays.
2. A debug-only Lua hook in our mod, at the start menu, calls `NewGame("<test gamestart>")`
   or `LoadGame("<save>")`. It must be told to by something the agent can set before the
   launch. Lua has no file I/O, so that is a user-data key in `<PROFILE>` (unverified), or
   a keystroke. Either way it TOUCHES THE PROFILE FOLDER.
3. The game is up. The MD opens the pipe, and the companion (`--source stdin`, driven by
   the agent) sends viewer commands. The agent reads the replies, `agent.txt` and the
   chat lines it would post.
4. `QuitGame()` (a pipe command), or the agent kills the process.

What tier 1 cannot avoid on Windows: **a real window on Simon's GPU and screen.** There
is no headless mode. Under Windows, the cage recipe in /run-offscreen does not apply.
What could hide the window, cheapest first:
- Launch it minimized, while Simon is away. It still takes the GPU, and Steam shows him
  "playing".
- A second Windows virtual desktop. It needs a third-party CLI; nothing built in.
- A second Windows user signed in through RDP loopback, or a VM with GPU partitioning.
  Both are hours of setup and own a Steam session.

## Recommendation

Do tier 0 now; it needs nobody (child tickets of r24). Tier 1 is Simon's call (the
question on r24). Its first step is the smallest thing that proves it works: an agent
launches X4 with the flags above while Simon is away, loads one named test save, fires
`ping` over the pipe, reads `pong` from the log, and quits.
