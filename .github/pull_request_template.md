<!-- Thanks for contributing! One change per pull request, please. The title becomes the commit title
     when it's merged: say what changes for the player ("She can plant crops on request"). -->

**What and why**

<!-- What changes, and why it's needed. Link the issue: "Fixes #123". -->

**How I tested it**

- [ ] `cd mod && ./gradlew build` (mod and its Java tests, for every Minecraft version)
- [ ] `cd brain && .venv/bin/python -m pytest -q` (brain)
- [ ] Tried in the sandbox if it changes what you see, hear or what she does
      (`./gradlew :26.3:runClient -PdevScript=devscripts/<script>.txt`); a screenshot or clip is welcome

**Checklist**

- [ ] It doesn't add blocks, items, entities or world data, and stays light on the game thread
- [ ] Docs and `CHANGELOG.md` (under "Unreleased") updated if players or contributors will notice
- [ ] No API keys, personal data or real player names in code, tests, logs or screenshots
- [ ] I signed the [CLA](../blob/main/CLA.md) (the bot asks on your first pull request)
- [ ] AI tools used for this change, if any: <!-- e.g. "Claude Code wrote the tests", or "none" -->
