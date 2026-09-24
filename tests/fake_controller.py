import socket
import threading

from ambilight.config import Config
from ambilight import protocol as p

# real controller status: brightness 38, 78 pixels x 2 segments
REAL_STATUS = bytes.fromhex("38 01 d3 d3 26 02 00 4e 00 02 55 00 ff 03 08 00 83")


class FakeController:
    def __init__(self, stray_reply=b"", silent=False):
        self.status = bytearray(REAL_STATUS)
        self.stray_reply = stray_reply
        self.silent = silent
        self.commands = []
        self.frames = 0
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen()
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def cfg(self, **overrides):
        return Config(controller_ip="127.0.0.1", controller_port=self.port,
                      **overrides)

    def close(self):
        self._srv.close()

    def _serve(self):
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    @staticmethod
    def _recv(conn, size):
        buf = b""
        while len(buf) < size:
            chunk = conn.recv(size - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _handle(self, conn):
        conn.settimeout(5)
        try:
            while True:
                pkt = self._recv(conn, 6)
                if pkt is None:
                    return
                cmd = pkt[4]
                self.commands.append(cmd)
                if self.silent:
                    continue
                if cmd == p.CMD_GET_STATUS:
                    conn.sendall(bytes(self.status))
                elif cmd == p.CMD_SET_BRIGHTNESS:
                    self.status[4] = pkt[1]
                    conn.sendall(self.stray_reply)
                elif cmd in (p.CMD_SET_DOT_COUNT, p.CMD_SET_SEGMENTS):
                    value = int.from_bytes(pkt[1:3], "little")
                    at = 6 if cmd == p.CMD_SET_DOT_COUNT else 8
                    self.status[at:at + 2] = value.to_bytes(2, "big")
                    conn.sendall(self.stray_reply)
                elif cmd == p.CMD_CUSTOM_PREVIEW:
                    conn.sendall(bytes([p.ACK_BYTE]))
                    while True:
                        frame = self._recv(conn, p.PREVIEW_FRAME_SIZE)
                        if frame is None:
                            return
                        self.frames += 1
                        conn.sendall(bytes([p.ACK_BYTE]))
        except OSError:
            pass
        finally:
            conn.close()
