"""Report which mouth meshes use which materials and UV maps."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


KEYWORDS = ("tongue", "teeth", "mouth", "jaw", "oral", "gum")
MATERIAL_NAMES = {
    "Tongue",
    "Upper_Teeth",
    "Lower_Teeth",
    "Material",
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def object_matches(obj: bpy.types.Object) -> bool:
    name = obj.name.lower()
    if any(word in name for word in KEYWORDS):
        return True
    for slot in obj.material_slots:
        if slot.material and slot.material.name in MATERIAL_NAMES:
            return True
    return False


def main():
    args = parse_args()
    report = {"blend_file": bpy.data.filepath, "objects": []}

    for obj in bpy.data.objects:
        if obj.type != "MESH" or not object_matches(obj):
            continue

        slot_names = [slot.material.name if slot.material else None for slot in obj.material_slots]
        polys_by_slot = defaultdict(int)
        tris_by_slot = defaultdict(int)
        for poly in obj.data.polygons:
            polys_by_slot[poly.material_index] += 1
            tris_by_slot[poly.material_index] += max(0, len(poly.vertices) - 2)

        report["objects"].append(
            {
                "name": obj.name,
                "material_slots": slot_names,
                "uv_maps": [uv.name for uv in obj.data.uv_layers],
                "active_uv": obj.data.uv_layers.active.name if obj.data.uv_layers.active else None,
                "poly_count": len(obj.data.polygons),
                "tri_count": sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons),
                "slot_usage": [
                    {
                        "slot_index": idx,
                        "material": slot_names[idx] if idx < len(slot_names) else None,
                        "polygons": polys_by_slot[idx],
                        "triangles": tris_by_slot[idx],
                    }
                    for idx in sorted(polys_by_slot.keys())
                ],
            }
        )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("MOUTH_MATERIAL_USAGE_OK")
    for row in report["objects"]:
        print(f"  {row['name']}: slots={row['material_slots']} active_uv={row['active_uv']}")
        for slot in row["slot_usage"]:
            print(
                f"    slot {slot['slot_index']}: {slot['material']} "
                f"polys={slot['polygons']} tris={slot['triangles']}"
            )


if __name__ == "__main__":
    main()
