"""One-shot RCON build of the dance-battle arena: a circular colosseum with
tiered stone seating, located in a nearby summer forest biome, plus a few
lodging cabins scattered in the woods just outside.

Direction mapping (DDR-style): north=up, south=down, east=right, west=left,
matching the tancmeystery:check_step_{up,down,right,left} functions -- the
step-tile mechanic itself (pressure plate over an impulse command block) is
unchanged from earlier versions of this script, only relocated.

The location is found via RCON `/locatebiome minecraft:forest` rather than
hardcoded, so the arena lands in a green, snow-free biome regardless of what
happens to be at world spawn. Ground level at that spot is then found via
binary search (`execute if block ... air`), and the whole footprint is
leveled before building, since Terralith/WWOO terrain can be uneven even
within a chosen biome patch.

Every RCON call uses a short drain_seconds (this script issues several
hundred commands; the client's default 1s post-response drain would make a
full build take minutes instead of seconds).

Safe to re-run; all commands are idempotent (setblock/fill overwrite).
"""
import math
import re
import sys
import time

from rcon_client import RconClient, RconError
from server_config import get_rcon_config

FOREST_BIOME = "minecraft:plains"  # open field, not woods -- avoids trees/mountains

FLOOR_BLOCK = "minecraft:quartz_block"
PLATE_BLOCK = "minecraft:stone_pressure_plate"

ARM_DISTANCE = 5
ARMS = {
    "up": (0, -ARM_DISTANCE, "check_step_up"),
    "down": (0, ARM_DISTANCE, "check_step_down"),
    "right": (ARM_DISTANCE, 0, "check_step_right"),
    "left": (-ARM_DISTANCE, 0, "check_step_left"),
}

FLOOR_RADIUS = 7    # 15x15 dance floor
TIER1_RADIUS = 11   # first seating step, 2 blocks tall
TIER2_RADIUS = 15   # second seating step, 4 blocks tall
TIER3_RADIUS = 19   # third seating step, 6 blocks tall, wall sits on top of it
WALL_HEIGHT = 6      # outer colosseum wall height above tier 3

CLEAR_RADIUS = 36
CLEAR_HEIGHT = 50
BASE_DEPTH = 8

MAIN_FLOOR = "minecraft:smooth_quartz"
BORDER_RING = "minecraft:purple_concrete"
ACCENT_RING = "minecraft:magenta_concrete"
SEAT_BLOCK = "minecraft:stone_bricks"
SEAT_STAIR = "minecraft:stone_brick_stairs[facing=south]"
WALL_BLOCK = "minecraft:chiseled_stone_bricks"
COLUMN_BLOCK = "minecraft:stone_brick_wall"

CABIN_LOG = "minecraft:spruce_log"
CABIN_PLANKS = "minecraft:spruce_planks"
CABIN_SPOTS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]  # quadrant direction, scaled below


class ResilientRcon:
    """Wraps RconClient and transparently reconnects once on a dropped
    connection -- this script issues hundreds of commands over tens of
    seconds, and the RCON connection has been observed to drop mid-run with
    no apparent cause; a single dropped socket shouldn't abort a build this
    far along."""

    def __init__(self, config):
        self._config = config
        self._client = RconClient(**config)
        self._client.connect()

    def command(self, command_str, drain_seconds=1.0):
        try:
            return self._client.command(command_str, drain_seconds=drain_seconds)
        except (ConnectionError, OSError, EOFError, RconError):
            self._client.close()
            self._client = RconClient(**self._config)
            self._client.connect()
            return self._client.command(command_str, drain_seconds=drain_seconds)

    def close(self):
        self._client.close()


def cmd(rcon, command_str):
    return rcon.command(command_str, drain_seconds=0.1)


