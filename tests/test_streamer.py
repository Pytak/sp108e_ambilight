import time
import unittest

from ambilight.config import Config
from ambilight.streamer import Streamer
from tests.fake_controller import FakeController


# a desktop session is necessary for the stream test
class StreamerTests(unittest.TestCase):
    def test_connection_refused(self):
        st = Streamer(Config(controller_ip="127.0.0.1", controller_port=9))
        st.start()
        st.join(10)
        self.assertTrue(st.error.startswith("Connection failed"))
        self.assertEqual(st.status, "Stopped")

    def test_bad_monitor(self):
        for monitor in (0, 99):
            st = Streamer(Config(monitor=monitor))
            st.start()
            st.join(10)
            self.assertEqual(st.error, f"Monitor {monitor} not found.")

    def test_preview_refused(self):
        fc = FakeController(silent=True)
        try:
            st = Streamer(fc.cfg())
            st.start()
            st.join(10)
            self.assertTrue(st.error.startswith("Preview init failed"))
        finally:
            fc.close()

    def test_error_after_stop_is_ignored(self):
        st = Streamer(Config())

        def closed_socket():
            st.stop()
            raise OSError(10038, "not a socket")

        st._run = closed_socket
        st.start()
        st.join(5)
        self.assertIsNone(st.error)
        self.assertEqual(st.status, "Stopped")

    def test_full_stream_against_fake_controller(self):
        fc = FakeController()
        try:
            st = Streamer(fc.cfg(target_fps=60))
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
