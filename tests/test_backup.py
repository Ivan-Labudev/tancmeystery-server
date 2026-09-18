import glob
import os
import shutil
import tempfile
import unittest

import backup


class BackupWorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.world_dir = os.path.join(self.tmp, "world")
        self.backup_dir = os.path.join(self.tmp, "backups")
        os.makedirs(self.world_dir)
        with open(os.path.join(self.world_dir, "level.dat"), "w") as f:
            f.write("fake level data")
        self.logs = []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def log(self, msg):
        self.logs.append(msg)

    def test_returns_none_when_world_missing(self):
        missing = os.path.join(self.tmp, "does-not-exist")
        result = backup.backup_world(missing, self.backup_dir, log=self.log)
        self.assertIsNone(result)
        self.assertTrue(any("not found" in m for m in self.logs))

    def test_creates_tar_gz_archive(self):
        result = backup.backup_world(self.world_dir, self.backup_dir, log=self.log)
        self.assertTrue(os.path.isfile(result))
        self.assertTrue(result.endswith(".tar.gz"))

    def test_rotates_out_old_backups_beyond_keep(self):
        # Pre-seed 8 fake backups, keep=7 should remove exactly 1 (the oldest by name).
        os.makedirs(self.backup_dir)
        for i in range(8):
            stamp = f"202601{i:02d}_000000"
            path = os.path.join(self.backup_dir, f"world_{stamp}.tar.gz")
            with open(path, "wb") as f:
                f.write(b"fake")
        backup.backup_world(self.world_dir, self.backup_dir, keep=7, log=self.log)
        remaining = sorted(glob.glob(os.path.join(self.backup_dir, "world_*.tar.gz")))
        # 8 pre-seeded + 1 just created - rotated out down to 7
        self.assertEqual(len(remaining), 7)
        self.assertNotIn(
            os.path.join(self.backup_dir, "world_20260100_000000.tar.gz"), remaining
        )


    def test_custom_prefix_uses_separate_rotation_pool(self):
        # Seed 7 "world_*" backups (the hourly job's pool) at the keep limit.
        os.makedirs(self.backup_dir)
        for i in range(7):
            path = os.path.join(self.backup_dir, f"world_202601{i:02d}_000000.tar.gz")
            with open(path, "wb") as f:
                f.write(b"fake")

        result = backup.backup_world(
            self.world_dir, self.backup_dir, keep=3, log=self.log, prefix="predeploy"
        )

        self.assertTrue(os.path.basename(result).startswith("predeploy_"))
        world_backups = glob.glob(os.path.join(self.backup_dir, "world_*.tar.gz"))
        predeploy_backups = glob.glob(os.path.join(self.backup_dir, "predeploy_*.tar.gz"))
        # The pre-existing 7 "world_*" backups must be untouched by a "predeploy_" rotation.
        self.assertEqual(len(world_backups), 7)
        self.assertEqual(len(predeploy_backups), 1)


if __name__ == "__main__":
    unittest.main()
