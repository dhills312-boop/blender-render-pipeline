#!/usr/bin/env python3
"""Create a lightweight local shader-test blend from the current lift-off scene."""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
LIFT_OFF = ROOT / "workspace" / "project" / "blender-output" / "lift-off"
INPUT_BLEND = LIFT_OFF / "LO_085_spiderverse_visible_halftone.blend"
OUTPUT_BLEND = LIFT_OFF / "LO_086_local_shader_test_stage.blend"
FREEZE_FRAME = 73

KEEP_COLLECTIONS = {
    "Backdrop",
    "Cameras",
    "Character",
    "Lighting",
    "LO_080 Arcane Base Lights",
}


def unlink_from_collection(obj: bpy.types.Object, collection_name: str) -> None:
    collection = bpy.data.collections.get(collection_name)
    if collection and obj.name in collection.objects:
        collection.objects.unlink(obj)


def visual_unparent(obj: bpy.types.Object) -> None:
    matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = matrix


def clear_animation() -> None:
    for datablock_collection in (
        bpy.data.objects,
        bpy.data.materials,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.worlds,
        bpy.data.collections,
    ):
        for datablock in datablock_collection:
            if hasattr(datablock, "animation_data_clear"):
                datablock.animation_data_clear()

    scene = bpy.context.scene
    scene.animation_data_clear()
    scene.frame_start = FREEZE_FRAME
    scene.frame_end = FREEZE_FRAME
    scene.frame_set(FREEZE_FRAME)


def delete_unwanted_objects() -> None:
    to_delete = []
    for obj in bpy.data.objects:
        collection_names = {collection.name for collection in obj.users_collection}
        if collection_names & KEEP_COLLECTIONS:
            continue
        to_delete.append(obj)

    for obj in to_delete:
        bpy.data.objects.remove(obj, do_unlink=True)
    print(f"[LO_086] Deleted {len(to_delete)} non-test object(s)")

    changed = True
    while changed:
        changed = False
        for collection in list(bpy.data.collections):
            if collection.name not in KEEP_COLLECTIONS and not collection.objects and not collection.children:
                bpy.data.collections.remove(collection)
                changed = True


def character_bounds() -> tuple[Vector, float]:
    objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and any(collection.name == "Character" for collection in obj.users_collection)
    ]
    if not objects:
        raise RuntimeError("No character mesh found")

    points = []
    for obj in objects:
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)

    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (minimum + maximum) * 0.5
    radius = max((maximum - minimum).length * 0.62, 3.0)
    return center, radius


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def configure_test_cameras() -> None:
    center, radius = character_bounds()
    target = center + Vector((0.0, 0.0, 0.35))
    distance = radius * 2.15
    height = target.z + radius * 0.22

    camera_b = bpy.data.objects.get("Lift Off camera B - front load hold jump")
    if camera_b is None:
        camera_b = next((obj for obj in bpy.data.objects if obj.type == "CAMERA"), None)
    if camera_b is None:
        raise RuntimeError("No camera found")

    camera_a = bpy.data.objects.get("Lift Off camera A - roof sitting side pan")
    camera_c = bpy.data.objects.get("Lift Off camera C - airborne hang")

    base_vector = camera_b.location - target
    if base_vector.length < 0.1:
        base_vector = Vector((0.0, -distance, 0.0))
    base_angle = math.atan2(base_vector.y, base_vector.x)

    for camera, label, offset in (
        (camera_a, "Shader Test camera A - 3/4 left", math.radians(-55.0)),
        (camera_b, "Shader Test camera B - front frame 0073", 0.0),
        (camera_c, "Shader Test camera C - 3/4 right", math.radians(55.0)),
    ):
        if camera is None:
            continue
        camera.name = label
        angle = base_angle + offset
        camera.location = Vector((target.x + math.cos(angle) * distance, target.y + math.sin(angle) * distance, height))
        look_at(camera, target)
        camera.data.lens = 58.0
        camera.data.dof.use_dof = False

    bpy.context.scene.camera = bpy.data.objects.get("Shader Test camera B - front frame 0073") or camera_b
    print(f"[LO_086] Camera target {tuple(round(v, 3) for v in target)}")


def configure_local_render_defaults() -> None:
    scene = bpy.context.scene
    scene.frame_set(FREEZE_FRAME)
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.eevee.taa_samples = 16
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100


def main() -> None:
    if not INPUT_BLEND.exists():
        raise FileNotFoundError(INPUT_BLEND)

    bpy.ops.wm.open_mainfile(filepath=str(INPUT_BLEND))
    bpy.context.scene.frame_set(FREEZE_FRAME)

    for obj in bpy.data.objects:
        visual_unparent(obj)

    delete_unwanted_objects()

    for obj in bpy.data.objects:
        unlink_from_collection(obj, "Roof")
        unlink_from_collection(obj, "Clouds")

    configure_test_cameras()
    clear_animation()
    configure_local_render_defaults()

    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
    print(f"[LO_086] Saved {OUTPUT_BLEND}")


if __name__ == "__main__":
    main()
