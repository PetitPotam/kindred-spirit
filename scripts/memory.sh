#!/bin/bash
# What Pip remembers, from anywhere:  scripts/memory.sh          (everything)
#                                      scripts/memory.sh forget   (erase it all, after asking)
cd "$(dirname "$0")/../brain" || exit 1
exec .venv/bin/python -m kindred.memory "$@"
