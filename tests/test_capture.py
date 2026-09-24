import unittest

from PIL import Image

from ambilight.capture import (FrameProducer, GdiGrabber, channel_lut,
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


class GdiTests(unittest.TestCase):
    """These tests need a desktop session."""

    def setUp(self):
        self.mon = list_monitors()[0]

    def test_grab_shape_and_mode(self):
        g = GdiGrabber(self.mon, 240)
        try:
            img = g.grab()
            self.assertEqual(img.size, (240, 1))
            self.assertEqual(img.mode, "RGB")
        finally:
            g.close()
            g.close()

    def test_producer_publishes_frames(self):
        cfg = Config(pixel_count=120, monitor=0)
        producer = FrameProducer(self.mon, cfg)
        producer.start()
        try:
            for _ in range(3):
                self.assertEqual(len(producer.get(timeout=3)), 900)
        finally:
            producer.stop()
            producer.join(3)
        self.assertFalse(producer.is_alive())
        self.assertIsNone(producer.error)


if __name__ == "__main__":
    unittest.main()
