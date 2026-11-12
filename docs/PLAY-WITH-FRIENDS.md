# Play with a friend's Pip (Windows)

Your friend hosts Pip: her AI, her voice, her memory all run on their computer. You only need
Minecraft with two small mod files. Then you see Pip exactly as they do and talk to her in chat.
No Python, no AI keys, nothing else to install.

What you need: **Minecraft Java Edition**, on the **same Wi-Fi / home network** as the host.

## 1. Install Fabric for Minecraft 1.21.1

1. Open the Minecraft Launcher once and start **release 1.21.1** (Installations → New installation →
   Version "release 1.21.1" → Create → Play), then quit the game. This downloads 1.21.1.
2. Download the **Fabric installer for Windows** (the `.exe`) from <https://fabricmc.net/use/installer/>.
3. Run it: tab **Client**, Minecraft version **1.21.1**, loader version the newest offered, leave
   "Create profile" ticked, click **Install**.
4. The launcher now has a **fabric-loader-1.21.1** installation.

## 2. Add the two mods

Both go in your mods folder: press `Win + R`, type `%APPDATA%\.minecraft\mods` and press Enter
(create the `mods` folder if it doesn't exist).

1. **Fabric API** for 1.21.1: from <https://modrinth.com/mod/fabric-api/versions?g=1.21.1>, download the
   file for **1.21.1** (version `0.116.x+1.21.1`) and put the `.jar` in `mods`.
2. **Kindred Spirit**: the host can send you their file
   (`kindred-spirit-0.1.0-preview+1.21.1.jar`, the one *without* `-sources`), or build it from this
   repository:
   - Install **Java 21** (Temurin JDK 21: <https://adoptium.net/temurin/releases/?version=21>, Windows,
     `.msi`).
   - In a terminal (PowerShell), in the folder where you cloned the repository:
     ```powershell
     git pull
     cd mod
     .\gradlew.bat build
     ```
   - Copy `mod\build\libs\kindred-spirit-0.1.0-preview+1.21.1.jar` into your `mods` folder.

   Use the same version as the host: whenever they update the mod, get the new one. With the
   repository, one command does it all (pull, build, replace the jar, and fetch Fabric API if it's
   missing), with Minecraft closed: double-click `scripts\update-pip-windows.cmd`, or in PowerShell
   `powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1`.

## 3. Play

1. The host opens their world and clicks **Open to LAN** (Esc → Open to LAN → Start LAN World).
2. You start the **fabric-loader-1.21.1** installation, then **Multiplayer**: their world appears at the
   bottom as a LAN world after a few seconds. Join it. (If it doesn't show up: **Direct Connection**
   with the host's local IP and the port shown in their chat, e.g. `192.168.1.20:52143`.)
3. You'll see a message: you see their Pip. She floats beside the host (or beside you, if the host
   asks her to stay with you).

**You can host too.** Open your world to LAN and let them join: their Pip comes along with them (her
brain stays on their computer). Your game shows her to everyone and carries out her powers in your world
for them. To stop her changing things in your world, set `"lanVisitors": false` (below). Without them,
your game shows no Pip at all: she only appears when someone's Pip is there.

Talking to her:

- In chat: **`Pip, can you give me night vision?`** Start with her name. She answers in your chat
  as `[Pip] ...` (and out loud on the host's computer).
- Your talk key (**V**) opens the chat with her name already typed.
- She can find people and animals, lead the way, give you items and effects, and protect you, if
  the host allows it and her power and style allow it. Otherwise she just talks with you.

## Settings (optional)

`%APPDATA%\.minecraft\config\kindredspirit.json` (created after the first start):

- `"sharedPip": "host"` (default): in a friend's world you see and share their Pip.
- `"sharedPip": "own"`: your own Pip instead. That needs the whole setup (the brain, an AI key...):
  see the README. Her brain's start scripts are written for macOS for now.
- `"lanVisitors": true` (default): when you host, a friend's Pip may use her powers in your world.

## If something's wrong

- **"Incompatible" or "outdated client"**: you're not on 1.21.1. Start the fabric-loader-1.21.1 installation.
- **The game crashes at start**: Fabric API missing or for the wrong version (it must say `+1.21.1`),
  or Java mods from another version in `mods`.
- **You see a small blue Allay named Pip instead of her**: your game doesn't have the mod (or not the
  same version as the host's). Check the `mods` folder.
- **She doesn't answer**: start your message with her name ("Pip, ..."); the host's brain must be running.
