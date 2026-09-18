"""One-shot RCON build of the dance-battle arena (cross platform 3x3 + 4 step tiles).

Direction mapping (DDR-style): north=up, south=down, east=right, west=left,
matching the tancmeystery:check_step_{up,down,right,left} functions.

Built in open sky at ORIGIN so it doesn't depend on terrain height.
Safe to re-run; all commands are idempotent (setblock/fill overwrite).
"""
import sys

from rcon_client import RconClient
from server_config import get_rcon_config

# Center of the 3x3 platform.
ORIGIN = (0, 100, 0)

FLOOR_BLOCK = "minecraft:quartz_block"
PLATE_BLOCK = "minecraft:stone_pressure_plate"

ARMS = {
    "up": (0, -2, "check_step_up"),
    "down": (0, 2, "check_step_down"),
    "right": (2, 0, "check_step_right"),
    "left": (-2, 0, "check_step_left"),
}


def build(rcon):
    cx, cy, cz = ORIGIN

    # Center 3x3 dance floor + support layer below.
    rcon.command(f"fill {cx-1} {cy} {cz-1} {cx+1} {cy} {cz+1} {FLOOR_BLOCK}")
    rcon.command(f"fill {cx-1} {cy-1} {cz-1} {cx+1} {cy-1} {cz+1} minecraft:smooth_quartz")

    for name, (dx, dz, function) in ARMS.items():
        x, z = cx + dx, cz + dz
        rcon.command(f"setblock {x} {cy-1} {z} {FLOOR_BLOCK} replace")
        cmd = f'setblock {x} {cy} {z} minecraft:command_block[facing=up]{{Command:"function tancmeystery:{function}"}} replace'
        rcon.command(cmd)
        rcon.command(f"setblock {x} {cy+1} {z} {PLATE_BLOCK} replace")
        print(f"[+] Built '{name}' step tile at ({x},{cy},{z}) -> {function}")

    rcon.command(f"setworldspawn {cx} {cy+1} {cz}")
    print(f"[+] Arena built at {ORIGIN}, world spawn set nearby.")


if __name__ == "__main__":
    try:
        with RconClient(**get_rcon_config()) as rcon:
            build(rcon)
    except Exception as e:
        print(f"[!] Failed: {e}")
        sys.exit(1)
