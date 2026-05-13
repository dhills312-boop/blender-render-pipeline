"""Transfer toe weights onto foot bones for export reduction."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


LEFT_TOE_GROUPS = [
    "DEF-toe.L",
    "DEF-toe_big.L",
    "DEF-toe_index.L",
    "DEF-toe_mid.L",
    "DEF-toe_ring.L",
    "DEF-toe_pinky.L",
]

RIGHT_TOE_GROUPS = [
    "DEF-toe.R",
    "DEF-toe_big.R",
    "DEF-toe_index.R",
    "DEF-toe_mid.R",
    "DEF-toe_ring.R",
    "DEF-toe_pinky.R",
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def ensure_group(obj: bpy.types.Object, name: str):
    group = obj.vertex_groups.get(name)
    if not group:
        group = obj.vertex_groups.new(name=name)
    return group


def transfer_groups(obj: bpy.types.Object, sources: list[str], target_name: str):
    target = ensure_group(obj, target_name)
    group_by_index = {group.index: group for group in obj.vertex_groups}
    source_indices = {
        group.index: group.name
        for group in obj.vertex_groups
        if group.name in sources
    }
    if not source_indices:
        return {
            "object": obj.name,
            "target": target_name,
            "sources_present": [],
            "vertices_changed": 0,
            "weights_transferred": 0.0,
        }

    changed_vertices = 0
    weights_transferred = 0.0
    vertices_by_source = defaultdict(list)

    for vertex in obj.data.vertices:
        total = 0.0
        present = []
        for membership in vertex.groups:
            source_name = source_indices.get(membership.group)
            if source_name:
                total += membership.weight
                present.append(source_name)
        if total > 0.0:
            changed_vertices += 1
            weights_transferred += total
            target.add([vertex.index], total, "ADD")
            for source_name in present:
                vertices_by_source[source_name].append(vertex.index)

    for source_name, indices in vertices_by_source.items():
        group = obj.vertex_groups.get(source_name)
        if group and indices:
            group.add(indices, 0.0, "REPLACE")
            group.remove(indices)

    return {
        "object": obj.name,
        "target": target_name,
        "sources_present": sorted(set(source_indices.values())),
        "vertices_changed": changed_vertices,
        "weights_transferred": weights_transferred,
    }


def main():
    args = parse_args()
    results = []

    for obj in bpy.data.objects:
        if obj.type != "MESH" or len(obj.data.vertices) == 0:
            continue
        if not obj.vertex_groups:
            continue

        left = transfer_groups(obj, LEFT_TOE_GROUPS, "DEF-foot.L")
        right = transfer_groups(obj, RIGHT_TOE_GROUPS, "DEF-foot.R")
        if left["sources_present"]:
            results.append(left)
        if right["sources_present"]:
            results.append(right)

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    report = {
        "blend_file": bpy.data.filepath,
        "results": results,
        "notes": "Toe weights transferred to foot groups and removed from toe groups to support toes-first export reduction.",
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("MERGE_TOE_WEIGHTS_OK")
    for row in results:
        print(
            f"  {row['object']} {row['target']} "
            f"verts={row['vertices_changed']} weight={row['weights_transferred']:.3f}"
        )


if __name__ == "__main__":
    main()
