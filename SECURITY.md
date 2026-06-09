# Security & Content-Leak Policy

This is a **public** repository, and the mod intentionally **launches a small companion
process** (see `docs/09-onboarding-oauth-and-companion-ux.md`). Both facts raise the bar:
nothing secret or personal may land in git, and everything that runs must stay auditable.

## 1. What must NEVER be committed

| Category | Examples | Where it lives instead |
|---|---|---|
| Twitch **client secret** | `TWITCH_CLIENT_SECRET`, app secret | env var / local-only, never a file in the repo |
| OAuth **tokens** | access/refresh tokens | `~/.config/x4-twitch-bridge/tokens.json` (outside the repo) |
| Viewer **economy data** | `viewers.json` (usernames, coins, karma) | bridge runtime dir, gitignored |
| **Savegames / logs** | `*.xml.gz`, `debuglog*.txt`, `crash_debug.log` | game/user dirs (contain chat, usernames, paths) |
| Runtime **sockets** | `twitch.xml`, `x4_python_host.xml`, `*.sock` | the savegame folder, gitignored |
| **PII / machine paths** | home dirs, OS usernames, the X4 numeric user-id, email | use placeholders (below) |
| Compiled **blobs** | `*.so`, `*.dll` without source | never vendor binaries without buildable source |

The Twitch **Client ID** is semi-public (it ships in OAuth redirects), but treat it as config,
not a committed constant — keep it in env/local config so forks don't inherit it.

## 2. Path & PII rule

- **Docs:** use placeholders — `<X4>` (install dir), `<SAVE>` (savegame dir), `<id>` (the
  per-user numeric folder). Never paste a literal `/home/<user>/…` path or the numeric id.
- **Code:** derive paths at runtime — `Path.home()` / glob in Python, `GetSaveFolderPath()` via
  FFI in Lua. Never hardcode a home directory (we already hit and fixed this in the Lua proof).

## 3. The `.gitignore` is the safety net, not the only one

`.gitignore` blocks the obvious files (tokens, `viewers.json`, saves, logs, sockets, `*.env`,
`*secret*`, `*.so`). But ignore rules don't help if you `git add -f` or paste a secret into a
tracked source/doc file. So also run the pre-commit check below.

## 4. Pre-commit checklist

```bash
# 1. No secrets or PII in what you're about to commit:
git diff --cached | grep -inE 'client_secret *= *["'"'"'][^"'"'"']|access_token|refresh_token|oauth_token|/home/[a-z]|[0-9]{8}|@[a-z0-9.]+\.(com|net)'
#    (env-var NAMES like TWITCH_CLIENT_SECRET are fine; a secret VALUE assigned to one is not.)

# 2. No accidentally-staged sensitive files:
git diff --cached --name-only | grep -iE 'token|\.env|secret|\.xml\.gz|debuglog|viewers\.json|\.so$'

# Both should print nothing.
```

## 5. If a secret is committed anyway

1. **Rotate it first** — revoke/regenerate the Twitch app secret in dev.twitch.tv, re-auth.
   (Assume anything pushed public is already scraped; rotation is the only real fix.)
2. Then scrub history (`git filter-repo` / BFG) and force-push.
3. Add a `.gitignore` rule so it can't recur.

## 6. Auditability (because the mod spawns a process)

The companion auto-launch is the same FFI technique native X4 mods use, but it *is* a
process launch — so we keep it trustworthy: no obfuscated/minified/compiled-without-source
code in the repo, the spawn command stays readable, and the README warns users plainly that a
helper process is started. If you can't audit it by reading the repo, it doesn't belong here.

## 7. Reporting

Found a leaked secret or a vulnerability? Open an issue (no secret values in the issue) or
contact the maintainer privately. Don't post tokens in a public issue.
