# SP108E Ambilight

Displays your screen's colors on an SP108E LED strip in real time.

The app samples a horizontal band from the middle of the screen, maps it onto the strip with some smoothing, and streams it to the controller at around 40 frames per second. It ships as a single Windows executable.

## Requirements

- Windows 10 or newer
- An SP108E controller on the same network as your PC
- A strip already configured in the SP108E app (chip type, color order, pixels per segment, segments)

## Quick start

1. Build `SP108E_Ambilight.exe` (see [Build](#build)) and put it wherever you like.
2. Run it.
3. Enter the controller's IP address. You can find it in your router's client list or in the SP108E app.
4. Set **Pixel count** to the number of LEDs on your strip.
5. Choose the **Monitor** you want to sample.
6. Click **Start**.

The meter shows the current frame rate. **Stop** ends the stream and the controller goes back to whatever mode it was in before. Settings are saved to `sp108e_ambilight.json` beside the exe whenever you start a stream or close the app, and they're locked while streaming.

## Settings

| Field                           | JSON key          | Default           | Meaning                                                                                                                                                            |
| ------------------------------- | ----------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| IP address                      | `controller_ip`   | `192.168.1.235`   | IP address of the SP108E                                                                                                                                           |
| Port                            | `controller_port` | `8189`            | TCP port                                                                                                                                                           |
| Pixel count                     | `pixel_count`     | `175`             | Number of LEDs that display the screen band, counted from the start of the strip. Max 300. This is independent of the pixel count in the phone app.                |
| Mirror strip                    | `mirror_strip`    | `true`            | Enable for strips that run right to left                                                                                                                           |
| Fill the rest of the strip with | `fill_mode`       | `mirror`          | What to do with the LEDs beyond the pixel count: `repeat`, `mirror` (forward, then reversed) or `none` (black)                                                     |
| Monitor                         | `monitor`         | `0`               | `0` treats all monitors as one desktop; `1`, `2`, ... selects a single monitor                                                                                     |
| Band height                     | `band_fraction`   | `0.03`            | Height of the sampled band as a fraction of screen height, centred vertically. Shown as a percentage in the GUI.                                                   |
| Target FPS                      | `target_fps`      | `30`              | Frame rate cap. The controller usually imposes a lower one anyway.                                                                                                 |
| Blur radius                     | `smooth_radius`   | `5`               | Gaussian blur along the strip, measured in LEDs. `0` disables it.                                                                                                  |
| Temporal alpha                  | `temporal_alpha`  | `0.1`             | How much weight the new frame gets when blended with the previous one. `1.0` turns blending off.                                                                   |
| (JSON only)                     | `channel_max`     | `[255, 255, 255]` | Color calibration: the maximum output of each channel, R, G, B. Colors are scaled linearly. With `[255, 158, 131]`, grey `128, 128, 128` is sent as `128, 79, 66`. |

### Smoothing

**Blur radius** controls how soft the gradient along the strip looks. Try `3` for a sharp result, `12` for something very soft.

**Temporal alpha** controls how quickly colors change and how much they flicker. Lower values mean slower changes and less flicker; higher values react faster to scene cuts. At `0.1` a new color takes about 20 frames to settle, at `0.5` about 3.

### Controller settings

**Pixels per segment**, **Segments** and **Brightness** are stored in the controller itself, and the phone app shows the same values. The app reads them at startup; **Read** fetches them again. To change one, edit the value and click the **Set** button on that row. The controller saves it.

Pixels per segment and segments describe your physical strips. If they're wrong, part of the strip stays dark. The valid ranges are 1–300 and 1–10. If you see 60 and 10, the controller has reset to its defaults and you'll need to set your values again.

These fields are locked during a stream because sending a configuration command ends preview mode. Every **Set** writes to the controller's flash, exactly like changing a value in the phone app. Only values that have actually changed are sent.

## Build

You'll need Python 3.9 or newer on the build machine.

1. Clone the repository.
2. Run `build.bat`.

The result is `dist\SP108E_Ambilight.exe`. You can copy that single file anywhere; it creates its settings file next to itself.

- The first launch takes a few seconds because a one-file exe has to unpack itself.
- SmartScreen will warn you about an unsigned executable. Click **More info**, then **Run anyway**.
- `icon.ico` is used as both the exe icon and the window icon.

## Tests

```
pip install mss Pillow
python -m unittest
```

A fake controller on `localhost` stands in for the SP108E, so the tests run on any Windows PC. The GUI test opens a hidden window for a few seconds.

## Console version

```
pip install mss Pillow
python sp108e_ambilight.py
```

It uses the same settings file as the GUI and prints the frame rate every 5 seconds. `Ctrl+C` stops it.

## Code layout

| File                      | Content                                 |
| ------------------------- | --------------------------------------- |
| `sp108e_ambilight_gui.py` | GUI, entry point of the exe             |
| `sp108e_ambilight.py`     | Console version                         |
| `ambilight/config.py`     | Settings and their JSON file            |
| `ambilight/protocol.py`   | SP108E commands, status, preview frames |
| `ambilight/capture.py`    | Screen capture                          |
| `ambilight/streamer.py`   | Stream thread                           |
| `icon.ico`                | Icon of the exe and the window          |
| `build.bat`               | PyInstaller build                       |
| `tests/`                  | Tests with a fake controller            |

## How it works

For each frame:

1. A GDI `StretchBlt` in HALFTONE mode copies the band and averages it down to one pixel per LED.
2. The strip is mirrored if needed.
3. A Gaussian blur is applied along the strip.
4. The result is blended with the previous frame.
5. The data is padded to 900 bytes, using repeats, mirrored repeats or black.
6. It's sent, then the app waits for the one-byte acknowledgement.

Capture and sending run in parallel, so whichever is slower determines the frame rate. **Start** only enters preview mode. Controller settings are only changed through **Set**.

## Protocol

TCP port 8189. A command is 6 bytes: `0x38`, three data bytes, the command byte, `0x83`. 16-bit values in commands are little-endian, but the same values in the status reply are big-endian.

- `0x10`: status. 17 bytes: on/off, mode, speed, brightness, color order, pixels per segment, segments, color, IC type, recorded patterns, white brightness.
- `0x24`: preview mode. After this, 900-byte RGB frames follow, each acknowledged with a single `0x31`.
- `0x2A`: brightness, `0` to `255`, in the first data byte.
- `0x2D`: pixels per segment, max 300.
- `0x2E`: segments.

Configuration values are stored in flash and survive a power cycle. An out-of-range value resets pixels per segment and segments to 60 and 10. Sending any command other than a frame during a preview stream ends preview mode and the strip will behave erratically. A 5-byte packet is silently ignored. When the connection closes, the controller returns to its previous mode.

## Troubleshooting

Errors show up in red on the status line.

**Connection failed**: check the IP address, and make sure the PC and controller are on the same network.

**Preview init failed**: power-cycle the controller. Another client, such as the phone app, may be holding the connection.

**Part of the strip is dark**: pixels per segment and segments in the controller don't match your strips. Click **Read**, correct them, then **Set**.

**Controller settings are empty**: the read at startup failed. Fix the IP address and click **Read**.

**Wrong colors**: set the color order in the SP108E app. This app sends RGB.

**Low FPS**: the controller's acknowledgement is usually the bottleneck. If capture is the limit, a smaller band height or pixel count will help.

**Settings not saved**: the folder is read-only. Move the exe somewhere writable, like your Desktop or Documents.
