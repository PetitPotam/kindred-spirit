#!/usr/bin/env python3
"""A first look at a new or edited issue, for .github/workflows/issue-triage.yml (no AI, no network).

Reads the issue forms' answers (### Heading, then the answer) and decides:
- the area labels, from "Which part is it about?";
- for a bug report with neither the computer nor any logs: `needs-info`, and one friendly comment when it's new;
  once one of them is there, `needs-info` comes off.

Prints JSON: {"add": [...], "remove": [...], "comment": "..." or ""}. The workflow applies it with `gh`.
Only labels from AREA_LABELS and `needs-info` are ever touched, whatever the issue says.
"""
import json
import os
import re
import sys

AREA_LABELS = {
    "In game: how she moves, looks and reacts": ["mod"],
    "In game: subtitles, HUD, settings screen, /kindred commands": ["mod"],
    "Talking and personality": ["brain"],
    "Helping (mining, chopping, crafting, trading...)": ["mod", "brain"],
    "Building and blueprints": ["mod"],
    "Memory": ["brain"],
    "Voice and hearing": ["services"],
    "Friends and LAN": ["lan"],
    "Skins and looks": ["content"],
    "Dashboard": ["services"],
    "Setup and installing": ["services"],
    "Performance (FPS, lag, memory)": ["mod"],
    "Another Minecraft version or mod loader (NeoForge, Quilt...)": ["versions"],
}
NEEDS_INFO = "needs-info"
MARKER = "<!-- kindred-triage -->"
ASK = (MARKER + "\nThanks for the report! To find what went wrong, could you add **your computer and operating "
       "system** and, if you can, **the logs** (`logs/latest.log` in your Minecraft folder, the lines with "
       "`kindredspirit`, and `~/.kindred-spirit/logs/brain.log`)? Edit the issue to add them; remove API keys and "
       "anything personal first.\n\n_This is an automatic first look by the triage workflow, not a person._")


def answers(body):
    """The form's answers by heading: {"Which part is it about?": "Memory", ...}. "_No response_" counts as empty."""
    out = {}
    for m in re.finditer(r"^###\s+(.+?)\s*\n(.*?)(?=^###\s|\Z)", body or "", re.S | re.M):
        text = m.group(2).strip()
        text = re.sub(r"^```\w*\s*|\s*```$", "", text).strip()  # (logs are rendered in a code block)
        out[m.group(1).strip()] = "" if text == "_No response_" else text
    return out


def triage(body, labels, action="opened"):
    a = answers(body)
    labels = set(labels)
    add = [lab for lab in AREA_LABELS.get(a.get("Which part is it about?", ""), []) if lab not in labels]
    remove, comment = [], ""
    if "bug" in labels:
        system = a.get("Computer and operating system", "")
        logs = a.get("Logs", "")
        if not system and not logs:
            if NEEDS_INFO not in labels:
                add.append(NEEDS_INFO)
                if action == "opened":
                    comment = ASK
        elif NEEDS_INFO in labels:
            remove.append(NEEDS_INFO)
    return {"add": add, "remove": remove, "comment": comment}


def main():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    issue = event["issue"]
    result = triage(issue.get("body") or "", [lab["name"] for lab in issue.get("labels", [])], event.get("action", ""))
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
