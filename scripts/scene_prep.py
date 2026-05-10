#!/usr/bin/env python3
"""Render-ready scene prep for remote Blender runs."""

from __future__ import annotations

import argparse
import sys

import bpy


def blender_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend-file")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args(blender_args())

    if args.blend_file:
        bpy.ops.wm.open_mainfile(filepath=args.blend_file)

    subsurf = particles = collections = 0
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type == "SUBSURF":
                modifier.levels = modifier.render_levels
                subsurf += 1
        for particle_system in obj.particle_systems:
            particle_system.settings.display_percentage = 100
            particles += 1

    for collection in bpy.data.collections:
        if collection.get("render_only") is True:
            collection.hide_viewport = False
            collection.hide_render = False
            collections += 1

    print(f"[scene_prep] subsurf synced: {subsurf}")
    print(f"[scene_prep] particle systems full display: {particles}")
    print(f"[scene_prep] render-only collections enabled: {collections}")
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)


if __name__ == "__main__":
    main()
