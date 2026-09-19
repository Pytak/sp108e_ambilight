# SP108E Ambilight

Stream the colours of your screen to an SP108E WiFi LED controller in real time.

The script will take a thin horizontal band from the middle of the screen, map it to the LED strip with smoothing, and send it to the controller at up to 30 frames per second. You do not need a cloud service or extra hardware.

## Requirements

- Python 3.9 or newer
- An SP108E controller on the same network as your PC
- An LED strip already configured in the SP108E app: pixel count, chip type, colour order

Install the two dependencies:

```
pip install mss Pillow
```

## Quick start

1. Find the IP address of your controller in your router's client list or in the SP108E app.
2. Open `sp108e_ambilight.py` and set `CONTROLLER_IP`.
3. Set `PIXEL_COUNT` to the number of LEDs on your strip.
4. Run the script:

```
python sp108e_ambilight.py
```

The strip will show the screen colours immediately. Press `Ctrl+C` to stop. The controller will go back to its previous mode.

## Configuration

All settings are constants at the top of the script.

| Setting           | Default         | Description                                                                                            |
| ----------------- | --------------- | ------------------------------------------------------------------------------------------------------ |
| `CONTROLLER_IP`   | `192.168.1.235` | IP address of the SP108E                                                                               |
| `CONTROLLER_PORT` | `8189`          | TCP port. Change it only for a firmware with a different port.                                         |
| `PIXEL_COUNT`     | `240`           | Number of LEDs in the frame. Maximum 300.                                                              |
| `TARGET_FPS`      | `30`            | Upper limit for the frame rate. The acknowledgement from the controller will usually limit it further. |
| `CAPTURE_MONITOR` | `None`          | Screen to sample. See below.                                                                           |
| `BAND_FRACTION`   | `0.03`          | Height of the sampled band as a fraction of the screen height, centred vertically.                     |
| `SMOOTH_RADIUS`   | `0`             | Spatial smoothing. Gaussian blur radius along the strip, in LEDs. Set `0` to disable.                  |
| `TEMPORAL_ALPHA`  | `0.1`           | Temporal smoothing. Weight of the new frame in the output, `0` to `1`. Set `1.0` to disable.           |
| `MIRROR_STRIP`    | `True`          | Set `True` to mirror the strip, for LEDs that run right-to-left relative to the screen.                |
| `ENABLE_PINGPONG` | `True`          | Set `True` to fill the rest of the frame with mirrored repeats of the strip. Set `False` to fill it with black. |

### Monitor selection

Set `CAPTURE_MONITOR` to one of three forms:

- `None`: all monitors combined into one wide virtual desktop
- `1`, `2`, ...: one physical monitor, by index
- `{"top": 0, "left": 0, "width": 1920, "height": 1080}`: an explicit pixel region

To list your monitors with their indices, run:

```
python -c "import mss; [print(i, m) for i, m in enumerate(mss.mss().monitors)]"
```

### Smoothing

Two independent settings control the look of the strip.

Use `SMOOTH_RADIUS` to blur the colours along the strip with a Gaussian falloff. A higher value will give a softer gradient. Try `3` for a sharp result or `12` for a very soft one.

Use `TEMPORAL_ALPHA` to blend each new frame with the previous one. A lower value will give slower colour changes and less flicker. A higher value will make the strip react faster to scene cuts. At `0.1` the strip will need about 20 frames to reach a new colour. At `0.5`, about 3.

The two settings do not interact. Adjust one at a time.

## How it works

1. Capture of a thin band of the screen in a background thread, with `mss`.
2. Resize of the band to `PIXEL_COUNT` columns with a box filter. The result for each LED is the exact average of its part of the screen.
3. Optional mirror of the strip (`MIRROR_STRIP`).
4. Gaussian blur along the strip (`SMOOTH_RADIUS`).
5. Blend with the previous frame (`TEMPORAL_ALPHA`).
6. Fill of the rest of the 900-byte frame. With `ENABLE_PINGPONG`, the fill is mirrored repeats of the strip: forward, then reversed, then forward again. Without it, the fill is black.
7. Transmission of the newest frame from the main thread, then a wait for the one-byte acknowledgement from the controller.

Capture and transmission run in parallel. The slower of the two will limit the frame rate.

## Protocol notes

Two commands of the SP108E protocol are in use, over TCP port 8189:

- `0x2D`: set the pixel count
- `0x24`: enter the custom preview mode. After it, the controller will accept raw 900-byte RGB frames.

When the connection closes, the controller will leave the preview mode and go back to its previous mode.

**Warning.** The controller will save configuration changes, such as the pixel count, to flash memory. A malformed configuration packet can overwrite a saved value, and the change will survive a power cycle. If part of your strip is dark after a change to the protocol code, open the SP108E app and set the pixel count again.

## Troubleshooting

**`Connection failed`**: Check `CONTROLLER_IP`. Make sure that your PC and the controller are on the same network.

**`Preview init failed`**: Power-cycle the controller and try again. This error will also appear if another client, for example the phone app, has an open connection to the controller.

**Part of the strip is dark**: The saved pixel count in the controller is lower than the LED count of your strip. Set it in the SP108E app.

**Wrong colours**: Set the colour order (RGB, GRB, ...) in the SP108E app. The script output is always RGB.

**Low FPS**: The `[STATS]` line will print the frame rate every 5 seconds. The acknowledgement from the controller is the usual limit. Reduce `BAND_FRACTION` or `PIXEL_COUNT` if capture is the limit.
