import queue
import threading
import time

import numpy as np
from PIL import Image, ImageFilter

from .protocol import build_frame

# 270: max error within 3/255, used to reduce cpu time
_SAMPLE_ROWS = 270


def _import_dxcam():
    # dpi awareness is set during the import, it must follow the gui setup
    import dxcam
    from dxcam.core.dxgi_duplicator import DXGIDuplicator

    def release(self):
        # release on garbage collection only to prevent a double release
        if self.duplicator is not None:
            self.release_frame()
            self.duplicator = None

    DXGIDuplicator.release = release
    return dxcam


def list_monitors():
    factory = getattr(_import_dxcam(), "__factory")
    monitors = []
    for d, outputs in enumerate(factory.outputs):
        for o, output in enumerate(outputs):
            output.update_desc()
            r = output.desc.DesktopCoordinates
            monitors.append({"device": d, "output": o, "left": r.left,
                             "top": r.top, "width": r.right - r.left,
                             "height": r.bottom - r.top})
    return monitors


class DxgiGrabber:
    def __init__(self, monitor, width):
        self.width = width
        self.averages = None
        self.camera = _import_dxcam().create(device_idx=monitor["device"],
                                             output_idx=monitor["output"],
                                             output_color="BGRA")

    def grab(self):
        frame = self.camera.grab(copy=False)
        if frame is not None:
            step = max(1, frame.shape[0] // _SAMPLE_ROWS)
            # bgra to rgb
            self.averages = frame[::step, :, 2::-1].mean(axis=0,
                                                          dtype=np.float32)
        if self.averages is None:
            raise RuntimeError("No desktop frame yet.")
        img = Image.fromarray(self.averages.astype(np.uint8)[np.newaxis])
        return img.resize((self.width, 1), Image.Resampling.BOX)

    def close(self):
        self.camera.release()


def channel_lut(channel_max):
    if list(channel_max) == [255, 255, 255]:
        return None
    return [round(i * m / 255) for m in channel_max for i in range(256)]


def sample_screen(grabber, cfg, prev_img):
    img = grabber.grab()
    if cfg.mirror_strip:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if cfg.smooth_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(cfg.smooth_radius))
    if prev_img is not None and cfg.temporal_alpha < 1.0:
        img = Image.blend(prev_img, img, cfg.temporal_alpha)
    return img


class FrameProducer(threading.Thread):
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
        lut = channel_lut(cfg.channel_max)
        prev_img = None
        try:
            grabber = DxgiGrabber(self.monitor, cfg.pixel_count)
        except Exception as e:
            self.error = f"Screen capture failed: {e}"
            return
        interval = 1.0 / cfg.target_fps
        try:
            while not self.stop_event.is_set():
                start = time.perf_counter()
                try:
                    img = sample_screen(grabber, cfg, prev_img)
                    prev_img = img
                    if lut:
                        img = img.point(lut)
                    frame = build_frame(img.tobytes(), cfg.fill_mode)
                except Exception:
                    # expected on the lock screen and during a mode switch
                    time.sleep(0.01)
                    continue
                with self._lock:
                    self._frame = frame
                    self._ready.set()
                self.stop_event.wait(interval - (time.perf_counter() - start))
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
