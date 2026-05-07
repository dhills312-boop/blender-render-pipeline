#!/usr/bin/env python3
"""Single-frame Blender render entrypoint for RunPod."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "render_config.json"


def blender_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one Blender frame.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--blend-file")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--output-name")
    parser.add_argument("--samples", type=int)
    parser.add_argument("--resolution-x", type=int)
    parser.add_argument("--resolution-y", type=int)
    parser.add_argument("--format", choices=["PNG", "OPEN_EXR", "JPEG", "TIFF"])
    parser.add_argument("--cpu", action="store_true", help="Force CPU rendering.")
    return parser.parse_args(blender_args())


def open_blend_if_needed(path: str | None) -> None:
    if not path:
        return
    blend = Path(path)
    if not blend.exists():
        raise FileNotFoundError(blend)
    bpy.ops.wm.open_mainfile(filepath=str(blend))


def configure_cycles(config: dict, force_cpu: bool = False) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(config["samples"])
    scene.cycles.use_denoising = bool(config.get("use_denoising", True))
    if hasattr(scene.cycles, "denoiser") and config.get("denoiser"):
        scene.cycles.denoiser = config["denoiser"]

    prefs = bpy.context.preferences.addons["cycles"].preferences
    device = "CPU" if force_cpu else config.get("device", "GPU")
    if device == "GPU":
        for compute_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = compute_type
                prefs.get_devices()
                if any(device.use for device in prefs.devices):
                    break
                for cycles_device in prefs.devices:
                    if cycles_device.type != "CPU":
                        cycles_device.use = True
                if any(device.use for device in prefs.devices):
                    break
            except Exception:
                continue
        scene.cycles.device = "GPU"
    else:
        scene.cycles.device = "CPU"


def configure_output(config: dict, output_name: str | None = None) -> Path:
    scene = bpy.context.scene
    scene.render.resolution_x = int(config["resolution_x"])
    scene.render.resolution_y = int(config["resolution_y"])
    scene.render.resolution_percentage = int(config.get("resolution_percentage", 100))

    image_settings = scene.render.image_settings
    image_settings.file_format = config.get("output_format", "PNG")
    if hasattr(image_settings, "color_depth"):
        image_settings.color_depth = str(config.get("color_depth", "16"))
    if image_settings.file_format == "PNG":
        image_settings.color_mode = "RGBA"

    output_dir = Path(config.get("output_dir", "/workspace/output/"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_name or f"frame_{int(config['frame']):04d}"
    scene.render.filepath = str(output_dir / stem)
    return output_dir / stem


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))
    for key, value in (
        ("blend_file", args.blend_file),
        ("frame", args.frame),
        ("output_dir", args.output_dir),
        ("samples", args.samples),
        ("resolution_x", args.resolution_x),
        ("resolution_y", args.resolution_y),
        ("output_format", args.format),
    ):
        if value is not None:
            config[key] = value

    open_blend_if_needed(config.get("blend_file"))
    bpy.context.scene.frame_set(int(config["frame"]))
    configure_cycles(config, force_cpu=args.cpu)
    output = configure_output(config, args.output_name)
    print(f"[render_still] Rendering frame {config['frame']} -> {output}")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
