#!/usr/bin/env python3
"""
SP108E Ambilight

Stream screen content to an SP108E LED controller with the
CMD_CUSTOM_PREVIEW protocol and 900-byte frames.

Capture runs in a background thread, in parallel with the wait for the
controller's per-frame acknowledgement. The slower of the two will limit
the frame rate.

Run this file directly for the console version. Run
sp108e_ambilight_gui.py for the desktop GUI. Both read and write the same
settings file, sp108e_ambilight.json, next to the program.
"""

import json
import os
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass, asdict, fields

try:
    import mss
    from PIL import Image, ImageFilter
except ImportError:
    print("pip install mss Pillow")
    sys.exit(1)


CONFIG_FILENAME = "sp108e_ambilight.json"

# ---- Protocol constants ----------------------------------------------------
CMD_FRAME_START    = 0x38
CMD_FRAME_END      = 0x83
CMD_GET_STATUS     = 0x10
CMD_CUSTOM_PREVIEW = 0x24
CMD_SET_BRIGHTNESS = 0x2A
PREVIEW_FRAME_SIZE = 900
FRAME_PIXELS = PREVIEW_FRAME_SIZE // 3
STATUS_SIZE = 17
ACK_BYTE = 0x31

# How to fill the LEDs beyond pixel_count, up to FRAME_PIXELS.
FILL_MODES = ("repeat", "mirror", "none")


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    # Network address of the controller.
    controller_ip: str = "192.168.1.235"
    controller_port: int = 8189

    # Number of LEDs in the frame. Maximum FRAME_PIXELS (300).
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
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, CONFIG_FILENAME)


def list_monitors():
    with mss.MSS() as sct:
        return list(sct.monitors)


# ============================================================================
# PROTOCOL
# ============================================================================

def make_packet(cmd, data=b'\x00\x00\x00'):
    return bytes([CMD_FRAME_START]) + data + bytes([cmd, CMD_FRAME_END])


def read_ack(sock, timeout=1.0):
    sock.settimeout(timeout)
    try:
        resp = sock.recv(1)
        return len(resp) == 1 and resp[0] == ACK_BYTE
    except socket.timeout:
        return False


def read_exact(sock, size, timeout=1.0):
    sock.settimeout(timeout)
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def get_status(sock):
    """Return the controller status as a dict, or None on a bad reply."""
    sock.sendall(make_packet(CMD_GET_STATUS))
    try:
        resp = read_exact(sock, STATUS_SIZE)
    except socket.timeout:
        return None
    if (len(resp) != STATUS_SIZE or resp[0] != CMD_FRAME_START
            or resp[-1] != CMD_FRAME_END):
        return None
    return {
        "on":                 resp[1] == 1,
        "mode":               resp[2],
        "speed":              resp[3],
        "brightness":         resp[4],
        "color_order":        resp[5],
        "pixels_per_segment": int.from_bytes(resp[6:8], "big"),
        "segments":           int.from_bytes(resp[8:10], "big"),
        "color":              tuple(resp[10:13]),
        "ic_type":            resp[13],
        "recorded_patterns":  resp[14],
        "white_brightness":   resp[15],
    }


def set_brightness(sock, value):
    data = bytes([max(0, min(255, int(value))), 0x00, 0x00])
    sock.sendall(make_packet(CMD_SET_BRIGHTNESS, data))


def connect(cfg, timeout=5.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((cfg.controller_ip, cfg.controller_port))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError as e:
        sock.close()
        raise RuntimeError(f"Connection failed: {e}")
    return sock


def read_brightness(cfg):
    """Open a short connection and return the brightness stored in the controller."""
    sock = connect(cfg)
    try:
        status = get_status(sock)
    finally:
        sock.close()
    if status is None:
        raise RuntimeError("Status read failed.")
    return status["brightness"]


def write_brightness(cfg, value):
    """Open a short connection, set the brightness and return the value read back.

    Never call this while a stream runs: the controller leaves the preview
    mode when it receives the brightness command.
    """
    sock = connect(cfg)
    try:
        set_brightness(sock, value)
        time.sleep(0.2)
        status = get_status(sock)
    finally:
        sock.close()
    if status is None:
        return int(value)
    return status["brightness"]


def enter_preview(sock):
    sock.sendall(make_packet(CMD_CUSTOM_PREVIEW))
    return read_ack(sock)


# ============================================================================
# SCREEN CAPTURE
# ============================================================================

def make_band_region(monitor, band_fraction):
    band_h = max(1, int(monitor["height"] * band_fraction))
    top = monitor["top"] + (monitor["height"] - band_h) // 2
    return {
        "top":    top,
        "left":   monitor["left"],
        "width":  monitor["width"],
        "height": band_h,
    }


def sample_band(sct, region, cfg, prev_img):
    """Grab the band, average each LED's column, blur, blend with the last frame."""
    shot = sct.grab(region)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    img = img.resize((cfg.pixel_count, 1), Image.Resampling.BOX)
    if cfg.mirror_strip:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if cfg.smooth_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(cfg.smooth_radius))
    if prev_img is not None and cfg.temporal_alpha < 1.0:
        img = Image.blend(prev_img, img, cfg.temporal_alpha)
    return img


