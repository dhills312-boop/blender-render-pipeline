"""Audit Body_Sculpt inner-thigh clearance.

This is a geometric heuristic: it samples vertices in the upper-leg height band
near the centerline and estimates the gap between the left and right inner thigh
surfaces. Small/negative gaps mean the thighs touch or intersect.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", default="Body_Sculpt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-z", type=float, default=0.42)
    parser.add_argument("--max-z", type=float, default=0.95)
    parser.add_argument("--slice-height", type=float, default=0.025)
    parser.add_argument("--max-center-x", type=float, default=0.22)
    parser.add_argument("--max-front-back-y", type=float, default=0.22)
    return parser.parse_args(argv)


def require_mesh(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {name}")
    return obj


def vertex_group_names(obj: bpy.types.Object) -> list[str]:
    return [g.name for g in obj.vertex_groups]


def names_matching(names: list[str], tokens: tuple[str, ...]) -> list[str]:
    found = []
    for name in names:
        low = name.lower()
        if any(token in low for token in tokens):
            found.append(name)
    return found


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = min(len(vals) - 1, max(0, int(round((pct / 100) * (len(vals) - 1)))))
    return vals[idx]


def main() -> None:
    args = parse_args()
    obj = require_mesh(args.object)
    group_names = vertex_group_names(obj)
    leg_groups = names_matching(group_names, ("thigh", "upperleg", "upleg", "leg", "calf"))

    slices: dict[int, dict[str, list[float]]] = defaultdict(lambda: {"left": [], "right": []})
    sampled = 0
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
        if x < 0:
            slices[bucket]["left"].append(x)
        elif x > 0:
            slices[bucket]["right"].append(x)
        sampled += 1

    gaps = []
    per_slice = []
    for bucket, sides in sorted(slices.items()):
        left = sides["left"]
        right = sides["right"]
        if not left or not right:
            continue
        # Inner left surface is the largest negative x. Inner right surface is
        # the smallest positive x. Their difference is centerline clearance.
        inner_left = max(left)
        inner_right = min(right)
        gap = inner_right - inner_left
        z_mid = args.min_z + (bucket + 0.5) * args.slice_height
        gaps.append(gap)
        per_slice.append(
            {
                "z_mid": z_mid,
                "gap_m": gap,
                "gap_cm": gap * 100,
                "left_inner_x": inner_left,
                "right_inner_x": inner_right,
                "left_samples": len(left),
                "right_samples": len(right),
            }
        )

    min_gap = min(gaps) if gaps else None
    tight_slices = [s for s in per_slice if s["gap_m"] <= 0.015]
    touching_slices = [s for s in per_slice if s["gap_m"] <= 0.003]
    recommendation = "unknown"
    if min_gap is not None:
        if min_gap <= 0.003:
            recommendation = "reduce_or_separate_inner_thighs"
        elif min_gap <= 0.015:
            recommendation = "inspect_manually_tight_clearance"
        else:
            recommendation = "clearance_looks_ok"

    report = {
        "blend_file": bpy.data.filepath,
        "object": obj.name,
        "bounds": {
            "min_z": args.min_z,
            "max_z": args.max_z,
            "slice_height": args.slice_height,
            "max_center_x": args.max_center_x,
            "max_front_back_y": args.max_front_back_y,
        },
        "matched_leg_vertex_groups": leg_groups,
        "sampled_vertices": sampled,
        "slice_count": len(per_slice),
        "min_gap_m": min_gap,
        "min_gap_cm": min_gap * 100 if min_gap is not None else None,
        "p10_gap_cm": percentile(gaps, 10) * 100 if gaps else None,
        "median_gap_cm": percentile(gaps, 50) * 100 if gaps else None,
        "tight_slice_count": len(tight_slices),
        "touching_slice_count": len(touching_slices),
        "recommendation": recommendation,
        "slices": per_slice,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("THIGH_AUDIT_OK")
    print(f"  sampled_vertices={sampled}")
    print(f"  min_gap_cm={report['min_gap_cm']}")
    print(f"  median_gap_cm={report['median_gap_cm']}")
    print(f"  recommendation={recommendation}")


if __name__ == "__main__":
    main()
