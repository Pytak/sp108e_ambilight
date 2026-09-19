#!/usr/bin/env python3
"""
SP108E Ambilight, console version.

Stream screen content to an SP108E LED controller. Run
sp108e_ambilight_gui.py for the desktop GUI. Both read and write the same
settings file, sp108e_ambilight.json, next to the program.
"""

import os
import sys
import time

try:
    import mss  # noqa: F401
    import PIL  # noqa: F401
except ImportError:
    print("pip install mss Pillow")
    sys.exit(1)

from ambilight.config import Config, config_path
from ambilight.streamer import Streamer


def main():
    path = config_path()
    cfg = Config.load(path)
    if not os.path.exists(path):
        cfg.save(path)

    print(f"SP108E Ambilight -> {cfg.controller_ip}:{cfg.controller_port}")
    print(f"Settings: {path}")
    print(f"pixels={cfg.pixel_count}  blur={cfg.smooth_radius}  "
          f"alpha={cfg.temporal_alpha}  fps_cap={cfg.target_fps}  "
          f"band={cfg.band_fraction * 100:.1f}%  monitor={cfg.monitor}")

    streamer = Streamer(cfg)
    streamer.start()
    print("Streaming. Ctrl+C to stop.")

    try:
        ticks = 0
        while streamer.is_alive():
            time.sleep(1.0)
            ticks += 1
            if ticks % 5 == 0 and streamer.status == "Streaming":
                print(f"[STATS] {streamer.fps:5.1f} FPS")
    except KeyboardInterrupt:
        pass

    streamer.stop()
    streamer.join(timeout=3)
    if streamer.error:
        print(streamer.error)
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