def locate_forest(rcon):
    # Unlike setblock/fill, this command searches chunks server-side and can
    # take several seconds -- needs a much longer drain than the fast bulk
    # building commands below.
    resp = rcon.command(f"locate biome {FOREST_BIOME}", drain_seconds=10.0)
    match = re.search(r"\[(-?\d+),\s*(-?\d+),\s*(-?\d+)\]", resp)
    if not match:
        raise RuntimeError(f"could not parse locate biome response: {resp!r}")
    return int(match.group(1)), int(match.group(3))


def find_surface_y(rcon, x, z, y_min=-64, y_max=320):
    lo, hi = y_min, y_max
    while lo < hi:
        mid = (lo + hi + 1) // 2
        resp = cmd(rcon, f"execute if block {x} {mid} {z} minecraft:air run seed")
        if resp.strip():
            hi = mid - 1
        else:
            lo = mid
    return lo


def force_load(rcon, cx, cz, radius, add=True):
    """/locate can point at chunks that were never generated/loaded; probing
    `execute if block` there returns a "not loaded" error, which our
    substring check misreads as "is air", collapsing the whole binary search
    to bedrock. Force-loading (and giving the server a moment to actually
    generate the terrain) before probing avoids that."""
    action = "add" if add else "remove"
    cmd(rcon, f"forceload {action} {cx-radius} {cz-radius} {cx+radius} {cz+radius}")
    if add:
        time.sleep(8)  # give worldgen (4 stacked terrain mods) time to finish the chunks


