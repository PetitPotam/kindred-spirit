# Host Pip on Windows

Run her brain, the gateway, her dashboard, her voice (Kokoro) and her hearing (Whisper) on your Windows PC, so you
can have your own Pip instead of joining a friend's (#40). It's a first version for technical players: three
PowerShell scripts, tested on GitHub's Windows machines (`scripts\test-install-windows.ps1`) but not yet on many
players' PCs. Tell us how it goes ([an issue](https://github.com/PetitPotam/kindred-spirit/issues/new/choose)).
The other way is Docker: [docker/README.md](../docker/README.md).

**What you need:** Windows 10 or 11 (x64), [Git](https://git-scm.com/download/win), Python 3.11 or newer
(`winget install Python.Python.3.12`, then open a new PowerShell), about 1.5 GB of disk, a Gemini key (or another
AI, chosen on her dashboard), and Minecraft with Fabric and the Kindred Spirit mod
([the install guide](https://kindred-spirit-pip.web.app/guides/install); for the mod,
`scripts\update-pip-windows.ps1` builds and installs it).

## Set her up (once)

In PowerShell, in your copy of this repository:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

It makes her Python environment (`brain\.venv`), and in `%USERPROFILE%\.kindred-spirit`: her voice (Kokoro,
~120 MB), her memory's embeddings (~65 MB) and her hearing (whisper.cpp's Windows build, checked against its SHA-256,
and the Whisper model this PC can run). `-NoVoice` sets up only her brain (typing to her, subtitles). Then put your
key in `%USERPROFILE%\.kindred-spirit\secrets.env`: `GEMINI_API_KEY=...`.

## Play

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1 -Background
```

starts everything in the background (`-Background` left out: her brain runs in that window, Ctrl+C stops it). Then
start Minecraft (the Fabric profile with the mod) and play: she connects by herself. **K** opens her dashboard.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-windows.ps1
```

stops it all. Her dashboard's "Put her to sleep" and "Wake her up" buttons (and `/kindred sleep`, `/kindred wake`)
work too. Logs: `%USERPROFILE%\.kindred-spirit\logs\` (`brain.log`, `gateway.log`, and each helper's `.out`/`.err`).

## What's different from a Mac

- **Hearing** runs on the CPU (whisper.cpp's CPU build); a GPU build is for later.
- **No Setup app** yet: these scripts are the Windows install for now. The dashboard's `/setup` page is for Macs.
- Helpers run at a lower priority than Minecraft, like on a Mac.
