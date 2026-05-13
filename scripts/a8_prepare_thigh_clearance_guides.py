"""Prepare non-destructive thigh clearance guides on Body_Sculpt.

This script is meant for interactive Blender use after opening the sculpt file.
It can:

- create left/right/all tight-thigh vertex groups on Body_Sculpt
- create a preview shape key that gently pushes inner-thigh vertices outward
- write a JSON report

It does not save a blend unless --out-blend is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from statistics import mean

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", default="Body_Sculpt")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out-blend")
    parser.add_argument("--min-z", type=float, default=0.42)
    parser.add_argument("--max-z", type=float, default=0.95)
    parser.add_argument("--slice-height", type=float, default=0.025)
    parser.add_argument("--max-center-x", type=float, default=0.22)
    parser.add_argument("--max-front-back-y", type=float, default=0.22)
    parser.add_argument("--tight-gap", type=float, default=0.015)
    parser.add_argument("--target-gap", type=float, default=0.025)
    parser.add_argument("--shape-key", default="A8_Thigh_Clearance_Guide")
    parser.add_argument("--no-shape-key", action="store_true")
    return parser.parse_args(argv)


def require_mesh(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {name}")
    return obj


def get_group(obj: bpy.types.Object, name: str) -> bpy.types.VertexGroup:
    existing = obj.vertex_groups.get(name)
    if existing:
        obj.vertex_groups.remove(existing)
    return obj.vertex_groups.new(name=name)


def get_or_create_shape_key(obj: bpy.types.Object, name: str) -> bpy.types.ShapeKey:
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis")
    existing = obj.data.shape_keys.key_blocks.get(name)
    if existing:
        return existing
    return obj.shape_key_add(name=name)


def collect_slice_data(obj: bpy.types.Object, args: argparse.Namespace):
    slices = defaultdict(lambda: {"left": [], "right": [], "vertices": []})
    for vertex in obj.data.vertices:
        world = obj.matrix_world @ vertex.co
        x, y, z = world.x, world.y, world.z
        if z < args.min_z or z > args.max_z:
            continue
        if abs(x) > args.max_center_x:
            continue
        if abs(y) > args.max_front_back_y:
            continue
        bucket = int((z - args.min_z) / args.slice_height)
        slices[bucket]["vertices"].append((vertex.index, x, y, z))
        if x < 0:
            slices[bucket]["left"].append(x)
        elif x > 0:
            slices[bucket]["right"].append(x)
    return slices


def main() -> None:
    args = parse_args()
    obj = require_mesh(args.object)
    slices = collect_slice_data(obj, args)

    tight_buckets = {}
    per_slice = []
    for bucket, data in sorted(slices.items()):
        if not data["left"] or not data["right"]:
            continue
        inner_left = max(data["left"])
        inner_right = min(data["right"])
        gap = inner_right - inner_left
        z_mid = args.min_z + (bucket + 0.5) * args.slice_height
        item = {
            "bucket": bucket,
            "z_mid": z_mid,
            "gap_m": gap,
            "gap_cm": gap * 100,
            "vertex_count": len(data["vertices"]),
        }
        per_slice.append(item)
        if gap <= args.tight_gap:
            tight_buckets[bucket] = gap

    left_group = get_group(obj, "A8_Thigh_Tight_Left")
    right_group = get_group(obj, "A8_Thigh_Tight_Right")
    all_group = get_group(obj, "A8_Thigh_Tight_All")
    guide_weights = {}

    for bucket, gap in tight_buckets.items():
        needed_per_side = max(0.0, (args.target_gap - gap) * 0.5)
        for vertex_index, x, _y, _z in slices[bucket]["vertices"]:
            center_weight = max(0.0, 1.0 - (abs(x) / args.max_center_x))
            weight = min(1.0, center_weight * center_weight)
            if weight <= 0.0:
                continue
            guide_weights[vertex_index] = max(guide_weights.get(vertex_index, 0.0), weight)
            all_group.add([vertex_index], weight, "REPLACE")
            if x < 0:
                left_group.add([vertex_index], weight, "REPLACE")
            elif x > 0:
                right_group.add([vertex_index], weight, "REPLACE")

    moved_distances = []
    if not args.no_shape_key:
        key = get_or_create_shape_key(obj, args.shape_key)
        key.value = 1.0
        for vertex in obj.data.vertices:
            key.data[vertex.index].co = vertex.co
        for bucket, gap in tight_buckets.items():
            needed_per_side = max(0.0, (args.target_gap - gap) * 0.5)
            for vertex_index, x, _y, _z in slices[bucket]["vertices"]:
                weight = guide_weights.get(vertex_index, 0.0)
                if weight <= 0.0:
                    continue
                direction = -1.0 if x < 0 else 1.0
                delta_world_x = direction * needed_per_side * weight
                local_delta_x = delta_world_x / obj.matrix_world.to_scale().x
                original = obj.data.vertices[vertex_index].co
                key.data[vertex_index].co = original.copy()
                key.data[vertex_index].co.x += local_delta_x
                moved_distances.append(abs(delta_world_x))

    report = {
        "blend_file": bpy.data.filepath,
        "object": obj.name,
        "created_groups": [
            "A8_Thigh_Tight_Left",
            "A8_Thigh_Tight_Right",
            "A8_Thigh_Tight_All",
        ],
        "created_shape_key": None if args.no_shape_key else args.shape_key,
        "tight_gap_m": args.tight_gap,
        "target_gap_m": args.target_gap,
        "tight_slice_count": len(tight_buckets),
        "guided_vertex_count": len(guide_weights),
        "mean_preview_move_cm": (mean(moved_distances) * 100) if moved_distances else 0.0,
        "max_preview_move_cm": (max(moved_distances) * 100) if moved_distances else 0.0,
        "slices": per_slice,
    }

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    if args.out_blend:
        os.makedirs(os.path.dirname(args.out_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    print("THIGH_GUIDES_OK")
    print(f"  tight_slice_count={report['tight_slice_count']}")
    print(f"  guided_vertex_count={report['guided_vertex_count']}")
    print(f"  mean_preview_move_cm={report['mean_preview_move_cm']:.3f}")
    print(f"  max_preview_move_cm={report['max_preview_move_cm']:.3f}")
    if args.out_blend:
        print(f"  saved={args.out_blend}")


if __name__ == "__main__":
    main()
