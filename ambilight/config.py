import json
import os
import sys
from dataclasses import dataclass, asdict, field, fields

CONFIG_FILENAME = "sp108e_ambilight.json"
FILL_MODES = ("repeat", "mirror", "none")


@dataclass
class Config:
    controller_ip: str = "192.168.1.235"
    controller_port: int = 8189
    # LEDs that show the screen band, from the start of the strip. Max 300.
    pixel_count: int = 175
    # Frame rate cap.
    target_fps: int = 30
    # mss monitor index. 0 = all monitors.
    monitor: int = 0
    # Height of the sampled band, fraction of the screen height.
    band_fraction: float = 0.03
    # Gaussian blur along the strip, in LEDs. 0 = off.
    smooth_radius: float = 5.0
    # Weight of the new frame when blended with the last one. 1.0 = off.
    temporal_alpha: float = 0.1
    # For strips that run right to left.
    mirror_strip: bool = True
    # Fill after pixel_count: repeat, mirror or none (black).
    fill_mode: str = "mirror"
    # Color calibration, JSON only: max output per channel (R, G, B).
    channel_max: list = field(default_factory=lambda: [255, 255, 255])

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
            if key not in types:
                continue
            if types[key] is bool:
                # bool("false") is True
                if isinstance(value, bool):
                    clean[key] = value
                continue
            try:
                clean[key] = types[key](value)
            except (TypeError, ValueError):
                pass
        if clean.get("fill_mode") not in FILL_MODES:
            clean.pop("fill_mode", None)
        cm = clean.get("channel_max")
        if cm is not None and not (
                len(cm) == 3 and all(type(v) is int and 0 <= v <= 255 for v in cm)):
            clean.pop("channel_max")
        return cls(**clean)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
            f.write("\n")


def config_path():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # sys.argv[0] is the entry script, so the file sits next to it.
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base, CONFIG_FILENAME)
