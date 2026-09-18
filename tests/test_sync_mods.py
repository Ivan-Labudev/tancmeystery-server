import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import sync_mods


FAKE_JAR_BYTES = b"fake jar bytes"
FAKE_JAR_SHA512 = hashlib.sha512(FAKE_JAR_BYTES).hexdigest()

SERVER_SIDE_TOML = f"""\
name = "Waystones"
filename = "waystones-fabric-1.20.1-14.1.21.jar"
side = "both"

[download]
url = "https://cdn.modrinth.com/data/LOpKHB2A/versions/LcO5SBoa/waystones-fabric-1.20.1-14.1.21.jar"
hash-format = "sha512"
hash = "{FAKE_JAR_SHA512}"

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
        entries, errors = sync_mods.load_pack_entries(self.tmp)
        names = [e["name"] for e in entries]
        self.assertIn("Waystones", names)

    def test_excludes_client_only_mods(self):
        entries, errors = sync_mods.load_pack_entries(self.tmp)
        names = [e["name"] for e in entries]
        self.assertNotIn("Bobby", names)

    def test_entry_has_filename_url_and_hash(self):
        entries, errors = sync_mods.load_pack_entries(self.tmp)
        waystones = next(e for e in entries if e["name"] == "Waystones")
        self.assertEqual(waystones["filename"], "waystones-fabric-1.20.1-14.1.21.jar")
        self.assertTrue(waystones["url"].startswith("https://cdn.modrinth.com/"))
        self.assertEqual(waystones["hash"], FAKE_JAR_SHA512)
        self.assertEqual(waystones["hash_format"], "sha512")

    def test_reports_missing_hash_key_as_error_not_crash(self):
        broken_toml = SERVER_SIDE_TOML.replace(
            'hash = "{}"'.format(FAKE_JAR_SHA512), ""
        )
        with open(os.path.join(self.tmp, "waystones.pw.toml"), "w", encoding="utf-8") as f:
            f.write(broken_toml)
        entries, errors = sync_mods.load_pack_entries(self.tmp)
        names = [e["name"] for e in entries]
        self.assertNotIn("Waystones", names)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], "waystones.pw.toml")
        self.assertIn("hash", errors[0][1])


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


class SafetyHelperTests(unittest.TestCase):
    def test_is_safe_filename_rejects_traversal(self):
        self.assertFalse(sync_mods.is_safe_filename("../evil.jar"))
        self.assertFalse(sync_mods.is_safe_filename("sub/evil.jar"))
        self.assertFalse(sync_mods.is_safe_filename(".."))
        self.assertFalse(sync_mods.is_safe_filename(""))

    def test_is_safe_filename_accepts_plain_name(self):
        self.assertTrue(sync_mods.is_safe_filename("waystones-fabric-1.20.1-14.1.21.jar"))

    def test_has_allowed_scheme(self):
        self.assertTrue(sync_mods.has_allowed_scheme("https://cdn.modrinth.com/x.jar"))
        self.assertTrue(sync_mods.has_allowed_scheme("http://example.com/x.jar"))
        self.assertFalse(sync_mods.has_allowed_scheme("file:///etc/passwd"))
        self.assertFalse(sync_mods.has_allowed_scheme("ftp://example.com/x.jar"))


class VerifyHashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "f.bin")
        with open(self.path, "wb") as f:
            f.write(FAKE_JAR_BYTES)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_matches_correct_hash(self):
        self.assertTrue(sync_mods.verify_hash(self.path, FAKE_JAR_SHA512))

    def test_rejects_wrong_hash(self):
        self.assertFalse(sync_mods.verify_hash(self.path, "0" * 128))

    def test_rejects_unsupported_hash_format(self):
        self.assertFalse(sync_mods.verify_hash(self.path, FAKE_JAR_SHA512, hash_format="md5"))


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

    def test_downloads_and_verifies_missing_mod(self):
        calls = []

        def fake_downloader(url, dest_path):
            calls.append((url, dest_path))
            with open(dest_path, "wb") as f:
                f.write(FAKE_JAR_BYTES)

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

    def test_rejects_hash_mismatch_and_removes_partial_file(self):
        def tampered_downloader(url, dest_path):
            with open(dest_path, "wb") as f:
                f.write(b"tampered bytes, not the pinned jar")

        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=tampered_downloader)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(len(result["failed"]), 1)
        name, reason = result["failed"][0]
        self.assertEqual(name, "waystones-fabric-1.20.1-14.1.21.jar")
        self.assertIn("hash", reason)
        self.assertFalse(os.path.exists(os.path.join(self.mods_dir, name)))

    def test_rejects_unsafe_filename_without_downloading(self):
        unsafe_toml = SERVER_SIDE_TOML.replace(
            'filename = "waystones-fabric-1.20.1-14.1.21.jar"',
            'filename = "../evil.jar"',
        )
        with open(os.path.join(self.modpack_dir, "waystones.pw.toml"), "w", encoding="utf-8") as f:
            f.write(unsafe_toml)

        def failing_downloader(url, dest_path):
            raise AssertionError("should not be called")

        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=failing_downloader)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("unsafe filename", result["failed"][0][1])

    def test_rejects_disallowed_url_scheme_without_downloading(self):
        unsafe_toml = SERVER_SIDE_TOML.replace(
            'url = "https://cdn.modrinth.com/data/LOpKHB2A/versions/LcO5SBoa/waystones-fabric-1.20.1-14.1.21.jar"',
            'url = "file:///etc/passwd"',
        )
        with open(os.path.join(self.modpack_dir, "waystones.pw.toml"), "w", encoding="utf-8") as f:
            f.write(unsafe_toml)

        def failing_downloader(url, dest_path):
            raise AssertionError("should not be called")

        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=failing_downloader)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("disallowed URL scheme", result["failed"][0][1])

    def test_malformed_manifest_entry_becomes_failed_not_a_crash(self):
        broken_toml = SERVER_SIDE_TOML.replace(
            'hash = "{}"'.format(FAKE_JAR_SHA512), ""
        )
        with open(os.path.join(self.modpack_dir, "waystones.pw.toml"), "w", encoding="utf-8") as f:
            f.write(broken_toml)

        def failing_downloader(url, dest_path):
            raise AssertionError("should not be called")

        # Must not raise.
        result = sync_mods.sync(self.modpack_dir, self.mods_dir, downloader=failing_downloader)
        self.assertEqual(result["downloaded"], [])
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0][0], "waystones.pw.toml")


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "out.jar")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_cleans_up_partial_file_on_failure(self):
        with mock.patch("sync_mods.urllib.request.urlopen", side_effect=OSError("network unreachable")):
            with self.assertRaises(OSError):
                sync_mods.download("https://example.com/x.jar", self.dest)
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_writes_dest_on_success(self):
        fake_resp = mock.MagicMock()
        fake_resp.__enter__.return_value.read.return_value = b"jar bytes"
        with mock.patch("sync_mods.urllib.request.urlopen", return_value=fake_resp):
            sync_mods.download("https://example.com/x.jar", self.dest)
        self.assertTrue(os.path.exists(self.dest))
        with open(self.dest, "rb") as f:
            self.assertEqual(f.read(), b"jar bytes")


if __name__ == "__main__":
    unittest.main()
