import time
import unittest

from ambilight.config import Config
from ambilight.streamer import Streamer
from tests.fake_controller import FakeController


class StreamerTests(unittest.TestCase):
    """The stream test needs a desktop session for the screen capture."""

    def test_connection_refused(self):
        st = Streamer(Config(controller_ip="127.0.0.1", controller_port=9))
        st.start()
        st.join(10)
        self.assertTrue(st.error.startswith("Connection failed"))
        self.assertEqual(st.status, "Stopped")

    def test_bad_monitor(self):
        st = Streamer(Config(monitor=99))
        st.start()
        st.join(10)
        self.assertEqual(st.error, "Monitor 99 not found.")

    def test_preview_refused(self):
        fc = FakeController(silent=True)
        try:
            st = Streamer(fc.cfg())
            st.start()
            st.join(10)
            self.assertTrue(st.error.startswith("Preview init failed"))
        finally:
            fc.close()

    def test_full_stream_against_fake_controller(self):
        fc = FakeController()
        try:
            st = Streamer(fc.cfg(target_fps=60, band_fraction=0.1))
            st.start()
            time.sleep(2.0)
            self.assertEqual(st.status, "Streaming")
            self.assertGreater(st.fps, 5)
            st.stop()
            st.join(5)
            self.assertFalse(st.is_alive())
            self.assertIsNone(st.error)
            self.assertGreater(fc.frames, 10)
            self.assertEqual(fc.commands, [0x24])
        finally:
            fc.close()


if __name__ == "__main__":
    unittest.main()
