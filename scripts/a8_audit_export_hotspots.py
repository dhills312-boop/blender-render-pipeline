"""Audit export-relevant mesh hotspots for the vtuber avatar."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--include-hidden", action="store_true")
    return parser.parse_args(argv)


def tri_count(obj: bpy.types.Object) -> int:
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def is_export_mesh(obj: bpy.types.Object, include_hidden: bool) -> bool:
    if obj.type != "MESH":
        return False
    if not include_hidden and (obj.hide_viewport or obj.hide_render or obj.hide_get()):
        return False
    if len(obj.data.vertices) == 0:
        return False
    if len(obj.material_slots) == 0:
        return False
    return True


def main():
    args = parse_args()
    rows = []
    material_tris = defaultdict(int)
    material_objects = defaultdict(set)
    texture_names = set()

    for obj in bpy.data.objects:
        if not is_export_mesh(obj, args.include_hidden):
            continue
        tris = tri_count(obj)
        if tris <= 0:
            continue
        mats = [slot.material.name for slot in obj.material_slots if slot.material]
        if not mats:
            continue

        skinned = any(mod.type == "ARMATURE" for mod in obj.modifiers)
        rows.append(
            {
                "name": obj.name,
                "tris": tris,
                "verts": len(obj.data.vertices),
                "materials": mats,
                "material_slots": len(mats),
                "uv_maps": [uv.name for uv in obj.data.uv_layers],
                "shape_key_count": len(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else 0,
                "skinned": skinned,
                "modifiers": [mod.type for mod in obj.modifiers],
            }
        )

        # Approximate material contribution by whole-object assignment.
        share = tris / max(1, len(mats))
        for mat_name in mats:
            material_tris[mat_name] += share
            material_objects[mat_name].add(obj.name)
            mat = bpy.data.materials.get(mat_name)
            if mat and mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image:
                        texture_names.add(node.image.name)

    rows.sort(key=lambda row: row["tris"], reverse=True)
    top_rows = rows[: args.top]

    images = []
    total_tex_bytes = 0
    for name in sorted(texture_names):
        img = bpy.data.images.get(name)
        if not img or img.name in {"Render Result", "Viewer Node"}:
            continue
        bytes_est = img.size[0] * img.size[1] * 4 if img.size[0] and img.size[1] else 0
        total_tex_bytes += bytes_est
        images.append(
            {
                "name": img.name,
                "size": [img.size[0], img.size[1]],
                "estimated_mb": round(bytes_est / (1024 * 1024), 3),
            }
        )

    images.sort(key=lambda row: row["estimated_mb"], reverse=True)

    report = {
        "blend_file": bpy.data.filepath,
        "include_hidden": bool(args.include_hidden),
        "object_count": len(rows),
        "skinned_mesh_count": sum(1 for row in rows if row["skinned"]),
        "total_tris": sum(row["tris"] for row in rows),
        "top_objects": top_rows,
        "materials_by_estimated_tris": [
            {
                "material": name,
                "estimated_tris": round(material_tris[name]),
                "objects": sorted(material_objects[name]),
            }
            for name in sorted(material_tris, key=lambda key: material_tris[key], reverse=True)
        ],
        "textures_by_estimated_mb": images[: args.top],
        "total_texture_estimated_mb": round(total_tex_bytes / (1024 * 1024), 3),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("EXPORT_HOTSPOTS_OK")
    print(f"  object_count={report['object_count']}")
    print(f"  skinned_mesh_count={report['skinned_mesh_count']}")
    print(f"  total_tris={report['total_tris']:,}")
    for row in top_rows[:8]:
        print(
            f"  {row['name']}: tris={row['tris']:,} "
            f"mats={row['material_slots']} skinned={row['skinned']}"
        )


if __name__ == "__main__":
    main()
