"""Audit armature export viability for the vtuber avatar."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--armature")
    parser.add_argument("--include-hidden", action="store_true")
    return parser.parse_args(argv)


def pick_armature(name: str | None) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "ARMATURE":
            raise RuntimeError(f"Missing armature: {name}")
        return obj
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("No armatures found")
    return max(armatures, key=lambda obj: len(obj.data.bones))


def visible_meshes(include_hidden: bool) -> list[bpy.types.Object]:
    out = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not include_hidden and (obj.hide_viewport or obj.hide_render or obj.hide_get()):
            continue
        if not any(mod.type == "ARMATURE" for mod in obj.modifiers):
            continue
        if len(obj.data.vertices) == 0 or len(obj.material_slots) == 0:
            continue
        out.append(obj)
    return out


def classify_name(name: str) -> str:
    if name.startswith("DEF-"):
        return "DEF"
    if name.startswith("ORG-"):
        return "ORG"
    if name.startswith("MCH-"):
        return "MCH"
    if name.startswith("WGT-"):
        return "WGT"
    if name.startswith("VIS_"):
        return "VIS"
    if name.startswith("tweak_"):
        return "tweak"
    return "other"


def bone_weights_for_mesh(obj: bpy.types.Object) -> dict[str, float]:
    weights = defaultdict(float)
    group_names = {group.index: group.name for group in obj.vertex_groups}
    for vertex in obj.data.vertices:
        for group in vertex.groups:
            name = group_names.get(group.group)
            if name:
                weights[name] += group.weight
    return weights


def main():
    args = parse_args()
    arm_obj = pick_armature(args.armature)
    arm = arm_obj.data
    meshes = visible_meshes(args.include_hidden)

    per_mesh_weights = {}
    weighted_bones = Counter()
    mesh_usage = defaultdict(list)
    for mesh in meshes:
        weights = bone_weights_for_mesh(mesh)
        per_mesh_weights[mesh.name] = weights
        for bone_name, total_weight in weights.items():
            if total_weight > 0:
                weighted_bones[bone_name] += 1
                mesh_usage[bone_name].append(mesh.name)

    rows = []
    prefix_counts = Counter()
    deform_counts = Counter()
    orphan_deform = []
    used_deform = []
    used_non_deform = []

    for bone in arm.bones:
        prefix = classify_name(bone.name)
        prefix_counts[prefix] += 1
        deform_counts["deform" if bone.use_deform else "non_deform"] += 1
        has_weights = bone.name in weighted_bones
        row = {
            "name": bone.name,
            "prefix": prefix,
            "use_deform": bool(bone.use_deform),
            "has_vertex_weights": has_weights,
            "mesh_count": weighted_bones[bone.name],
            "meshes": sorted(mesh_usage.get(bone.name, [])),
            "parent": bone.parent.name if bone.parent else None,
        }
        rows.append(row)

        if bone.use_deform and has_weights:
            used_deform.append(row)
        elif bone.use_deform and not has_weights:
            orphan_deform.append(row)
        elif (not bone.use_deform) and has_weights:
            used_non_deform.append(row)

    report = {
        "blend_file": bpy.data.filepath,
        "armature": arm_obj.name,
        "include_hidden": bool(args.include_hidden),
        "visible_skinned_meshes": [mesh.name for mesh in meshes],
        "counts": {
            "total_bones": len(arm.bones),
            "deform_bones": sum(1 for bone in arm.bones if bone.use_deform),
            "non_deform_bones": sum(1 for bone in arm.bones if not bone.use_deform),
            "weighted_bones": len(weighted_bones),
            "weighted_deform_bones": len(used_deform),
            "weighted_non_deform_bones": len(used_non_deform),
            "orphan_deform_bones": len(orphan_deform),
        },
        "prefix_counts": dict(prefix_counts),
        "deform_usage_counts": dict(deform_counts),
        "weighted_non_deform_bones": sorted(used_non_deform, key=lambda row: row["mesh_count"], reverse=True),
        "orphan_deform_bones": sorted(orphan_deform, key=lambda row: row["name"]),
        "top_weighted_deform_bones": sorted(used_deform, key=lambda row: row["mesh_count"], reverse=True)[:100],
        "export_notes": [
            "FBX export with Only Deform Bones should drop non-deform control/mechanism bones automatically.",
            "Weighted non-deform bones are the dangerous case: they may still matter unless weights are transferred or those bones are marked deform.",
            "Orphan deform bones are safe candidates to review for removal from export if they truly do not influence the visible meshes.",
        ],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("BONE_EXPORT_AUDIT_OK")
    print(f"  armature={arm_obj.name}")
    print(f"  total_bones={report['counts']['total_bones']}")
    print(f"  deform_bones={report['counts']['deform_bones']}")
    print(f"  non_deform_bones={report['counts']['non_deform_bones']}")
    print(f"  weighted_deform_bones={report['counts']['weighted_deform_bones']}")
    print(f"  weighted_non_deform_bones={report['counts']['weighted_non_deform_bones']}")
    print(f"  orphan_deform_bones={report['counts']['orphan_deform_bones']}")


if __name__ == "__main__":
    main()
