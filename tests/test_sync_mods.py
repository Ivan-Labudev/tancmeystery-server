import os
import shutil
import tempfile
import unittest

import sync_mods


SERVER_SIDE_TOML = """\
name = "Waystones"
filename = "waystones-fabric-1.20.1-14.1.21.jar"
side = "both"

[download]
url = "https://cdn.modrinth.com/data/LOpKHB2A/versions/LcO5SBoa/waystones-fabric-1.20.1-14.1.21.jar"
hash-format = "sha512"
hash = "deadbeef"

[update]
[update.modrinth]
mod-id = "LOpKHB2A"
version = "LcO5SBoa"
"""

CLIENT_ONLY_TOML = """\
name = "Bobby"
filename = "bobby-5.0.1.1.jar"
side = "client"

[download]
url = "https://cdn.modrinth.com/data/M08ruV16/versions/Uh3M3z1g/bobby-5.0.1.1.jar"
hash-format = "sha512"
hash = "cafebabe"

[update]
[update.modrinth]
mod-id = "M08ruV16"
version = "Uh3M3z1g"
"""


class LoadPackEntriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "waystones.pw.toml"), "w", encoding="utf-8") as f:
            f.write(SERVER_SIDE_TOML)
        with open(os.path.join(self.tmp, "bobby.pw.toml"), "w", encoding="utf-8") as f:
            f.write(CLIENT_ONLY_TOML)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_includes_server_and_both_side_mods(self):
        entries = sync_mods.load_pack_entries(self.tmp)
        names = [e["name"] for e in entries]
        self.assertIn("Waystones", names)

    def test_excludes_client_only_mods(self):
        entries = sync_mods.load_pack_entries(self.tmp)
        names = [e["name"] for e in entries]
        self.assertNotIn("Bobby", names)

    def test_entry_has_filename_and_url(self):
        entries = sync_mods.load_pack_entries(self.tmp)
        waystones = next(e for e in entries if e["name"] == "Waystones")
        self.assertEqual(waystones["filename"], "waystones-fabric-1.20.1-14.1.21.jar")
        self.assertTrue(waystones["url"].startswith("https://cdn.modrinth.com/"))


class AlreadyPresentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_false_when_absent(self):
        self.assertFalse(sync_mods.already_present("foo.jar", self.tmp))

    def test_true_when_present(self):
        open(os.path.join(self.tmp, "foo.jar"), "w").close()
        self.assertTrue(sync_mods.already_present("foo.jar", self.tmp))

    def test_true_when_manually_disabled(self):
        open(os.path.join(self.tmp, "foo.jar.disabled"), "w").close()
        self.assertTrue(sync_mods.already_present("foo.jar", self.tmp))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.modpack_dir = os.path.join(self.tmp, "modpack_mods")
        self.mods_dir = os.path.join(self.tmp, "mods")
        os.makedirs(self.modpack_dir)
        with open(os.path.join(self.modpack_dir, "waystones.pw.toml"), "w", encoding="utf-8") as f:
            f.write(SERVER_SIDE_TOML)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_downloads_missing_mod(self):
        calls = []

        def fake_downloader(url, dest_path):
            calls.append((url, dest_path))
            with open(dest_path, "wb") as f:
                f.write(b"fake jar bytes")

        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=fake_downloader)
        self.assertEqual(result["downloaded"], ["waystones-fabric-1.20.1-14.1.21.jar"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["failed"], [])
        self.assertEqual(len(calls), 1)

    def test_skips_already_present_mod(self):
        os.makedirs(self.mods_dir)
        open(os.path.join(self.mods_dir, "waystones-fabric-1.20.1-14.1.21.jar"), "w").close()

        def failing_downloader(url, dest_path):
            raise AssertionError("should not be called")

        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=failing_downloader)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(result["skipped"], ["waystones-fabric-1.20.1-14.1.21.jar"])

    def test_records_failed_downloads(self):
        def broken_downloader(url, dest_path):
            raise OSError("network unreachable")

        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=broken_downloader)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0][0], "waystones-fabric-1.20.1-14.1.21.jar")


if __name__ == "__main__":
    unittest.main()
