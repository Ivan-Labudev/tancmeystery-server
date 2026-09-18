"""Minimal Source RCON protocol client (Minecraft-compatible)."""
import socket
import struct

SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


class RconError(Exception):
    pass


class RconClient:
    def __init__(self, host="127.0.0.1", port=25575, password="", timeout=10):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.sock = None
        self._req_id = 0

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._auth()

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def _next_id(self):
        self._req_id += 1
        return self._req_id

    def _send_packet(self, req_id, pkt_type, body):
        payload = struct.pack("<ii", req_id, pkt_type) + body.encode("utf-8") + b"\x00\x00"
        length = struct.pack("<i", len(payload))
        self.sock.sendall(length + payload)

    def _read_packet(self):
        raw_len = self._recv_exact(4)
        length = struct.unpack("<i", raw_len)[0]
        data = self._recv_exact(length)
        req_id, pkt_type = struct.unpack("<ii", data[:8])
        body = data[8:-2].decode("utf-8", errors="replace")
        return req_id, pkt_type, body

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RconError("Connection closed while reading")
            buf += chunk
        return buf

    def _auth(self):
        req_id = self._next_id()
        self._send_packet(req_id, SERVERDATA_AUTH, self.password)
        resp_id, _, _ = self._read_packet()
        if resp_id == -1:
            raise RconError("RCON authentication failed")

    def command(self, cmd, drain_seconds=1.0):
        """Send a command and collect every packet that arrives within
        `drain_seconds` of silence. Needed because some plugins (e.g.
        LuckPerms) execute commands asynchronously and push follow-up
        packets that aren't paired with the request id — a strict
        one-packet-per-command read would misattribute them to whatever
        command happens to be read next.
        """
        req_id = self._next_id()
        self._send_packet(req_id, SERVERDATA_EXECCOMMAND, cmd)

        bodies = []
        self.sock.settimeout(drain_seconds)
        try:
            while True:
                _, _, body = self._read_packet()
                if body:
                    bodies.append(body)
        except socket.timeout:
            pass
        finally:
            self.sock.settimeout(self.timeout)
        return "\n".join(bodies)
