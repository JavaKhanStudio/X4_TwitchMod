# References — link bank

Every source backing this reference bank. Grouped by topic. (Researched 2026-06.)

## X4 modding — official / wiki
- X Community Wiki (authoritative MD/AI/UI ref): https://wiki.egosoft.com/
- h2odragon's HOWTO-hackx4f (modding basics): https://wiki.egosoft.com/X4%20Foundations%20Wiki/Modding%20Support/ScriptingMD/Community%20Guides/h2odragon's%20HOWTO-hackx4f/
- Egosoft forum — Tools/Tutorials/Resources index: https://forum.egosoft.com/viewtopic.php?f=181&t=402382
- Steam Workshop modding (content.xml / packing): https://wiki.egosoft.com/X%20Rebirth%20Wiki/Modding%20support/Steam%20Workshop%20for%20X%20Rebirth%20and%20X4/

## X4 modding — tools & examples
- X4 Customizer (bvbohnen): https://github.com/bvbohnen/X4_Customizer
- ratilicus/x4 (modding examples + compile scripts): https://github.com/ratilicus/x4
- kuertee UI extensions (Lua UI patterns): https://github.com/kuertee/x4-mod-ui-extensions
  - README: https://github.com/kuertee/x4-mod-ui-extensions/blob/master/README.md
- "Getting into X4 modding (on Linux)" — beko: https://beko.famkos.net/2021/05/01/getting-into-x4-foundations-modding-on-linux/

## Mod Support APIs (Named Pipes / Lua Loader / Simple Menu / etc.)
- bvbohnen/x4-projects (source): https://github.com/bvbohnen/x4-projects
- sn_mod_support_apis dir: https://github.com/bvbohnen/x4-projects/tree/master/extensions/sn_mod_support_apis
- **Named Pipes API doc:** https://github.com/bvbohnen/x4-projects/blob/master/extensions/sn_mod_support_apis/documentation/Named_Pipes_API.md
- Releases: https://github.com/bvbohnen/x4-projects/releases
- Nexus — Mod Support APIs: https://www.nexusmods.com/x4foundations/mods/503
- Nexus — Mod Support APIs **Community Edition** (patch 7): https://www.nexusmods.com/x4foundations/mods/1699
- Steam Workshop — SirNukes Mod Support APIs: https://steamcommunity.com/workshop/filedetails/?id=2042901274
- X4 External App (Mycu, example companion): https://www.nexusmods.com/x4foundations/mods/818

## Linux socket bridge (LuaSocket) — bekopharm ✅ our path
- **Quick-manual (LuaSocket setup on Linux, "X4 8.x"):** https://github.com/bekopharm/x4-projects/wiki/Quick-manual
- bekopharm/x4-projects (linux-compat branch, MIT): https://github.com/bekopharm/x4-projects/tree/linux-compat
- Fedora package `lua5.1-socket`: https://packages.fedoraproject.org/pkgs/lua-socket/lua5.1-socket/
- djfhe/x4_http — HTTP/HTTPS client inside X4 Lua (luasocket+luasec): https://github.com/djfhe/x4_http
- "Community Edition" fork (ARCHIVED 2025-09, X4 7.X only — do NOT use for 8.x): https://github.com/iomatix/x4-projects ; https://www.nexusmods.com/x4foundations/mods/1699
- Egosoft cross-platform cloud saves (Feb 2026): https://www.gamingonlinux.com/2026/02/x4-foundations-is-getting-cross-platform-cloud-saves-possible-breakage-coming-for-linux/
- x4-simpit (working example using the socket): https://github.com/bekopharm/x4-simpit
- "Running X4 with my SimPit" writeup: https://beko.famkos.net/2023/04/04/running-x4-foundations-with-my-simpit/
- "Modding my X4 into using…" (LuaSocket origin post): https://beko.famkos.net/2023/04/03/15628467/
- SimPit on Linux overview: https://linux.simpit.dev/games/x4-foundations/
- Hackaday log: https://hackaday.io/project/191048/log/218903-running-x4-foundations-with-my-simpit

## Twitch API (2026-current)
- Chat & Chatbots hub: https://dev.twitch.tv/docs/chat
- Authenticating & setting up EventSub: https://dev.twitch.tv/docs/chat/authenticating/
- Send & receive chat messages: https://dev.twitch.tv/docs/chat/send-receive-messages/
- Example chatbot guide: https://dev.twitch.tv/docs/chat/chatbot-guide/
- Migrating from IRC (why EventSub now): https://dev.twitch.tv/docs/chat/irc-migration/
- "Twitch Chat on EventSub + send API + Conduit" announce: https://discuss.dev.twitch.com/t/available-today-twitch-chat-on-eventsub-an-api-for-sending-chat-and-the-conduit-transport-method-for-eventsub/54596
- App Access Tokens capabilities (Barry Carlyon, 2026): https://barrycarlyon.co.uk/wordpress/2026/02/28/twitch-app-access-tokens-can-do-more/

## Native code / C++ / LuaJIT FFI route (see doc 05)
- LuaJIT FFI API (`ffi.load`, `ffi.cdef`): https://luajit.org/ext_ffi_api.html
- LuaJIT FFI tutorial: https://luajit.org/ext_ffi_tutorial.html
- "Writing a shared C++ library and loading it in LuaJIT": https://csl.name/post/luajit-cpp/
- carrascodev/x4-mods — C++ framework (HenMod.Commons) + Nakama multiplayer: https://github.com/carrascodev/x4-mods
- Official **X Tools** (Steam → Library → Tools) — asset/XML tooling, not a C++ code SDK
- ioTools — X4 Modding Kit (unpack + doc WebApp): https://www.nexusmods.com/x4foundations/mods/1420
- X4 Modding Tools update announcement: https://store.steampowered.com/news/app/392160/view/3646281279393578329
- X4 Lua functions reference (gist): https://gist.github.com/NodusCursorius/b61f26177fdcb490d2456e353d57f363

## Viewer-economy design reference (see doc 08)
- **TwitchToolkit** (hodlhodl1132, RimWorld — DEPRECATED, concepts only, no live code): https://github.com/hodlhodl1132/twitchtoolkit
  - The reference design for "viewers spend a watch-time currency to inject events." We port
    the *economy concepts* (wallet, karma governor, store, voting), not the RimWorld events or
    the dead IRC/`tmi-chatters` transport. Full mapping → X4 in `docs/08-viewer-economy-and-events.md`.
- **TwitchToolkit item-list** (the buyable-catalog site): https://github.com/twitchtoolkit/item-list
  - Static GitHub Pages site (Bootstrap + List.js) rendering JSON catalog data (`StoreEvents.json`,
    `StoreItems.json`) as searchable/sortable tables — shared with viewers as a link. The model for
    our local catalog view + shareable export. Schema/plan in `docs/08` §10.

## Twitch client libraries (for the Bridge)
- Python `twitchAPI` (PyTwitchAPI): https://pytwitchapi.dev/ (PyPI: twitchAPI)
- Node `@twurple`: https://twurple.js.org/

## Notes
- Twitch IRC mod commands deprecated 2023-02-18; PubSub decommissioned 2025-04-14.
- X4 Lua is **5.1** — LuaSocket must be built for 5.1 (`lua5.4-socket` will NOT work).
- Named pipes (Path A) are Windows-only; Linux uses LuaSocket (Path B).
