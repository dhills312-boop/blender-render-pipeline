"""Inspect whether Body_Sculpt could plausibly replace Body for export.

This is read-only. It compares mesh topology, UVs, materials, vertex groups,
shape keys, modifiers, and armature relationships for Body and Body_Sculpt.
"""

import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--body", default="Body")
    parser.add_argument("--sculpt", default="Body_Sculpt")
    return parser.parse_args(argv)


def mesh_info(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    armature_mods = [m for m in obj.modifiers if m.type == "ARMATURE"]
    shape_keys = mesh.shape_keys.key_blocks if mesh.shape_keys else []
    return {
        "exists": True,
        "type": obj.type,
        "visible_viewport": obj.visible_get(),
        "hide_viewport": obj.hide_viewport,
        "hide_render": obj.hide_render,
        "verts": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "tris": len(mesh.loop_triangles),
        "uv_layers": [u.name for u in mesh.uv_layers],
        "uv_layer_count": len(mesh.uv_layers),
        "materials": [
            slot.material.name if slot.material else None
            for slot in obj.material_slots
        ],
        "material_slot_count": len(obj.material_slots),
        "vertex_group_count": len(obj.vertex_groups),
        "vertex_groups_sample": [g.name for g in obj.vertex_groups[:25]],
        "shape_key_count": len(shape_keys),
        "shape_keys_sample": [k.name for k in shape_keys[:25]],
        "modifiers": [
            {
                "name": m.name,
                "type": m.type,
                "object": getattr(getattr(m, "object", None), "name", None),
            }
            for m in obj.modifiers
        ],
        "armature_modifier_count": len(armature_mods),
        "armature_targets": [
            m.object.name for m in armature_mods if getattr(m, "object", None)
        ],
    }


def missing_info(name):
    return {"exists": False, "name": name}


def main():
    args = parse_args()
    body = bpy.data.objects.get(args.body)
    sculpt = bpy.data.objects.get(args.sculpt)

    report = {
        "blend_file": bpy.data.filepath,
        "body_name": args.body,
        "sculpt_name": args.sculpt,
        "body": mesh_info(body) if body and body.type == "MESH" else missing_info(args.body),
        "sculpt": mesh_info(sculpt) if sculpt and sculpt.type == "MESH" else missing_info(args.sculpt),
        "verdict": [],
    }

    if body and sculpt and body.type == "MESH" and sculpt.type == "MESH":
        if len(sculpt.vertex_groups) == 0:
            report["verdict"].append("Body_Sculpt has no vertex groups; it is not directly rigged for export.")
        if not any(m.type == "ARMATURE" for m in sculpt.modifiers):
            report["verdict"].append("Body_Sculpt has no armature modifier; it will not deform as the avatar body.")
        if not sculpt.data.shape_keys:
            report["verdict"].append("Body_Sculpt has no shape keys; Body shape-key behavior would need transfer/rebuild.")
        if len(sculpt.data.vertices) != len(body.data.vertices):
            report["verdict"].append("Body_Sculpt vertex count differs from Body; direct shape-key style swap is not available.")
        if len(sculpt.data.uv_layers) == 0:
            report["verdict"].append("Body_Sculpt has no UV layers; texture/material transfer would need rebuilding.")
        if len(sculpt.material_slots) != len(body.material_slots):
            report["verdict"].append("Body_Sculpt material slot count differs from Body.")
        if len(sculpt.data.loop_triangles) > 70000:
            report["verdict"].append("Body_Sculpt alone exceeds the PC Good triangle budget.")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"INSPECT_OK out={args.out}")
    for line in report["verdict"]:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
