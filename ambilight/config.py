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
    # leds used for the screen, from the start of the strip
    pixel_count: int = 175
    target_fps: int = 30
    # number in the monitor list, from 1
    monitor: int = 1
    # gaussian blur along the strip, in leds, 0 = off
    smooth_radius: float = 5.0
    # new frame weight in the blend, 1 = off
    temporal_alpha: float = 0.1
    # for strips wired right to left
    mirror_strip: bool = True
    # led content after pixel_count
    fill_mode: str = "mirror"
    # white balance: max output of r, g, b
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
        if clean.get("monitor", 1) < 1:
            clean.pop("monitor")
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
        # same directory as the entry script
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base, CONFIG_FILENAME)
