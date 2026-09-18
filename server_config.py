"""Shared helper for reading the local, gitignored server.properties file.

server.properties holds machine-specific secrets (rcon.password) and is never
committed to git — every script that needs RCON credentials reads them from
here at runtime instead of hardcoding them.
"""
import os

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
PROPERTIES_PATH = os.path.join(SERVER_DIR, "server.properties")

DEFAULT_RCON_HOST = "127.0.0.1"
DEFAULT_RCON_PORT = 25575


def read_properties(path=PROPERTIES_PATH):
    props = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            props[key.strip()] = value.strip()
    return props


def get_rcon_config(path=PROPERTIES_PATH):
    props = read_properties(path)
    return {
        "host": DEFAULT_RCON_HOST,
        "port": int(props.get("rcon.port") or DEFAULT_RCON_PORT),
        "password": props["rcon.password"],
    }
