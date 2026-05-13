"""Check whether Body_Sculpt Geometry Nodes actually changes evaluated geometry."""

from __future__ import annotations

import argparse
import json
import os
import sys

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", default="Body_Sculpt")
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def bounds_from_coords(coords):
    mins = [min(c[i] for c in coords) for i in range(3)]
    maxs = [max(c[i] for c in coords) for i in range(3)]
    return {"min": mins, "max": maxs, "size": [maxs[i] - mins[i] for i in range(3)]}


def main() -> None:
    args = parse_args()
    obj = bpy.data.objects.get(args.object)
    if not obj or obj.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {args.object}")

    original_world = [obj.matrix_world @ v.co for v in obj.data.vertices]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    eval_mesh = evaluated.to_mesh()
    try:
        evaluated_world = [evaluated.matrix_world @ v.co for v in eval_mesh.vertices]
        count = min(len(original_world), len(evaluated_world))
        deltas = [(evaluated_world[i] - original_world[i]).length for i in range(count)]
        moved = [d for d in deltas if d > 0.00001]
        x_deltas = [evaluated_world[i].x - original_world[i].x for i in range(count)]
        report = {
            "blend_file": bpy.data.filepath,
            "object": obj.name,
            "modifier_summary": [
                {
                    "name": mod.name,
                    "type": mod.type,
                    "show_viewport": mod.show_viewport,
                    "show_render": mod.show_render,
                    "show_in_editmode": getattr(mod, "show_in_editmode", None),
                    "show_on_cage": getattr(mod, "show_on_cage", None),
                    "node_group": getattr(getattr(mod, "node_group", None), "name", None),
                }
                for mod in obj.modifiers
            ],
            "original_vertex_count": len(original_world),
            "evaluated_vertex_count": len(evaluated_world),
            "moved_vertex_count": len(moved),
            "max_delta_m": max(deltas) if deltas else 0.0,
            "max_delta_cm": (max(deltas) * 100) if deltas else 0.0,
            "avg_moved_delta_cm": (sum(moved) / len(moved) * 100) if moved else 0.0,
            "min_x_delta_cm": (min(x_deltas) * 100) if x_deltas else 0.0,
            "max_x_delta_cm": (max(x_deltas) * 100) if x_deltas else 0.0,
            "original_bounds": bounds_from_coords(original_world),
            "evaluated_bounds": bounds_from_coords(evaluated_world),
        }
    finally:
        evaluated.to_mesh_clear()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("GEONODES_EFFECT_OK")
    print(f"  moved_vertex_count={report['moved_vertex_count']}")
    print(f"  max_delta_cm={report['max_delta_cm']:.4f}")
    print(f"  x_delta_cm=[{report['min_x_delta_cm']:.4f}, {report['max_x_delta_cm']:.4f}]")
    for mod in report["modifier_summary"]:
        if mod["type"] == "NODES":
            print(
                "  modifier="
                f"{mod['name']} viewport={mod['show_viewport']} "
                f"editmode={mod['show_in_editmode']} cage={mod['show_on_cage']}"
            )


if __name__ == "__main__":
    main()
