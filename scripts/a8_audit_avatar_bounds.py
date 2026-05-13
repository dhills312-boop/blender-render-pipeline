"""Audit world-space bounds for visible avatar mesh objects."""

from __future__ import annotations

import argparse
import json
import os
import sys

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--include-hidden", action="store_true")
    return parser.parse_args(argv)


def cm(value: float) -> float:
    return value * 100.0


def main() -> None:
    args = parse_args()
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    points = []
    objects = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not args.include_hidden and (obj.hide_viewport or obj.hide_get()):
            continue
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        try:
            world_points = [obj_eval.matrix_world @ v.co for v in mesh.vertices]
            if not world_points:
                continue
            points.extend(world_points)
            xs = [p.x for p in world_points]
            ys = [p.y for p in world_points]
            zs = [p.z for p in world_points]
            objects.append(
                {
                    "name": obj.name,
                    "vertices": len(mesh.vertices),
                    "triangles": sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons),
                    "hidden_viewport": bool(obj.hide_viewport or obj.hide_get()),
                    "hidden_render": bool(obj.hide_render),
                    "height_cm": cm(max(zs) - min(zs)),
                    "min_z_cm": cm(min(zs)),
                    "max_z_cm": cm(max(zs)),
                    "width_cm": cm(max(xs) - min(xs)),
                    "depth_cm": cm(max(ys) - min(ys)),
                }
            )
        finally:
            obj_eval.to_mesh_clear()

    if not points:
        raise RuntimeError("No mesh points found")

    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    report = {
        "blend_file": bpy.data.filepath,
        "include_hidden": args.include_hidden,
        "bounds_cm": {
            "height": cm(max(zs) - min(zs)),
            "width": cm(max(xs) - min(xs)),
            "depth": cm(max(ys) - min(ys)),
            "min_z": cm(min(zs)),
            "max_z": cm(max(zs)),
        },
        "mesh_totals": {
            "objects": len(objects),
            "vertices": sum(obj["vertices"] for obj in objects),
            "triangles": sum(obj["triangles"] for obj in objects),
        },
        "objects": sorted(objects, key=lambda row: row["triangles"], reverse=True),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("AVATAR_BOUNDS_OK")
    print(f"  height_cm={report['bounds_cm']['height']:.1f}")
    print(f"  width_cm={report['bounds_cm']['width']:.1f}")
    print(f"  depth_cm={report['bounds_cm']['depth']:.1f}")
    print(f"  visible_mesh_objects={report['mesh_totals']['objects']}")
    print(f"  visible_triangles={report['mesh_totals']['triangles']}")


if __name__ == "__main__":
    main()
