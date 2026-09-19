#!/usr/bin/env python3
"""
Generate icon.ico for the executable and the window.

A dark rounded tile, a glowing rainbow band across the middle and a row
of LED dots under it. Run this only to change the icon. icon.ico is part
of the repository, and build.bat uses it as it is.
"""

import colorsys
import os

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]
BACKGROUND = (22, 25, 36, 255)


def rainbow(width, height):
    strip = Image.new("RGB", (width, 1))
    px = strip.load()
    for x in range(width):
        hue = 0.83 * x / (width - 1)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
        px[x, 0] = (int(r * 255), int(g * 255), int(b * 255))
    return strip.resize((width, height), Image.Resampling.NEAREST)


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def render(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    tile = Image.new("RGBA", (size, size), BACKGROUND)
    img.paste(tile, mask=rounded_mask((size, size), int(size * 0.22)))

    band_w, band_h = int(size * 0.74), int(size * 0.20)
    band_x, band_y = (size - band_w) // 2, int(size * 0.36)
    band = rainbow(band_w, band_h)
    band_mask = rounded_mask((band_w, band_h), band_h // 2)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow.paste(band, (band_x, band_y), band_mask)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.06))
    glow.putalpha(glow.getchannel("A").point(lambda a: int(a * 0.85)))
    img.alpha_composite(glow)

    sharp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sharp.paste(band, (band_x, band_y), band_mask)
    img.alpha_composite(sharp)

    count = 9
    dot = int(size * 0.055)
    gap = (band_w - count * dot) // (count - 1)
    dot_y = band_y + band_h + int(size * 0.11)
    dots = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dots)
    for i in range(count):
        x = band_x + i * (dot + gap)
        colour = band.getpixel((min(x - band_x + dot // 2, band_w - 1), 0))
        draw.ellipse((x, dot_y, x + dot, dot_y + dot), fill=colour + (255,))
    img.alpha_composite(dots)
    return img


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    render(SIZE).save(out, sizes=ICO_SIZES)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
