"""Report vertices where Body_Sculpt_Conform differs most from Body basis."""

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
    parser.add_argument("--body", default="Body")
    parser.add_argument("--shape-key", default="Body_Sculpt_Conform")
    parser.add_argument("--out", required=True)
    parser.add_argument("--top", type=int, default=80)
    return parser.parse_args(argv)


def material_names_for_vertex(obj: bpy.types.Object) -> dict[int, set[str]]:
    slot_names = [slot.material.name if slot.material else "" for slot in obj.material_slots]
    out: dict[int, set[str]] = defaultdict(set)
    for poly in obj.data.polygons:
        mat = slot_names[poly.material_index] if poly.material_index < len(slot_names) else ""
        for vi in poly.vertices:
            out[vi].add(mat)
    return out


def main() -> None:
    args = parse_args()
    body = bpy.data.objects.get(args.body)
    if not body or body.type != "MESH":
        raise RuntimeError(f"Missing mesh body: {args.body}")
    if not body.data.shape_keys or args.shape_key not in body.data.shape_keys.key_blocks:
        raise RuntimeError(f"Missing shape key: {args.shape_key}")

    key = body.data.shape_keys.key_blocks[args.shape_key]
    mats_by_vertex = material_names_for_vertex(body)
    rows = []
    for vertex in body.data.vertices:
        basis = vertex.co
        keyed = key.data[vertex.index].co
        delta = keyed - basis
        world_basis = body.matrix_world @ basis
        rows.append(
            {
                "index": vertex.index,
                "delta_cm": delta.length * body.matrix_world.to_scale().x * 100,
                "world_basis": [world_basis.x, world_basis.y, world_basis.z],
                "local_basis": [basis.x, basis.y, basis.z],
                "local_delta": [delta.x, delta.y, delta.z],
                "materials": sorted(mats_by_vertex.get(vertex.index, [])),
            }
        )

    rows.sort(key=lambda r: r["delta_cm"], reverse=True)
    report = {
        "blend_file": bpy.data.filepath,
        "body": body.name,
        "shape_key": key.name,
        "top": rows[: args.top],
        "counts": {
            "over_1cm": len([r for r in rows if r["delta_cm"] > 1.0]),
            "over_2cm": len([r for r in rows if r["delta_cm"] > 2.0]),
            "over_3cm": len([r for r in rows if r["delta_cm"] > 3.0]),
        },
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("CONFORM_OUTLIERS_OK")
    print(report["counts"])
    for row in rows[:10]:
        p = row["world_basis"]
        print(
            f"  v={row['index']} delta_cm={row['delta_cm']:.3f} "
            f"world=({p[0]:.3f},{p[1]:.3f},{p[2]:.3f}) mats={row['materials']}"
        )


if __name__ == "__main__":
    main()
