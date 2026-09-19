#!/usr/bin/env python3
"""
SP108E Ambilight

Stream screen content to an SP108E LED controller with the
CMD_CUSTOM_PREVIEW protocol and 900-byte frames.

Capture runs in a background thread, in parallel with the wait for the
controller's per-frame acknowledgement. The slower of the two will limit
the frame rate.
"""

import socket
import time
import sys
import signal
import threading
import queue

try:
    import mss
    from PIL import Image, ImageFilter
except ImportError:
    print("pip install mss Pillow")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Controller network address.
CONTROLLER_IP   = "192.168.1.235"
CONTROLLER_PORT = 8189

# Pixel count sent to the controller and used as the frame length.
# 240 fills the strip fully on the triangles.
PIXEL_COUNT = 175

# Upper bound on frame rate; the controller's ack pacing usually caps lower.
TARGET_FPS = 30

# Screen to sample. Accepts three forms:
#   None  -> all monitors combined (virtual desktop)
#   1     -> first physical monitor
#   2     -> second physical monitor, etc.
#   {"top": 0, "left": 0, "width": 1920, "height": 1080}  -> explicit region
# To discover which index maps to which monitor, run:
#   python -c "import mss; [print(i, m) for i, m in enumerate(mss.mss().monitors)]"
CAPTURE_MONITOR = None

# Height of the sampled band, as a fraction of monitor height, centered
# vertically. Larger = more vertical smoothing at slight capture cost.
BAND_FRACTION = 0.03

# Spatial smoothing: Gaussian blur radius along the strip, in LED units.
# Each LED will blend with its neighbours, with smooth falloff weights.
# 0 to disable. Larger = colours spread further along the strip.
SMOOTH_RADIUS = 5

# Temporal smoothing: weight of the new frame in the output (0..1).
# 1.0 = no smoothing. Lower = slower colour changes, less flicker.
TEMPORAL_ALPHA = 0.1

# Set True to mirror the strip, if the LEDs run right-to-left
# relative to the screen.
MIRROR_STRIP = True

# Set True to fill the rest of the 900-byte frame with mirrored repeats
# of the strip. Set False to fill it with black.
ENABLE_PINGPONG = True

# ---- Protocol constants ----------------------------------------------------
CMD_FRAME_START    = 0x38
CMD_FRAME_END      = 0x83
CMD_CUSTOM_PREVIEW = 0x24
CMD_DOT_COUNT      = 0x2D
PREVIEW_FRAME_SIZE = 900
FRAME_PIXELS = PREVIEW_FRAME_SIZE // 3
ACK_BYTE = 0x31


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


def set_dot_count(sock, count):
    packet = bytes([CMD_FRAME_START, count & 0xFF, 0x00,
                    CMD_DOT_COUNT, CMD_FRAME_END])
    sock.sendall(packet)
    time.sleep(0.3)


def enter_preview(sock):
    sock.sendall(make_packet(CMD_CUSTOM_PREVIEW))
    return read_ack(sock)


# ============================================================================
# SCREEN CAPTURE
# ============================================================================

def make_band_region(monitor):
    band_h = max(1, int(monitor["height"] * BAND_FRACTION))
    top = monitor["top"] + (monitor["height"] - band_h) // 2
    return {
        "top":    top,
        "left":   monitor["left"],
        "width":  monitor["width"],
        "height": band_h,
    }


def sample_band(sct, region, target_n, prev_img):
    """Grab the band, average each LED's column, blur, blend with the last frame."""
    shot = sct.grab(region)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    img = img.resize((target_n, 1), Image.Resampling.BOX)
    if MIRROR_STRIP:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if SMOOTH_RADIUS > 0:
        img = img.filter(ImageFilter.GaussianBlur(SMOOTH_RADIUS))
    if prev_img is not None and TEMPORAL_ALPHA < 1.0:
        img = Image.blend(prev_img, img, TEMPORAL_ALPHA)
    return img


def build_frame(colors):
    """Fill the frame with the strip, then mirrored repeats of it or black."""
    colors = list(colors)
    pixels = list(colors)
    if ENABLE_PINGPONG:
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

    def __init__(self, monitor, target_n):
        super().__init__(daemon=True)
        self.monitor = monitor
        self.target_n = target_n
        self._lock = threading.Lock()
        self._frame = None
        self._ready = threading.Event()
        self.stop_event = threading.Event()

    def run(self):
        region = make_band_region(self.monitor)
        prev_img = None
        with mss.MSS() as sct:
            while not self.stop_event.is_set():
                try:
                    img = sample_band(sct, region, self.target_n, prev_img)
                    prev_img = img
                    frame = build_frame(img.getdata())
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
# MAIN
# ============================================================================

def main():
    print(f"SP108E Ambilight -> {CONTROLLER_IP}:{CONTROLLER_PORT}")
    print(f"pixels={PIXEL_COUNT}  blur={SMOOTH_RADIUS}  "
          f"alpha={TEMPORAL_ALPHA}  fps_cap={TARGET_FPS}  "
          f"band={BAND_FRACTION*100:.1f}%")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect((CONTROLLER_IP, CONTROLLER_PORT))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    set_dot_count(sock, PIXEL_COUNT)

    if not enter_preview(sock):
        print("Preview init failed. Power-cycle the controller and retry.")
        sock.close()
        sys.exit(1)

    with mss.MSS() as sct:
        if CAPTURE_MONITOR is None:
            monitor = sct.monitors[0]
        elif isinstance(CAPTURE_MONITOR, int):
            monitor = sct.monitors[CAPTURE_MONITOR]
        else:
            monitor = CAPTURE_MONITOR

    region = make_band_region(monitor)
    print(f"Band: {region['width']}x{region['height']} at y={region['top']}")

    producer = FrameProducer(monitor, PIXEL_COUNT)
    producer.start()
    print("Streaming. Ctrl+C to stop.")

    running = True

    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)

    interval = 1.0 / TARGET_FPS
    frame_count = 0
    last_report = time.time()

    while running:
        loop_start = time.time()

        try:
            frame = producer.get(timeout=1.0)
        except queue.Empty:
            print("Producer stalled.")
            break

        try:
            sock.sendall(frame)
        except Exception as e:
            print(f"Send error: {e}")
            break

        read_ack(sock, timeout=0.5)

        frame_count += 1

        now = time.time()
        if now - last_report >= 5.0:
            elapsed = now - last_report
            fps = frame_count / elapsed
            print(f"[STATS] {fps:5.1f} FPS")
            frame_count = 0
            last_report = now

        elapsed = time.time() - loop_start
        if elapsed < interval:
            time.sleep(interval - elapsed)

    producer.stop()
    sock.close()
    print("Done.")


if __name__ == "__main__":
    main()