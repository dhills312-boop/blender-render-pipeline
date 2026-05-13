"""Generate a white/black ombre hair atlas and a visible preview sheet.

This script is designed for hair-card textures with mostly-black backgrounds.
It preserves the source alpha and only recolors visible strand/card pixels.
"""

from __future__ import annotations

import argparse
from array import array
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--preview", required=True)
    return p.parse_args(argv)


def save_image(name: str, width: int, height: int, pixels: array, out_path: str):
    img = bpy.data.images.new(name, width, height, alpha=True)
    img.pixels.foreach_set(pixels)
    img.update()
    img.colorspace_settings.name = "sRGB"
    img.filepath_raw = out_path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def main():
    args = parse_args()
    src = bpy.data.images.load(args.src, check_existing=True)
    w, h = src.size
    n_pixels = w * h

    pixels = array("f", [0.0]) * (n_pixels * 4)
    src.pixels.foreach_get(pixels)

    out_pixels = array("f", [0.0]) * (n_pixels * 4)
    preview_pixels = array("f", [0.0]) * (n_pixels * 4)

    preview_bg = 0.42

    for y in range(h):
        # We want roots at the top of the image to be white and tips at the
        # bottom to be black. In Blender image storage, y=0 is the bottom row.
        root_factor = y / max(1, h - 1)

        for x in range(w):
            idx = (y * w + x) * 4
            r = pixels[idx]
            g = pixels[idx + 1]
            b = pixels[idx + 2]
            a = pixels[idx + 3]

            # Preserve the existing strand/card shading without letting fully
            # black background pixels dominate the result.
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

            # Only visible pixels get recolored. Leave black background black.
            if a > 0.02 or lum > 0.02:
                # White roots -> black tips, with source luminance used as local
                # shading so strand breakup stays visible.
                target = root_factor
                shade = 0.55 + (lum * 0.65)
                value = max(0.0, min(1.0, target * shade))
            else:
                value = 0.0

            out_pixels[idx] = value
            out_pixels[idx + 1] = value
            out_pixels[idx + 2] = value
            out_pixels[idx + 3] = a

            # Composite onto a mid-gray background so the preview is actually
            # readable outside Blender.
            preview_rgb = (value * a) + (preview_bg * (1.0 - a))
            preview_pixels[idx] = preview_rgb
            preview_pixels[idx + 1] = preview_rgb
            preview_pixels[idx + 2] = preview_rgb
            preview_pixels[idx + 3] = 1.0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    os.makedirs(os.path.dirname(args.preview), exist_ok=True)

    save_image("WhiteBlackOmbre", w, h, out_pixels, args.out)
    save_image("WhiteBlackOmbrePreview", w, h, preview_pixels, args.preview)

    print(f"SAVED_ATLAS: {args.out}")
    print(f"SAVED_PREVIEW: {args.preview}")

    bpy.data.images.remove(src)


if __name__ == "__main__":
    main()
