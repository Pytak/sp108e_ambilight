"""Capture runs in its own thread, parallel to the wait for the
controller's acknowledgement. The slower of the two sets the frame rate."""

import queue
import socket
import threading
import time

from .capture import FrameProducer, list_monitors
from .protocol import enter_preview, read_ack


class Streamer(threading.Thread):
    """status, fps and error are safe to read from other threads."""

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.status = "Starting"
        self.fps = 0.0
        self.error = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sock = None

    def stop(self):
        self._stop.set()
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass

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

        if self._stop.is_set():
            return

        self.status = "Connecting"
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self._lock:
            self._sock = sock
        try:
            sock.settimeout(5.0)
            sock.connect((cfg.controller_ip, cfg.controller_port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            sock.close()
            with self._lock:
                self._sock = None
            if self._stop.is_set():
                return
            raise RuntimeError("Connection failed.")

        if self._stop.is_set():
            sock.close()
            with self._lock:
                self._sock = None
            return

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
            window_start = time.perf_counter()

            while not self._stop.is_set():
                loop_start = time.perf_counter()

                try:
                    frame = producer.get(timeout=1.0)
                except queue.Empty:
                    raise RuntimeError(producer.error or "Screen capture stalled.")

                try:
                    sock.sendall(frame)
                except OSError as e:
                    if self._stop.is_set():
                        return
                    raise RuntimeError(f"Send error: {e}")

                read_ack(sock, timeout=0.5)
                frame_count += 1

                now = time.perf_counter()
                if now - window_start >= 1.0:
                    self.fps = frame_count / (now - window_start)
                    frame_count = 0
                    window_start = now

                elapsed = time.perf_counter() - loop_start
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        finally:
            if producer is not None:
                producer.stop()
                producer.join(timeout=2)
            sock.close()
            with self._lock:
                self._sock = None
