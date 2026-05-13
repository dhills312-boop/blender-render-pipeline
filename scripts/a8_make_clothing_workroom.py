"""Make a lightweight clothing workroom from the v20 clothing file.

This keeps the body, armature, and clothing fit objects visible while hiding
heavy accessories/hair/face extras that are not needed for clothing fitting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


VISIBLE_NAMES = {
    "Body",
    "FIT_PleatedSkirt_Shrinkwrap",
    "FIT_PleatedSkirt_Shrinkwrap_fitTest",
    "FIT_StreetwearTop",
    "FIT_Underwear_Support.001",
    "SC_Guide_BustCollision",
    "SC_Guide_UnderbustCollision",
    "SC_Guide_WaistCollision",
    "SC_Guide_HipsButtCollision",
}


VISIBLE_PREFIXES = (
    "Armature",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v20_clothing_fit_light_30.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v22_clothing_workroom.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v22_clothing_workroom_report.json"),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name, hide=False):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = hide
    coll.hide_render = hide
    return coll


def move_to_collection(obj, coll):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)


def keep_visible(obj):
    if obj.name in VISIBLE_NAMES:
        return True
    return any(obj.name.startswith(prefix) for prefix in VISIBLE_PREFIXES)


def mesh_stats(obj):
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    return {
        "verts": len(obj.data.vertices),
        "polys": len(obj.data.polygons),
        "tris": tris,
        "mods": [f"{m.name}:{m.type}:view={m.show_viewport}" for m in obj.modifiers],
    }


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    workroom = ensure_collection("A8_CLOTHING_WORKROOM", hide=False)
    hidden = ensure_collection("A8_Workroom_Hidden_NonClothing", hide=True)

    visible = []
    hidden_objs = []
    for obj in bpy.data.objects:
        if keep_visible(obj):
            obj.hide_viewport = False
            obj.hide_render = obj.name.startswith("SC_Guide_")
            move_to_collection(obj, workroom)
            visible.append(obj.name)
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            move_to_collection(obj, hidden)
            hidden_objs.append(obj.name)

    # Keep only clothing/body relevant live modifiers evaluating in this workroom.
    for obj in bpy.data.objects:
        if obj.hide_viewport:
            for mod in obj.modifiers:
                mod.show_viewport = False
                mod.show_render = False
        elif obj.name.startswith("FIT_"):
            for mod in obj.modifiers:
                if mod.type == "CLOTH":
                    mod.show_viewport = False
                    mod.show_render = False
                if mod.type == "CORRECTIVE_SMOOTH":
                    mod.show_viewport = False
                    mod.show_render = False

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "visible": visible,
        "hidden_count": len(hidden_objs),
        "visible_mesh_stats": {
            obj.name: mesh_stats(obj)
            for obj in bpy.data.objects
            if obj.type == "MESH" and not obj.hide_viewport
        },
        "notes": [
            "This is a lightweight clothing workroom, not a final avatar file.",
            "Hair, piercings, muzzle, face accessories, and most small meshes are hidden.",
            "Use this file for skirt/top fitting if the full v20 file stalls.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
