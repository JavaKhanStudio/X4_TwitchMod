#!/usr/bin/env python3
"""Milestone 1 round-trip probe: connect to X4's live `twitch` Unix socket, send a
`ping` command line, and print whatever X4 sends back.

This is the minimal "hello socket" proof — it does NOT touch Twitch. It mimics what
the bridge's x4link client will do, but as a single shot so we can eyeball both
directions. Run it WHILE X4 is running with a game loaded (so the socket exists).

Expected: X4's md Twitch_OnPing fires (visible in the debug log as "[Twitch] ping:")
and replies with {"t":"say","msg":"pong"} — which prints here as  <- {"t":"say"...}.

Usage:
    python tools/socket_roundtrip.py            # auto-find socket in the save dir
    python tools/socket_roundtrip.py /path/to/twitch.xml
"""
import glob
import os
import socket
import sys
import time


def find_socket() -> str:
    home = os.path.expanduser("~")
    hits = sorted(
        glob.glob(os.path.join(home, ".config/EgoSoft/X4/*/save/twitch.xml")),
        key=lambda p: os.stat(p).st_mtime, reverse=True,
    )
    return hits[0] if hits else ""


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else find_socket()
    if not path:
        print("No twitch.xml socket found. Is X4 running with a game loaded?")
        return 2
    if not os.path.exists(path):
        print(f"Socket not present: {path}\n(Load a game in X4 first — it's runtime-only.)")
        return 2

    print(f"Connecting to {path}")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect(path)
    print("Connected. (X4 accepts the client on its next host-pipe read cycle.)")

    line = b'{"t":"cmd","id":"ping","by":"roundtrip"}\n'
    print(f"-> {line.decode().strip()}")
    s.sendall(line)

    # Read replies; X4 only accepts the client on its host-pipe read cycle, so the
    # reply can take several seconds to appear. Note X4 currently writes WITHOUT a
    # trailing newline, so we print whatever bytes arrive, not just \n-framed lines.
    s.settimeout(1.0)
    deadline = time.time() + 12.0
    buf = b""
    got = False
    while time.time() < deadline:
        try:
            chunk = s.recv(4096)
        except TimeoutError:
            if got:  # already saw the reply; no need to keep waiting
                break
            continue
        if not chunk:
            print("(X4 closed the connection)")
            break
        buf += chunk
        # print complete lines if newline-framed...
        while b"\n" in buf:
            msg, buf = buf.split(b"\n", 1)
            if msg.strip():
                print(f"<- {msg.decode(errors='replace').strip()}")
                got = True
        # ...otherwise flush whatever we have (X4 omits the trailing newline)
        if buf.strip():
            print(f"<- {buf.decode(errors='replace').strip()}  (no trailing newline)")
            buf = b""
            got = True
    s.close()
    print("\nRESULT:", "round-trip OK ✅" if got
          else "sent OK, no reply seen — check the debug log for '[Twitch] ping:'")
    return 0 if got else 1


if __name__ == "__main__":
    raise SystemExit(main())
