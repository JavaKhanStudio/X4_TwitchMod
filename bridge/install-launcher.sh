#!/usr/bin/env bash
# Install a clickable desktop launcher for the companion (app menu + double-click).
# Generates the .desktop with the ABSOLUTE path at install time, so no personal
# path is committed to the (public) repo. Run once:  ./install-launcher.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
DESK="$APPS/x4-twitch-companion.desktop"

cat > "$DESK" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=X4 ⇄ Twitch Companion
Comment=Start the X4 Twitch companion + dashboard
Exec=$HERE/run-companion.sh
Icon=input-gaming
Terminal=true
Categories=Game;Utility;
EOF
chmod +x "$DESK"
update-desktop-database "$APPS" 2>/dev/null || true

echo "✅ Installed launcher: $DESK"
echo "   Find 'X4 ⇄ Twitch Companion' in your application menu."
echo "   (To also put it on the desktop: cp '$DESK' \"\$HOME/Desktop/\" && chmod +x \"\$HOME/Desktop/x4-twitch-companion.desktop\")"
