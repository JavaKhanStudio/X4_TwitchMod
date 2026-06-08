# 03 — Twitch API (2026-current)

> **Implemented** in `bridge/twitch_bridge/sources/twitch.py` using **twitchAPI 4.5**
> (`EventSubWebsocket` + `UserAuthenticationStorageHelper` + Helix `send_chat_message`).
> Concrete mapping: `listen_channel_chat_message`→`chat`, `..._points_custom_reward_
> redemption_add`→`redeem`, `..._subscribe`→`sub`, `..._cheer`→`cheer`, `..._raid`→`raid`,
> `..._follow_v2`→`follow`. Scopes: `USER_READ_CHAT`, `USER_WRITE_CHAT`, `USER_BOT`,
> `CHANNEL_READ_REDEMPTIONS`, `CHANNEL_READ_SUBSCRIPTIONS`, `BITS_READ`,
> `MODERATOR_READ_FOLLOWERS` (raid needs none). Names verified by `tools/test_twitch_api.py`.
> Still TODO live: create the dev app + first OAuth. The notes below are the background.

This is what the **Bridge process** implements. The X4 side never talks to Twitch
directly. Sources in `references.md`; all current as of mid-2026.

## What changed (don't use stale tutorials)

- **IRC is legacy.** Twitch recommends **EventSub** for *reading* chat and **Helix REST**
  for *sending* chat. IRC chat moderation commands (`/ban`, `/timeout`, `/clear`,
  `/uniquechat`) were **deprecated 2023-02-18** and no longer work over IRC.
- **PubSub was decommissioned 2025-04-14.** Do not use it.
- So: **EventSub WebSocket (read) + Helix (write/act). OAuth via the standard flows.**

## Reading chat & events — EventSub WebSocket

The Bridge opens a **WebSocket to EventSub**, then subscribes to event types. The key one:

- **`channel.chat.message`** — every chat message in the target channel, in real time.
  Delivers user, message text, badges, bits, emotes, etc. This is our main command stream.

Other high-value subscriptions for "Twitch controls the game":

| EventSub type | Use in-game |
|---------------|-------------|
| `channel.chat.message` | `!commands`, votes, raw chat → events |
| `channel.channel_points_custom_reward_redemption.add` | redemptions spawn ships / events |
| `channel.subscribe` / `channel.subscription.gift` | subs trigger rewards/buffs |
| `channel.cheer` | bits → scaled events |
| `channel.raid` | raid → big in-game event |
| `channel.follow` | follow → small reward |

### EventSub WebSocket flow
1. Connect WS to the EventSub endpoint; receive a **`session_welcome`** with a
   `session_id`.
2. For each event type, **POST** a subscription to Helix
   `POST /helix/eventsub/subscriptions` with `transport: { method: "websocket",
   session_id }` and the required `condition` (e.g. `broadcaster_user_id`, `user_id`).
3. Receive `notification` messages over the WS; **respond to keepalives**; reconnect on
   `session_reconnect`.

## OAuth & scopes

- **`channel.chat.message`** requires (minimum) **`user:read:chat`** from the chatting
  (bot) user.
  - With an **App Access Token** you additionally need **`user:bot`** from the bot user,
    plus either moderator status or **`channel:bot`** from the broadcaster.
  - Simplest for a personal mod: **User Access Token** for the broadcaster's own account
    acting as its own bot.
- **Sending chat** (`POST /helix/chat/messages`) requires **`user:write:chat`** (and
  `user:bot`, or `channel:bot` from the broadcaster).
- **Moderation** (if we ever auto-moderate): `POST /helix/moderation/bans`,
  `DELETE /helix/moderation/chat` with `moderator:manage:banned_users` etc.

### Token mechanics
- Register an app in the **Twitch Developer Console** → get **Client ID + Secret**.
- For a single-user local mod, the **Authorization Code** or **Device Code** grant gives a
  user token + **refresh token**; the Bridge refreshes automatically. Store tokens in a
  local file the Bridge owns (never in the X4 extension).
- **Validate tokens hourly** (Twitch requirement) via `GET /oauth2/validate`.

## Sending chat & acting — Helix REST

- **Send a message:** `POST /helix/chat/messages` with `broadcaster_id`, `sender_id`,
  `message`. (This replaced IRC `PRIVMSG` for bots.)
- **Announcements, shoutouts, etc.:** various `/helix/chat/*` and `/helix/moderation/*`
  endpoints if we want richer game→chat feedback.

## Bridge responsibilities (summary)

The Bridge process must:
1. Hold Client ID/Secret + tokens; do OAuth + hourly validate + refresh.
2. Maintain the **EventSub WebSocket** (subscribe, keepalive, reconnect).
3. Normalize incoming events into our **line protocol** (`{"t":"chat",...}` etc.) and push
   to X4 over the socket.
4. Receive `{"t":"say",...}` / action lines from X4 and call the matching **Helix**
   endpoint.
5. Be resilient: if X4 isn't connected yet, queue or drop; if Twitch drops, reconnect.

### Library choices for the Bridge
- **Python:** `twitchAPI` (async, has EventSub WS + Helix + OAuth helpers) — fastest path.
  Or hand-rolled with `websockets` + `httpx` + `authlib`.
- **Node.js:** `@twurple/*` (eventsub-ws, api, auth) — very ergonomic.
- Pick based on what's nicest to ship alongside a Linux X4 install. Python pairs naturally
  with the existing X4 modding ecosystem (X4 Customizer, pipe servers are Python).

## Minimal command-mapping idea (design seed)
A small, data-driven mapping table in the Bridge **or** in X4 MD:

```
!spawn <type>      → {"t":"spawn","ship":<type>,"by":<user>}   (sub/mod gated)
channel-point "Pirate Attack" → {"t":"event","id":"pirate_attack"}
raid (N viewers)   → {"t":"event","id":"reinforcements","scale":N}
```
Keep the *policy* (who's allowed, cooldowns, costs) configurable. Decide whether policy
lives in the Bridge (easy to edit, hot-reload) or in X4 MD (closer to game state). Likely
**Bridge owns rate-limit/permission, X4 owns game effect.**
