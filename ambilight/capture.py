import ctypes
import queue
import threading
import time
from ctypes import wintypes

import mss
from PIL import Image, ImageFilter

from .protocol import build_frame


def list_monitors():
    with mss.MSS() as sct:
        return list(sct.monitors)


def make_band_region(monitor, band_fraction):
    band_h = max(1, int(monitor["height"] * band_fraction))
    top = monitor["top"] + (monitor["height"] - band_h) // 2
    return {
        "top":    top,
        "left":   monitor["left"],
        "width":  monitor["width"],
        "height": band_h,
    }


# ---- GDI -------------------------------------------------------------------

_user32 = ctypes.WinDLL("user32")
_gdi32 = ctypes.WinDLL("gdi32")
_user32.GetDC.restype = ctypes.c_void_p
_user32.GetDC.argtypes = [ctypes.c_void_p]
_user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
_gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
_gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
_gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_int]
_gdi32.SelectObject.restype = ctypes.c_void_p
_gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
_gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
_gdi32.SetStretchBltMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
_gdi32.SetBrushOrgEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_void_p]
_gdi32.StretchBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, wintypes.DWORD]
_gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                             wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.UINT]

_SRCCOPY = 0x00CC0020
_HALFTONE = 4


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class GdiGrabber:
    """HALFTONE makes GDI average the source pixels, so the downscale to
    width x 1 happens inside the copy."""

    def __init__(self, region, width):
        self.region = region
        self.width = width
        self.src = _user32.GetDC(None)
        self.mem = _gdi32.CreateCompatibleDC(self.src)
        self.bmp = _gdi32.CreateCompatibleBitmap(self.src, width, 1)
        if not (self.src and self.mem and self.bmp):
            self.close()
            raise RuntimeError("GDI initialisation failed.")
        _gdi32.SelectObject(self.mem, self.bmp)
        _gdi32.SetStretchBltMode(self.mem, _HALFTONE)
        _gdi32.SetBrushOrgEx(self.mem, 0, 0, None)
        self.bmi = _BITMAPINFO()
        header = self.bmi.bmiHeader
        header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -1
        header.biPlanes = 1
        header.biBitCount = 32
        self.buf = ctypes.create_string_buffer(width * 4)

    def grab(self):
        r = self.region
        ok = _gdi32.StretchBlt(self.mem, 0, 0, self.width, 1, self.src,
                               r["left"], r["top"], r["width"], r["height"],
                               _SRCCOPY)
        if not ok:
            raise RuntimeError("StretchBlt failed.")
        lines = _gdi32.GetDIBits(self.mem, self.bmp, 0, 1, self.buf,
                                 ctypes.byref(self.bmi), 0)
        if lines != 1:
            raise RuntimeError("GetDIBits failed.")
        return Image.frombytes("RGB", (self.width, 1), self.buf.raw,
                               "raw", "BGRX")

    def close(self):
        # Also called from a half-finished __init__.
        if getattr(self, "bmp", None):
            _gdi32.DeleteObject(self.bmp)
        if getattr(self, "mem", None):
            _gdi32.DeleteDC(self.mem)
        if getattr(self, "src", None):
            _user32.ReleaseDC(None, self.src)
        self.bmp = self.mem = self.src = None


# ---- processing ------------------------------------------------------------

def sample_band(grabber, cfg, prev_img):
    img = grabber.grab()
    if cfg.mirror_strip:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if cfg.smooth_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(cfg.smooth_radius))
    if prev_img is not None and cfg.temporal_alpha < 1.0:
        img = Image.blend(prev_img, img, cfg.temporal_alpha)
    return img


class FrameProducer(threading.Thread):
    """Keeps only the newest frame."""

    def __init__(self, monitor, cfg):
        super().__init__(daemon=True)
        self.monitor = monitor
        self.cfg = cfg
        self.error = None
        self._lock = threading.Lock()
        self._frame = None
        self._ready = threading.Event()
        self.stop_event = threading.Event()

    def run(self):
        cfg = self.cfg
        region = make_band_region(self.monitor, cfg.band_fraction)
        prev_img = None
        try:
            grabber = GdiGrabber(region, cfg.pixel_count)
        except Exception as e:
            self.error = f"Screen capture failed: {e}"
            return
        try:
            while not self.stop_event.is_set():
                try:
                    img = sample_band(grabber, cfg, prev_img)
                    prev_img = img
                    frame = build_frame(img.tobytes(), cfg.fill_mode)
                except Exception:
                    # will fall on a lock screen or during a mode switch.
                    time.sleep(0.01)
                    continue
                with self._lock:
                    self._frame = frame
                    self._ready.set()
        finally:
            grabber.close()

    def get(self, timeout=1.0):
        if not self._ready.wait(timeout=timeout):
            raise queue.Empty
        with self._lock:
            frame = self._frame
            self._ready.clear()
        return frame

    def stop(self):
        self.stop_event.set()
