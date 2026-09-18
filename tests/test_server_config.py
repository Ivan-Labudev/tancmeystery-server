import os
import tempfile
import unittest

import server_config


SAMPLE_PROPERTIES = """\
#Minecraft server properties
#comment line
enable-rcon=true
rcon.port=25575
rcon.password=hunter2
server-ip=
"""


class ReadPropertiesTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".properties")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(SAMPLE_PROPERTIES)

    def tearDown(self):
        os.remove(self.path)

    def test_parses_key_value_pairs(self):
        props = server_config.read_properties(self.path)
        self.assertEqual(props["rcon.password"], "hunter2")
        self.assertEqual(props["rcon.port"], "25575")

    def test_skips_comments_and_blank_values(self):
        props = server_config.read_properties(self.path)
        self.assertNotIn("#Minecraft server properties", props)
        self.assertEqual(props["server-ip"], "")


class GetRconConfigTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".properties")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(SAMPLE_PROPERTIES)

    def tearDown(self):
        os.remove(self.path)

    def test_returns_host_port_password(self):
        config = server_config.get_rcon_config(self.path)
        self.assertEqual(config, {"host": "127.0.0.1", "port": 25575, "password": "hunter2"})

    def test_defaults_port_when_missing(self):
        fd, path = tempfile.mkstemp(suffix=".properties")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("rcon.password=onlypassword\n")
        try:
            config = server_config.get_rcon_config(path)
            self.assertEqual(config["port"], 25575)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
