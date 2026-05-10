"""Quick preview render of a VTuber-model .blend.

Frames all visible meshes, places a 3-quarter front camera + key/fill lights,
renders a solid-shaded EEVEE PNG for fast visual review.

Run via:
    blender -b <file>.blend -P preview_render.py -- --out preview.png \
        [--angle front|side|back|three_quarter] [--res 1024 1024]
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--angle", default="three_quarter",
                   choices=["front", "side", "back", "three_quarter", "head"])
    p.add_argument("--engine", default="workbench",
                   choices=["workbench", "eevee"])
    p.add_argument("--res", nargs=2, type=int, default=[1024, 1280])
    return p.parse_args(argv)


def visible_mesh_bounds():
    """Return (center, max_dim) of all visible mesh objects in world space."""
    points = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.hide_get() or obj.hide_render:
            continue
        for v in obj.bound_box:
            points.append(obj.matrix_world @ Vector(v))
    if not points:
        return Vector((0, 0, 1)), 2.0
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    mn = Vector((min(xs), min(ys), min(zs)))
    mx = Vector((max(xs), max(ys), max(zs)))
    center = (mn + mx) / 2
    size = mx - mn
    max_dim = max(size.x, size.y, size.z)
    return center, max_dim


def head_position_guess():
    """Find a head bone or top-of-mesh point so we can frame on the head."""
    for arm in bpy.data.objects:
        if arm.type == "ARMATURE":
            for bone in arm.data.bones:
                if bone.name.lower() in ("head", "def-head", "org-head"):
                    pos = arm.matrix_world @ bone.head_local
                    return pos
    # Fallback: top of bounds.
    center, size = visible_mesh_bounds()
    return Vector((center.x, center.y, center.z + size * 0.4))


def place_camera(angle, frame_target, frame_size):
    """Create a camera positioned to frame the target nicely."""
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50  # mm
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.collection.objects.link(cam)

    distance = frame_size * 1.6

    if angle == "front":
        cam.location = frame_target + Vector((0, -distance, 0))
    elif angle == "back":
        cam.location = frame_target + Vector((0, distance, 0))
    elif angle == "side":
        cam.location = frame_target + Vector((distance, 0, 0))
    elif angle == "head":
        cam.location = frame_target + Vector((0, -distance * 0.4, 0))
    else:  # three_quarter
        cam.location = frame_target + Vector(
            (-distance * 0.7, -distance * 0.7, distance * 0.05)
        )

    # Track-to constraint pointing at the frame target.
    empty = bpy.data.objects.new("PreviewTarget", None)
    empty.location = frame_target
    bpy.context.collection.objects.link(empty)
    track = cam.constraints.new("TRACK_TO")
    track.target = empty
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    bpy.context.scene.camera = cam
    return cam


def add_lights(target):
    """Add a simple 3-point lighting rig + a uniform world background.

    Also remove any pre-existing scene lights (CC4 ships its own spot/point
    rig that overpowers ours and can render badly without their setup).
    """
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT" and not obj.name.startswith(
            ("KeyLight", "FillLight", "RimLight")
        ):
            light_data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if light_data.users == 0:
                bpy.data.lights.remove(light_data)
    # Boost world background so character isn't a silhouette.
    world = bpy.context.scene.world
    if world and world.use_nodes:
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Strength"].default_value = 2.0
            bg.inputs["Color"].default_value = (0.7, 0.7, 0.75, 1.0)

    # Key light — much stronger now.
    key_data = bpy.data.lights.new("KeyLight", "AREA")
    key_data.energy = 5000
    key_data.size = 2
    key = bpy.data.objects.new("KeyLight", key_data)
    key.location = target + Vector((-2, -3, 3))
    bpy.context.collection.objects.link(key)

    # Fill light.
    fill_data = bpy.data.lights.new("FillLight", "AREA")
    fill_data.energy = 2000
    fill_data.size = 3
    fill = bpy.data.objects.new("FillLight", fill_data)
    fill.location = target + Vector((3, -2, 2))
    bpy.context.collection.objects.link(fill)

    # Rim light.
    rim_data = bpy.data.lights.new("RimLight", "AREA")
    rim_data.energy = 2500
    rim_data.size = 2
    rim = bpy.data.objects.new("RimLight", rim_data)
    rim.location = target + Vector((1, 2, 3))
    bpy.context.collection.objects.link(rim)


def configure_render(out_path, res, engine):
    sc = bpy.context.scene
    sc.render.resolution_x = res[0]
    sc.render.resolution_y = res[1]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.render.filepath = out_path
    sc.view_settings.view_transform = "Standard"

    if engine == "eevee":
        sc.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(sc.eevee, "taa_render_samples"):
            sc.eevee.taa_render_samples = 32
        # Force opaque background and neutral tonemapping; CC4 sometimes ships
        # film_transparent=True + AgX High Contrast which clips to silhouette.
        sc.render.film_transparent = False
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = 0
        sc.view_settings.gamma = 1.0
    else:
        # Workbench (solid view) — doesn't load textures into VRAM.
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.display.shading.light = "STUDIO"
        sc.display.shading.color_type = "MATERIAL"
        sc.display.shading.show_cavity = True
        sc.display.shading.cavity_type = "WORLD"
        sc.display.render_aa = "8"


def main():
    args = parse_args()

    # Frame the model.
    if args.angle == "head":
        target = head_position_guess()
        _, full_size = visible_mesh_bounds()
        # Tighter frame for head shot.
        frame_size = full_size * 0.25
    else:
        target, full_size = visible_mesh_bounds()
        frame_size = full_size

    print(f"Frame target: {target}, size: {frame_size:.2f}")

    place_camera(args.angle, target, frame_size)
    add_lights(target)
    configure_render(args.out, args.res, args.engine)

    print(f"Rendering to {args.out} ({args.res[0]}x{args.res[1]})...")
    bpy.ops.render.render(write_still=True)
    print(f"DONE: {args.out}")


if __name__ == "__main__":
    main()
