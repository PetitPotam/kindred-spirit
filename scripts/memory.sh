#!/bin/bash
# What your companion remembers, from any folder:
#   scripts/memory.sh           everything she remembers
#   scripts/memory.sh forget    forget every memory (asks first); keeps your bond and her powers
#   scripts/memory.sh reset     a brand-new companion: memories, bond, discovered powers and
#                               conversations all erased (asks first; quit the game before)
#   scripts/memory.sh worlds    your worlds, and what she knows in each (each world has its own companion)
#   scripts/memory.sh import "Old World" ["New World"]
#                               bring what she knew about you and herself into another world (by
#                               default the one you played last); with the game closed, her bond and
#                               discovered powers come along too
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/brain" || exit 1
if [ "$1" = "reset" ]; then
  if lsof -nP -iTCP:47811 -sTCP:ESTABLISHED 2>/dev/null | grep -q java; then
    echo "Minecraft is connected to her right now. Quit the game first, then try again."
    exit 1
  fi
  # restart brain and gateway so nothing she knew stays in their memory and gets saved back
  pkill -f "Python -m kindred$" 2>/dev/null; pkill -f "python -m kindred$" 2>/dev/null
  pkill -f "kindred_gateway.py serve" 2>/dev/null
  sleep 2
  "$ROOT/scripts/start.sh" --background >/dev/null
  for _ in $(seq 1 20); do curl -s -m 1 http://127.0.0.1:11437/health >/dev/null && break; sleep 1; done
fi
if lsof -nP -iTCP:47811 -sTCP:ESTABLISHED 2>/dev/null | grep -q java; then export KINDRED_GAME_CONNECTED=1; fi
exec .venv/bin/python -m kindred.memory "$@"
