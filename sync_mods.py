"""Sync server-side mod jars from the tancmeystery-modpack packwiz manifest.

The *.pw.toml files in tancmeystery-modpack/mods/ are the single source of
truth for pinned mod versions (shared with the client pack). This script
downloads the jar for every entry that isn't client-only into mods/, and
never overwrites a jar (or a manually-disabled one) that's already present.
"""
import glob
import os
import sys
import tomllib
import urllib.request

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
MODS_DIR = os.path.join(SERVER_DIR, "mods")
MODPACK_MODS_DIR = os.path.join(SERVER_DIR, "..", "tancmeystery-modpack", "mods")


def load_pack_entries(modpack_mods_dir=MODPACK_MODS_DIR):
    entries = []
    for path in sorted(glob.glob(os.path.join(modpack_mods_dir, "*.pw.toml"))):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        if data.get("side", "both") == "client":
            continue
        entries.append({
            "name": data["name"],
            "filename": data["filename"],
            "url": data["download"]["url"],
        })
    return entries


def already_present(filename, mods_dir=MODS_DIR):
    return (
        os.path.exists(os.path.join(mods_dir, filename))
        or os.path.exists(os.path.join(mods_dir, filename + ".disabled"))
    )


def download(url, dest_path):
    req = urllib.request.Request(url, headers={"User-Agent": "tancmeystery-server-sync/1.0"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        out.write(resp.read())


def sync(modpack_mods_dir=MODPACK_MODS_DIR, mods_dir=MODS_DIR, downloader=download):
    os.makedirs(mods_dir, exist_ok=True)
    downloaded, skipped, failed = [], [], []
    for entry in load_pack_entries(modpack_mods_dir):
        filename = entry["filename"]
        if already_present(filename, mods_dir):
            skipped.append(filename)
            continue
        dest = os.path.join(mods_dir, filename)
        try:
            downloader(entry["url"], dest)
            downloaded.append(filename)
        except Exception as e:
            failed.append((filename, str(e)))
    return {"downloaded": downloaded, "skipped": skipped, "failed": failed}


def main():
    result = sync()
    for name in result["downloaded"]:
        print(f"[+] downloaded {name}")
    for name in result["skipped"]:
        print(f"[=] already present: {name}")
    for name, err in result["failed"]:
        print(f"[!] failed {name}: {err}")
    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
