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
| **Wake her up** | Starts them in the background (her brain, the gateway and her dashboard) and checks that each one answers. |
| **Her conversation (System 1)** | The AI that answers you: Gemini with a free key (recommended; the step shows how to get one in about two minutes), another service with your key (OpenAI, Groq, Mistral, OpenRouter, Claude API), a model on your Mac with Ollama, or an AI subscription you already have (Claude Code, Codex, Gemini CLI). **Use this** saves it and asks her a first question; the answer and how long it took are shown. |
| **Her instincts (System 0)** | A small model on your Mac (bge-small, about 65 MB) that finds the memories that matter; or the AI's own service, or keyword search. |
| **Her voice** | Kokoro on your Mac (about 400 MB with its program), with Lily's voice by default: **Hear it** plays each voice before you choose. Or OpenAI's voices, or subtitles only. |
| **Her hearing** | Whisper on your Mac, sized for it (from 32 MB to 574 MB; you can pick another size), then **Test the microphone**: say something and see what she heard. Or Groq or OpenAI with your key, or typing. |
| **Minecraft** | Adds a **Kindred Spirit** profile to the Minecraft Launcher, for the newest Minecraft (recommended) or an older one the mod supports, with Fabric Loader, Fabric API and the mod, in a game folder of its own (your other profiles, mods and worlds are untouched). Or puts the mod and Fabric API into another launcher's mods folder (Prism, CurseForge, MultiMC…). Quit the Minecraft Launcher first, and open it at least once before. |
| **Say hi to her** | **Open Minecraft** starts the launcher; choose the Kindred Spirit profile, open a world and type "hi Pip" in the chat. The page sees the game reach her brain and her answer. |
| **Her slow thinking (System 2)** | The AI she uses now and then to learn from your time together and write her story: the same one (recommended), another one, or off. |
| **Every time you play** | Whether she wakes by herself when you log in to your Mac (off unless you choose it), or when you open Kindred Spirit Setup. |

**Your keys** go to `~/.kindred-spirit/secrets.env`, which only you can read. The Setup never shows a key again,
never writes one to a log, and leaves it out of help prompts. On Gemini's free tier, Google may use what is sent to
improve its products; a paid key (or Ollama, on your own Mac) avoids that.

Her models download in the background with a progress bar. Each file is checked against its published
fingerprint (SHA-256) before it's used, and an interrupted download continues where it stopped: press **Use this**
again. They go in `~/.kindred-spirit` (`embed/`, `kokoro/`, `whisper/`).

**Only joining a friend who hosts Pip on a LAN world?** You need just the **Minecraft** step: her brain, AI and
models live on your friend's computer.

**Talking by voice:** hold **V** in the game. Start Minecraft with **Open Minecraft** in the last step: macOS then
asks for the microphone in Kindred Spirit Setup's name. Started from the Dock, the launcher has no microphone
permission of its own and she hears silence.

You can close the page at any time: Pip keeps running, and the Setup itself quits a few minutes later (or press
**Close the Setup**).

## Her dashboard

Her dashboard is a page on your Mac where you see what she feels, remembers and builds: her heart and mood, your
conversations, past sessions, her memories, the buildings she knows, and her settings
([what's in it](DASHBOARD.md)). It starts and stops together with her brain, and only your Mac can open it.

- **In the game, press K.**
- **Once she's set up, open Kindred Spirit Setup**: it wakes her if she isn't running and opens her dashboard.
- In the Setup's steps, **Open her dashboard** (top right) whenever she's running.
- Or go straight to **http://127.0.0.1:11440** in your browser while she's running.

To come back to the steps, press **Setup steps** in the dashboard's side bar.

## Updates

The last step, **Updates**, asks GitHub for the newest version and shows what's new. **Update** then:
- downloads that version's Setup for your Mac, checked against its fingerprint;
- installs its program next to the current one, and wakes her up on it;
- puts the matching mod into your Kindred Spirit profile (or the mods folder you gave);
- replaces the Setup app itself.

Her brain, the mod and the Setup always move together, because they must be the same version. Your settings, keys
and memories stay as they are. The version before is kept: **Go back to …** returns to it. Quit Minecraft before
updating.

## Where things go

| What | Where |
|---|---|
| Her settings, your keys, her memories, logs | `~/.kindred-spirit` (your home folder; hidden: in Finder press ⌘⇧. to show it) |
| The program (her brain, gateway, dashboard and their Python) | `~/Library/Application Support/Kindred Spirit` |
| The Setup app | wherever you put it (Applications) |
| Waking her at login, only if you chose it | `~/Library/LaunchAgents/io.github.petitpotam.kindredspirit.plist` (System Settings → General → Login Items lists it as "bash") |

The Setup never touches anything else, and installing again keeps your settings and memories.

## Removing it

Quit Minecraft, then in the dashboard's Setup steps choose **When I open Kindred Spirit Setup** under "Every time you
play" (this removes the login item, if you had one) and press **Stop** under "Wake her up". Then delete
**Kindred Spirit Setup** from Applications and the folder `~/Library/Application Support/Kindred Spirit`.
`~/.kindred-spirit` holds her memories and your keys: delete it too only if you want her to forget everything.

## For contributors

How the app is built and tested: [setup/README.md](../setup/README.md).
