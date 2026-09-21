# SP108E Ambilight

Stream your screen's colours to an SP108E WiFi LED controller in real time.

The app samples a thin horizontal band from the middle of the screen, maps it onto the LED strip with some smoothing, and sends it to the controller at up to 30 frames per second — in practice the controller's own acknowledgement usually caps it lower. It runs over local network and ships as a single Windows executable with no additional dependencies.

## Requirements

- Windows 10 or newer
- An SP108E controller on the same network as your PC
- A strip already configured in the SP108E phone app: chip type, colour order, pixels per segment, segments

## Quick start

1. Build `SP108E_Ambilight.exe` (see [Build](#build)) or copy a built one to a folder you can write to.
2. Run it.
3. Enter the controller's IP address. You can find it in your router's client list or in the SP108E app.
4. Set **Pixel count** to the number of LEDs on your strip.
5. Choose the **Monitor** you want to sample.
6. Click **Start**.

The strip shows the screen colours immediately, and the meter at the bottom shows the current frame rate. **Stop** ends the stream, and the controller returns to whatever mode it was in before.

Settings are saved to `sp108e_ambilight.json` next to the exe whenever you start a stream or close the app. They're locked while streaming, so click **Stop** first if you want to change something.

## Settings

| Field                           | JSON key          | Default           | Meaning                                                                                                                                                                                         |
| ------------------------------- | ----------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IP address                      | `controller_ip`   | `192.168.1.235`   | IP address of the SP108E                                                                                                                                                                        |
| Port                            | `controller_port` | `8189`            | TCP port. Only change it for firmware that uses a different one.                                                                                                                                |
| Pixel count                     | `pixel_count`     | `175`             | How many LEDs, counted from the start of the strip, display the screen band. The rest show the fill (below). Maximum 300. This is independent of the pixel and segment counts in the phone app. |
| Mirror strip                    | `mirror_strip`    | `true`            | Turn on for strips that run right-to-left relative to the screen.                                                                                                                               |
| Fill the rest of the strip with | `fill_mode`       | `mirror`          | What the LEDs past the pixel count show: `repeat` repeats the strip, `mirror` repeats it forwards then reversed, `none` leaves them black.                                                      |
| Monitor                         | `monitor`         | `0`               | Which screen to capture. `0` treats all monitors as one wide virtual desktop; `1`, `2`, ... selects a single physical monitor.                                                                  |
| Band height                     | `band_fraction`   | `0.03`            | Height of the sampled band as a fraction of screen height, centred vertically. The GUI shows it as a percentage.                                                                                |
| Target FPS                      | `target_fps`      | `30`              | Frame rate cap. The controller usually imposes a lower one anyway.                                                                                                                              |
| Blur radius                     | `smooth_radius`   | `5`               | Gaussian blur along the strip, measured in LEDs. `0` disables it.                                                                                                                               |
| Temporal alpha                  | `temporal_alpha`  | `0.1`             | How much weight a new frame gets when blended with the previous one. `1.0` turns blending off.                                                                                                  |
| (JSON only)                     | `channel_max`     | `[255, 255, 255]` | Colour calibration: the maximum output of each channel, R, G, B. Colours are scaled linearly. With `[255, 158, 131]`, a grey of `128, 128, 128` is sent as `128, 79, 66`.                       |

### Smoothing

**Blur radius** controls how soft the gradient along the strip looks. Try `3` for a sharp result, `12` for something very soft.

**Temporal alpha** controls how quickly colours change and how much they flicker. Lower values mean slower changes and less flicker; higher values react faster to scene cuts. At `0.1`, a new colour takes about 20 frames to settle; at `0.5`, about 3.

The two settings are independent, so adjust one at a time.

### Colour calibration

Some strips have channels that are brighter than others, which throws off whites and pastels. The `channel_max` setting in the JSON file scales each channel individually: it gives the value that should be treated as full output for red, green and blue. Leave it at `[255, 255, 255]` for no correction.

It's JSON-only, so edit the file while the app isn't streaming, and remember it's saved back on the next start or close.

### Controller settings

**Pixels per segment**, **Segments** and **Brightness** live in the controller itself, and the phone app shows the same values. The app reads them at startup; **Read** fetches them again — handy after a change in the phone app. To change one, edit the value and click the **Set** button on that row. The controller saves it, so it survives a power cycle and shows up in the phone app too. Brightness isn't part of the settings file.

Pixels per segment and segments describe your physical strips. If they're wrong, part of the strip stays dark. The valid ranges are 1–300 and 1–10. If you see 60 and 10, the controller has reset to its defaults and you'll need to set your values again.

These fields are locked during a stream, because sending a configuration command ends preview mode. Every **Set** writes to the controller's flash, exactly like changing a value in the phone app, so only values that have actually changed are sent.

## Build

You only need Python 3.9 or newer on the build machine. The result is self-contained.

1. Clone or download the repository.
2. Run `build.bat`.

The script installs PyInstaller, mss and Pillow if they're missing, then produces `dist\SP108E_Ambilight.exe`. Copy that one file wherever you like; it creates its settings file next to itself.

A few things worth knowing:

- The first launch takes a few seconds, because a one-file exe has to unpack itself to a temporary folder.
- SmartScreen warns about unsigned executables. Click **More info**, then **Run anyway**.
- `icon.ico` is used for both the exe and the window. To change it, edit and run `make_icon.py`, then build again.

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

It reads the same `sp108e_ambilight.json`, creating it with default values if it doesn't exist, prints the frame rate every 5 seconds, and stops on `Ctrl+C`. Edit the JSON file to change settings.

## Code layout

| File                      | Contents                                               |
| ------------------------- | ------------------------------------------------------ |
| `sp108e_ambilight_gui.py` | The desktop GUI, entry point of the exe                |
| `sp108e_ambilight.py`     | The console version                                    |
| `ambilight/config.py`     | Settings and their JSON file                           |
| `ambilight/protocol.py`   | SP108E commands, status, brightness, preview frames    |
| `ambilight/capture.py`    | Monitor list, band region, GDI grabber, capture thread |
| `ambilight/streamer.py`   | The stream thread that feeds the controller            |
| `make_icon.py`            | Generates `icon.ico`; run by hand only                 |
| `icon.ico`                | Icon of the exe and the window                         |
| `build.bat`               | PyInstaller build                                      |
| `tests/`                  | Tests with a fake controller                           |

## How it works

**Start** connects to the controller and enters preview mode. It doesn't change the pixel count, the segments or any other setting stored in the controller — those are only written through **Set**. Configure them in the phone app if you prefer.

For each frame:

1. A GDI `StretchBlt` in HALFTONE mode captures the band in a background thread. It averages the source pixels belonging to each LED during the copy, so the band is already downscaled to the pixel count by the time Python sees it. Each LED ends up with the average of its share of the screen.
2. The strip is mirrored if needed.
3. A Gaussian blur is applied along the strip.
4. The result is blended with the previous frame.
5. The data is padded to 900 bytes, using repeats, mirrored repeats or black.
6. The frame is sent, then the app waits for the one-byte acknowledgement.

Capture and sending run in parallel, so whichever is slower determines the frame rate.

## Protocol

Three commands from the SP108E protocol are in use, over TCP port 8189. A command is a 6-byte packet: `0x38`, three data bytes, the command byte, `0x83`. 16-bit values in commands are little-endian, but the same values in the status reply are big-endian.

- `0x10`: read the status. The reply is 17 bytes: on/off, mode, speed, brightness, colour order, pixels per segment, segments, colour, IC type, number of recorded patterns, white brightness.
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

**Wrong colours**: set the colour order (RGB, GRB, ...) in the SP108E app. The app always sends RGB. If the colours are right but the white balance is off, use `channel_max` (see [Colour calibration](#colour-calibration)).

**Low FPS**: the controller's acknowledgement is usually the bottleneck. If capture is the limit, a smaller band height or pixel count will help.

**Settings not saved**: the folder is read-only. Move the exe somewhere writable, like your Desktop or Documents.
