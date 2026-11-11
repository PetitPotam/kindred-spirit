#!/bin/bash
# Stops what scripts/start.sh started (and nothing else).
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
for f in "$KH"/run/*.pid; do
  [[ -f "$f" ]] || continue
  pid="$(cat "$f")"; name="$(basename "$f" .pid)"
  if kill "$pid" 2>/dev/null; then echo "stopped $name"; fi
  rm -f "$f"
done
