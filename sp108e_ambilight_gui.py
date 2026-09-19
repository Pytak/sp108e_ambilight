#!/usr/bin/env python3
"""
SP108E Ambilight desktop GUI.

Start and stop the stream, edit all settings, and watch the frame rate.
Settings are saved to sp108e_ambilight.json next to the program.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import sp108e_ambilight as engine

POLL_MS = 250
PAD = {"padx": 6, "pady": 3}
FILL_LABELS = {"repeat": "repeats", "mirror": "mirrored repeats",
               "none": "nothing"}


def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def monitor_label(index, mon):
    size = f"{mon['width']}x{mon['height']}"
    if index == 0:
        return f"All monitors ({size})"
    return f"Monitor {index} ({size} at {mon['left']},{mon['top']})"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SP108E Ambilight")
        self.resizable(False, False)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except tk.TclError:
            pass
        self.config_path = engine.config_path()
        self.cfg = engine.Config.load(self.config_path)
        self.monitors = engine.list_monitors()
        self.streamer = None
        self.inputs = []
        self._build()
        self._show(self.cfg)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._poll)

    # ---- layout ---------------------------------------------------------

    def _build(self):
        root = ttk.Frame(self, padding=10)
        root.grid(sticky="nsew")

        self.v_ip = tk.StringVar()
        self.v_port = tk.StringVar()
        self.v_pixels = tk.StringVar()
        self.v_fps = tk.StringVar()
        self.v_band = tk.StringVar()
        self.v_radius = tk.StringVar()
        self.v_alpha = tk.StringVar()
        self.v_mirror = tk.BooleanVar()

        conn = self._section(root, "Controller", 0)
        self._entry(conn, 0, "IP address", self.v_ip)
        self._spin(conn, 1, "Port", self.v_port, 1, 65535, 1)

        strip = self._section(root, "Strip", 1)
        self._spin(strip, 0, "Pixel count", self.v_pixels,
                   1, engine.FRAME_PIXELS, 1)
        self._check(strip, 1, "Mirror strip (LEDs run right to left)",
                    self.v_mirror)
        self.cb_fill = ttk.Combobox(
            strip, state="readonly", width=18,
            values=[FILL_LABELS[m] for m in engine.FILL_MODES])
        self._row(strip, 2, "Fill the rest of the strip with", self.cb_fill)
        self.inputs.append((self.cb_fill, "readonly"))

        cap = self._section(root, "Capture", 2)
        self.cb_monitor = ttk.Combobox(
            cap, state="readonly", width=36,
            values=[monitor_label(i, m) for i, m in enumerate(self.monitors)])
        self._row(cap, 0, "Monitor", self.cb_monitor)
        self.inputs.append((self.cb_monitor, "readonly"))
        self._spin(cap, 1, "Band height (% of screen)", self.v_band, 1, 100, 1)
        self._spin(cap, 2, "Target FPS", self.v_fps, 1, 240, 1)

        smooth = self._section(root, "Smoothing", 3)
        self._spin(smooth, 0, "Blur radius (LEDs, 0 to disable)",
                   self.v_radius, 0, 100, 0.5)
        self._spin(smooth, 1, "Temporal alpha (1.0 to disable)",
                   self.v_alpha, 0.01, 1.0, 0.05)

        bottom = ttk.Frame(root)
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
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

    def _spin(self, parent, row, label, var, lo, hi, step):
        widget = ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                             increment=step, width=10)
        self._row(parent, row, label, widget)
        self.inputs.append((widget, "normal"))

    def _check(self, parent, row, text, var):
        widget = ttk.Checkbutton(parent, text=text, variable=var)
        widget.grid(row=row, column=0, columnspan=2, sticky="w", **PAD)
        self.inputs.append((widget, "normal"))

    def _set_inputs(self, enabled):
        for widget, active_state in self.inputs:
            widget.configure(state=active_state if enabled else "disabled")

    # ---- config <-> widgets --------------------------------------------

    def _show(self, cfg):
        self.v_ip.set(cfg.controller_ip)
        self.v_port.set(str(cfg.controller_port))
        self.v_pixels.set(str(cfg.pixel_count))
        self.v_fps.set(str(cfg.target_fps))
        self.v_band.set(f"{cfg.band_fraction * 100:g}")
        self.v_radius.set(f"{cfg.smooth_radius:g}")
        self.v_alpha.set(f"{cfg.temporal_alpha:g}")
        self.v_mirror.set(cfg.mirror_strip)
        self.cb_fill.current(engine.FILL_MODES.index(cfg.fill_mode))
        index = cfg.monitor if 0 <= cfg.monitor < len(self.monitors) else 0
        self.cb_monitor.current(index)

    def _read(self):
        try:
            cfg = engine.Config(
                controller_ip=self.v_ip.get().strip(),
                controller_port=int(self.v_port.get()),
                pixel_count=int(self.v_pixels.get()),
                target_fps=int(self.v_fps.get()),
                monitor=self.cb_monitor.current(),
                band_fraction=float(self.v_band.get()) / 100.0,
                smooth_radius=float(self.v_radius.get()),
                temporal_alpha=float(self.v_alpha.get()),
                mirror_strip=self.v_mirror.get(),
                fill_mode=engine.FILL_MODES[max(self.cb_fill.current(), 0)],
            )
        except ValueError:
            raise ValueError("One of the number fields is not valid.")

        if not cfg.controller_ip:
            raise ValueError("Enter the IP address of the controller.")
        if not 1 <= cfg.controller_port <= 65535:
            raise ValueError("Port must be 1 to 65535.")
        if not 1 <= cfg.pixel_count <= engine.FRAME_PIXELS:
            raise ValueError(f"Pixel count must be 1 to {engine.FRAME_PIXELS}.")
        if not 1 <= cfg.target_fps <= 240:
            raise ValueError("Target FPS must be 1 to 240.")
        if cfg.monitor < 0:
            raise ValueError("Select a monitor.")
        if not 0 < cfg.band_fraction <= 1:
            raise ValueError("Band height must be 1 to 100 percent.")
        if cfg.smooth_radius < 0:
            raise ValueError("Blur radius must be 0 or more.")
        if not 0 < cfg.temporal_alpha <= 1:
            raise ValueError("Temporal alpha must be more than 0 and at most 1.")
        return cfg

    def _save(self, cfg):
        try:
            cfg.save(self.config_path)
        except OSError as e:
            messagebox.showwarning(
                "Settings not saved",
                f"Cannot write {self.config_path}\n\n{e}")

    # ---- start / stop --------------------------------------------------

    def _toggle(self):
        if self.streamer is not None and self.streamer.is_alive():
            self.streamer.stop()
            self.v_status.set("Stopping")
            return
        try:
            cfg = self._read()
        except ValueError as e:
            messagebox.showerror("Settings", str(e))
            return
        self.cfg = cfg
        self._save(cfg)
        self.lbl_status.configure(foreground="")
        self.streamer = engine.Streamer(cfg)
        self.streamer.start()
        self._set_inputs(False)
        self.btn.configure(text="Stop")

    def _poll(self):
        streamer = self.streamer
        if streamer is not None:
            if streamer.is_alive():
                self.v_status.set(streamer.status)
                self.v_meter.set(f"{streamer.fps:.1f} FPS")
            else:
                self.streamer = None
                self._set_inputs(True)
                self.btn.configure(text="Start")
                self.v_meter.set("0.0 FPS")
                if streamer.error:
                    self.lbl_status.configure(foreground="red")
                    self.v_status.set(streamer.error)
                else:
                    self.v_status.set("Stopped")
        self.after(POLL_MS, self._poll)

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
