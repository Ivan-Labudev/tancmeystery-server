"""Sync server-side mod jars from the tancmeystery-modpack packwiz manifest.

The *.pw.toml files in tancmeystery-modpack/mods/ are the single source of
truth for pinned mod versions (shared with the client pack). This script
downloads the jar for every entry that isn't client-only into mods/, and
never overwrites a jar (or a manually-disabled one) that's already present.

Every download is verified against the sha512 hash pinned in the manifest
before it's kept, and only http(s) URLs / plain filenames (no path
separators) from the manifest are ever trusted -- the manifest lives in a
sibling repo and this script writes into a live server's mods directory
unattended, so a corrupted or malicious entry must fail closed, not write
anywhere, and a single malformed manifest file must not stop every other
mod from syncing.
"""
import glob
import hashlib
import os
import sys
import tomllib
import urllib.parse
import urllib.request

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
MODS_DIR = os.path.join(SERVER_DIR, "mods")
MODPACK_MODS_DIR = os.path.join(SERVER_DIR, "..", "tancmeystery-modpack", "mods")

ALLOWED_URL_SCHEMES = ("http", "https")
SUPPORTED_HASH_FORMATS = ("sha512",)


def load_pack_entries(modpack_mods_dir=MODPACK_MODS_DIR):
    """Returns (entries, errors). errors is a list of (manifest_filename, reason)
    for any *.pw.toml that couldn't be parsed into a usable entry, so one bad
    file never prevents the rest of the manifest from loading."""
    entries = []
    errors = []
    for path in sorted(glob.glob(os.path.join(modpack_mods_dir, "*.pw.toml"))):
        manifest_filename = os.path.basename(path)
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            if data.get("side", "both") == "client":
                continue
            download = data["download"]
            entries.append({
                "name": data["name"],
                "filename": data["filename"],
                "url": download["url"],
                "hash": download["hash"],
                "hash_format": download.get("hash-format", "sha512"),
            })
        except tomllib.TOMLDecodeError as e:
            errors.append((manifest_filename, f"invalid TOML: {e}"))
        except KeyError as e:
            errors.append((manifest_filename, f"missing required key: {e}"))
    return entries, errors


def already_present(filename, mods_dir=MODS_DIR):
    return (
        os.path.exists(os.path.join(mods_dir, filename))
        or os.path.exists(os.path.join(mods_dir, filename + ".disabled"))
    )


def is_safe_filename(filename):
    return (
        filename not in ("", ".", "..")
        and os.path.basename(filename) == filename
    )


def has_allowed_scheme(url):
    return urllib.parse.urlsplit(url).scheme in ALLOWED_URL_SCHEMES


def download(url, dest_path):
    tmp_path = dest_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "tancmeystery-server-sync/1.0"})
    try:
        with urllib.request.urlopen(req) as resp, open(tmp_path, "wb") as out:
            out.write(resp.read())
        os.replace(tmp_path, dest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def verify_hash(path, expected_hash, hash_format="sha512"):
    if hash_format not in SUPPORTED_HASH_FORMATS:
        return False
    digest = hashlib.new(hash_format)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected_hash


def sync(modpack_mods_dir=MODPACK_MODS_DIR, mods_dir=MODS_DIR, downloader=download):
    os.makedirs(mods_dir, exist_ok=True)
    downloaded, skipped, failed = [], [], []

    entries, load_errors = load_pack_entries(modpack_mods_dir)
    failed.extend(load_errors)

    for entry in entries:
        filename = entry["filename"]

        if not is_safe_filename(filename):
            failed.append((filename, "unsafe filename (path traversal risk)"))
            continue

        if already_present(filename, mods_dir):
            skipped.append(filename)
            continue

        if not has_allowed_scheme(entry["url"]):
            failed.append((filename, f"disallowed URL scheme: {entry['url']}"))
            continue

        dest = os.path.join(mods_dir, filename)
        try:
            downloader(entry["url"], dest)
        except Exception as e:
            failed.append((filename, str(e)))
            continue

        if not verify_hash(dest, entry["hash"], entry["hash_format"]):
            os.remove(dest)
            failed.append((filename, "downloaded file hash does not match manifest"))
            continue

        downloaded.append(filename)

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
