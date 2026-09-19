"""The stream thread: connect, enter the preview mode, send frames, report fps.

Capture runs in its own thread (FrameProducer), in parallel with the wait
for the controller's per-frame acknowledgement. The slower of the two will
limit the frame rate.
"""

import queue
import threading
import time

from .capture import FrameProducer, list_monitors
from .protocol import connect, enter_preview, read_ack


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
