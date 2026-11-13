# Kindred Spirit Setup (macOS)

One download that gets Pip ready on your Mac, with a guide that explains every step. No terminal, no Python to
install by hand.

> **Status:** the Setup is being built in parts ([#82](https://github.com/PetitPotam/kindred-spirit/issues/82)).
> This page describes what the app does today. Until a release includes it, follow the
> [setup in the README](../README.md#setup-macos-about-10-minutes).

## 1. Download it

From the project's [releases page](https://github.com/PetitPotam/kindred-spirit/releases), under the newest
version, pick the file for your Mac's chip:

| Your Mac | The file |
|---|---|
| Apple silicon (M1, M2, M3, M4…) | `Kindred-Spirit-Setup-<version>-macos-arm64.dmg` |
| Intel | `Kindred-Spirit-Setup-<version>-macos-x86_64.dmg` |

Not sure? Apple menu  → **About This Mac**: it says **Chip: Apple M…** or **Processor: Intel**.
It needs macOS 12 (Monterey) or newer and about 3 GB of free space.

*Checking the download (optional):* next to each file is a `.sha256` file with its fingerprint. In Terminal,
`shasum -a 256 ~/Downloads/Kindred-Spirit-Setup-*.dmg` must print the same long number.

## 2. Open it (the first time, macOS asks)

1. Open the `.dmg`, then drag **Kindred Spirit Setup** onto the **Applications** folder next to it.
2. Open it from Applications.

macOS will probably stop it the first time, saying Apple could not verify that it is free of malware. That's
normal for a free app from a small project: Apple only recognises apps whose makers pay for a yearly Apple
Developer membership, and this one doesn't (yet). The app's code is all on GitHub, for anyone to read.

**To open it anyway (once):**

- **macOS 15 Sequoia or newer:** press **Done** (not "Move to Trash"). Open **System Settings → Privacy &
  Security**, scroll down to **Security**, and next to "Kindred Spirit Setup was blocked…" press **Open Anyway**.
  Confirm with your password or Touch ID, then press **Open Anyway** once more.
- **macOS 12, 13 or 14:** in Applications, hold **Control** and click the app (or right-click it), choose
  **Open**, then **Open** again.

After that, it opens with a double-click like any other app. The same note is in the disk image, as
"If macOS won't open it".

*If macOS says the app "is damaged and can't be opened":* the download was probably cut short. Download it again.
If it still says so, and you downloaded it from the releases page above (and the fingerprint matches), this
command in Terminal removes the "downloaded from the internet" mark from that one app, after which step 2 works:
`xattr -dr com.apple.quarantine "/Applications/Kindred Spirit Setup.app"`.

## 3. Follow the steps

The app opens its guide in your web browser, at `http://127.0.0.1:11441/setup`: a page served by your own Mac,
which nobody else can reach. Each step has:

- **what it does**, in plain words, and **what we recommend** (you can just take the recommendation);
- **Test it**, which checks that the step worked;
- **Copy a help prompt**, for when something goes wrong: it copies a message with the step, your Mac (macOS
  version, chip, memory, free space), the Setup's version and the exact error, ready to paste into ChatGPT,
  Claude or another assistant. The page shows you exactly what was copied. API keys, tokens, e-mail addresses,
  your user name and your home folder's path are taken out first.

The steps today:

| Step | What it does |
|---|---|
| **Your computer** | Looks at your memory, chip and free space, and picks settings that keep Minecraft smooth (Light, Balanced or Best). |
| **Her brain on this computer** | Installs her brain, the gateway and the dashboard, with their own Python, into your user folder (about 130 MB, no administrator password). |
| **Wake her up** | Starts them in the background and checks that each one answers. |

Coming next, in the same guide: choosing her AI (a free Gemini key by default, other services, a model on your
own Mac or an AI subscription you already have), her voice, hearing and memory models, and installing Minecraft's
Fabric with the mod and saying hi to her once to check everything ([#94](https://github.com/PetitPotam/kindred-spirit/issues/94),
[#95](https://github.com/PetitPotam/kindred-spirit/issues/95), [#96](https://github.com/PetitPotam/kindred-spirit/issues/96)).

You can close the page at any time: Pip keeps running, and the Setup itself quits a few minutes later (or press
**Close the Setup**). To come back to the steps, open the app again, or **Setup steps** in the dashboard
(`http://127.0.0.1:11440`).

## Where things go

| What | Where |
|---|---|
| Her settings, your keys, her memories, logs | `~/.kindred-spirit` (your home folder; hidden: in Finder press ⌘⇧. to show it) |
| The program (her brain, gateway, dashboard and their Python) | `~/Library/Application Support/Kindred Spirit` |
| The Setup app | wherever you put it (Applications) |

The Setup never touches anything else, and installing again keeps your settings and memories.

## Removing it

Quit Minecraft, then in the dashboard's Setup steps press **Stop** under "Wake her up". Then delete
**Kindred Spirit Setup** from Applications and the folder `~/Library/Application Support/Kindred Spirit`.
`~/.kindred-spirit` holds her memories and your keys: delete it too only if you want her to forget everything.

## For contributors

How the app is built and tested: [setup/README.md](../setup/README.md).
