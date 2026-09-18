import unittest

import deploy


class WarningMessageTests(unittest.TestCase):
    def test_plural_minutes(self):
        self.assertIn("15 минут", deploy.warning_message(15))
        self.assertIn("5 минут", deploy.warning_message(5))

    def test_singular_minute(self):
        self.assertIn("1 минуту", deploy.warning_message(1))


class BroadcastWarningsTests(unittest.TestCase):
    def test_sends_in_order_with_correct_gaps(self):
        commands = []
        sleeps = []

        class FakeRcon:
            def command(self, cmd):
                commands.append(cmd)

        deploy.broadcast_warnings(
            FakeRcon(), schedule=[15, 10, 5, 1], sleep=sleeps.append, log=lambda m: None
        )

        self.assertEqual(len(commands), 4)
        self.assertIn("15", commands[0])
        self.assertIn("1", commands[3])
        # gaps: 15->10 (5min), 10->5 (5min), 5->1 (4min), 1->0 (1min), all in seconds
        self.assertEqual(sleeps, [5 * 60, 5 * 60, 4 * 60, 1 * 60])


class ParsePidsTests(unittest.TestCase):
    def test_parses_multiple_pids(self):
        self.assertEqual(deploy.parse_pids("1234\n5678\n"), [1234, 5678])

    def test_ignores_blank_lines(self):
        self.assertEqual(deploy.parse_pids("\n1234\n\n"), [1234])

    def test_empty_output_is_empty_list(self):
        self.assertEqual(deploy.parse_pids(""), [])


class StopServerTests(unittest.TestCase):
    def test_returns_true_when_process_exits_before_timeout(self):
        commands = []

        class FakeRcon:
            def command(self, cmd):
                commands.append(cmd)

        alive_calls = {"count": 0}

        def fake_is_alive(pid):
            alive_calls["count"] += 1
            return alive_calls["count"] < 2  # alive once, then gone

        killed = []
        result = deploy.stop_server(
            FakeRcon(),
            timeout=60,
            poll_interval=1,
            sleep=lambda s: None,
            log=lambda m: None,
            find_pids=lambda: [111],
            is_alive=fake_is_alive,
            kill=killed.append,
        )
        self.assertTrue(result)
        self.assertEqual(killed, [])
        self.assertEqual(commands, ["stop"])

    def test_force_kills_after_timeout(self):
        class FakeRcon:
            def command(self, cmd):
                pass

        killed = []
        result = deploy.stop_server(
            FakeRcon(),
            timeout=3,
            poll_interval=1,
            sleep=lambda s: None,
            log=lambda m: None,
            find_pids=lambda: [111],
            is_alive=lambda pid: True,  # never exits on its own
            kill=killed.append,
        )
        self.assertFalse(result)
        self.assertEqual(killed, [111])


    def test_returns_none_and_skips_wait_when_no_pids_found(self):
        commands = []

        class FakeRcon:
            def command(self, cmd):
                commands.append(cmd)

        sleeps = []
        result = deploy.stop_server(
            FakeRcon(),
            timeout=60,
            poll_interval=1,
            sleep=sleeps.append,
            log=lambda m: None,
            find_pids=lambda: [],
            is_alive=lambda pid: True,
            kill=lambda pid: None,
        )
        self.assertIsNone(result)
        self.assertEqual(commands, ["stop"])
        self.assertEqual(sleeps, [])  # no pids to wait on, must not sleep at all


class VerifyOnlineTests(unittest.TestCase):
    def test_true_on_first_success(self):
        class FakeRcon:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def command(self, cmd):
                return "ok"

        result = deploy.verify_online(
            {"host": "x", "port": 1, "password": "y"},
            timeout=10,
            poll_interval=1,
            sleep=lambda s: None,
            log=lambda m: None,
            rcon_factory=lambda **kw: FakeRcon(),
        )
        self.assertTrue(result)

    def test_false_when_never_comes_online(self):
        def always_fails(**kw):
            raise ConnectionRefusedError()

        result = deploy.verify_online(
            {"host": "x", "port": 1, "password": "y"},
            timeout=3,
            poll_interval=1,
            sleep=lambda s: None,
            log=lambda m: None,
            rcon_factory=always_fails,
        )
        self.assertFalse(result)


class SyncModsStepTests(unittest.TestCase):
    def test_returns_true_when_no_failures(self):
        logs = []
        ok = deploy.sync_mods_step(
            log=logs.append,
            syncer=lambda: {"downloaded": ["a.jar"], "skipped": [], "failed": []},
        )
        self.assertTrue(ok)
        self.assertTrue(any("a.jar" in m for m in logs))

    def test_returns_false_when_failures(self):
        ok = deploy.sync_mods_step(
            log=lambda m: None,
            syncer=lambda: {"downloaded": [], "skipped": [], "failed": [("b.jar", "boom")]},
        )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
