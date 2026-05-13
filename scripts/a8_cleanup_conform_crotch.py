"""Dampen Body_Sculpt_Conform artifact regions.

Nearest-surface conform can pull low-poly crotch vertices into high-poly sculpt
creases or sharp breast detail. This script preserves the general body conform
but blends selected artifact vertices back toward the original Body basis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from statistics import mean

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", default="Body")
    parser.add_argument("--shape-key", default="Body_Sculpt_Conform")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out-blend")
    parser.add_argument("--min-z", type=float, default=0.66)
    parser.add_argument("--max-z", type=float, default=0.95)
    parser.add_argument("--inner-x", type=float, default=0.16)
    parser.add_argument("--full-x", type=float, default=0.10)
    parser.add_argument("--min-y", type=float, default=-0.08)
    parser.add_argument("--max-y", type=float, default=0.14)
    parser.add_argument("--full-strength", type=float, default=0.92)
    parser.add_argument("--skip-breast", action="store_true")
    parser.add_argument("--breast-strength", type=float, default=0.68)
    parser.add_argument("--breast-center-y", type=float, default=-0.103)
    parser.add_argument("--breast-center-z", type=float, default=1.168)
    parser.add_argument("--breast-center-x", type=float, default=0.086)
    parser.add_argument("--breast-radius-x", type=float, default=0.070)
    parser.add_argument("--breast-radius-y", type=float, default=0.048)
    parser.add_argument("--breast-radius-z", type=float, default=0.100)
    parser.add_argument("--breast-full-radius", type=float, default=0.45)
    return parser.parse_args(argv)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def crotch_weight(args: argparse.Namespace, world) -> float:
    if world.z < args.min_z or world.z > args.max_z:
        return 0.0
    if world.y < args.min_y or world.y > args.max_y:
        return 0.0
    ax = abs(world.x)
    if ax > args.inner_x:
        return 0.0

    # Full restore near the centerline, feathering out toward inner_x.
    if ax <= args.full_x:
        return args.full_strength
    fade = 1.0 - smoothstep(args.full_x, args.inner_x, ax)
    return args.full_strength * fade


def breast_weight(args: argparse.Namespace, world) -> float:
    if args.skip_breast:
        return 0.0

    # Two small ellipsoids target the conform spike clusters without flattening
    # the broader bust volume.
    cx = args.breast_center_x if world.x >= 0.0 else -args.breast_center_x
    dx = (world.x - cx) / args.breast_radius_x
    dy = (world.y - args.breast_center_y) / args.breast_radius_y
    dz = (world.z - args.breast_center_z) / args.breast_radius_z
    radius = (dx * dx + dy * dy + dz * dz) ** 0.5
    if radius >= 1.0:
        return 0.0
    if radius <= args.breast_full_radius:
        return args.breast_strength
    fade = 1.0 - smoothstep(args.breast_full_radius, 1.0, radius)
    return args.breast_strength * fade


def main() -> None:
    args = parse_args()
    body = bpy.data.objects.get(args.body)
    if not body or body.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {args.body}")
    if not body.data.shape_keys or args.shape_key not in body.data.shape_keys.key_blocks:
        raise RuntimeError(f"Missing shape key: {args.shape_key}")

    key = body.data.shape_keys.key_blocks[args.shape_key]
    world_scale = body.matrix_world.to_scale().x
    changed = 0
    crotch_changed = 0
    breast_changed = 0
    restore_weights = []
    before_cm = []
    after_cm = []
    crotch_before_cm = []
    crotch_after_cm = []
    breast_before_cm = []
    breast_after_cm = []

    for vertex in body.data.vertices:
        world = body.matrix_world @ vertex.co
        cw = crotch_weight(args, world)
        bw = breast_weight(args, world)
        weight = max(cw, bw)
        if weight <= 0.0:
            continue

        basis = vertex.co
        old = key.data[vertex.index].co.copy()
        new = old.lerp(basis, weight)
        key.data[vertex.index].co = new
        changed += 1
        restore_weights.append(weight)
        before_cm.append((old - basis).length * world_scale * 100)
        after_cm.append((new - basis).length * world_scale * 100)
        if cw > 0.0:
            crotch_changed += 1
            crotch_before_cm.append(before_cm[-1])
            crotch_after_cm.append(after_cm[-1])
        if bw > 0.0:
            breast_changed += 1
            breast_before_cm.append(before_cm[-1])
            breast_after_cm.append(after_cm[-1])

    report = {
        "blend_file": bpy.data.filepath,
        "body": body.name,
        "shape_key": key.name,
        "crotch_region": {
            "min_z": args.min_z,
            "max_z": args.max_z,
            "inner_x": args.inner_x,
            "full_x": args.full_x,
            "min_y": args.min_y,
            "max_y": args.max_y,
            "full_strength": args.full_strength,
        },
        "breast_region": {
            "enabled": not args.skip_breast,
            "strength": args.breast_strength,
            "center_x_abs": args.breast_center_x,
            "center_y": args.breast_center_y,
            "center_z": args.breast_center_z,
            "radius_x": args.breast_radius_x,
            "radius_y": args.breast_radius_y,
            "radius_z": args.breast_radius_z,
            "full_radius": args.breast_full_radius,
        },
        "changed_vertices": changed,
        "crotch_changed_vertices": crotch_changed,
        "breast_changed_vertices": breast_changed,
        "mean_restore_weight": mean(restore_weights) if restore_weights else 0.0,
        "mean_delta_before_cm": mean(before_cm) if before_cm else 0.0,
        "mean_delta_after_cm": mean(after_cm) if after_cm else 0.0,
        "max_delta_before_cm": max(before_cm) if before_cm else 0.0,
        "max_delta_after_cm": max(after_cm) if after_cm else 0.0,
        "crotch_mean_delta_before_cm": mean(crotch_before_cm) if crotch_before_cm else 0.0,
        "crotch_mean_delta_after_cm": mean(crotch_after_cm) if crotch_after_cm else 0.0,
        "breast_mean_delta_before_cm": mean(breast_before_cm) if breast_before_cm else 0.0,
        "breast_mean_delta_after_cm": mean(breast_after_cm) if breast_after_cm else 0.0,
        "breast_max_delta_before_cm": max(breast_before_cm) if breast_before_cm else 0.0,
        "breast_max_delta_after_cm": max(breast_after_cm) if breast_after_cm else 0.0,
    }

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    if args.out_blend:
        os.makedirs(os.path.dirname(args.out_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    print("CONFORM_ARTIFACT_CLEANUP_OK")
    print(f"  changed_vertices={changed}")
    print(f"  crotch_changed_vertices={crotch_changed}")
    print(f"  breast_changed_vertices={breast_changed}")
    print(f"  mean_delta_before_cm={report['mean_delta_before_cm']:.3f}")
    print(f"  mean_delta_after_cm={report['mean_delta_after_cm']:.3f}")
    print(f"  breast_max_delta_before_cm={report['breast_max_delta_before_cm']:.3f}")
    print(f"  breast_max_delta_after_cm={report['breast_max_delta_after_cm']:.3f}")
    print(f"  max_delta_before_cm={report['max_delta_before_cm']:.3f}")
    print(f"  max_delta_after_cm={report['max_delta_after_cm']:.3f}")
    if args.out_blend:
        print(f"  saved={args.out_blend}")


if __name__ == "__main__":
    main()
