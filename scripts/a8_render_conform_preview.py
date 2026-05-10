"""Render a Body-to-Body_Sculpt conform preview without saving a blend.

This combines the conservative conform pass with the existing still-render
pipeline. It is intended for remote visual checks: the pod opens the protected
blend, creates the Body_Sculpt_Conform shape key in memory, hides Body_Sculpt,
renders, and exits.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import a8_conform_body_to_sculpt as conform
import render_still


def blender_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--blend-file")
    parser.add_argument("--output-dir")
    parser.add_argument("--output-name", default="a8_body_conform_preview")
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-distance", type=float, default=0.18)
    parser.add_argument("--strength", type=float, default=1.0)
    parser.add_argument("--compare-sculpt", action="store_true")
    parser.add_argument("--comparison-offset", type=float, default=0.95)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--resolution-x", type=int)
    parser.add_argument("--resolution-y", type=int)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args(blender_args())


def make_evaluated_copy(
    source: bpy.types.Object,
    name: str,
    x_offset: float,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
    mesh.name = f"{name}_mesh"
    for slot in source.material_slots:
        mesh.materials.append(slot.material)
    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = source.matrix_world.copy()
    obj.location.x += x_offset
    collection.objects.link(obj)
    return obj


def setup_comparison(body_name: str, sculpt_name: str, offset: float) -> None:
    body = bpy.data.objects.get(body_name)
    sculpt = bpy.data.objects.get(sculpt_name)
    if not body or not sculpt:
        raise RuntimeError("Body/Sculpt missing for comparison render")

    collection = bpy.context.scene.collection
    make_evaluated_copy(body, "Preview_Conformed_Body", -offset, collection)

    sculpt.hide_set(False)
    sculpt.hide_viewport = False
    sculpt.hide_render = False
    make_evaluated_copy(sculpt, "Preview_Body_Sculpt_Reference", offset, collection)

    for obj in bpy.data.objects:
        if obj.type == "MESH" and not obj.name.startswith("Preview_"):
            obj.hide_viewport = True
            obj.hide_render = True


def main() -> None:
    args = parse_args()
    launch_cwd = Path.cwd()
    config = render_still.load_config(Path(args.config))
    if args.blend_file:
        config["blend_file"] = args.blend_file
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = launch_cwd / output_dir
        config["output_dir"] = str(output_dir)
    if args.samples is not None:
        config["samples"] = args.samples
    if args.resolution_x is not None:
        config["resolution_x"] = args.resolution_x
    if args.resolution_y is not None:
        config["resolution_y"] = args.resolution_y

    render_still.open_blend_if_needed(config.get("blend_file"))

    conform.run_conform(argparse.Namespace(
        body="Body",
        sculpt="Body_Sculpt",
        shape_key="Body_Sculpt_Conform",
        report=str((launch_cwd / args.report) if not Path(args.report).is_absolute() else Path(args.report)),
        out_blend=None,
        max_distance=args.max_distance,
        strength=args.strength,
        include_material=[],
        include_head=False,
        keep_sculpt_visible=False,
    ))

    if args.compare_sculpt:
        setup_comparison("Body", "Body_Sculpt", args.comparison_offset)

    bpy.context.scene.frame_set(int(config["frame"]))
    render_still.configure_cycles(config, force_cpu=args.cpu)
    output = render_still.configure_output(config, args.output_name)
    print(f"[a8_render_conform_preview] Rendering conformed preview -> {output}")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
