"""Conform rigged Body proportions toward Body_Sculpt as a non-destructive key.

The goal is to preserve Body's UVs, rig weights, material slots, and shape keys
while borrowing large silhouette/proportion changes from Body_Sculpt.

Default behavior is report-only: it builds the shape key in-memory, hides
Body_Sculpt for preview/export, writes a JSON report, and does not save a blend.
Pass --out-blend only when a visual test has been accepted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from statistics import mean

import bpy
from mathutils.bvhtree import BVHTree


DEFAULT_INCLUDE_MATERIALS = ("Skin_Body", "Skin_Arm", "Skin_Leg")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", default="Body")
    parser.add_argument("--sculpt", default="Body_Sculpt")
    parser.add_argument("--shape-key", default="Body_Sculpt_Conform")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out-blend")
    parser.add_argument("--max-distance", type=float, default=0.18)
    parser.add_argument("--strength", type=float, default=1.0)
    parser.add_argument(
        "--include-material",
        action="append",
        default=[],
        help="Material name to conform. Defaults to Skin_Body/Skin_Arm/Skin_Leg.",
    )
    parser.add_argument("--include-head", action="store_true")
    parser.add_argument("--keep-sculpt-visible", action="store_true")
    return parser.parse_args(argv)


def require_mesh(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {name}")
    return obj


def material_names_for_vertex(obj: bpy.types.Object) -> dict[int, set[str]]:
    mesh = obj.data
    slot_names = [
        slot.material.name if slot.material else ""
        for slot in obj.material_slots
    ]
    vertex_materials: dict[int, set[str]] = defaultdict(set)
    for poly in mesh.polygons:
        mat_name = slot_names[poly.material_index] if poly.material_index < len(slot_names) else ""
        for vi in poly.vertices:
            vertex_materials[vi].add(mat_name)
    return vertex_materials


def get_or_create_shape_key(obj: bpy.types.Object, key_name: str) -> bpy.types.ShapeKey:
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis")
    existing = obj.data.shape_keys.key_blocks.get(key_name)
    if existing:
        return existing
    return obj.shape_key_add(name=key_name)


def build_bvh(obj: bpy.types.Object) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(obj, depsgraph)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def run_conform(args: argparse.Namespace) -> dict:
    body = require_mesh(args.body)
    sculpt = require_mesh(args.sculpt)

    include_materials = set(args.include_material or DEFAULT_INCLUDE_MATERIALS)
    if args.include_head:
        include_materials.add("Skin_Head")

    bvh = build_bvh(sculpt)
    shape_key = get_or_create_shape_key(body, args.shape_key)
    shape_key.value = 1.0

    body_inv = body.matrix_world.inverted()
    sculpt_inv = sculpt.matrix_world.inverted()
    vertex_materials = material_names_for_vertex(body)
    distances: list[float] = []
    skipped_by_material = 0
    skipped_by_distance = 0
    changed = 0

    for vert in body.data.vertices:
        mats = vertex_materials.get(vert.index, set())
        if not mats.intersection(include_materials):
            shape_key.data[vert.index].co = vert.co
            skipped_by_material += 1
            continue

        world_co = body.matrix_world @ vert.co
        sculpt_local_co = sculpt_inv @ world_co
        nearest = bvh.find_nearest(sculpt_local_co)
        if nearest is None:
            shape_key.data[vert.index].co = vert.co
            continue

        nearest_sculpt_local, _normal, _face_index, _dist = nearest
        nearest_world = sculpt.matrix_world @ nearest_sculpt_local
        world_dist = (nearest_world - world_co).length
        if world_dist > args.max_distance:
            shape_key.data[vert.index].co = vert.co
            skipped_by_distance += 1
            continue

        target_local = body_inv @ nearest_world
        new_local = vert.co.lerp(target_local, args.strength)
        shape_key.data[vert.index].co = new_local
        distances.append(world_dist)
        changed += 1

    if not args.keep_sculpt_visible:
        sculpt.hide_set(True)
        sculpt.hide_viewport = True
        sculpt.hide_render = True

    report = {
        "blend_file": bpy.data.filepath,
        "body": body.name,
        "sculpt": sculpt.name,
        "shape_key": shape_key.name,
        "shape_key_value": shape_key.value,
        "include_materials": sorted(include_materials),
        "max_distance": args.max_distance,
        "strength": args.strength,
        "body_vertices": len(body.data.vertices),
        "body_tris": len(body.data.loop_triangles),
        "sculpt_vertices": len(sculpt.data.vertices),
        "changed_vertices": changed,
        "skipped_by_material": skipped_by_material,
        "skipped_by_distance": skipped_by_distance,
        "distance_stats": {
            "mean": mean(distances) if distances else 0.0,
            "p50": percentile(distances, 50),
            "p90": percentile(distances, 90),
            "p99": percentile(distances, 99),
            "max": max(distances) if distances else 0.0,
        },
        "sculpt_hidden_for_preview": not args.keep_sculpt_visible,
        "saved_blend": args.out_blend,
    }

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    if args.out_blend:
        os.makedirs(os.path.dirname(args.out_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    print("CONFORM_OK")
    print(f"  changed_vertices={changed}")
    print(f"  skipped_by_material={skipped_by_material}")
    print(f"  skipped_by_distance={skipped_by_distance}")
    print(f"  mean_distance={report['distance_stats']['mean']:.5f}")
    print(f"  p99_distance={report['distance_stats']['p99']:.5f}")
    if args.out_blend:
        print(f"  saved={args.out_blend}")
    return report


def main() -> None:
    run_conform(parse_args())


if __name__ == "__main__":
    main()
