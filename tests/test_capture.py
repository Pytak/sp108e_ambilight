import gc
import sys
import time
import tkinter as tk
import unittest

from PIL import Image

from ambilight.capture import (DxgiGrabber, FrameProducer, channel_lut,
                               list_monitors)
from ambilight.config import Config


class CalibrationTests(unittest.TestCase):
    def test_identity_has_no_lut(self):
        self.assertIsNone(channel_lut([255, 255, 255]))

    def test_grey_is_scaled_per_channel(self):
        lut = channel_lut([255, 158, 131])
        img = Image.new("RGB", (2, 1), (128, 128, 128)).point(lut)
        self.assertEqual(img.getpixel((0, 0)), (128, 79, 66))
        white = Image.new("RGB", (1, 1), (255, 255, 255)).point(lut)
        self.assertEqual(white.getpixel((0, 0)), (255, 158, 131))
        black = Image.new("RGB", (1, 1), (0, 0, 0)).point(lut)
        self.assertEqual(black.getpixel((0, 0)), (0, 0, 0))


def first_grab(grabber):
    # the first frame of a duplication can be late
    for _ in range(100):
        try:
            return grabber.grab()
        except RuntimeError:
            time.sleep(0.01)
    return grabber.grab()


# a desktop session is necessary for these tests
class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.mon = list_monitors()[0]

    def test_grab_every_monitor(self):
        for mon in list_monitors():
            g = DxgiGrabber(mon, 120)
            try:
                img = first_grab(g)
                self.assertEqual((img.size, img.mode), ((120, 1), "RGB"))
                # on an unchanged screen, the result stays the same
                for _ in range(5):
                    self.assertEqual(g.grab().size, (120, 1))
            finally:
                g.close()

    def test_colors_are_rgb(self):
        mon = self.mon
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#ff0000")
        root.geometry(f"{mon['width'] // 4}x{mon['height']}"
                      f"+{mon['left']}+{mon['top']}")
        g = DxgiGrabber(mon, 100)
        try:
            end = time.time() + 0.5
            while time.time() < end:
                root.update()
                time.sleep(0.02)
            first_grab(g)
            time.sleep(0.1)
            img = g.grab()
            for x in range(5, 20):
                r, gr, b = img.getpixel((x, 0))
                self.assertTrue(r > 200 and gr < 60 and b < 60, (x, r, gr, b))
        finally:
            g.close()
            root.destroy()

    def test_release_is_clean(self):
        # without the patch, dxcam 0.3.0 causes a double release
        errors = []
        old_hook = sys.unraisablehook
        sys.unraisablehook = errors.append
        try:
            for _ in range(3):
                g = DxgiGrabber(self.mon, 60)
                first_grab(g)
                g.close()
                del g
                gc.collect()
        finally:
            sys.unraisablehook = old_hook
        self.assertEqual(errors, [])

    def test_producer_publishes_frames(self):
        producer = FrameProducer(self.mon, Config(pixel_count=120))
        producer.start()
        try:
            for _ in range(3):
                self.assertEqual(len(producer.get(timeout=3)), 900)
        finally:
            producer.stop()
            producer.join(3)
        self.assertFalse(producer.is_alive())
        self.assertIsNone(producer.error)

    def test_producer_keeps_the_target_rate(self):
        producer = FrameProducer(self.mon, Config(target_fps=20))
        producer.start()
        try:
            producer.get(timeout=3)
            count, start = 0, time.perf_counter()
            while time.perf_counter() - start < 1.0:
                producer.get(timeout=1)
                count += 1
        finally:
            producer.stop()
            producer.join(3)
        self.assertTrue(15 <= count <= 21, count)

    def test_unavailable_output_is_an_error(self):
        mon = dict(self.mon, output=99)
        producer = FrameProducer(mon, Config())
        producer.start()
        producer.join(3)
        self.assertTrue(producer.error.startswith("Screen capture failed"))


if __name__ == "__main__":
    unittest.main()
