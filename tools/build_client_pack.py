"""Build the client mods.zip from the packwiz manifests in ../tancmeystery-modpack.

Includes every manifest whose side is `both` or `client` (server-only mods are skipped), writes the jars flat at
the zip root, and verifies each download against the sha512 pinned in the manifest. Jars already downloaded for
the server (mc-server/mods) are reused when their hash matches.

The finished zip is run through tools/check_client_deps.py first; it is only moved to its final path if every
dependency is satisfied and the players' Fabric Loader is new enough for the whole set (nested modules included).

Usage:  python tools/build_client_pack.py [--out PATH] [--player-loader 0.17.2]
Default output: ~/Downloads/tancmeystery-client-mods.zip
"""
import argparse
import glob
import os
import shutil
import sys
import tempfile
import tomllib
import zipfile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, SERVER_DIR)   # sync_mods (download / hash / filename safety helpers)
sys.path.insert(0, TOOLS_DIR)    # check_client_deps

import sync_mods as sm  # noqa: E402
from check_client_deps import check, fmt, parse_version  # noqa: E402

MANIFEST_DIR = os.path.join(SERVER_DIR, "..", "tancmeystery-modpack", "mods")
SERVER_MODS_DIR = os.path.join(SERVER_DIR, "mods")
DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "tancmeystery-client-mods.zip")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--player-loader", default="0.17.2",
                    help="oldest Fabric Loader players run (default: 0.17.2)")
    args = ap.parse_args()
    player_loader = parse_version(args.player_loader)

    entries, failed = [], []
    for path in sorted(glob.glob(os.path.join(MANIFEST_DIR, "*.pw.toml"))):
        with open(path, "rb") as f:
            d = tomllib.load(f)
        side = d.get("side", "both")
        if side == "server":
            continue
        dl = d["download"]
        entries.append((side, d["filename"], dl["url"], dl["hash"], dl.get("hash-format", "sha512")))

    with tempfile.TemporaryDirectory() as stage:
        built = []
        for side, filename, url, expected, fmt_ in entries:
            if not sm.is_safe_filename(filename) or not sm.has_allowed_scheme(url):
                failed.append((filename, "unsafe manifest entry"))
                continue
            dest = os.path.join(stage, filename)
            server_copy = os.path.join(SERVER_MODS_DIR, filename)
            if os.path.exists(server_copy) and sm.verify_hash(server_copy, expected, fmt_):
                shutil.copyfile(server_copy, dest)
            else:
                try:
                    sm.download(url, dest)
                except Exception as e:  # noqa: BLE001
                    failed.append((filename, str(e)))
                    continue
                if not sm.verify_hash(dest, expected, fmt_):
                    os.remove(dest)
                    failed.append((filename, "hash mismatch"))
                    continue
            built.append((side, filename, dest))

        if failed:
            for name, err in failed:
                print(f"[!] {name}: {err}")
            sys.exit(1)

        out_dir = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(out_dir, exist_ok=True)
        tmp_zip = os.path.join(out_dir, ".building-" + os.path.basename(args.out))
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for _side, filename, dest in built:
                z.write(dest, arcname=filename)  # flat: jars at the zip root

        for side, filename, _ in built:
            print(f"{side:7} {filename}")
        print()
        ok, report = check(tmp_zip, player_loader)
        print("\n".join(report))
        if not ok:
            os.remove(tmp_zip)
            print(f"\nNOT WRITTEN: {args.out} (fix the problems above; players' loader = {fmt(player_loader)})")
            sys.exit(1)
        os.replace(tmp_zip, args.out)
        print(f"\n{len(built)} jars -> {args.out} ({os.path.getsize(args.out) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
