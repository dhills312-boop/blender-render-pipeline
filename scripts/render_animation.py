#!/usr/bin/env python3
"""Frame-range Blender render entrypoint for RunPod."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "render_config.json"


def blender_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Blender animation frames.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--blend-file")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--step", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--samples", type=int)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args(blender_args())


def configure_cycles(config: dict, force_cpu: bool) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(config["samples"])
    scene.cycles.use_denoising = bool(config.get("use_denoising", True))
    if hasattr(scene.cycles, "denoiser") and config.get("denoiser"):
        scene.cycles.denoiser = config["denoiser"]

    prefs = bpy.context.preferences.addons["cycles"].preferences
    if force_cpu or config.get("device") == "CPU":
        scene.cycles.device = "CPU"
        return
    for compute_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = compute_type
            prefs.get_devices()
            for cycles_device in prefs.devices:
                cycles_device.use = cycles_device.type != "CPU"
            if any(device.use for device in prefs.devices):
                break
        except Exception:
            continue
    scene.cycles.device = "GPU"


def main() -> None:
    args = parse_args()
    with Path(args.config).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    for key, value in (
        ("blend_file", args.blend_file),
        ("frame_start", args.start),
        ("frame_end", args.end),
        ("frame_step", args.step),
        ("output_dir", args.output_dir),
        ("samples", args.samples),
    ):
        if value is not None:
            config[key] = value

    blend_file = Path(config["blend_file"])
    if not blend_file.exists():
        raise FileNotFoundError(blend_file)
    bpy.ops.wm.open_mainfile(filepath=str(blend_file))

    scene = bpy.context.scene
    scene.frame_start = int(config["frame_start"])
    scene.frame_end = int(config["frame_end"])
    scene.frame_step = int(config.get("frame_step", 1))
    scene.render.resolution_x = int(config["resolution_x"])
    scene.render.resolution_y = int(config["resolution_y"])
    scene.render.resolution_percentage = int(config.get("resolution_percentage", 100))
    scene.render.image_settings.file_format = config.get("output_format", "PNG")
    scene.render.image_settings.color_depth = str(config.get("color_depth", "16"))
    output_dir = Path(config.get("output_dir", "/workspace/output/"))
    output_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output_dir / "frame_")

    configure_cycles(config, args.cpu)
    print(f"[render_animation] Rendering frames {scene.frame_start}-{scene.frame_end} step {scene.frame_step}")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
