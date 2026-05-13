"""Audit how closely conformed Body fits evaluated Body_Sculpt."""

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
    parser.add_argument("--out", required=True)
    parser.add_argument("--include-material", action="append", default=[])
    return parser.parse_args(argv)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def material_names_for_vertex(obj: bpy.types.Object) -> dict[int, set[str]]:
    mesh = obj.data
    slot_names = [slot.material.name if slot.material else "" for slot in obj.material_slots]
    vertex_materials: dict[int, set[str]] = defaultdict(set)
    for poly in mesh.polygons:
        mat_name = slot_names[poly.material_index] if poly.material_index < len(slot_names) else ""
        for vi in poly.vertices:
            vertex_materials[vi].add(mat_name)
    return vertex_materials


def require_mesh(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {name}")
    return obj


def main() -> None:
    args = parse_args()
    body = require_mesh(args.body)
    sculpt = require_mesh(args.sculpt)
    include_materials = set(args.include_material or DEFAULT_INCLUDE_MATERIALS)

    sculpt_visibility = (sculpt.hide_viewport, sculpt.hide_render)
    sculpt.hide_viewport = False
    sculpt.hide_render = False
    try:
        sculpt.hide_set(False)
    except RuntimeError:
        pass
    bpy.context.view_layer.update()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    sculpt_eval = sculpt.evaluated_get(depsgraph)
    sculpt_mesh = sculpt_eval.to_mesh()
    body_eval = body.evaluated_get(depsgraph)
    body_mesh = body_eval.to_mesh()

    body_vertex_materials = material_names_for_vertex(body)
    distances = []
    by_material = defaultdict(list)
    sampled = 0
    skipped = 0

    try:
        for vertex in body_mesh.vertices:
            mats = body_vertex_materials.get(vertex.index, set())
            if not mats.intersection(include_materials):
                skipped += 1
                continue
            if "sculpt_bvh" not in locals():
                coords = [sculpt_eval.matrix_world @ v.co for v in sculpt_mesh.vertices]
                polygons = [tuple(poly.vertices) for poly in sculpt_mesh.polygons]
                sculpt_bvh = BVHTree.FromPolygons(coords, polygons)
            world = body_eval.matrix_world @ vertex.co
            nearest = sculpt_bvh.find_nearest(world)
            if not nearest:
                continue
            nearest_world = nearest[0]
            dist = (nearest_world - world).length
            distances.append(dist)
            for mat in mats.intersection(include_materials):
                by_material[mat].append(dist)
            sampled += 1
    finally:
        body_eval.to_mesh_clear()
        sculpt_eval.to_mesh_clear()
        sculpt.hide_viewport, sculpt.hide_render = sculpt_visibility

    report = {
        "blend_file": bpy.data.filepath,
        "body": body.name,
        "sculpt": sculpt.name,
        "include_materials": sorted(include_materials),
        "sampled_vertices": sampled,
        "skipped_vertices": skipped,
        "distance_cm": {
            "mean": mean(distances) * 100 if distances else 0.0,
            "p50": percentile(distances, 50) * 100,
            "p90": percentile(distances, 90) * 100,
            "p99": percentile(distances, 99) * 100,
            "max": max(distances) * 100 if distances else 0.0,
        },
        "over_1cm": len([d for d in distances if d > 0.01]),
        "over_2cm": len([d for d in distances if d > 0.02]),
        "over_4cm": len([d for d in distances if d > 0.04]),
        "by_material_cm": {
            mat: {
                "count": len(vals),
                "mean": mean(vals) * 100 if vals else 0.0,
                "p90": percentile(vals, 90) * 100,
                "max": max(vals) * 100 if vals else 0.0,
            }
            for mat, vals in sorted(by_material.items())
        },
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("BODY_CONFORM_FIT_OK")
    print(f"  sampled_vertices={sampled}")
    print(f"  mean_cm={report['distance_cm']['mean']:.3f}")
    print(f"  p90_cm={report['distance_cm']['p90']:.3f}")
    print(f"  p99_cm={report['distance_cm']['p99']:.3f}")
    print(f"  max_cm={report['distance_cm']['max']:.3f}")
    print(f"  over_2cm={report['over_2cm']}")


if __name__ == "__main__":
    main()
