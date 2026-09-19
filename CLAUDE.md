# Notes for Claude Code (machine-specific gotchas)

Read this before touching scripts or setting the server up on a new machine. The README describes the
pipeline; this file records what turned out to differ between machines.

## Paths differ between machines

- The scripts were originally written on a machine whose Windows account was named `user`, and hardcoded
  `C:\Users\user\mc-server` / `C:\Users\user\tancmeystery-modpack`. The home PC (the real server) uses a
  different account name, so those paths did not exist there.
- Fixed in commit `8632a50`: `run_deploy.ps1`, `ensure_server_running.ps1` and
  `setup_scheduled_tasks.ps1` now derive everything from `$PSScriptRoot`. The two repos **must stay
  siblings in the same parent folder** (`<parent>\mc-server` and `<parent>\tancmeystery-modpack`) -
  `run_deploy.ps1` finds the modpack as `<parent of mc-server>\tancmeystery-modpack`. The server repo must
  be cloned into a folder named `mc-server` (the GitHub repo name is `tancmeystery-server`, so use
  `git clone <url> mc-server`).
- `start.ps1` used to hardcode the JDK path (a specific Temurin patch folder), which breaks on any other
  machine. It now finds Java itself: `JAVA_HOME`, then `java.exe` on `PATH`, then `jdk*` folders under
  `Program Files\Eclipse Adoptium`, `\Java` and `\Microsoft`. Java 17 is preferred; anything older than 17
  is rejected (checked from the exe's version info). `.\start.ps1 -DryRun` prints the Java it would use and
  exits without starting the server - use it to check a new machine. If none is found it exits with code 1
  and a message. `-Xmx12G -Xms4G` are still fixed in the script; lower them on machines with little RAM.
- Do not put user names, tunnel addresses, RCON passwords or player nicknames in this repo (it is public).

## Setting up a second / test server

1. Clone both repos as siblings (see above), install Java 17 (Temurin) and Python 3 **for all users**
   (scheduled tasks run as SYSTEM and need `python` on the machine PATH).
2. Follow the README first-time setup, plus: run the Fabric installer for Minecraft 1.20.1 with loader
   `0.19.5` (the version pinned in `tancmeystery-modpack/pack.toml`) into `mc-server\`, write
   `eula.txt`, copy `server.properties.template` to `server.properties` and generate a **new** random
   `rcon.password` (never reuse the production one).
3. `.\start.ps1 -DryRun` confirms Java is found (no path edit needed any more), then `python sync_mods.py`
   downloads the pinned jars (verified against the sha512 in each `.pw.toml`).
4. `world/` and `backups/` are gitignored. To experiment on a copy of the live world, copy a backup tarball
   over and extract it so that `world\` sits in `mc-server\`. The Simon Says datapack is in
   `tancmeystery_datapack.zip`: extract it into `world\datapacks\tancmeystery\` so `pack.mcmeta` and `data\`
   sit directly in that folder (the zip contains a `tancmeystery/` subfolder - flatten it).
5. Then `python setup_luckperms.py` for the rank groups.
6. Do **not** register the scheduled tasks on a test machine unless you want it auto-deploying from `master`.

## SYSTEM scheduled tasks

- Tasks run as SYSTEM. SYSTEM has no GitHub credentials, so both repos are public (pull needs no login) and
  `safe.directory` for both folders was added to the **system-wide** git config (`git config --system`),
  otherwise git refuses with "dubious ownership" for folders owned by another account.
- `run_deploy.ps1` compares HEAD before/after `git pull --ff-only` in both repos. Any commit to either repo
  therefore triggers a full `deploy.py` run at 05:00 (15 min in-game warnings, backup, restart), even if the
  mods are already installed. `deploy.py` always sleeps through the 15/10/5/1 minute warnings.
- Local uncommitted edits to tracked files make `git pull --ff-only` fail if upstream touches the same file.
  Commit and push script fixes instead of leaving them local.

## Editing the modpack (packwiz is not installed)

- `packwiz.exe` is not present on the home PC. New mods were added by writing `mods/<slug>.pw.toml`
  by hand (name, filename, side, `[download]` url + sha512, `[update.modrinth]` mod-id + version) from the
  Modrinth API, then updating `index.toml` and the index hash in `pack.toml`.
- **Line endings matter for hashes.** Git blobs are LF; on Windows (`core.autocrlf=true`) the working tree
  is CRLF. `index.toml` hashes (sha256) and the `pack.toml` index hash are computed over the **LF** content.
  Hashing the CRLF working-tree copy gives mismatches everywhere. Write new manifests with LF.
- `side` mapping used: client unsupported -> `server`, server unsupported -> `client`, else `both`.
  `sync_mods.py` skips `side = "client"`.
- Modrinth "required dependency" metadata is not always complete. Repurposed Structures needs MidnightLib
  >= 1.4.0 without declaring it. **Always start the server and read the log before pushing**, because the
  nightly deploy applies whatever is on `master`.
- The client `mods.zip` is not tracked (`dist/` is gitignored). It is built from the manifests: every
  entry with `side` = `both` or `client`, jars flat at the zip root. Players must clear their `mods` folder
  and extract so the jars sit directly in `.minecraft\mods` (not in a nested folder).
- **Modrinth `side` flags are wrong for some libraries.** `structure-pool-api` is listed server-only, but
  Jewelry (both sides) hard-depends on it, so clients crashed with "Install structure_pool_api". Before
  publishing a client zip, check it offline: read `fabric.mod.json` of every jar (and its nested `jars`),
  collect `id` + `provides`, and verify every `depends` entry (except minecraft/java/fabricloader) is present.
  Fix by setting the library's manifest to `side = "both"`, then refresh `index.toml` + `pack.toml` hashes.
- **Minimum Fabric Loader for clients** = the highest `fabricloader` lower bound among the jars (0.16.9 today,
  from Fabric Language Kotlin). Clients on an older loader (e.g. TLauncher's bundled "Fabric 1.20.1", 0.17.2)
  get "requires version X or later of Fabric Loader". State the required loader in every release note; players
  install it with the official Fabric installer (Client tab, 1.20.1, loader 0.19.5).
- **Decision: JEI, Farmer's Delight and Ranged Weapon API are pinned below their latest release on purpose.**
  Players' TLauncher ships Fabric Loader 0.17.2. Latest JEI needs >= 0.19.4, latest Farmer's Delight (bundled
  Porting Lib) >= 0.18.2, latest Ranged Weapon API (2.x, the version with the `velocity` attribute Jewelry
  wants) >= 0.19.5 — all above the client floor, so Fabric would refuse to start the game for every player.
  Pinned to the newest release still under 0.17.2 instead: JEI 15.49.0.194 (>=0.16.3), Farmer's Delight
  2.5.2 (>=0.16), Ranged Weapon API 1.1.4 (>=0.15.7, but it only registers `damage`/`haste` — no `velocity`,
  so that one Jewelry effect stays dead). Do not re-add a newer version of any of these without checking its
  `fabricloader` floor first. After removing/downgrading a mod, delete the old jar from `mc-server\mods` by
  hand - the deploy's `sync_mods.py` never deletes - and expect harmless "missing from registry / unknown
  attribute" warnings once, from leftover player data.
- **Decision: Visual Jukebox was tried and dropped; Ledger is pinned to 1.2.8, not the "latest".** Both are
  server-only (never shipped to clients), so the 0.17.2 client floor above doesn't apply to them — the
  constraint here is the *server's* Java 17 runtime instead. Visual Jukebox's only Modrinth build for 1.20.1
  (1.0.0) ships a Mixin config that requires Mixin compatibility level JAVA_21, which throws at boot on Java 17
  ("Level is not supported by the active JRE") — there is no older build to fall back to, so it's not in the
  pack at all. Ledger's "latest" 1.20.1 build (1.3.18-backport) is compiled straight to Java 21 bytecode (class
  file version 65) and crashes the server with `UnsupportedClassVersionError` on `net/minecraft/class_2248`
  before a single mod even initializes — pinned to 1.2.8 (2023, Java 17 bytecode, still satisfies its
  `fabric-language-kotlin >= 1.9.4` requirement against what we ship) instead. If bumping the server off Java
  17 ever becomes worthwhile, both are worth revisiting.
- **Publishing the client zip:** as an asset of a GitHub Release on the modpack repo (tag
  `client-YYYY-MM-DD[-n]`, `--target master`), using the GitHub CLI (`gh`, portable zip, log in with
  `gh auth login --web`). Stable link:
  `https://github.com/Ivan-Labudev/tancmeystery-modpack/releases/latest/download/tancmeystery-client-mods.zip`.
  After publishing, download that link anonymously and compare the SHA-256. Delete a broken release together
  with its tag (`gh release delete <tag> --cleanup-tag --yes`) once a fixed one is up.

## Running and checking the server

- Starting via `cmd /c start.bat` in a hidden window did not launch the server once; running
  `Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','start.ps1'
  -WorkingDirectory <mc-server> -WindowStyle Hidden` works. A cold start with the current mod set takes
  well under a minute on the existing world (first world generation took ~80 s).
- Graceful restart: RCON `save-all flush`, `stop`, wait until no `java.exe` with `fabric-server-launch.jar`
  remains, back up (`backup.backup_world`), `python sync_mods.py`, start, wait for `Done (...)!` in
  `logs\latest.log`, then check the log for `ERROR` / "Incompatible mods".
- LuckPerms on Fabric returns **empty strings over RCON** (even for `lp listgroups`), so `setup_luckperms.py`
  printing nothing does not mean failure. Verify with `lp export <name>` and read
  `mods\luckperms\<name>.json.gz`, then delete it.
- `online-mode=false` (players use offline launchers): nicknames are not authenticated, so anyone can join
  under an operator's nickname. Keep that in mind before granting op, and consider an offline-auth mod.
- Simple Voice Chat needs its own UDP tunnel; set `voice_host=<host>:<port>` in
  `config/voicechat/voicechat-server.properties` (config is read at startup - restart after editing).
- Sleep/hibernate must stay disabled on the server PC (`powercfg /change standby-timeout-ac 0`), otherwise
  the server and the tunnel die when Windows sleeps.
