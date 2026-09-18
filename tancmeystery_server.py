"""Tancmeystery server automation — run hourly via Windows Task Scheduler.

Does three things each run:
1. Backs up the world folder to a rotated tar.gz (keeps last 7).
2. Converts each tracked player's `dance_wins` scoreboard delta into
   `dance_coins` (1 win = 10 coins), then zeroes `dance_wins`.
3. Promotes players through the LuckPerms rank chain
   (novice -> student -> master -> legend) once their dance_coins
   cross the configured thresholds.
"""
import datetime
import glob
import os
import re
import sys
import tarfile

from rcon_client import RconClient
from server_config import get_rcon_config

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
WORLD_DIR = os.path.join(SERVER_DIR, "world")
BACKUP_DIR = os.path.join(SERVER_DIR, "backups")
BACKUP_KEEP = 7

COINS_PER_WIN = 10

# dance_coins threshold -> LuckPerms group. Checked from highest to lowest.
PROMOTION_THRESHOLDS = [
    (1000, "legend"),
    (500, "master"),
    (100, "student"),
]

TRACKED_RE = re.compile(r"There are \d+ tracked entit(?:y|ies): (.*)")
SCORE_RE = re.compile(r"has (-?\d+)")


def log(msg):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}")


def backup_world():
    if not os.path.isdir(WORLD_DIR):
        log("world/ not found yet, skipping backup")
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"world_{stamp}.tar.gz")

    def skip_locked(tarinfo):
        if tarinfo.name.endswith("session.lock"):
            return None
        return tarinfo

    with tarfile.open(dest, "w:gz") as tar:
        tar.add(WORLD_DIR, arcname="world", filter=skip_locked)
    log(f"Backup created: {dest}")

    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "world_*.tar.gz")))
    while len(backups) > BACKUP_KEEP:
        oldest = backups.pop(0)
        os.remove(oldest)
        log(f"Rotated out old backup: {oldest}")


def get_tracked_players(rcon):
    resp = rcon.command("scoreboard players list")
    match = TRACKED_RE.search(resp)
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",") if name.strip()]


def get_score(rcon, player, objective):
    resp = rcon.command(f"scoreboard players get {player} {objective}")
    match = SCORE_RE.search(resp)
    return int(match.group(1)) if match else 0


def sync_dance_coins(rcon):
    players = get_tracked_players(rcon)
    for player in players:
        wins = get_score(rcon, player, "dance_wins")
        if wins <= 0:
            continue
        coins_earned = wins * COINS_PER_WIN
        rcon.command(f"scoreboard players add {player} dance_coins {coins_earned}")
        rcon.command(f"scoreboard players set {player} dance_wins 0")
        log(f"{player}: +{coins_earned} dance_coins ({wins} wins)")


def apply_promotions(rcon):
    players = get_tracked_players(rcon)
    for player in players:
        coins = get_score(rcon, player, "dance_coins")
        for threshold, group in PROMOTION_THRESHOLDS:
            if coins >= threshold:
                resp = rcon.command(f"lp user {player} parent add {group}")
                if "already" not in resp.lower():
                    log(f"{player}: promoted to '{group}' ({coins} dance_coins)")
                break


def main():
    backup_world()
    try:
        with RconClient(**get_rcon_config()) as rcon:
            sync_dance_coins(rcon)
            apply_promotions(rcon)
    except (ConnectionRefusedError, OSError) as e:
        log(f"RCON unavailable, skipping coin/rank sync: {e}")


if __name__ == "__main__":
    main()
    sys.exit(0)
