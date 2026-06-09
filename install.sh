#!/usr/bin/env bash
# One-step install for the X4 Twitch integration:
#   1. installs the mod into X4's extensions folder,
#   2. bundles the companion (the Python bridge) INSIDE the mod — so it travels
#      with the mod and is found by looking at X4's installed mods,
#   3. adds an app-menu launcher that runs the bundled companion.
#
# Re-run after code changes to redeploy.  Override detection with X4_DIR=/path.
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"

# --- 1. locate X4 -----------------------------------------------------------
find_x4() {
  local d
  for d in \
    "$HOME/.local/share/Steam/steamapps/common/X4 Foundations" \
    "$HOME/.steam/steam/steamapps/common/X4 Foundations" \
    "$HOME/.steam/root/steamapps/common/X4 Foundations" \
    "$HOME/Games/X4 Foundations" ; do
    [ -d "$d/extensions" ] && { printf '%s' "$d"; return 0; }
  done
  return 1
}
X4="${X4_DIR:-$(find_x4 || true)}"
if [ -z "$X4" ] || [ ! -d "$X4/extensions" ]; then
  echo "error: could not find X4. Re-run with:  X4_DIR='/path/to/X4 Foundations' ./install.sh" >&2
  exit 1
fi
EXT="$X4/extensions/twitch_integration"
echo "X4 found at: $X4"

# --- 2. install the mod -----------------------------------------------------
mkdir -p "$EXT"
cp -r "$REPO/extensions/twitch_integration/." "$EXT/"
echo "✅ mod installed:        $EXT"

# --- 3. bundle the companion inside the mod ---------------------------------
COMP="$EXT/companion"
rm -rf "$COMP"; mkdir -p "$COMP"
cp -r "$REPO/bridge/twitch_bridge" "$COMP/"
cp "$REPO/bridge/run-companion.sh" "$COMP/"
[ -f "$REPO/bridge/requirements.txt" ] && cp "$REPO/bridge/requirements.txt" "$COMP/"
chmod +x "$COMP/run-companion.sh"
find "$COMP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
echo "✅ companion bundled in:  $COMP"

# --- 4. app-menu launcher -> the bundled companion --------------------------
APPS="$HOME/.local/share/applications"; mkdir -p "$APPS"
cat > "$APPS/x4-twitch-companion.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=X4 ⇄ Twitch Companion
Comment=Start the X4 Twitch companion + dashboard
Exec=$COMP/run-companion.sh
Icon=input-gaming
Terminal=true
Categories=Game;Utility;
EOF
chmod +x "$APPS/x4-twitch-companion.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

echo "✅ launcher installed:    'X4 ⇄ Twitch Companion' in your app menu"
echo
echo "Done. The companion now lives INSIDE the mod ($COMP),"
echo "so it's found wherever X4's mods are. Launch it from the app menu,"
echo "or run:  $COMP/run-companion.sh"
