"""Overwrite Torso_Decals_1k.png and Torso_Decals_4k.png with actual
white pixels using PIL/Pillow (Blender's image save chain produced black).

Also reloads the image inside the .blend so the in-memory data matches.

Run:
    blender -b a6_v10_skin_shader_rebuilt.blend -P fix_torso_decals_white.py -- \
        --out-blend <path>
"""
import argparse
import os
import sys
import struct
import zlib
import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    return p.parse_args(argv)


def write_white_png(path, size):
    """Write a fully-white PNG using only stdlib (no PIL dependency)."""
    width = height = size

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
        )

    # PNG signature.
    out = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, bit depth=8, color type=2 (RGB), compression=0,
    # filter=0, interlace=0.
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    out += chunk(b"IHDR", ihdr)
    # IDAT: each row prefixed with filter byte 0, then 3 bytes per pixel = white.
    raw = b""
    row = b"\x00" + b"\xff\xff\xff" * width  # filter 0 + RGB white pixels
    for _ in range(height):
        raw += row
    out += chunk(b"IDAT", zlib.compress(raw, 9))
    out += chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(out)


def main():
    args = parse_args()
    tex_dir = os.path.join(
        os.path.dirname(bpy.data.filepath), "textures"
    )

    path_1k = os.path.join(tex_dir, "Torso_Decals_1k.png")
    path_4k = os.path.join(tex_dir, "Torso_Decals_4k.png")

    print(f"Writing white PNGs:")
    print(f"  {path_1k} (1024x1024)")
    print(f"  {path_4k} (1024x1024)")
    write_white_png(path_1k, 1024)
    write_white_png(path_4k, 1024)
    print(f"  done. Sizes: 1k={os.path.getsize(path_1k)}, "
          f"4k={os.path.getsize(path_4k)} bytes")

    # Force-reload the in-Blender image data block.
    img = bpy.data.images.get("Torso_Decals")
    if img:
        # Make sure it's pointing at the disk file, not embedded data.
        if img.packed_file:
            try:
                img.unpack(method="REMOVE")
            except Exception:
                pass
        img.source = "FILE"
        img.filepath = "//textures/Torso_Decals_1k.png"
        img.colorspace_settings.name = "sRGB"
        img.reload()
        print(f"Reloaded {img.name}: {list(img.size)}")
    else:
        print("WARN: Torso_Decals image data block not found")

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")


if __name__ == "__main__":
    main()
