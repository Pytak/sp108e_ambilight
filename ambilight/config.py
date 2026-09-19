"""Settings of the program: the Config dataclass, its JSON file and its location."""

import json
import os
import sys
from dataclasses import dataclass, asdict, fields

CONFIG_FILENAME = "sp108e_ambilight.json"

# How to fill the LEDs beyond pixel_count, up to the 300 pixels of a frame.
FILL_MODES = ("repeat", "mirror", "none")


@dataclass
class Config:
    # Network address of the controller.
    controller_ip: str = "192.168.1.235"
    controller_port: int = 8189

    # Number of LEDs, from the start of the strip, that show the screen
    # band. Maximum 300 (FRAME_PIXELS in protocol.py).
    pixel_count: int = 175

    # Upper limit for the frame rate. The acknowledgement pacing of the
    # controller will usually limit it further.
    target_fps: int = 30

    # mss monitor index. 0 = all monitors combined, 1 = first monitor, ...
    monitor: int = 0

    # Height of the sampled band as a fraction of the screen height,
    # centred vertically.
    band_fraction: float = 0.03

    # Spatial smoothing: Gaussian blur radius along the strip, in LEDs.
    # Set 0 to disable.
    smooth_radius: float = 5.0

    # Temporal smoothing: weight of the new frame in the output (0..1).
    # Set 1.0 to disable.
    temporal_alpha: float = 0.1

    # Set True for LEDs that run right-to-left relative to the screen.
    mirror_strip: bool = True

    # Fill for the rest of the 900-byte frame, one of FILL_MODES:
    #   "repeat": repeats of the strip
    #   "mirror": mirrored repeats of the strip (forward, reversed, ...)
    #   "none":   black
    fill_mode: str = "mirror"

    @classmethod
    def load(cls, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        types = {f.name: f.type for f in fields(cls)}
        clean = {}
        for key, value in data.items():
            if key in types:
                try:
                    clean[key] = types[key](value)
                except (TypeError, ValueError):
                    pass
        if clean.get("fill_mode") not in FILL_MODES:
            clean.pop("fill_mode", None)
        return cls(**clean)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
            f.write("\n")


def config_path():
    """Path of the settings file: next to the exe, or next to the entry script."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base, CONFIG_FILENAME)
