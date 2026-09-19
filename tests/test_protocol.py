import socket
import unittest

from ambilight import protocol as p
from ambilight.config import Config
from tests.fake_controller import REAL_STATUS, FakeController

R, G, B = b"\xff\x00\x00", b"\x00\xff\x00", b"\x00\x00\xff"


class FakeSock:
    def __init__(self, reply=b""):
        self.sent = b""
        self.reply = reply

    def settimeout(self, _timeout):
        pass

    def sendall(self, data):
        self.sent += data

    def recv(self, size):
        if not self.reply:
            raise socket.timeout()
        chunk, self.reply = self.reply[:size], self.reply[size:]
        return chunk


class PacketTests(unittest.TestCase):
    def test_make_packet(self):
        self.assertEqual(p.make_packet(0x10), bytes.fromhex("38 00 00 00 10 83"))

    def test_brightness_in_first_byte(self):
        fs = FakeSock()
        p.set_brightness(fs, 38)
        self.assertEqual(fs.sent, bytes.fromhex("38 26 00 00 2a 83"))
        fs = FakeSock()
        p.set_brightness(fs, 999)
        self.assertEqual(fs.sent[1], 255)

    def test_counts_are_little_endian(self):
        fs = FakeSock()
        p.set_dot_count(fs, 78)
        self.assertEqual(fs.sent, bytes.fromhex("38 4e 00 00 2d 83"))
        fs = FakeSock()
        p.set_segments(fs, 2)
        self.assertEqual(fs.sent, bytes.fromhex("38 02 00 00 2e 83"))
        fs = FakeSock()
        p.set_dot_count(fs, 300)
        self.assertEqual(fs.sent[1:3], b"\x2c\x01")

    def test_status_parse_of_real_reply(self):
        fs = FakeSock(REAL_STATUS)
        st = p.get_status(fs)
        self.assertEqual(fs.sent, bytes.fromhex("38 00 00 00 10 83"))
        self.assertEqual(st["brightness"], 38)
        self.assertEqual(st["pixels_per_segment"], 78)
        self.assertEqual(st["segments"], 2)
        self.assertEqual(st["color"], (85, 0, 255))
        self.assertTrue(st["on"])

    def test_status_parse_rejects_bad_replies(self):
        self.assertIsNone(p.get_status(FakeSock(b"")))
        self.assertIsNone(p.get_status(FakeSock(REAL_STATUS[:10])))
        self.assertIsNone(p.get_status(FakeSock(b"\x00" + REAL_STATUS[1:])))


class FrameTests(unittest.TestCase):
    def test_repeat(self):
        f = p.build_frame(R + G + B, "repeat")
        self.assertEqual(len(f), 900)
        self.assertEqual(f[:18], (R + G + B) * 2)

    def test_mirror(self):
        f = p.build_frame(R + G + B, "mirror")
        self.assertEqual(f[:27], R + G + B + B + G + R + R + G + B)

    def test_none_is_black(self):
        self.assertEqual(p.build_frame(R + G + B, "none"), R + G + B + bytes(891))

    def test_empty_and_long_input(self):
        self.assertEqual(p.build_frame(b"", "mirror"), bytes(900))
        big = bytes(range(256)) * 4
        self.assertEqual(p.build_frame(big, "repeat"), big[:900])


class ConnectionTests(unittest.TestCase):
    def test_read_and_write_settings(self):
        fc = FakeController()
        try:
            cfg = fc.cfg()
            st = p.read_settings(cfg)
            self.assertEqual((st["pixels_per_segment"], st["segments"],
                              st["brightness"]), (78, 2, 38))
            st = p.write_settings(cfg, segments=1)
            self.assertEqual((st["pixels_per_segment"], st["segments"]), (78, 1))
            st = p.write_settings(cfg, pixels_per_segment=80, brightness=200)
            self.assertEqual((st["pixels_per_segment"], st["segments"],
                              st["brightness"]), (80, 1, 200))
            self.assertEqual(fc.commands, [0x10, 0x2E, 0x10, 0x2D, 0x2A, 0x10])
        finally:
            fc.close()

    def test_stray_reply_is_drained(self):
        fc = FakeController(stray_reply=b"\x31")
        try:
            st = p.write_settings(fc.cfg(), segments=2)
            self.assertEqual(st["segments"], 2)
        finally:
            fc.close()

    def test_connection_refused(self):
        cfg = Config(controller_ip="127.0.0.1", controller_port=9)
        with self.assertRaises(RuntimeError) as ctx:
            p.read_settings(cfg)
        self.assertTrue(str(ctx.exception).startswith("Connection failed"))

    def test_silent_controller(self):
        fc = FakeController(silent=True)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                p.read_settings(fc.cfg())
            self.assertEqual(str(ctx.exception), "Status read failed.")
        finally:
            fc.close()


if __name__ == "__main__":
    unittest.main()
