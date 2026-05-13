"""Create a no-physics clothing edit checkpoint from the light clothing file.

The output duplicates visible FIT clothing into plain EDIT meshes using the
current evaluated result, then hides the live modifier versions. This gives the
user editable meshes with no Cloth/Shrinkwrap/Armature modifier cost.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v20_clothing_fit_light_30.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v21_clothing_edit_frozen.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v21_clothing_edit_frozen_report.json"),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name: str, hide: bool = False):
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


def mesh_stats(obj):
    tris = sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
    return {
        "verts": len(obj.data.vertices),
        "polys": len(obj.data.polygons),
        "tris": tris,
    }


def visible_fit_clothing():
    result = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.hide_viewport:
            continue
        if not obj.name.startswith("FIT_"):
            continue
        lower = obj.name.lower()
        if any(token in lower for token in ("skirt", "top", "underwear", "streetwear")):
            result.append(obj)
    return sorted(result, key=lambda item: item.name)


def make_edit_material():
    mat = bpy.data.materials.get("A8_Edit_Frozen_Clothing")
    if mat is None:
        mat = bpy.data.materials.new("A8_Edit_Frozen_Clothing")
        mat.diffuse_color = (0.75, 0.75, 0.78, 1.0)
    return mat


def freeze_object(obj, coll, mat):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph)
    frozen = bpy.data.objects.new(f"EDIT_{obj.name}_Frozen", mesh)
    frozen.matrix_world = obj.matrix_world.copy()
    frozen.show_name = True
    frozen.show_in_front = False
    coll.objects.link(frozen)

    if not frozen.data.materials:
        frozen.data.materials.append(mat)

    obj.hide_viewport = True
    obj.hide_render = True
    return frozen


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    edit_coll = ensure_collection("CLOTHING_EDIT_FROZEN")
    live_backup = ensure_collection("A8_Live_Clothing_Backup", hide=True)
    mat = make_edit_material()

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "frozen_objects": {},
        "hidden_live_objects": [],
        "notes": [
            "Frozen EDIT meshes have no modifiers and are intended for manual sculpt/proportional-edit work.",
            "Live FIT meshes are hidden in A8_Live_Clothing_Backup.",
            "Return to v20 if you need live Shrinkwrap/Cloth again.",
        ],
    }

    for obj in visible_fit_clothing():
        frozen = freeze_object(obj, edit_coll, mat)
        move_to_collection(obj, live_backup)
        report["hidden_live_objects"].append(obj.name)
        report["frozen_objects"][frozen.name] = {
            "source": obj.name,
            "stats": mesh_stats(frozen),
            "modifiers": [f"{m.name}:{m.type}" for m in frozen.modifiers],
        }

    # Keep accidental physics from evaluating on the hidden live versions too.
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if mod.type in {"CLOTH", "SHRINKWRAP", "CORRECTIVE_SMOOTH"}:
                if obj.name in report["hidden_live_objects"]:
                    mod.show_viewport = False
                    mod.show_render = False

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
