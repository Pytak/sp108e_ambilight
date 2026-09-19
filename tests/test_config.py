import json
import os
import tempfile
import unittest

from ambilight.config import CONFIG_FILENAME, Config, config_path


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "c.json")

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def test_round_trip(self):
        cfg = Config(controller_ip="1.2.3.4", pixel_count=12, band_fraction=0.5,
                     mirror_strip=False, fill_mode="repeat")
        cfg.save(self.path)
        self.assertEqual(Config.load(self.path), cfg)

    def test_missing_or_corrupt_file_gives_defaults(self):
        self.assertEqual(Config.load(self.path), Config())
        self.write("{not json")
        self.assertEqual(Config.load(self.path), Config())
        self.write([1, 2, 3])
        self.assertEqual(Config.load(self.path), Config())

    def test_partial_and_unknown_keys(self):
        self.write({"pixel_count": "77", "bogus": 1, "target_fps": "abc"})
        cfg = Config.load(self.path)
        self.assertEqual(cfg.pixel_count, 77)
        self.assertEqual(cfg.target_fps, Config().target_fps)

    def test_bool_fields_accept_only_bools(self):
        self.write({"mirror_strip": "false"})
        self.assertEqual(Config.load(self.path).mirror_strip, Config().mirror_strip)
        self.write({"mirror_strip": False})
        self.assertFalse(Config.load(self.path).mirror_strip)

    def test_invalid_fill_mode_falls_back(self):
        self.write({"fill_mode": "bogus"})
        self.assertEqual(Config.load(self.path).fill_mode, "mirror")
        self.write({"fill_mode": "none"})
        self.assertEqual(Config.load(self.path).fill_mode, "none")

    def test_config_path_filename(self):
        self.assertEqual(os.path.basename(config_path()), CONFIG_FILENAME)


if __name__ == "__main__":
    unittest.main()