def build_frame(colors, fill_mode):
    """Fill the frame with the strip, then repeats, mirrored repeats or black."""
    colors = list(colors)
    pixels = list(colors)
    if fill_mode == "repeat":
        while len(pixels) < FRAME_PIXELS:
            pixels.extend(colors)
    elif fill_mode == "mirror":
        forward = False
        while len(pixels) < FRAME_PIXELS:
            pixels.extend(colors if forward else reversed(colors))
            forward = not forward
    buf = bytearray()
    for r, g, b in pixels[:FRAME_PIXELS]:
        buf.extend((r, g, b))
    buf.extend(bytes(PREVIEW_FRAME_SIZE - len(buf)))
    return bytes(buf)


# ============================================================================
# BACKGROUND CAPTURE THREAD
# ============================================================================

class FrameProducer(threading.Thread):
    """Capture frames continuously and publish the most recent one."""

    def __init__(self, monitor, cfg):
        super().__init__(daemon=True)
        self.monitor = monitor
        self.cfg = cfg
        self._lock = threading.Lock()
        self._frame = None
        self._ready = threading.Event()
        self.stop_event = threading.Event()

    def run(self):
        cfg = self.cfg
        region = make_band_region(self.monitor, cfg.band_fraction)
        prev_img = None
        with mss.MSS() as sct:
            while not self.stop_event.is_set():
                try:
                    img = sample_band(sct, region, cfg, prev_img)
                    prev_img = img
                    frame = build_frame(img.getdata(), cfg.fill_mode)
                except Exception:
                    time.sleep(0.01)
                    continue
                with self._lock:
                    self._frame = frame
                    self._ready.set()

    def get(self, timeout=1.0):
        if not self._ready.wait(timeout=timeout):
            raise queue.Empty
        with self._lock:
            frame = self._frame
            self._ready.clear()
        return frame

    def stop(self):
        self.stop_event.set()


# ============================================================================
# STREAMER
# ============================================================================

class Streamer(threading.Thread):
    """Connect to the controller and stream frames until stop() is called.

    Read `status`, `fps` and `error` from any thread. `error` is None on
    a clean stop and a message on failure.
    """

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.status = "Starting"
        self.fps = 0.0
        self.error = None
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.error = str(e)
        finally:
            self.status = "Stopped"
            self.fps = 0.0

    def _run(self):
        cfg = self.cfg
        monitors = list_monitors()
        if not 0 <= cfg.monitor < len(monitors):
            raise RuntimeError(f"Monitor {cfg.monitor} not found.")

        self.status = "Connecting"
        sock = connect(cfg)

        producer = None
        try:
            if not enter_preview(sock):
                raise RuntimeError(
                    "Preview init failed. Power-cycle the controller and retry.")

            producer = FrameProducer(monitors[cfg.monitor], cfg)
            producer.start()
            self.status = "Streaming"

            interval = 1.0 / cfg.target_fps
            frame_count = 0
            window_start = time.time()

            while not self._stop.is_set():
                loop_start = time.time()

                try:
                    frame = producer.get(timeout=1.0)
                except queue.Empty:
                    raise RuntimeError("Screen capture stalled.")

                try:
                    sock.sendall(frame)
                except OSError as e:
                    raise RuntimeError(f"Send error: {e}")

                read_ack(sock, timeout=0.5)
                frame_count += 1

                now = time.time()
                if now - window_start >= 1.0:
                    self.fps = frame_count / (now - window_start)
                    frame_count = 0
                    window_start = now

                elapsed = time.time() - loop_start
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        finally:
            if producer is not None:
                producer.stop()
                producer.join(timeout=2)
            sock.close()


# ============================================================================
# CONSOLE ENTRY POINT
# ============================================================================

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
