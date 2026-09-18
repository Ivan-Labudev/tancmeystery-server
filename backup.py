"""Shared world backup/rotation logic, used by tancmeystery_server.py and deploy.py."""
import datetime
import glob
import os
import tarfile

BACKUP_KEEP = 7


def backup_world(world_dir, backup_dir, keep=BACKUP_KEEP, log=print, prefix="world"):
    if not os.path.isdir(world_dir):
        log("world/ not found yet, skipping backup")
        return None

    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"{prefix}_{stamp}.tar.gz")

    def skip_locked(tarinfo):
        if tarinfo.name.endswith("session.lock"):
            return None
        return tarinfo

    with tarfile.open(dest, "w:gz") as tar:
        tar.add(world_dir, arcname="world", filter=skip_locked)
    log(f"Backup created: {dest}")

    backups = sorted(glob.glob(os.path.join(backup_dir, f"{prefix}_*.tar.gz")))
    while len(backups) > keep:
        oldest = backups.pop(0)
        os.remove(oldest)
        log(f"Rotated out old backup: {oldest}")

    return dest
