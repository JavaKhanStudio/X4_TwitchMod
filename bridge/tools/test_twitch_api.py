"""Verify every twitchAPI name our TwitchSource uses exists in the installed lib.

Catches API drift without needing live Twitch credentials. Needs `twitchAPI`
(pip install -r requirements.txt). FAILS (exit 1) if not installed, never a
silent skip (r37): under WSL, run it with Windows `py.exe`, which has it.

    python tools/test_twitch_api.py
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import twitchAPI.object.eventsub as es
    from twitchAPI.eventsub.websocket import EventSubWebsocket
    from twitchAPI.oauth import UserAuthenticationStorageHelper
    from twitchAPI.twitch import Twitch
    from twitchAPI.type import AuthScope
except ImportError:
    print("FAIL: twitchAPI not installed (pip install -r requirements.txt; under WSL use py.exe)")
    sys.exit(1)

fail = 0
def check(cond, label):
    global fail
    print(f"{'PASS' if cond else 'FAIL'}: {label}")
    fail += 0 if cond else 1

for name in ["USER_READ_CHAT", "USER_WRITE_CHAT", "USER_BOT",
             "CHANNEL_READ_REDEMPTIONS", "CHANNEL_READ_SUBSCRIPTIONS",
             "BITS_READ", "MODERATOR_READ_FOLLOWERS"]:
    check(hasattr(AuthScope, name), f"AuthScope.{name}")

for m in ["start", "stop", "listen_channel_chat_message",
          "listen_channel_points_custom_reward_redemption_add",
          "listen_channel_subscribe", "listen_channel_cheer",
          "listen_channel_follow_v2", "listen_channel_raid"]:
    check(hasattr(EventSubWebsocket, m), f"EventSubWebsocket.{m}")

check(list(inspect.signature(EventSubWebsocket.listen_channel_chat_message)
           .parameters)[1:4] == ["broadcaster_user_id", "user_id", "callback"],
      "listen_channel_chat_message(broadcaster, user, callback)")
check("to_broadcaster_user_id" in inspect.signature(
        EventSubWebsocket.listen_channel_raid).parameters,
      "listen_channel_raid(callback, to_broadcaster_user_id=...)")
check(list(inspect.signature(EventSubWebsocket.listen_channel_follow_v2)
           .parameters)[1:4] == ["broadcaster_user_id", "moderator_user_id", "callback"],
      "listen_channel_follow_v2(broadcaster, moderator, callback)")

for p in ["broadcaster_id", "sender_id", "message"]:
    check(p in inspect.signature(Twitch.send_chat_message).parameters,
          f"send_chat_message param {p}")
check("storage_path" in inspect.signature(
        UserAuthenticationStorageHelper.__init__).parameters,
      "UserAuthenticationStorageHelper(storage_path=...)")

# Event payload attributes our callbacks read.
payloads = {
    "ChannelChatMessageEvent": ["chatter_user_name", "message", "badges"],
    "ChannelPointsCustomRewardRedemptionAddEvent": ["user_name", "reward"],
    "ChannelSubscribeEvent": ["user_name", "tier"],
    "ChannelCheerEvent": ["user_name", "bits"],
    "ChannelRaidEvent": ["from_broadcaster_user_name", "viewers"],
    "ChannelFollowEvent": ["user_name"],
}
for wrapper, want in payloads.items():
    ev_type = getattr(es, wrapper).__annotations__["event"]
    have = set(getattr(ev_type, "__annotations__", {}))
    for f in want:
        check(f in have, f"{wrapper}.event.{f}")

# Our module imports cleanly and builds its scope list.
from twitch_bridge.sources import twitch as T  # noqa: E402

check(T._IMPORT_ERROR is None, "twitch.py imports twitchAPI cleanly")
check(len(T._scopes()) == 7, "twitch.py _scopes() builds 7 scopes")

print(f"\n{'ALL PASS' if fail == 0 else str(fail) + ' FAILURES'}")
sys.exit(1 if fail else 0)
