"""Audit inner-thigh clearance on evaluated Body_Sculpt geometry.

This includes active modifiers such as Geometry Nodes, unlike the base-mesh
audit. Thresholds are in world meters.
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
    parser.add_argument("--max-center-x", type=float, default=0.25)
    parser.add_argument("--max-front-back-y", type=float, default=0.22)
    return parser.parse_args(argv)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def main() -> None:
    args = parse_args()
    obj = bpy.data.objects.get(args.object)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {args.object}")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        slices = defaultdict(lambda: {"left": [], "right": []})
        sampled = 0
        for vertex in mesh.vertices:
            world = evaluated.matrix_world @ vertex.co
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
            if not sides["left"] or not sides["right"]:
                continue
            inner_left = max(sides["left"])
            inner_right = min(sides["right"])
            gap = inner_right - inner_left
            gaps.append(gap)
            per_slice.append(
                {
                    "z_mid": args.min_z + (bucket + 0.5) * args.slice_height,
                    "gap_m": gap,
                    "gap_cm": gap * 100,
                    "left_samples": len(sides["left"]),
                    "right_samples": len(sides["right"]),
                }
            )

        min_gap = min(gaps) if gaps else None
        report = {
            "blend_file": bpy.data.filepath,
            "object": obj.name,
            "evaluated": True,
            "modifier_summary": [
                {
                    "name": mod.name,
                    "type": mod.type,
                    "show_viewport": mod.show_viewport,
                    "show_render": mod.show_render,
                }
                for mod in obj.modifiers
            ],
            "sampled_vertices": sampled,
            "slice_count": len(per_slice),
            "min_gap_cm": min_gap * 100 if min_gap is not None else None,
            "p10_gap_cm": percentile(gaps, 10) * 100 if gaps else None,
            "median_gap_cm": percentile(gaps, 50) * 100 if gaps else None,
            "tight_slice_count": len([g for g in gaps if g <= 0.015]),
            "touching_slice_count": len([g for g in gaps if g <= 0.003]),
            "recommendation": (
                "clearance_looks_ok"
                if min_gap is not None and min_gap > 0.015
                else "inspect_or_increase_clearance"
            ),
            "slices": per_slice,
        }
    finally:
        evaluated.to_mesh_clear()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("EVALUATED_THIGH_AUDIT_OK")
    print(f"  sampled_vertices={report['sampled_vertices']}")
    print(f"  min_gap_cm={report['min_gap_cm']}")
    print(f"  median_gap_cm={report['median_gap_cm']}")
    print(f"  tight_slice_count={report['tight_slice_count']}")
    print(f"  touching_slice_count={report['touching_slice_count']}")
    print(f"  recommendation={report['recommendation']}")


if __name__ == "__main__":
    main()
