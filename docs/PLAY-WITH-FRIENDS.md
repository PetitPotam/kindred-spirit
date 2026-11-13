# Play with a friend's Pip (Windows)

Your friend hosts Pip: her AI, her voice, her memory all run on their computer. You only need
Minecraft with two small mod files. Then you see Pip exactly as they do and talk to her in chat.
No Python, no AI keys, nothing else to install.

What you need: **Minecraft Java Edition**, on the **same Wi-Fi / home network** as the host, and the **same
Minecraft version as the host**. Kindred Spirit is made for **26.3** (the newest) and **1.21.1**: ask the host
which one they play. Below, `<version>` means that one.

## 1. Install Fabric for your Minecraft version

1. Open the Minecraft Launcher once and start **release `<version>`** (Installations → New installation →
   Version "release `<version>`" → Create → Play), then quit the game. This downloads that version.
2. Download the **Fabric installer for Windows** (the `.exe`) from <https://fabricmc.net/use/installer/>.
3. Run it: tab **Client**, Minecraft version **`<version>`**, loader version the newest offered, leave
   "Create profile" ticked, click **Install**.
4. The launcher now has a **fabric-loader-`<version>`** installation.

## 2. Add the two mods

Both go in your mods folder: press `Win + R`, type `%APPDATA%\.minecraft\mods` and press Enter
(create the `mods` folder if it doesn't exist).

1. **Fabric API** for your version: from <https://modrinth.com/mod/fabric-api/versions>, pick your Minecraft
   version, download the newest file (its name ends in `+<version>.jar`) and put it in `mods`.
2. **Kindred Spirit** for your version: the host can send you their file (its name ends in `+<version>.jar`,
   e.g. `kindred-spirit-0.2.0-preview+26.3.jar`), or build it from this repository:
   - Install **Java 25** (Temurin JDK 25: <https://adoptium.net/temurin/releases/?version=25>, Windows,
     `.msi`). Only the build needs it; Minecraft keeps using its own Java.
   - In a terminal (PowerShell), in the folder where you cloned the repository (with your version, e.g.
     `:26.3:build`):
     ```powershell
     git pull
     cd mod
     .\gradlew.bat :<version>:build
     ```
   - Copy `mod\build\libs\kindred-spirit-...+<version>.jar` into your `mods` folder.

   Use the same version as the host: whenever they update the mod, get the new one. With the
   repository, one command does it all (pull, build, replace the jar, and fetch Fabric API if it's
   missing), with Minecraft closed: double-click `scripts\update-pip-windows.cmd`, or in PowerShell
   `powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1`. It keeps the Minecraft version of
   the Kindred jar you have (the newest the first time); to switch, add `-Minecraft 26.3` (or `-Minecraft 1.21.1`).

## 3. Play

1. The host opens their world and clicks **Open to LAN** (Esc → Open to LAN → Start LAN World).
2. You start the **fabric-loader-`<version>`** installation, then **Multiplayer**: their world appears at the
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

- **"Incompatible" or "outdated client"**: you're not on the host's Minecraft version. Start the
  fabric-loader installation for their version (and use the Kindred jar for it).
- **The game crashes at start, or says Kindred Spirit needs another Minecraft**: Fabric API or the Kindred jar
  is for another version (both file names must end in `+<version>.jar`), or mods from another version are in
  `mods`.
- **You see a small blue Allay named Pip instead of her**: your game doesn't have the mod (or not the
  same version as the host's). Check the `mods` folder.
- **She doesn't answer**: start your message with her name ("Pip, ..."); the host's brain must be running.
