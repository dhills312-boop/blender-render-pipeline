"""Merge simple skinned outfit meshes in-place for export cleanup."""

from __future__ import annotations

import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--new-name", default="Outfit")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["top_cloth", "bottome"],
        help="Mesh object names to join into a single skinned outfit mesh.",
    )
    return parser.parse_args(argv)


def get_mesh(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {name}")
    return obj


def shape_key_count(obj: bpy.types.Object) -> int:
    keys = obj.data.shape_keys
    return len(keys.key_blocks) if keys else 0


def armature_targets(obj: bpy.types.Object) -> list[str]:
    targets = []
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            targets.append(mod.object.name)
    return targets


def tri_count(obj: bpy.types.Object) -> int:
    mesh = obj.data
    return sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons)


def main():
    args = parse_args()
    targets = [get_mesh(name) for name in args.targets]

    preflight = []
    armature_sets = set()
    total_before_tris = 0

    for obj in targets:
        key_count = shape_key_count(obj)
        if key_count:
            raise RuntimeError(f"{obj.name} has {key_count} shape keys; refusing merge")
        armatures = armature_targets(obj)
        if len(armatures) != 1:
            raise RuntimeError(
                f"{obj.name} must have exactly one armature modifier, found {armatures}"
            )
        armature_sets.add(tuple(armatures))
        tris = tri_count(obj)
        total_before_tris += tris
        preflight.append(
            {
                "name": obj.name,
                "verts": len(obj.data.vertices),
                "tris": tris,
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
                "vertex_group_count": len(obj.vertex_groups),
                "armature": armatures[0],
            }
        )

    if len(armature_sets) != 1:
        raise RuntimeError(f"Targets do not share a single armature: {sorted(armature_sets)}")

    for obj in bpy.context.selected_objects:
        obj.select_set(False)

    base = targets[0]
    bpy.context.view_layer.objects.active = base
    base.select_set(True)
    for obj in targets[1:]:
        obj.select_set(True)

    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.join()

    merged = bpy.context.view_layer.objects.active
    merged.name = args.new_name
    merged.data.name = args.new_name

    total_after_tris = tri_count(merged)
    report = {
        "blend_file": bpy.data.filepath,
        "targets": [item["name"] for item in preflight],
        "new_name": merged.name,
        "armature": preflight[0]["armature"],
        "before": preflight,
        "after": {
            "name": merged.name,
            "verts": len(merged.data.vertices),
            "tris": total_after_tris,
            "materials": [slot.material.name if slot.material else None for slot in merged.material_slots],
            "material_slot_count": len(merged.material_slots),
            "vertex_group_count": len(merged.vertex_groups),
            "shape_key_count": shape_key_count(merged),
        },
        "summary": {
            "total_before_tris": total_before_tris,
            "total_after_tris": total_after_tris,
            "joined_object_count": len(preflight),
        },
        "notes": "Joined simple clothing meshes to reduce skinned mesh count without altering body, face, or sculpt source art.",
    }

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("MERGE_SIMPLE_OUTFIT_MESHES_OK")
    print(f"  merged={report['targets']} -> {merged.name}")
    print(f"  tris_before={total_before_tris}")
    print(f"  tris_after={total_after_tris}")


if __name__ == "__main__":
    main()
