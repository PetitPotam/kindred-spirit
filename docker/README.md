# Host Pip with Docker (Windows, Linux)

Her brain, the gateway, her dashboard, her voice (Kokoro) and her hearing (Whisper) in one Docker image that runs
**on your own computer**. Nothing is hosted anywhere: Minecraft on the same computer talks to her at 127.0.0.1, the
way it does on a Mac with the Setup. It's for technical players for now (#128); the native Windows install is
[docs/HOSTING-WINDOWS.md](../docs/HOSTING-WINDOWS.md), and on a Mac use Kindred Spirit Setup.

**What you need:** Docker ([Docker Desktop](https://docs.docker.com/desktop/) on Windows: it needs WSL 2, sometimes a
restart, and on some PCs virtualization switched on in the BIOS; [Docker Engine](https://docs.docker.com/engine/install/)
on Linux), about 2 GB of disk, and Minecraft with Fabric and the Kindred Spirit mod (the
[install guide](https://kindred-spirit-pip.web.app/guides/install)).

## Start her

From a copy of this repository (or download the one script):

```bash
scripts/docker-run.sh                        # Linux
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\docker-run.ps1    # Windows
```

The first start downloads the image (about 1 GB) and then, inside your `~/.kindred-spirit`, her voice (~120 MB)
and hearing (57 MB). Put your Gemini key in `~/.kindred-spirit/secrets.env` (`GEMINI_API_KEY=...`), or choose
another AI on her dashboard, and start again. Run the same command to update; `--stop` (`-Stop`) stops her.

Or by hand (what the scripts do):

```bash
docker run -d --name kindred-spirit --restart unless-stopped --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:47811:47811 -p 127.0.0.1:11440:11440 \
  -v "$HOME/.kindred-spirit:/home/pip/.kindred-spirit" ghcr.io/petitpotam/kindred-spirit-brain:latest
```

- **Ports on 127.0.0.1 only**: 47811 for the game, 11440 for her dashboard (**K** in the game opens it). Never
  publish them on all addresses (`-p 47811:47811`): her dashboard has no password, it trusts this computer.
- **Your files**: `~/.kindred-spirit` (`%USERPROFILE%\.kindred-spirit` on Windows) is mounted, so her settings,
  memories, key, and the token the game reads are the same files as without Docker.
- **Her log**: `docker logs -f kindred-spirit`. Other logs: `~/.kindred-spirit/logs/`.
- **Sleep and stop**: her dashboard's "Put her to sleep" stops her brain, voice and hearing (the container keeps
  running, to wake her); "Stop everything" stops the container. `/kindred sleep` and `/kindred wake` in the game too.

## What's different from a Mac

- **Hearing** uses the small English Whisper model on the CPU (`ggml-base.en-q5_1.bin`). A better one, slower:
  `-e KINDRED_WHISPER_MODEL=ggml-small.en-q5_1.bin`. No GPU inside the container.
- **Blueprints**: the game's own village houses are in the game's folder, which the container can't see. To let her
  find them, mount the game's `config/kindredspirit` folder and say where:
  `-v "<your .minecraft>/config/kindredspirit:/home/pip/game:ro" -e KINDRED_BLUEPRINTS=/home/pip/game/blueprints:/home/pip/game/blueprints-from-minecraft`.
  Building works without it (the game builds from its own files); only her suggestions need it.
- **In-game settings** on her dashboard's Settings page: the same, mount the game's `config` folder
  (`-v "<your .minecraft>/config:/home/pip/game-config"`) and set
  `-e KINDRED_MOD_CONFIG=/home/pip/game-config/kindredspirit.json`. The game's own settings screen (J) works either way.
- **The Setup app** (its page at `/setup`) is for Macs; ignore it here.

## Build it yourself

```bash
docker build -f docker/Dockerfile -t kindred-spirit-brain .
KINDRED_IMAGE=kindred-spirit-brain scripts/docker-run.sh
scripts/test-install.sh docker     # the same checks as CI: build, run, a pretend game talks to her
```