def fill_box_chunked(rcon, x1, y1, z1, x2, y2, z2, block):
    """fill, but split into Y-slabs to stay under vanilla's ~32768-block
    per-command limit for large volumes."""
    area = (x2 - x1 + 1) * (z2 - z1 + 1)
    max_layers = max(1, 30000 // area)
    y = y1
    while y <= y2:
        y_end = min(y + max_layers - 1, y2)
        cmd(rcon, f"fill {x1} {y} {z1} {x2} {y_end} {z2} {block}")
        y = y_end + 1


def repair_previous_attempt(rcon, cx, cy, cz):
    """Backfill a prior failed build attempt (e.g. one that landed at
    bedrock due to the unloaded-chunk bug above) before building for real."""
    if cy <= -64:
        return
    fill_box_chunked(
        rcon, cx - CLEAR_RADIUS, -64, cz - CLEAR_RADIUS,
        cx + CLEAR_RADIUS, cy - 1, cz + CLEAR_RADIUS, "minecraft:stone",
    )
    print("[+] Repaired previous failed build attempt (backfilled with stone)")


def fill_square(rcon, cx, cy, cz, radius, block):
    cmd(rcon, f"fill {cx-radius} {cy} {cz-radius} {cx+radius} {cy} {cz+radius} {block}")


def fill_square_ring(rcon, cx, cy, cz, radius, block):
    cmd(rcon, f"fill {cx-radius} {cy} {cz-radius} {cx+radius} {cy} {cz-radius} {block}")
    cmd(rcon, f"fill {cx-radius} {cy} {cz+radius} {cx+radius} {cy} {cz+radius} {block}")
    cmd(rcon, f"fill {cx-radius} {cy} {cz-radius+1} {cx-radius} {cy} {cz+radius-1} {block}")
    cmd(rcon, f"fill {cx+radius} {cy} {cz-radius+1} {cx+radius} {cy} {cz+radius-1} {block}")


def fill_annulus_3d(rcon, cx, y_low, y_high, cz, r_inner, r_outer, block):
    """Fill a circular ring (annulus) between two radii, from y_low to y_high,
    approximated with one or two /fill boxes per Z row."""
    for dz in range(-r_outer, r_outer + 1):
        outer_span = math.floor(math.sqrt(max(r_outer * r_outer - dz * dz, 0)))
        if abs(dz) <= r_inner:
            inner_span = math.floor(math.sqrt(max(r_inner * r_inner - dz * dz, 0)))
            if inner_span < outer_span:
                cmd(rcon, f"fill {cx-outer_span} {y_low} {cz+dz} {cx-inner_span-1} {y_high} {cz+dz} {block}")
                cmd(rcon, f"fill {cx+inner_span+1} {y_low} {cz+dz} {cx+outer_span} {y_high} {cz+dz} {block}")
        else:
            cmd(rcon, f"fill {cx-outer_span} {y_low} {cz+dz} {cx+outer_span} {y_high} {cz+dz} {block}")


def ring_outline_3d(rcon, cx, y_low, y_high, cz, radius, block, thickness=1):
    fill_annulus_3d(rcon, cx, y_low, y_high, cz, radius - thickness, radius, block)


def level_terrain(rcon, cx, cy, cz):
    # Plain /fill errors out silently past ~32768 blocks -- this footprint is
    # far bigger than that, so it must be split into vertical slabs.
    fill_box_chunked(
        rcon, cx - CLEAR_RADIUS, cy + 1, cz - CLEAR_RADIUS,
        cx + CLEAR_RADIUS, cy + CLEAR_HEIGHT, cz + CLEAR_RADIUS, "minecraft:air",
    )
    fill_box_chunked(
        rcon, cx - CLEAR_RADIUS, cy - BASE_DEPTH, cz - CLEAR_RADIUS,
        cx + CLEAR_RADIUS, cy - 1, cz + CLEAR_RADIUS, "minecraft:stone",
    )
    # A flat grass surface across the whole cleared footprint at y=cy, so
    # nothing outside the colosseum/cabins is bare stone or leftover terrain.
    fill_box_chunked(
        rcon, cx - CLEAR_RADIUS, cy, cz - CLEAR_RADIUS,
        cx + CLEAR_RADIUS, cy, cz + CLEAR_RADIUS, "minecraft:grass_block",
    )
    print(f"[+] Leveled a {2*CLEAR_RADIUS+1}x{2*CLEAR_RADIUS+1} open field at y={cy}")


def build_floor(rcon, cx, cy, cz):
    fill_square(rcon, cx, cy, cz, FLOOR_RADIUS, MAIN_FLOOR)
    fill_square_ring(rcon, cx, cy, cz, FLOOR_RADIUS, BORDER_RING)
    fill_square_ring(rcon, cx, cy, cz, FLOOR_RADIUS - 1, ACCENT_RING)
    # Functional 3x3 dance core, unchanged from earlier versions.
    cmd(rcon, f"fill {cx-1} {cy} {cz-1} {cx+1} {cy} {cz+1} {FLOOR_BLOCK}")
    cmd(rcon, f"fill {cx-1} {cy-1} {cz-1} {cx+1} {cy-1} {cz+1} minecraft:smooth_quartz")
    print(f"[+] Built {2*FLOOR_RADIUS+1}x{2*FLOOR_RADIUS+1} floor with border/accent rings")


def build_arms(rcon, cx, cy, cz):
    for name, (dx, dz, function) in ARMS.items():
        x, z = cx + dx, cz + dz
        cmd(rcon, f"setblock {x} {cy-1} {z} minecraft:smooth_quartz replace")
        c = f'setblock {x} {cy} {z} minecraft:command_block[facing=up]{{Command:"function tancmeystery:{function}"}} replace'
        cmd(rcon, c)
        cmd(rcon, f"setblock {x} {cy+1} {z} {PLATE_BLOCK} replace")
        print(f"[+] Built '{name}' step tile at ({x},{cy},{z}) -> {function}, distance {ARM_DISTANCE}")


def carve_entrances(rcon, cx, cy, cz):
    w = 1  # half-width; opening is 2*w+1 = 3 blocks wide
    top = cy + 6
    cmd(rcon, f"fill {cx-w} {cy+1} {cz-TIER3_RADIUS} {cx+w} {top} {cz-FLOOR_RADIUS-1} minecraft:air")
    cmd(rcon, f"fill {cx-w} {cy+1} {cz+FLOOR_RADIUS+1} {cx+w} {top} {cz+TIER3_RADIUS} minecraft:air")
    cmd(rcon, f"fill {cx+FLOOR_RADIUS+1} {cy+1} {cz-w} {cx+TIER3_RADIUS} {top} {cz+w} minecraft:air")
    cmd(rcon, f"fill {cx-TIER3_RADIUS} {cy+1} {cz-w} {cx-FLOOR_RADIUS-1} {top} {cz+w} minecraft:air")
    print("[+] Carved 4 entrances (N/S/E/W)")


def build_columns(rcon, cx, cy, cz):
    n = 12
    for i in range(n):
        angle = 2 * math.pi * i / n
        px = cx + round(TIER3_RADIUS * math.cos(angle))
        pz = cz + round(TIER3_RADIUS * math.sin(angle))
        cmd(rcon, f"fill {px} {cy+7} {pz} {px} {cy+6+WALL_HEIGHT+2} {pz} {COLUMN_BLOCK}")
        cmd(rcon, f"setblock {px} {cy+7+WALL_HEIGHT+2} {pz} minecraft:lantern replace")
    print(f"[+] Built {n} lit columns around the wall")


def decorate_tiers(rcon, cx, cy, cz):
    """Extra torches and banners across the tiers, beyond the column lanterns."""
    n = 16
    banners = ["minecraft:purple_banner", "minecraft:magenta_banner", "minecraft:light_blue_banner"]
    for i in range(n):
        angle = 2 * math.pi * i / n
        tx = cx + round(TIER1_RADIUS * math.cos(angle))
        tz = cz + round(TIER1_RADIUS * math.sin(angle))
        cmd(rcon, f"setblock {tx} {cy+3} {tz} minecraft:torch replace")
        if i % 2 == 0:
            bx = cx + round(TIER2_RADIUS * math.cos(angle))
            bz = cz + round(TIER2_RADIUS * math.sin(angle))
            banner = banners[i % len(banners)]
            cmd(rcon, f"setblock {bx} {cy+6} {bz} {banner} replace")
    print(f"[+] Placed {n} torches on tier 1 and {n//2} banners on tier 2")


def build_colosseum(rcon, cx, cy, cz):
    fill_annulus_3d(rcon, cx, cy + 1, cy + 2, cz, FLOOR_RADIUS, TIER1_RADIUS, SEAT_BLOCK)
    ring_outline_3d(rcon, cx, cy + 3, cy + 3, cz, TIER1_RADIUS, SEAT_STAIR, thickness=1)

    fill_annulus_3d(rcon, cx, cy + 1, cy + 4, cz, TIER1_RADIUS, TIER2_RADIUS, SEAT_BLOCK)
    ring_outline_3d(rcon, cx, cy + 5, cy + 5, cz, TIER2_RADIUS, SEAT_STAIR, thickness=1)

    fill_annulus_3d(rcon, cx, cy + 1, cy + 6, cz, TIER2_RADIUS, TIER3_RADIUS, SEAT_BLOCK)

    ring_outline_3d(rcon, cx, cy + 7, cy + 6 + WALL_HEIGHT, cz, TIER3_RADIUS, WALL_BLOCK, thickness=2)

    carve_entrances(rcon, cx, cy, cz)
    build_columns(rcon, cx, cy, cz)
    decorate_tiers(rcon, cx, cy, cz)

    jx, jz = cx, cz + FLOOR_RADIUS + 2
    cmd(rcon, f"setblock {jx} {cy} {jz} minecraft:smooth_quartz replace")
    cmd(rcon, f"setblock {jx} {cy+1} {jz} minecraft:jukebox replace")
    print(f"[+] Colosseum built: 3 tiers to radius {TIER3_RADIUS}, wall height {WALL_HEIGHT}")


def build_lodging_cabins(rcon, cx, cy, cz):
    ring = TIER3_RADIUS + 14
    for i, (sx, sz) in enumerate(CABIN_SPOTS):
        x, z = cx + sx * ring, cz + sz * ring
        # Bound the search near the plaza's own elevation -- WWOO/Terralith
        # terrain can hide caves a short distance out, and an unbounded
        # search can converge on a cave floor instead of the true surface.
        y = find_surface_y(rcon, x, z, y_min=cy - 20, y_max=cy + 40)
        cmd(rcon, f"fill {x-3} {y+1} {z-3} {x+3} {y+8} {z+3} minecraft:air")
        cmd(rcon, f"fill {x-3} {y-2} {z-3} {x+3} {y} {z+3} minecraft:grass_block")
        cmd(rcon, f"fill {x-2} {y+1} {z-2} {x+2} {y+1} {z+2} {CABIN_PLANKS}")
        cmd(rcon, f"fill {x-2} {y+2} {z-2} {x+2} {y+4} {z+2} {CABIN_LOG} hollow")
        cmd(rcon, f"fill {x-1} {y+2} {z-2} {x+1} {y+3} {z-2} minecraft:air")  # doorway
        cmd(rcon, f"setblock {x-2} {y+3} {z} minecraft:glass_pane replace")
        cmd(rcon, f"setblock {x+2} {y+3} {z} minecraft:glass_pane replace")
        cmd(rcon, f"fill {x-3} {y+5} {z-3} {x+3} {y+5} {z+3} {CABIN_PLANKS}")
        cmd(rcon, f"setblock {x-1} {y+2} {z} minecraft:red_bed[facing=east,part=foot] replace")
        cmd(rcon, f"setblock {x} {y+2} {z} minecraft:red_bed[facing=east,part=head] replace")
        cmd(rcon, f"setblock {x-2} {y+3} {z-1} minecraft:torch replace")
        print(f"[+] Cabin {i+1} built at ({x},{y},{z})")


def build(rcon):
    fx, fz = locate_forest(rcon)
    print(f"[+] Located forest biome at ({fx}, {fz})")
    cx, cz = fx, fz

    cy = None
    for attempt in range(3):
        force_load(rcon, cx, cz, CLEAR_RADIUS + 16)
        cy = find_surface_y(rcon, fx, fz)
        print(f"[+] Detected ground level at y={cy} for ({cx},{cz}) (attempt {attempt+1})")
        if -60 < cy < 300:
            break
        print("[!] Suspicious height (chunk likely still generating), retrying...")
        time.sleep(5)
    else:
        raise RuntimeError(
            f"surface detection kept returning y={cy} after 3 attempts -- "
            "refusing to build; investigate before re-running"
        )

    repair_previous_attempt(rcon, cx, cy, cz)
    level_terrain(rcon, cx, cy, cz)
    build_floor(rcon, cx, cy, cz)
    build_arms(rcon, cx, cy, cz)
    build_colosseum(rcon, cx, cy, cz)
    build_lodging_cabins(rcon, cx, cy, cz)

    # Just outside the south entrance, not inside the colosseum itself.
    # level_terrain() clears above/below this point but leaves the original
    # y=cy layer untouched, which can be water (plains biomes have ponds) --
    # force dry solid ground under the actual spawn point.
    spawn_x, spawn_z = cx, cz + TIER3_RADIUS + 2
    cmd(rcon, f"fill {spawn_x-2} {cy} {spawn_z-2} {spawn_x+2} {cy} {spawn_z+2} minecraft:grass_block")
    cmd(rcon, f"fill {spawn_x-2} {cy+1} {spawn_z-2} {spawn_x+2} {cy+2} {spawn_z+2} minecraft:air")
    cmd(rcon, f"setworldspawn {spawn_x} {cy+1} {spawn_z}")
    print(f"[+] Arena built at ({cx},{cy},{cz}), world spawn set nearby at ({spawn_x},{cy+1},{spawn_z}).")

    force_load(rcon, cx, cz, CLEAR_RADIUS + 16, add=False)


if __name__ == "__main__":
    rcon = ResilientRcon(get_rcon_config())
    try:
        build(rcon)
    except Exception as e:
        print(f"[!] Failed: {e}")
        sys.exit(1)
    finally:
        rcon.close()
