"""Nightly deploy orchestration, run by run_deploy.ps1 after `git pull` brings changes.

Sequence: backup world -> warn players (RCON say, 15/10/5/1 min) -> graceful
RCON stop (force-kill on timeout) -> sync mod jars from the packwiz manifest
-> restart via start.ps1 -> verify the server answers RCON again. Every step
logs to logs/deploy.log so the owner can check what happened without having
to watch it live.
"""
import datetime
import os
import subprocess
import sys
import time
import traceback

from backup import backup_world
from rcon_client import RconClient, RconError
from server_config import get_rcon_config
import sync_mods

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
WORLD_DIR = os.path.join(SERVER_DIR, "world")
BACKUP_DIR = os.path.join(SERVER_DIR, "backups")
LOG_PATH = os.path.join(SERVER_DIR, "logs", "deploy.log")
START_PS1 = os.path.join(SERVER_DIR, "start.ps1")

WARNING_SCHEDULE = [15, 10, 5, 1]  # minutes before restart


def make_logger(log_path=LOG_PATH):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(msg):
        line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    return log


def _minute_word(n):
    if n == 1:
        return "минуту"
    if 2 <= n <= 4:
        return "минуты"
    return "минут"


def warning_message(minutes):
    return f"§eСервер уйдёт на перезапуск для обновления через {minutes} {_minute_word(minutes)}. Сохраните прогресс!"


def broadcast_warnings(rcon, schedule=WARNING_SCHEDULE, sleep=time.sleep, log=print):
    for i, minutes in enumerate(schedule):
        rcon.command(f"say {warning_message(minutes)}")
        log(f"Warned players: {minutes} min until restart")
        next_minutes = schedule[i + 1] if i + 1 < len(schedule) else 0
        sleep((minutes - next_minutes) * 60)


def find_server_pids():
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "(Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
            "Where-Object { $_.CommandLine -like '*fabric-server-launch.jar*' }).ProcessId",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return parse_pids(result.stdout)


def parse_pids(output):
    return [int(line.strip()) for line in output.splitlines() if line.strip().isdigit()]


def pid_alive(pid):
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue) -ne $null"],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip().lower() == "true"


def kill_pid(pid):
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
        capture_output=True, text=True, timeout=15,
    )


def stop_server(rcon, timeout=60, poll_interval=2, sleep=time.sleep, log=print,
                 find_pids=find_server_pids, is_alive=pid_alive, kill=kill_pid):
    pids = find_pids()
    try:
        rcon.command("stop")
    except (RconError, ConnectionError):
        # Minecraft closes the RCON socket while it shuts down, so reading the reply
        # to "stop" fails with "Connection closed" even though the stop was accepted.
        # The process-exit wait below is the real check, not this reply.
        log("RCON connection closed during stop (expected while the server shuts down)")
    log("Sent RCON stop, waiting for process to exit")

    if not pids:
        log("Could not identify any server process to watch (find_pids returned none) - "
            "cannot confirm the old server actually stopped")
        return None

    waited = 0
    while waited < timeout:
        if not any(is_alive(pid) for pid in pids):
            log("Server process exited cleanly")
            return True
        sleep(poll_interval)
        waited += poll_interval

    log(f"Server did not exit within {timeout}s, force-killing")
    for pid in pids:
        if is_alive(pid):
            kill(pid)
    return False


def sync_mods_step(log=print, syncer=sync_mods.sync):
    result = syncer()
    for name in result["downloaded"]:
        log(f"[mods] downloaded {name}")
    for name in result["skipped"]:
        log(f"[mods] already present: {name}")
    for name, err in result["failed"]:
        log(f"[mods] FAILED {name}: {err}")
    return len(result["failed"]) == 0


def start_server(server_dir=SERVER_DIR, start_ps1=START_PS1):
    subprocess.Popen([
        "powershell", "-NoProfile", "-Command",
        f"Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{start_ps1}' "
        f"-WorkingDirectory '{server_dir}' -WindowStyle Hidden",
    ])


def verify_online(rcon_config, timeout=300, poll_interval=5, sleep=time.sleep, log=print,
                   rcon_factory=RconClient):
    waited = 0
    while waited < timeout:
        try:
            with rcon_factory(**rcon_config) as rcon:
                rcon.command("list")
            log("Server responded to RCON, deploy verified online")
            return True
        except (ConnectionRefusedError, OSError, RconError):
            sleep(poll_interval)
            waited += poll_interval
    log(f"Server did not respond to RCON within {timeout}s after restart")
    return False


def main():
    log = make_logger()

    try:
        rcon_config = get_rcon_config()
    except (FileNotFoundError, KeyError) as e:
        log(f"Could not read RCON config from server.properties, aborting deploy: {e}")
        sys.exit(1)

    try:
        backup_world(WORLD_DIR, BACKUP_DIR, prefix="predeploy", keep=3, log=log)
    except Exception as e:
        log(f"World backup failed, aborting deploy before touching the running server: {e}")
        sys.exit(1)

    try:
        with RconClient(**rcon_config) as rcon:
            broadcast_warnings(rcon, log=log)
            stopped = stop_server(rcon, log=log)
    except (ConnectionRefusedError, OSError, RconError) as e:
        log(f"Could not reach RCON to warn/stop server, aborting deploy: {e}")
        sys.exit(1)

    if stopped is None:
        log("Could not confirm the old server process stopped; aborting deploy before "
            "restart to avoid running two servers at once. Check manually.")
        sys.exit(1)

    if not sync_mods_step(log=log):
        log("Mod sync had failures; starting server with existing mods")

    start_server()

    if verify_online(rcon_config, log=log):
        log("Deploy finished successfully")
    else:
        log("Deploy finished but server did not come back online - check manually")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"UNHANDLED EXCEPTION:\n{traceback.format_exc()}\n"
            )
        raise
