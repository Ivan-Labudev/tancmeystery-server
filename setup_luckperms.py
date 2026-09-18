"""One-time LuckPerms group/rank setup via RCON for the Tancmeystery server.

NOTE: the spec references a permissions table "from a previous discussion"
that wasn't available here. Sensible defaults are used below (waystone
cooldown bypass for master+, small thematic perks for the student
sub-tracks). Adjust PERMISSIONS as needed and re-run — `lp` commands are
idempotent.
"""
import sys
import time

from rcon_client import RconClient
from server_config import get_rcon_config

GROUPS = [
    "novice", "student", "master", "legend",
    "moderator", "admin",
    "waltz", "break", "techno",
]

# child -> parent
PARENTS = {
    "novice": "default",
    "student": "novice",
    "master": "student",
    "legend": "master",
    "admin": "moderator",
    "waltz": "student",
    "break": "student",
    "techno": "student",
}

# group -> list of permission nodes
PERMISSIONS = {
    "student": ["dance.join"],
    "master": ["waystone.nocooldown"],
    "legend": ["waystone.nocooldown", "trinkets.extraslot"],
    "waltz": ["effect.precision"],
    "break": ["effect.speed"],
    "techno": ["effect.haste"],
    "moderator": ["luckperms.user.info", "essential.kick"],
    "admin": ["luckperms.*"],
}


def run():
    with RconClient(**get_rcon_config()) as rcon:
        for group in GROUPS:
            print(rcon.command(f"lp creategroup {group}"))
            time.sleep(0.4)

        for child, parent in PARENTS.items():
            print(rcon.command(f"lp group {child} parent add {parent}"))
            time.sleep(0.4)

        for group, perms in PERMISSIONS.items():
            for perm in perms:
                print(rcon.command(f"lp group {group} permission set {perm} true"))
                time.sleep(0.4)

        time.sleep(1.5)
        print("--- listgroups ---")
        print(rcon.command("lp listgroups"))
        print("LuckPerms structure applied.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"[!] Failed: {e}")
        sys.exit(1)
