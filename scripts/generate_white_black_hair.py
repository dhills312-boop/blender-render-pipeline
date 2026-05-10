"""Convert Purple.png hair texture to a white-roots → black-tips ombre,
preserving strand detail.

Approach:
1. Load Purple.png pixels (via Blender's image system since these are
   pre-existing assets, not the failure-prone case)
2. Compute per-pixel luminance (preserves strand highlights/shadows)
3. Generate a vertical gradient: V=0 (top) -> 0 (white roots, bright)
   V=1 (bottom) -> dark
4. Combine: output = luminance * gradient_factor + invert_luminance for
   highlight preservation
5. Save as Asset_Addon_Library/HairCards/WhiteBlackOmbre.png

We're writing to the asset library directly so the texture is reusable.

Run:
    blender -b -P generate_white_black_hair.py -- \
        --src "<purple.png>" --out "<whiteblackombre.png>"
"""
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
    return p.parse_args(argv)


def main():
    args = parse_args()
    print(f"SRC: {args.src}")
    print(f"OUT: {args.out}")

    # Load source.
    src = bpy.data.images.load(args.src)
    w, h = src.size
    print(f"Loaded: {w}x{h}")

    n_pixels = w * h
    pixels = array("f", [0.0]) * (n_pixels * 4)
    src.pixels.foreach_get(pixels)

    # For each pixel, compute luminance and remap based on Y position.
    # We want: roots (top, V=1 in image space which is row 0 from top) = white,
    # tips (bottom, V=0 = row h-1) = black, with strand detail preserved.
    new_pixels = array("f", [0.0]) * (n_pixels * 4)

    for y in range(h):
        # Image is stored bottom-up in Blender (V=0 at row 0).
        # In texture-as-displayed space, "top of image" = high V = row h-1.
        # Hair textures: roots are at TOP of the strip (= high V).
        # So gradient: V near 1 = root = white, V near 0 = tip = black.
        v_norm = y / max(1, h - 1)  # 0 at bottom row, 1 at top row
        # Smooth ombre: white at top, black at bottom, midpoint around 0.5
        # Use a soft-step: top 60% transitions, bottom 40% solid.
        gradient_brightness = v_norm  # 0=tip=black, 1=root=white

        for x in range(w):
            idx = (y * w + x) * 4
            r = pixels[idx + 0]
            g = pixels[idx + 1]
            b = pixels[idx + 2]
            a = pixels[idx + 3]

            # Luminance (preserves strand structure).
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

            # Blend: gradient sets the base value, lum modulates within +-0.3
            # so strand highlights/shadows stay visible.
            base = gradient_brightness
            # Modulate: pixels brighter than mid-gray stay bright relative,
            # darker stay dark.
            modulation = (lum - 0.5) * 0.6  # +-0.3 range
            value = max(0.0, min(1.0, base + modulation))

            new_pixels[idx + 0] = value
            new_pixels[idx + 1] = value
            new_pixels[idx + 2] = value
            new_pixels[idx + 3] = a

    # Write out as a new image.
    out_img = bpy.data.images.new(
        os.path.basename(args.out).replace(".png", ""),
        w, h, alpha=True
    )
    out_img.pixels.foreach_set(new_pixels)
    out_img.update()
    out_img.colorspace_settings.name = "sRGB"
    out_img.filepath_raw = args.out
    out_img.file_format = "PNG"
    out_img.save()
    print(f"\nSaved: {args.out} ({os.path.getsize(args.out)} bytes)")

    bpy.data.images.remove(src)
    bpy.data.images.remove(out_img)


if __name__ == "__main__":
    main()
