"""Render vtuber-a8 material-review shots with the scene's real materials.

Usage:
    blender -b workspace/project/vtuber-a8/a6_v42_relinked_texture_paths.blend \
      -P scripts/a8_render_v42_material_review.py -- \
      --out-dir render-output/vtuber-previews/v42 --shots all
"""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SHOT_PRESETS = {
    "front": {
        "target": (0.0, -0.02, 0.86),
        "location": (0.0, -3.0, 0.98),
        "lens": 64,
        "res": (1600, 2200),
    },
    "three_quarter": {
        "target": (0.0, -0.02, 0.95),
        "location": (-1.25, -2.65, 1.03),
        "lens": 70,
        "res": (1600, 2200),
    },
    "face": {
        "target": (0.0, -0.055, 1.49),
        "location": (0.0, -0.92, 1.49),
        "lens": 80,
        "res": (1800, 1800),
    },
    "tank_athena": {
        "target": (0.0, -0.16, 1.03),
        "location": (0.0, -1.25, 1.04),
        "lens": 90,
        "res": (1800, 1800),
    },
    "undies_pomp": {
        "target": (0.0, -0.06, 0.77),
        "location": (0.0, -1.18, 0.79),
        "lens": 95,
        "res": (1800, 1800),
    },
    "tattoos_side": {
        "target": (-0.16, -0.03, 0.78),
        "location": (-0.95, -0.95, 0.86),
        "lens": 100,
        "res": (1800, 1800),
    },
    "ankle_wrist": {
        "target": (-0.12, -0.04, 0.63),
        "location": (-1.35, -1.45, 0.72),
        "lens": 88,
        "res": (1800, 2200),
    },
    "tail_back": {
        "target": (0.0, 0.32, 0.76),
        "location": (0.0, 2.25, 0.88),
        "lens": 82,
        "res": (1800, 1800),
    },
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shots", nargs="+", default=["all"])
    parser.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    parser.add_argument("--res", nargs=2, type=int, default=None)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--transparent", action="store_true")
    return parser.parse_args(argv)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_collection_visible(name, visible):
    col = bpy.data.collections.get(name)
    if col:
        col.hide_viewport = not visible
        col.hide_render = not visible


def remove_existing_render_helpers():
    for obj in list(bpy.data.objects):
        if obj.name.startswith(("A8ReviewCam", "A8ReviewTarget", "A8_Key", "A8_Fill", "A8_Rim", "A8_Softbox")):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and getattr(data, "users", 0) == 0:
                if hasattr(bpy.data, "lights") and data.__class__.__name__ == "Light":
                    bpy.data.lights.remove(data)
                elif hasattr(bpy.data, "cameras") and data.__class__.__name__ == "Camera":
                    bpy.data.cameras.remove(data)


def configure_scene(engine, samples, transparent):
    scene = bpy.context.scene

    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.device = "GPU"
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = samples
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True
        if hasattr(scene.eevee, "gtao_distance"):
            scene.eevee.gtao_distance = 2.0
        if hasattr(scene.eevee, "gtao_factor"):
            scene.eevee.gtao_factor = 0.8

    scene.render.film_transparent = transparent
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    set_collection_visible("DECALS_Locked_v41", True)


def add_light(name, location, energy, size, target=(0, 0, 1)):
    light_data = bpy.data.lights.new(name, "AREA")
    light_data.energy = energy
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(light)
    light.location = Vector(location)
    look_at(light, target)
    return light


def add_lighting():
    add_light("A8_Key", (-1.5, -2.2, 2.2), 520, 3.0, (0, -0.02, 1.0))
    add_light("A8_Fill", (1.8, -1.6, 1.55), 110, 4.0, (0, -0.02, 1.0))
    add_light("A8_Rim", (0.9, 1.1, 1.8), 170, 2.4, (0, -0.02, 1.15))
    add_light("A8_Softbox_Low", (0.0, -1.8, 0.55), 80, 3.0, (0, -0.02, 0.78))


def ensure_lighting():
    existing = [obj for obj in bpy.data.objects if obj.type == "LIGHT" and not obj.hide_render]
    if not existing:
        add_lighting()


def create_camera(preset):
    existing = bpy.context.scene.camera
    if existing:
        camera = existing
        camera.data.lens = preset["lens"]
    else:
        camera_data = bpy.data.cameras.new("A8ReviewCam")
        camera_data.lens = preset["lens"]
        camera_data.sensor_width = 36
        camera = bpy.data.objects.new("A8ReviewCam", camera_data)
        bpy.context.collection.objects.link(camera)
    camera.location = Vector(preset["location"])
    look_at(camera, preset["target"])
    bpy.context.scene.camera = camera
    return camera


def render_shot(name, preset, out_dir, engine, samples, override_res):
    remove_existing_render_helpers()
    configure_scene(engine, samples, transparent=False)
    ensure_lighting()
    create_camera(preset)

    scene = bpy.context.scene
    res = override_res or preset["res"]
    scene.render.resolution_x = res[0]
    scene.render.resolution_y = res[1]
    scene.render.filepath = str(Path(out_dir) / f"a6_v42_material_review_{name}.png")

    print(f"[a8_render_v42_material_review] Rendering {name} -> {scene.render.filepath}")
    bpy.ops.render.render(write_still=True)


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if "all" in args.shots:
        shots = list(SHOT_PRESETS.keys())
    else:
        shots = args.shots

    unknown = [shot for shot in shots if shot not in SHOT_PRESETS]
    if unknown:
        raise SystemExit(f"Unknown shots: {unknown}. Available: {sorted(SHOT_PRESETS)}")

    for shot in shots:
        render_shot(shot, SHOT_PRESETS[shot], out_dir, args.engine, args.samples, args.res)


if __name__ == "__main__":
    main()
