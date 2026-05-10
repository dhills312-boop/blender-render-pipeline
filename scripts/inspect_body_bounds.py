"""Read-only bounds and transform report for Body and Body_Sculpt."""

import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def world_bounds(obj):
    corners = [obj.matrix_world @ __import__("mathutils").Vector(c) for c in obj.bound_box]
    mins = [min(c[i] for c in corners) for i in range(3)]
    maxs = [max(c[i] for c in corners) for i in range(3)]
    return {"min": mins, "max": maxs, "size": [maxs[i] - mins[i] for i in range(3)]}


def info(name):
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"exists": False}
    obj.data.calc_loop_triangles()
    return {
        "exists": True,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "matrix_world": [list(row) for row in obj.matrix_world],
        "bounds": world_bounds(obj),
        "verts": len(obj.data.vertices),
        "tris": len(obj.data.loop_triangles),
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
    }


def main():
    args = parse_args()
    report = {
        "blend_file": bpy.data.filepath,
        "Body": info("Body"),
        "Body_Sculpt": info("Body_Sculpt"),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("BOUNDS_OK")
    for name in ("Body", "Body_Sculpt"):
        b = report[name]["bounds"]
        print(f"  {name}: min={b['min']} max={b['max']} size={b['size']}")


if __name__ == "__main__":
    main()
