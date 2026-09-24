# SP108E Ambilight

Stream the colors of your screen to an SP108E WiFi LED controller in real time.

The app samples the screen, maps it onto the LED strip with some smoothing, and sends it to the controller. It runs over local network as a single Windows executable with no additional dependencies.

## Requirements

- Windows 10 or newer
- An SP108E controller on the same network as your PC
- A strip already configured in the SP108E phone app: chip type, color order, pixels per segment, segments

## Quick start

1. Build `SP108E_Ambilight.exe` (see [Build](#build)) or copy a built one to a folder you can write to.
2. Run it.
3. Enter the controller's IP address. You can find it in your router's client list or in the SP108E app.
4. Set **Pixel count** to the number of LEDs on your strip.
5. Choose the **Monitor** you want to sample.
6. Click **Start**.

FPS shown is the actual framerate of the LED strip as reported by the controller. Cicking **Stop** ends the stream, the controller will return to its previous mode.

Settings are saved to `sp108e_ambilight.json` next to the exe whenever you start a stream or close the app. They're locked while streaming, so click **Stop** first if you want to change something.

## Settings

| Field                           | JSON key          | Default           | Meaning                                                                                                                                                                                     |
| ------------------------------- | ----------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IP address                      | `controller_ip`   | `192.168.1.235`   | IP address of the SP108E                                                                                                                                                                    |
| Port                            | `controller_port` | `8189`            | TCP port. Only change it for firmware that uses a different one.                                                                                                                            |
| Pixel count                     | `pixel_count`     | `175`             | How many LEDs, counted from the start of the strip, display the screen. The rest are filled (see below). Maximum 300. This is independent of the pixel and segment counts in the phone app. |
| Mirror strip                    | `mirror_strip`    | `true`            | Turn on for strips that run right-to-left relative to the screen.                                                                                                                           |
| Fill the rest of the strip with | `fill_mode`       | `mirror`          | What to do with LEDs past the pixel count: `repeat` repeats the frame, `mirror` repeats it mirrored, `none` leaves them black.                                                              |
| Monitor                         | `monitor`         | `0`               | Which screen to capture. `0` treats all monitors as one wide virtual desktop; `1`, `2`, ... to a single physical monitor.                                                                   |
| Target FPS                      | `target_fps`      | `30`              | Local capture frame rate cap.                                                                                                                                                               |
| Blur radius                     | `smooth_radius`   | `5`               | Gaussian blur along the strip, measured in LEDs. `0` to disable it.                                                                                                                         |
| Temporal alpha                  | `temporal_alpha`  | `0.1`             | Transparency of the previous frame on top of the new one. `1.0` turns blending off.                                                                                                         |
| White balance                   | `channel_max`     | `[255, 255, 255]` | Color calibration: maximum output of each channel, R, G, B, scaled linearly. With `[255, 158, 131]`, a grey of `128, 128, 128` is sent as `128, 79, 66`.                                    |

### Behavior

**Blur radius** applies blur around each LED, specified in amount of LEDs. Makes individual LEDs less visible when set higher. 0 to disable (sharpest).

**Temporal alpha** smooths out each frame by overlaying the previous one at the specified transparency. 0.01 is minimum (very slow fading), 1 to disable.

**White balance** controls the max value of each R/G/B channel sent to the strip, match it with your screen's white balance.

### Controller settings

**Pixels per segment**, **Segments**, and **Brightness** are stored in the controller, and shown in the LED Shop Android app. They are loaded at startup (if the IP and port is correct). Click **Read** to refresh them. Click **Set** to send the settings to the controller. They will persist when the controller is swiched off and back on.

**Pixels per segment** and **Segments** should match your actual LED strip setup. If they are wrong, part of the strip will stay dark. Valid ranges: 1–300 and 1–10.

You cannot change these during a stream, click **Stop** to unlock them.

These values are not stored locally and are always re-read from the controller when the app starts.

## Build

Python 3.9 or newer is required to build. The result is a single exe file.

1. Clone or download the repository.
2. Run `build.bat`.

The script installs PyInstaller, mss and Pillow if they're missing, then produces `dist\SP108E_Ambilight.exe`. The settings file is created in the same directory as the executable.

A few things worth knowing:

- The first launch takes a few seconds to unpack Python and dependencies.
- SmartScreen will warn about unsigned executables. Click **More info**, then **Run anyway**.

## Tests

```
pip install mss Pillow
python -m unittest
```

Tests run against a mock controller on localhost. A few windows will open and close when tests are running, this is normal.

## Console version

```
pip install mss Pillow
python sp108e_ambilight.py
```

Uses the same settings file as the GUI app, prints the frame rate every 5 seconds, and stops on `Ctrl+C`. Edit the JSON file to change settings.

## Code layout

| File                      | Contents                                            |
| ------------------------- | --------------------------------------------------- |
| `sp108e_ambilight_gui.py` | The desktop GUI, entry point of the exe             |
| `sp108e_ambilight.py`     | The console version                                 |
| `ambilight/config.py`     | Settings and their JSON file                        |
| `ambilight/protocol.py`   | SP108E commands, status, brightness, preview frames |
| `ambilight/capture.py`    | Monitor list, GDI grabber, capture thread           |
| `ambilight/streamer.py`   | The stream thread that feeds the controller         |
| `icon.ico`                | Icon of the exe and the window                      |
| `build.bat`               | PyInstaller build                                   |
| `tests/`                  | Tests with a fake controller                        |

## How it works

**Start** connects to the controller and enters preview mode. It doesn't change the pixel count, the segments or any other setting stored in the controller — those are only written through **Set**. Configure them in the phone app if you prefer.

For each frame:

1. A GDI `StretchBlt` in HALFTONE mode captures the screen in a background thread. It averages the source pixels belonging to each LED during the copy, so the screen is already downscaled to the pixel count by the time Python sees it. Each LED ends up with the average of its share of the screen.
2. The strip is mirrored if needed.
3. A Gaussian blur is applied along the strip.
4. The result is blended with the previous frame.
5. The data is padded to 900 bytes, using repeats, mirrored repeats or black.
6. The frame is sent, then the app waits for the one-byte acknowledgement.

Capture and sending run in parallel, so whichever is slower determines the frame rate.

## Protocol

Three commands from the SP108E protocol are in use, over TCP port 8189. A command is a 6-byte packet: `0x38`, three data bytes, the command byte, `0x83`. 16-bit values in commands are little-endian, but the same values in the status reply are big-endian.

- `0x10`: read the status. The reply is 17 bytes: on/off, mode, speed, brightness, color order, pixels per segment, segments, color, IC type, number of recorded patterns, white brightness.
- `0x24`: enter preview mode. After this, the controller accepts raw 900-byte RGB frames, each acknowledged with a single `0x31`.
- `0x2A`: set the brightness, `0` to `255`, in the first data byte. Never send it during a preview stream — the controller leaves preview mode and the strip output turns erratic. The app only sends it while stopped, over a separate short connection.
- `0x2D`: pixels per segment, maximum 300.
- `0x2E`: segments.

Configuration values are stored in flash and survive a power cycle. An out-of-range value resets pixels per segment and segments to 60 and 10. Sending any command other than a frame during a preview stream ends preview mode, and the strip behaves erratically until it's restarted. A 5-byte packet is silently ignored, so a wrong packet length can look like a command that works. When the connection closes, the controller returns to its previous mode.

## Troubleshooting

Errors show up in red on the status line.

**Connection failed**: check the IP address, and make sure the PC and controller are on the same network.

**Preview init failed**: power-cycle the controller. This also happens when another client, such as the phone app, is holding the connection.

**Part of the strip is dark**: pixels per segment and segments in the controller don't match your strips. Click **Read**, correct them, then **Set**.

**Controller settings are empty, or brightness shows n/a**: the read at startup failed, usually because the controller was off or the IP address was wrong. Fix the address and click **Read**. Streaming works regardless.

**Wrong colors**: set the color order (RGB, GRB, ...) in the SP108E app. The app always sends RGB. If the colors are right but the white balance is off, use **White balance** (see [color calibration](#color-calibration)).

**Low FPS**: the controller's acknowledgement is usually the bottleneck. If capture is the limit, capture a single monitor instead of all monitors.

**Settings not saved**: the folder is read-only. Move the exe somewhere writable, like your Desktop or Documents.
