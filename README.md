# tancmeystery-server

Fabric 1.20.1 server for "Танцмейстеры". See `../Документы/Майнкрафт/CLAUDE.md` (on the
machine where that folder exists) for full background on the project and its scripts.

## First-time setup on a new machine

1. `git clone` this repo and `tancmeystery-modpack` as siblings (same parent folder).
2. Copy `server.properties.template` to `server.properties` and set a real `rcon.password`.
3. Run `python sync_mods.py` to download the pinned mod jars into `mods/`.
4. Run `start.bat` (or `start.ps1`) once to generate the world and accept the EULA.

## Deploy pipeline (home PC only)

- `run_deploy.ps1` runs nightly at 05:00 (local time zone — must be Moscow time) via Task
  Scheduler: pulls this repo and `tancmeystery-modpack`, and if either changed, runs `deploy.py`.
- `deploy.py` backs up the world, warns players in-game (15/10/5/1 minutes), stops the server
  gracefully over RCON, re-syncs mod jars, restarts, and verifies it came back online. Every run
  is logged to `logs/deploy.log`.
- `ensure_server_running.ps1` runs at system startup and starts the server if it isn't already
  running (power-outage recovery).
- `setup_scheduled_tasks.ps1` registers both Task Scheduler entries — run once, as Administrator,
  after first-time setup above.

## Mod versions

The single source of truth for mod versions is `tancmeystery-modpack/mods/*.pw.toml`. To bump a
mod: update the relevant `.pw.toml` (e.g. via `packwiz.exe modrinth add --project-id <id>
--version-id <id>`), commit and push both repos. The next nightly deploy (or a manual `python
sync_mods.py`) picks it up on the server. The client `mods.zip` for players is rebuilt and
handed out separately — there's no client auto-update (players are on TLauncher, not a
packwiz-aware launcher).
