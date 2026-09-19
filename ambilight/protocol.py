"""SP108E wire protocol: packets, status, brightness and preview frames.

Each command is a 6-byte packet: 0x38, three data bytes, the command,
0x83. A 16-bit value in a command is little-endian (low byte first); the
same values in the status reply are big-endian. The controller ignores a
5-byte packet without an error. A value outside the range the firmware
accepts makes it reset pixels per segment and segments to defaults (60
and 10 on the firmware seen here).

Never send a command other than a preview frame while a preview stream
runs. The controller leaves the preview mode and the strip goes erratic.
"""

import socket
import time

CMD_FRAME_START    = 0x38
CMD_FRAME_END      = 0x83
CMD_GET_STATUS     = 0x10
CMD_CUSTOM_PREVIEW = 0x24
CMD_SET_BRIGHTNESS = 0x2A
CMD_SET_DOT_COUNT  = 0x2D
CMD_SET_SEGMENTS   = 0x2E
PREVIEW_FRAME_SIZE = 900
FRAME_PIXELS = PREVIEW_FRAME_SIZE // 3
STATUS_SIZE = 17
ACK_BYTE = 0x31


# ---- packets ---------------------------------------------------------------

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


def _u16_packet(cmd, value):
    """16-bit value, low byte first. The status reply uses the opposite order."""
    value = max(0, min(0xFFFF, int(value)))
    return make_packet(cmd, bytes([value & 0xFF, value >> 8, 0x00]))


def drain(sock, timeout=0.3):
    """Discard any bytes the controller sent that nobody asked for."""
    sock.settimeout(timeout)
    try:
        while sock.recv(64):
            pass
    except (socket.timeout, OSError):
        pass


def set_dot_count(sock, pixels_per_segment):
    sock.sendall(_u16_packet(CMD_SET_DOT_COUNT, pixels_per_segment))


def set_segments(sock, segments):
    sock.sendall(_u16_packet(CMD_SET_SEGMENTS, segments))


def enter_preview(sock):
    sock.sendall(make_packet(CMD_CUSTOM_PREVIEW))
    return read_ack(sock)


# ---- connections -----------------------------------------------------------

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


def read_settings(cfg):
    """Open a short connection and return the status dict of the controller."""
    sock = connect(cfg)
    try:
        status = get_status(sock)
    finally:
        sock.close()
    if status is None:
        raise RuntimeError("Status read failed.")
    return status


def write_settings(cfg, pixels_per_segment=None, segments=None,
                   brightness=None):
    """Open a short connection, send the given values, return the status read back.

    Each value is one write to the flash memory of the controller. Send
    only values that differ from the current status. Never call this while
    a stream runs.
    """
    sock = connect(cfg)
    try:
        if pixels_per_segment is not None:
            set_dot_count(sock, pixels_per_segment)
            time.sleep(0.3)
        if segments is not None:
            set_segments(sock, segments)
            time.sleep(0.3)
        if brightness is not None:
            set_brightness(sock, brightness)
            time.sleep(0.2)
        drain(sock)
        status = get_status(sock)
    finally:
        sock.close()
    if status is None:
        raise RuntimeError("Status read failed after the write.")
    return status


# ---- preview frames --------------------------------------------------------

def build_frame(rgb, fill_mode):
    """Fill the frame with the strip, then repeats, mirrored repeats or black.

    `rgb` is the raw RGB byte string of the strip, 3 bytes per pixel.
    """
    data = bytes(rgb)
    pixels = bytearray(data)
    if data and fill_mode == "repeat":
        while len(pixels) < PREVIEW_FRAME_SIZE:
            pixels += data
    elif data and fill_mode == "mirror":
        reverse = b"".join(data[i:i + 3] for i in range(len(data) - 3, -1, -3))
        forward = False
        while len(pixels) < PREVIEW_FRAME_SIZE:
            pixels += data if forward else reverse
            forward = not forward
    del pixels[PREVIEW_FRAME_SIZE:]
    pixels += bytes(PREVIEW_FRAME_SIZE - len(pixels))
    return bytes(pixels)
