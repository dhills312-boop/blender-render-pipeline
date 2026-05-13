"""Create a stripped positioning stage for the Hair-16 ombre alternate.

Visible: Body + ALT_PocolovHair16 hair only.
Hidden: current hair, clothes, accessories, alt head helper, and source clutter.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v32_hair16_ombre_alt.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v33_hair16_position_stage.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v33_hair16_position_stage_report.json"),
    )
    return parser.parse_known_args()[0]


def set_visible(obj: bpy.types.Object, visible: bool, render: bool | None = None):
    obj.hide_viewport = not visible
    obj.hide_set(not visible)
    obj.hide_render = not visible if render is None else not render


def world_bounds(obj: bpy.types.Object):
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return min_v, max_v, (min_v + max_v) * 0.5


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    body = bpy.data.objects.get("Body")
    hair = bpy.data.objects.get("ALT_PocolovHair16_SRC_PocolovHair16_Hair_16")
    alt_head = bpy.data.objects.get("ALT_PocolovHair16_SRC_PocolovHair16_Head")
    if body is None:
        raise RuntimeError("Body object not found")
    if hair is None:
        raise RuntimeError("ALT_PocolovHair16 hair object not found")

    accepted_hair = bpy.data.objects.get("Hair_30629")
    alignment = None
    if accepted_hair is not None:
        _, _, target_center = world_bounds(accepted_hair)
        _, _, hair_center = world_bounds(hair)
        delta = target_center - hair_center
        hair.location += delta
        alignment = {
            "target": accepted_hair.name,
            "delta": [round(v, 6) for v in delta],
            "new_location": [round(v, 6) for v in hair.location],
        }

    for obj in bpy.data.objects:
        if obj.type in {"MESH", "CURVE", "EMPTY", "LIGHT", "CAMERA"}:
            set_visible(obj, False)

    set_visible(body, True)
    set_visible(hair, True)
    if alt_head:
        set_visible(alt_head, False)

    for coll in bpy.data.collections:
        if coll.name == "ALT_PocolovHair16_Source":
            coll.hide_viewport = False
            coll.hide_render = False

    bpy.ops.object.select_all(action="DESELECT")
    hair.select_set(True)
    bpy.context.view_layer.objects.active = hair

    # Make transform editing predictable in the viewport.
    bpy.context.scene.tool_settings.transform_pivot_point = "MEDIAN_POINT"

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "visible_objects": [
            obj.name
            for obj in bpy.data.objects
            if obj.type == "MESH" and not obj.hide_get() and not obj.hide_render
        ],
        "active_object": bpy.context.view_layer.objects.active.name,
        "alignment": alignment,
        "notes": [
            "Positioning stage only: Body and Hair-16 ombre alt are visible.",
            "Hair-16 object is selected and active for immediate move/scale/rotate edits.",
            "Do not treat this as a full visual pass; use it to place the alternate hair cleanly.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
