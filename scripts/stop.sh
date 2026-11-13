#!/bin/bash
# Stops what scripts/start.sh started (and nothing else), and waits until each has really exited (up to 5 s,
# then it's forced): a restart (an update, the Setup's "Start") needs their ports free again.
KH="${KINDRED_HOME:-$HOME/.kindred-spirit}"
pids=""
for f in "$KH"/run/*.pid; do
  [[ -f "$f" ]] || continue
  pid="$(cat "$f")"; name="$(basename "$f" .pid)"
  if kill "$pid" 2>/dev/null; then echo "stopped $name"; pids="$pids $pid"; fi
  rm -f "$f"
done
for _ in $(seq 1 20); do
  alive=""
  for p in $pids; do kill -0 "$p" 2>/dev/null && alive="$alive $p"; done
  [[ -z "$alive" ]] && exit 0
  pids="$alive"; sleep 0.25
done
for p in $pids; do kill -9 "$p" 2>/dev/null; done
exit 0
