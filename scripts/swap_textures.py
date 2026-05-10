#!/usr/bin/env python3
"""Swap Blender image paths between local 1K and render 4K texture variants."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def blender_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=["up", "down"], required=True)
    parser.add_argument("--blend-file")
    parser.add_argument("--save", action="store_true")
    return parser.parse_args(blender_args())


def main() -> None:
    args = parse_args()
    if args.blend_file:
        bpy.ops.wm.open_mainfile(filepath=args.blend_file)

    source, target = ("_1k.", "_4k.") if args.direction == "up" else ("_4k.", "_1k.")
    swaps = 0
    for image in bpy.data.images:
        if not image.filepath:
            continue
        old_path = image.filepath
        if source not in old_path:
            continue
        new_path = old_path.replace(source, target)
        image.filepath = new_path
        try:
            image.reload()
        except RuntimeError as exc:
            print(f"[swap_textures] reload failed for {image.name}: {exc}")
        swaps += 1
        print(f"[swap_textures] {image.name}: {old_path} -> {new_path}")

    print(f"[swap_textures] swapped {swaps} image path(s)")
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)


if __name__ == "__main__":
    main()
