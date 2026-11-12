# Notes for coding agents

Kindred Spirit: a Minecraft Java 1.21.1 Fabric mod (`mod/`, Java 21) with a companion called Pip,
whose "brain" (`brain/`, Python), gateway and voice (`services/`) run on the computer of whoever hosts her.
Docs: `README.md`, `docs/ARCHITECTURE.md`.

## Setting up a friend's Windows PC to play with the host's Pip (most likely why you're here)

The friend needs **no brain, no Python, no AI keys**: only Minecraft 1.21.1 with Fabric, Fabric API and
the Kindred mod jar built from this repository. The full guide for the person is
`docs/PLAY-WITH-FRIENDS.md`; the steps for you:

1. **Java 21 JDK** (to build the mod). Check `java -version`; if missing or older than 21, install
   Eclipse Temurin 21 (e.g. `winget install EclipseAdoptium.Temurin.21.JDK`), then open a new terminal.
2. **Build the mod** from the repository root, in PowerShell:
   ```powershell
   git pull
   cd mod
   .\gradlew.bat build
   ```
   The jar is `mod\build\libs\kindred-spirit-0.1.0-preview+1.21.1.jar` (not the `-sources` one). The
   first build downloads Gradle and Minecraft's files: a few minutes. Tests run as part of the build.
3. **Minecraft 1.21.1 with Fabric** (the person clicks through these; guide them):
   - Minecraft Launcher → Installations → New installation → version **release 1.21.1** → start once.
   - Fabric installer for Windows from https://fabricmc.net/use/installer/ → Client, Minecraft 1.21.1,
     newest loader, "Create profile" ticked → Install.
4. **Mods folder** `%APPDATA%\.minecraft\mods` (create it if needed), containing exactly:
   - Fabric API for 1.21.1 (`fabric-api-0.116.x+1.21.1.jar`, from
     https://modrinth.com/mod/fabric-api/versions?g=1.21.1);
   - the Kindred jar from step 2 (replace any older Kindred jar).
5. They start the **fabric-loader-1.21.1** installation and join the host's LAN world from Multiplayer.

**Steps 2 and 4 in one command** (after Git, Java 21 and Fabric are set up), and the way to update
whenever the host pushes changes (Minecraft closed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update-pip-windows.ps1
```

It pulls, builds the mod (tests skipped), replaces the Kindred jar in `%APPDATA%\.minecraft\mods`, and
downloads Fabric API for 1.21.1 from Modrinth if it's missing. `scripts\update-pip-windows.cmd` does the
same on a double-click; a desktop shortcut to it is handy. Keep their Kindred jar the same version as the
host's: update after every push. In game they talk to Pip in chat: "Pip, ...".

Don't set up `brain/` or `services/` on the friend's PC unless they explicitly want their own Pip (the
brain's scripts are written for macOS). Never commit or push from the friend's machine unless asked.

## Working on the code

- Mod: `cd mod && ./gradlew build` (Java 21+; tests with JUnit). Brain: `cd brain && .venv/bin/python -m pytest`.
- Sandbox checks drive a dev client with scripts: `./gradlew runClient -PdevScript=devscripts/<script>.txt`.
