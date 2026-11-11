#!/bin/bash
# macOS: double-click to play. Starts everything, then opens the Minecraft Launcher FROM THIS
# TERMINAL. That matters: the launcher has no microphone permission of its own, so started from
# the Dock the game records silence; started from Terminal it uses Terminal's permission.
# Keep this window open while you play. Pick the "Kindred Spirit (Fabric 1.21.1)" profile.
cd "$(dirname "$0")/.." || exit 1
scripts/start.sh --background
echo
echo "Opening the Minecraft Launcher: pick the Kindred Spirit profile and press Play."
echo "In game: hold V to talk, or type /kindred <message>."
/Applications/Minecraft.app/Contents/MacOS/launcher >/dev/null 2>&1
