# SP108E Ambilight

Stream the colours of your screen to an SP108E WiFi LED controller in real time.

The program will take a thin horizontal band from the middle of the screen, map it to the LED strip with smoothing, and send it to the controller at up to 30 frames per second. It is a single Windows executable. You do not need Python, a cloud service or extra hardware to run it.

## Requirements

- Windows 10 or newer
- An SP108E controller on the same network as your PC
- An LED strip already configured in the SP108E app: pixel count, chip type, colour order

## Quick start

1. Build `SP108E_Ambilight.exe` (see [Build](#build)) or copy a built one to a folder of your choice.
2. Start the program.
3. Find the IP address of your controller in your router's client list or in the SP108E app, and enter it in the **IP address** field.
4. Set **Pixel count** to the number of LEDs on your strip.
5. Select the **Monitor** to capture.
6. Click **Start**.

The strip will show the screen colours immediately, and the meter at the bottom will show the frame rate. Click **Stop** to end the stream. The controller will go back to its previous mode.

The program will save all settings to `sp108e_ambilight.json` in its own folder, on **Start** and on close. Settings are locked while the stream runs. Click **Stop** to change them.

## Settings

| Field in the GUI | Key in the JSON file | Default | Description |
| --- | --- | --- | --- |
| IP address | `controller_ip` | `192.168.1.235` | IP address of the SP108E |
| Port | `controller_port` | `8189` | TCP port. Change it only for a firmware with a different port. |
| Pixel count | `pixel_count` | `175` | Number of LEDs in the frame. Maximum 300. |
| Mirror strip | `mirror_strip` | `true` | Set on for LEDs that run right-to-left relative to the screen. |
| Fill the rest of the strip with | `fill_mode` | `mirror` | Content for the LEDs beyond the pixel count, up to 300. `repeat`: repeats of the strip. `mirror`: mirrored repeats, forward then reversed. `none`: black. |
| Monitor | `monitor` | `0` | Screen to capture. `0` is all monitors combined into one wide virtual desktop. `1`, `2`, ... is one physical monitor. |
| Band height | `band_fraction` | `0.03` | Height of the sampled band as a fraction of the screen height, centred vertically. The GUI shows it in percent. |
| Target FPS | `target_fps` | `30` | Upper limit for the frame rate. The acknowledgement from the controller will usually limit it further. |
| Blur radius | `smooth_radius` | `5` | Spatial smoothing. Gaussian blur radius along the strip, in LEDs. Set `0` to disable. |
| Temporal alpha | `temporal_alpha` | `0.1` | Temporal smoothing. Weight of the new frame in the output, `0` to `1`. Set `1.0` to disable. |

### Smoothing

Two independent settings control the look of the strip.

Use **Blur radius** to blur the colours along the strip with a Gaussian falloff. A higher value will give a softer gradient. Try `3` for a sharp result or `12` for a very soft one.

Use **Temporal alpha** to blend each new frame with the previous one. A lower value will give slower colour changes and less flicker. A higher value will make the strip react faster to scene cuts. At `0.1` the strip will need about 20 frames to reach a new colour. At `0.5`, about 3.

The two settings do not interact. Adjust one at a time.

## Build

The build needs Python 3.9 or newer on the build machine only. The result is a self-contained executable.

1. Clone or download this repository.
2. Run `build.bat`.

The script will install PyInstaller, mss and Pillow if they are missing, then produce `dist\SP108E_Ambilight.exe`. Copy that one file wherever you want. It will create its settings file next to itself on first start.

Notes:

- The first start of a one-file executable will take a few seconds, because it unpacks itself to a temporary folder.
- Windows SmartScreen may show a warning for an unsigned executable. Choose **More info**, then **Run anyway**.
- `icon.ico` is the icon of the executable and the window. To change it, edit and run `make_icon.py`, then build again.

## Console version

The same code will also run without the GUI:

```
pip install mss Pillow
python sp108e_ambilight.py
```

It will read the same `sp108e_ambilight.json`, create it with default values if it does not exist, print the frame rate every 5 seconds, and stop on `Ctrl+C`. Edit the JSON file to change settings.

## How it works

1. Capture of a thin band of the screen in a background thread, with `mss`.
2. Resize of the band to the pixel count with a box filter. The result for each LED is the exact average of its part of the screen.
3. Optional mirror of the strip.
4. Gaussian blur along the strip.
5. Blend with the previous frame.
6. Fill of the rest of the 900-byte frame, with repeats of the strip, mirrored repeats, or black.
7. Transmission of the newest frame, then a wait for the one-byte acknowledgement from the controller.

Capture and transmission run in parallel. The slower of the two will limit the frame rate.

## Protocol notes

Two commands of the SP108E protocol are in use, over TCP port 8189:

- `0x2D`: set the pixel count
- `0x24`: enter the custom preview mode. After it, the controller will accept raw 900-byte RGB frames.

When the connection closes, the controller will leave the preview mode and go back to its previous mode.

**Warning.** The controller will save configuration changes, such as the pixel count, to flash memory. A malformed configuration packet can overwrite a saved value, and the change will survive a power cycle. If part of your strip is dark after a change to the protocol code, open the SP108E app and set the pixel count again.

## Troubleshooting

Errors appear in red in the status line at the bottom of the window.

**Connection failed**: Check the IP address. Make sure that your PC and the controller are on the same network.

**Preview init failed**: Power-cycle the controller and try again. This error will also appear if another client, for example the phone app, has an open connection to the controller.

**Part of the strip is dark**: The saved pixel count in the controller is lower than the LED count of your strip. Set it in the SP108E app.

**Wrong colours**: Set the colour order (RGB, GRB, ...) in the SP108E app. The program output is always RGB.

**Low FPS**: The acknowledgement from the controller is the usual limit. Reduce **Band height** or **Pixel count** if capture is the limit.

**Settings not saved**: The program cannot write to its own folder. Move it to a folder where you have write access, for example your Desktop or Documents.
