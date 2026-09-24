import time
import unittest

import sp108e_ambilight_gui as gui

DEVICE = {"pixels_per_segment": 78, "segments": 2, "brightness": 38}


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


class FakeStreamer:
    alive = True
    status = "Streaming"
    fps = 1.0
    error = None

    def is_alive(self):
        return self.alive

    def stop(self):
        self.alive = False

    def join(self, timeout=None):
        pass


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.errors = []
        self._orig = (gui.read_settings, gui.write_settings,
                      gui.messagebox.showerror)
        gui.read_settings = self._read
        gui.write_settings = self._write
        gui.messagebox.showerror = lambda title, msg: self.errors.append(msg)
        self.app = gui.App()
        self.app.withdraw()
        pump(self.app, 0.8)

    def tearDown(self):
        self.app.destroy()
        gui.read_settings, gui.write_settings, gui.messagebox.showerror = self._orig

    def _read(self, cfg):
        self.calls.append("read")
        return dict(DEVICE)

    def _write(self, cfg, **kw):
        self.calls.append(("write", kw))
        result = dict(DEVICE)
        result.update(kw)
        return result

    def writes(self):
        return [c for c in self.calls if c != "read"]

    def controls_enabled(self):
        return [not w.instate(["disabled"]) for w in self.app.controller_controls]

    def test_startup_read_fills_controller_settings(self):
        self.assertEqual(self.calls, ["read"])
        self.assertEqual(self.app.v_seg_pixels.get(), "78")
        self.assertEqual(self.app.v_segments.get(), "2")
        self.assertEqual(self.app.v_bright_text.get(), "38")
        self.assertEqual(self.app.v_bright.get(), 38.0)
        self.assertTrue(all(self.controls_enabled()))

    def test_slider_and_box_stay_in_sync(self):
        self.app._on_slider_move("200.7")
        self.assertEqual(self.app.v_bright_text.get(), "200")
        self.app.v_bright_text.set("77")
        self.assertEqual(self.app.v_bright.get(), 77.0)
        self.app.v_bright_text.set("abc")
        self.assertEqual(self.app.v_bright.get(), 77.0)

    def test_set_sends_only_changed_values(self):
        self.app._set_counts()
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.app.v_status.get(), "Pixels and segments unchanged")
        self.app.v_segments.set("1")
        self.app._set_counts()
        pump(self.app, 0.5)
        self.assertEqual(self.writes(), [("write", {"segments": 1})])
        self.assertEqual(self.app.v_segments.get(), "1")
        self.app._set_brightness()
        self.assertEqual(self.app.v_status.get(), "Brightness unchanged")
        self.app.v_bright_text.set("120")
        self.app._set_brightness()
        pump(self.app, 0.5)
        self.assertEqual(self.writes()[-1], ("write", {"brightness": 120}))

    def test_validation(self):
        self.app.v_seg_pixels.set("301")
        self.app._set_counts()
        self.assertIn("1 to 300", self.errors[-1])
        self.app.v_seg_pixels.set("78")
        self.app.v_segments.set("11")
        self.app._set_counts()
        self.assertIn("1 to 10", self.errors[-1])
        self.app.v_segments.set("2")
        self.app.v_bright_text.set("300")
        self.app._set_brightness()
        self.assertIn("0 to 255", self.errors[-1])
        self.assertEqual(self.writes(), [])
        self.app.v_pixels.set("abc")
        with self.assertRaises(ValueError):
            self.app._read()

    def test_controller_settings_locked_during_stream(self):
        fake = FakeStreamer()
        self.app.streamer = fake
        self.app._set_inputs(False)
        self.app._set_controller_controls(False)
        count = len(self.calls)
        self.app._read_controller()
        self.app._set_counts()
        self.app._set_brightness()
        self.assertEqual(len(self.calls), count)
        self.assertFalse(any(self.controls_enabled()))
        fake.alive = False
        pump(self.app, 0.5)
        self.assertTrue(all(self.controls_enabled()))
        self.assertEqual(self.app.btn.cget("text"), "Start")

    def test_settings_round_trip_through_widgets(self):
        cfg = self.app._read()
        self.app._show(cfg)
        self.assertEqual(self.app._read(), cfg)

    def test_white_balance_widgets(self):
        cfg = self.app._read()
        cfg.channel_max = [255, 158, 131]
        self.app._show(cfg)
        self.assertEqual([v.get() for v in self.app.v_white],
                         ["255", "158", "131"])
        self.assertEqual(self.app._read().channel_max, [255, 158, 131])
        self.app.v_white[1].set("256")
        with self.assertRaises(ValueError):
            self.app._read()


if __name__ == "__main__":
    unittest.main()
