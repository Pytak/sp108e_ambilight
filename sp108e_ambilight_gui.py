#!/usr/bin/env python3
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from ambilight.capture import list_monitors
from ambilight.config import Config, FILL_MODES, config_path
from ambilight.protocol import FRAME_PIXELS, read_settings, write_settings
from ambilight.streamer import Streamer

POLL_MS = 250
PAD = {"padx": 6, "pady": 3}
FILL_LABELS = {"repeat": "repeats", "mirror": "mirrored repeats",
               "none": "nothing"}


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def resource_path(name):
    # location of bundled files in a pyinstaller build
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def monitor_label(number, mon):
    return (f"Monitor {number} ({mon['width']}x{mon['height']} "
            f"at {mon['left']},{mon['top']})")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SP108E Ambilight")
        self.resizable(False, False)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except tk.TclError:
            pass
        self.config_path = config_path()
        self.cfg = Config.load(self.config_path)
        self.monitors = list_monitors()
        self.streamer = None
        self.inputs = []
        self._results = queue.Queue()
        self._controller_busy = False
        self._device = None
        self._build()
        self._show(self.cfg)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._timers = [
            self.after(POLL_MS, self._poll),
            self.after(200, lambda: self._read_controller(silent=True)),
        ]

    def destroy(self):
        for timer in self._timers:
            self.after_cancel(timer)
        super().destroy()

    def _build(self):
        root = ttk.Frame(self, padding=10)
        root.grid(sticky="nsew")

        self.v_ip = tk.StringVar()
        self.v_port = tk.StringVar()
        self.v_pixels = tk.StringVar()
        self.v_fps = tk.StringVar()
        self.v_radius = tk.StringVar()
        self.v_alpha = tk.StringVar()
        self.v_mirror = tk.BooleanVar()
        self.v_white = [tk.StringVar() for _ in range(3)]

        conn = self._section(root, "Controller", 0)
        self._entry(conn, 0, "IP address", self.v_ip)
        self._spin(conn, 1, "Port", self.v_port, 1, 65535, 1)

        ctl = self._section(root, "Controller Settings", 1)
        # true during the brightness slider and box sync
        self._syncing = False
        self.v_seg_pixels = tk.StringVar()
        self.v_segments = tk.StringVar()
        self.v_bright = tk.DoubleVar(value=0)
        self.v_bright_text = tk.StringVar()

        counts = ttk.Frame(ctl)
        counts.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(counts, text="Pixels per segment").grid(row=0, column=0,
                                                          sticky="w", **PAD)
        self.ent_seg_pixels = ttk.Spinbox(counts, from_=1, to=300, increment=1,
                                          width=6,
                                          textvariable=self.v_seg_pixels)
        self.ent_seg_pixels.grid(row=0, column=1, **PAD)
        ttk.Label(counts, text="Segments").grid(row=0, column=2, sticky="w",
                                                **PAD)
        self.ent_segments = ttk.Spinbox(counts, from_=1, to=10, increment=1,
                                        width=4, textvariable=self.v_segments)
        self.ent_segments.grid(row=0, column=3, **PAD)
        counts.columnconfigure(4, weight=1)
        self.btn_read_counts = ttk.Button(counts, text="Read", width=6,
                                          command=self._read_controller)
        self.btn_read_counts.grid(row=0, column=5, **PAD)
        self.btn_set_counts = ttk.Button(counts, text="Set", width=6,
                                         command=self._set_counts)
        self.btn_set_counts.grid(row=0, column=6, **PAD)

        bright = ttk.Frame(ctl)
        bright.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(bright, text="Brightness").grid(row=0, column=0, sticky="w",
                                                  **PAD)
        self.scale = ttk.Scale(bright, from_=0, to=255, orient="horizontal",
                               variable=self.v_bright,
                               command=self._on_slider_move)
        self.scale.grid(row=0, column=1, sticky="ew", **PAD)
        self.ent_bright = ttk.Spinbox(bright, from_=0, to=255, increment=1,
                                      width=5, textvariable=self.v_bright_text)
        self.ent_bright.grid(row=0, column=2, **PAD)
        self.v_bright_text.trace_add("write", self._on_text_change)
        bright.columnconfigure(1, weight=1)
        self.btn_read = ttk.Button(bright, text="Read", width=6,
                                   command=self._read_controller)
        self.btn_read.grid(row=0, column=3, **PAD)
        self.btn_set = ttk.Button(bright, text="Set", width=6,
                                  command=self._set_brightness)
        self.btn_set.grid(row=0, column=4, **PAD)

        self.controller_controls = [
            self.ent_seg_pixels, self.ent_segments,
            self.btn_read_counts, self.btn_set_counts,
            self.scale, self.ent_bright, self.btn_read, self.btn_set]

        strip = self._section(root, "Strip", 2)
        self._spin(strip, 0, "Frame width", self.v_pixels,
                   1, FRAME_PIXELS, 1)
        self._check(strip, 1, "Mirror strip (LEDs run right to left)",
                    self.v_mirror)
        self.cb_fill = ttk.Combobox(
            strip, state="readonly", width=18,
            values=[FILL_LABELS[m] for m in FILL_MODES])
        self._row(strip, 2, "Fill the rest of the strip with", self.cb_fill)
        self.inputs.append((self.cb_fill, "readonly"))

        cap = self._section(root, "Capture", 3)
        self.cb_monitor = ttk.Combobox(
            cap, state="readonly", width=36,
            values=[monitor_label(i, m)
                    for i, m in enumerate(self.monitors, start=1)])
        self._row(cap, 0, "Monitor", self.cb_monitor)
        self.inputs.append((self.cb_monitor, "readonly"))
        self._spin(cap, 1, "Target FPS", self.v_fps, 1, 240, 1)

        behavior = self._section(root, "Behavior", 4)
        self._spin(behavior, 0, "Blur radius (LEDs, 0 to disable)",
                   self.v_radius, 0, 100, 0.5)
        self._spin(behavior, 1, "Temporal alpha (1.0 to disable)",
                   self.v_alpha, 0.01, 1.0, 0.05)
        white = ttk.Frame(behavior)
        for col, var in enumerate(self.v_white):
            self._make_spin(white, var, 0, 255, 1, 5).grid(
                row=0, column=col, padx=(0 if col == 0 else 6, 0))
        self._row(behavior, 2, "White balance (R, G, B)", white)

        bottom = ttk.Frame(root)
        bottom.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(1, weight=1)

        self.btn = ttk.Button(bottom, text="Start", width=12,
                              command=self._toggle)
        self.btn.grid(row=0, column=0, rowspan=2, sticky="w")

        self.v_meter = tk.StringVar(value="0.0 FPS")
        ttk.Label(bottom, textvariable=self.v_meter, anchor="e",
                  font=("Segoe UI", 18, "bold")).grid(row=0, column=1,
                                                      sticky="e")

        self.v_status = tk.StringVar(value="Stopped")
        self.lbl_status = ttk.Label(bottom, textvariable=self.v_status,
                                    anchor="e", justify="right",
                                    wraplength=320)
        self.lbl_status.grid(row=1, column=1, sticky="e")

    def _section(self, parent, title, row):
        frame = ttk.LabelFrame(parent, text=title, padding=(8, 4))
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        frame.columnconfigure(1, weight=1)
        return frame

    def _row(self, parent, row, label, widget):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w",
                                           **PAD)
        widget.grid(row=row, column=1, sticky="ew", **PAD)

    def _entry(self, parent, row, label, var):
        widget = ttk.Entry(parent, textvariable=var, width=20)
        self._row(parent, row, label, widget)
        self.inputs.append((widget, "normal"))

    def _make_spin(self, parent, var, lo, hi, step, width):
        widget = ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                             increment=step, width=width)
        widget.bind("<FocusOut>",
                    lambda _e, v=var, a=lo, b=hi: self._clamp(v, a, b))
        self.inputs.append((widget, "normal"))
        return widget

    def _spin(self, parent, row, label, var, lo, hi, step):
        self._row(parent, row, label,
                  self._make_spin(parent, var, lo, hi, step, 10))

    @staticmethod
    def _clamp(var, lo, hi):
        try:
            n = type(lo)(var.get())
        except (ValueError, TypeError):
            var.set(str(lo))
            return
        var.set(str(max(lo, min(hi, n))))

    def _check(self, parent, row, text, var):
        widget = ttk.Checkbutton(parent, text=text, variable=var)
        widget.grid(row=row, column=0, columnspan=2, sticky="w", **PAD)
        self.inputs.append((widget, "normal"))

    def _set_inputs(self, enabled):
        for widget, active_state in self.inputs:
            widget.configure(state=active_state if enabled else "disabled")

    def _show(self, cfg):
        self.v_ip.set(cfg.controller_ip)
        self.v_port.set(str(cfg.controller_port))
        self.v_pixels.set(str(cfg.pixel_count))
        self.v_fps.set(str(cfg.target_fps))
        self.v_radius.set(f"{cfg.smooth_radius:g}")
        self.v_alpha.set(f"{cfg.temporal_alpha:g}")
        self.v_mirror.set(cfg.mirror_strip)
        for var, value in zip(self.v_white, cfg.channel_max):
            var.set(str(value))
        self.cb_fill.current(FILL_MODES.index(cfg.fill_mode))
        if 1 <= cfg.monitor <= len(self.monitors):
            self.cb_monitor.current(cfg.monitor - 1)

    def _read(self):
        try:
            cfg = Config(
                controller_ip=self.v_ip.get().strip(),
                controller_port=int(self.v_port.get()),
                pixel_count=int(self.v_pixels.get()),
                target_fps=int(self.v_fps.get()),
                monitor=self.cb_monitor.current() + 1,
                smooth_radius=float(self.v_radius.get()),
                temporal_alpha=float(self.v_alpha.get()),
                mirror_strip=self.v_mirror.get(),
                fill_mode=FILL_MODES[max(self.cb_fill.current(), 0)],
                channel_max=[int(v.get()) for v in self.v_white],
            )
        except ValueError:
            raise ValueError("One of the number fields is not valid.")

        if not cfg.controller_ip:
            raise ValueError("Enter the IP address of the controller.")
        if not 1 <= cfg.controller_port <= 65535:
            raise ValueError("Port must be 1 to 65535.")
        if not 1 <= cfg.pixel_count <= FRAME_PIXELS:
            raise ValueError(f"Frame width must be 1 to {FRAME_PIXELS}.")
        if not 1 <= cfg.target_fps <= 240:
            raise ValueError("Target FPS must be 1 to 240.")
        if cfg.monitor < 1:
            raise ValueError("Select a monitor.")
        if cfg.smooth_radius < 0:
            raise ValueError("Blur radius must be 0 or more.")
        if not 0 < cfg.temporal_alpha <= 1:
            raise ValueError("Temporal alpha must be more than 0 and at most 1.")
        if not all(0 <= v <= 255 for v in cfg.channel_max):
            raise ValueError("White balance values must be 0 to 255.")
        return cfg

    def _save(self, cfg):
        try:
            cfg.save(self.config_path)
        except OSError as e:
            messagebox.showwarning(
                "Settings not saved",
                f"Cannot write {self.config_path}\n\n{e}")

    def _show_brightness(self, value):
        self._syncing = True
        try:
            self.v_bright.set(int(value))
            self.v_bright_text.set(str(int(value)))
        finally:
            self._syncing = False

    def _show_device(self, status):
        self._device = status
        self.v_seg_pixels.set(str(status["pixels_per_segment"]))
        self.v_segments.set(str(status["segments"]))
        self._show_brightness(status["brightness"])

    def _on_slider_move(self, value):
        if not self._syncing:
            self._show_brightness(int(float(value)))

    def _on_text_change(self, *_):
        if self._syncing:
            return
        text = self.v_bright_text.get().strip()
        if text.isdigit() and 0 <= int(text) <= 255:
            self._syncing = True
            try:
                self.v_bright.set(int(text))
            finally:
                self._syncing = False

    @staticmethod
    def _int_field(var, lo, hi, name):
        text = var.get().strip()
        if not text.isdigit() or not lo <= int(text) <= hi:
            raise ValueError(f"{name} must be a whole number from {lo} to {hi}.")
        return int(text)

    def _set_controller_controls(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget in self.controller_controls:
            widget.configure(state=state)

    def _connection_fields(self):
        ip = self.v_ip.get().strip()
        try:
            port = int(self.v_port.get())
        except ValueError:
            port = 0
        if not ip or not 1 <= port <= 65535:
            raise ValueError("Enter a valid IP address and port first.")
        return Config(controller_ip=ip, controller_port=port)

    def _read_controller(self, silent=False):
        try:
            cfg = self._connection_fields()
        except ValueError as e:
            if not silent:
                messagebox.showerror("Controller settings", str(e))
            return
        self._run_controller_job(lambda: read_settings(cfg),
                                 "Reading controller settings",
                                 "Controller read failed")

    def _set_counts(self):
        try:
            cfg = self._connection_fields()
            pixels = self._int_field(self.v_seg_pixels, 1, 300,
                                     "Pixels per segment")
            segments = self._int_field(self.v_segments, 1, 10, "Segments")
        except ValueError as e:
            messagebox.showerror("Controller settings", str(e))
            return
        changes = {}
        if self._device is None or pixels != self._device["pixels_per_segment"]:
            changes["pixels_per_segment"] = pixels
        if self._device is None or segments != self._device["segments"]:
            changes["segments"] = segments
        if not changes:
            self.v_status.set("Pixels and segments unchanged")
            return
        self._run_controller_job(lambda: write_settings(cfg, **changes),
                                 "Setting pixels and segments",
                                 "Controller set failed")

    def _set_brightness(self):
        try:
            cfg = self._connection_fields()
            value = self._int_field(self.v_bright_text, 0, 255, "Brightness")
        except ValueError as e:
            messagebox.showerror("Controller settings", str(e))
            return
        if self._device is not None and value == self._device["brightness"]:
            self.v_status.set("Brightness unchanged")
            return
        self._run_controller_job(lambda: write_settings(cfg, brightness=value),
                                 "Setting brightness", "Controller set failed")

    def _run_controller_job(self, job, busy_text, error_prefix):
        if self._controller_busy:
            return
        if self.streamer is not None and self.streamer.is_alive():
            return
        self._controller_busy = True
        self._set_controller_controls(False)
        self.lbl_status.configure(foreground="")
        self.v_status.set(busy_text)

        def worker():
            try:
                self._results.put(("device", job()))
            except Exception as e:
                self._results.put(("error", f"{error_prefix}: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_results(self):
        while True:
            try:
                kind, payload = self._results.get_nowait()
            except queue.Empty:
                break
            self._controller_busy = False
            if kind == "device":
                self._show_device(payload)
                self.lbl_status.configure(foreground="")
                self.v_status.set("Stopped")
            else:
                self.lbl_status.configure(foreground="red")
                self.v_status.set(payload)
            streaming = self.streamer is not None and self.streamer.is_alive()
            self._set_controller_controls(not streaming)

    def _toggle(self):
        if self.streamer is not None and self.streamer.is_alive():
            self.streamer.stop()
            self.v_status.set("Stopping")
            return
        if self._controller_busy:
            messagebox.showinfo(
                "Controller settings",
                "Wait for the controller operation to finish.")
            return
        try:
            cfg = self._read()
        except ValueError as e:
            messagebox.showerror("Settings", str(e))
            return
        self.cfg = cfg
        self._save(cfg)
        self.lbl_status.configure(foreground="")
        self.streamer = Streamer(cfg)
        self.streamer.start()
        self._set_inputs(False)
        self._set_controller_controls(False)
        self.btn.configure(text="Stop")

    def _poll(self):
        self._drain_results()
        streamer = self.streamer
        if streamer is not None:
            if streamer.is_alive():
                self.v_status.set(streamer.status)
                self.v_meter.set(f"{streamer.fps:.1f} FPS")
            else:
                self.streamer = None
                self._set_inputs(True)
                if not self._controller_busy:
                    self._set_controller_controls(True)
                self.btn.configure(text="Start")
                self.v_meter.set("0.0 FPS")
                if streamer.error:
                    self.lbl_status.configure(foreground="red")
                    self.v_status.set(streamer.error)
                else:
                    self.v_status.set("Stopped")
        self._timers[0] = self.after(POLL_MS, self._poll)

    def _on_close(self):
        if self.streamer is not None and self.streamer.is_alive():
            self.streamer.stop()
            self.streamer.join(timeout=3)
        try:
            self.cfg = self._read()
        except ValueError:
            pass
        self._save(self.cfg)
        self.destroy()


def main():
    enable_dpi_awareness()
    App().mainloop()


if __name__ == "__main__":
    main()
