"""Plan weighted bone merges for export reduction."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


MERGE_CANDIDATES = {
    # Toes collapse into the main toe, then main toe into foot if desired.
    "DEF-toe_big.L": "DEF-toe.L",
    "DEF-toe_index.L": "DEF-toe.L",
    "DEF-toe_mid.L": "DEF-toe.L",
    "DEF-toe_ring.L": "DEF-toe.L",
    "DEF-toe_pinky.L": "DEF-toe.L",
    "DEF-toe_big.R": "DEF-toe.R",
    "DEF-toe_index.R": "DEF-toe.R",
    "DEF-toe_mid.R": "DEF-toe.R",
    "DEF-toe_ring.R": "DEF-toe.R",
    "DEF-toe_pinky.R": "DEF-toe.R",
    "DEF-toe.L": "DEF-foot.L",
    "DEF-toe.R": "DEF-foot.R",
    # Limb helper splits.
    "DEF-elbow_share.L": "DEF-forearm.L",
    "DEF-elbow_share.R": "DEF-forearm.R",
    "DEF-knee_share.L": "DEF-shin.L",
    "DEF-knee_share.R": "DEF-shin.R",
    "DEF-upper_arm.L.001": "DEF-upper_arm.L",
    "DEF-upper_arm.R.001": "DEF-upper_arm.R",
    "DEF-forearm.L.001": "DEF-forearm.L",
    "DEF-forearm.R.001": "DEF-forearm.R",
    "DEF-thigh.L.001": "DEF-thigh.L",
    "DEF-thigh.R.001": "DEF-thigh.R",
    "DEF-shin.L.001": "DEF-shin.L",
    "DEF-shin.R.001": "DEF-shin.R",
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    arm_obj = max((obj for obj in bpy.data.objects if obj.type == "ARMATURE"), key=lambda obj: len(obj.data.bones))

    bone_meshes = defaultdict(set)
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if len(obj.data.vertices) == 0:
            continue
        group_names = {group.index: group.name for group in obj.vertex_groups}
        for vertex in obj.data.vertices:
            for group in vertex.groups:
                name = group_names.get(group.group)
                if name:
                    bone_meshes[name].add(obj.name)

    rows = []
    removable = 0
    for src, dst in MERGE_CANDIDATES.items():
        src_bone = arm_obj.data.bones.get(src)
        dst_bone = arm_obj.data.bones.get(dst)
        src_weighted = src in bone_meshes
        dst_weighted = dst in bone_meshes
        if src_bone and src_bone.use_deform:
            removable += 1
        rows.append(
            {
                "source": src,
                "target": dst,
                "source_exists": bool(src_bone),
                "target_exists": bool(dst_bone),
                "source_use_deform": bool(src_bone.use_deform) if src_bone else False,
                "target_use_deform": bool(dst_bone.use_deform) if dst_bone else False,
                "source_weighted": src_weighted,
                "target_weighted": dst_weighted,
                "source_meshes": sorted(bone_meshes.get(src, [])),
                "target_meshes": sorted(bone_meshes.get(dst, [])),
            }
        )

    safe_candidates = [
        row for row in rows
        if row["source_exists"]
        and row["target_exists"]
        and row["source_use_deform"]
        and row["target_use_deform"]
        and row["source_weighted"]
    ]

    report = {
        "blend_file": bpy.data.filepath,
        "armature": arm_obj.name,
        "candidate_count": len(rows),
        "weighted_candidate_count": len(safe_candidates),
        "estimated_deform_reduction_if_merged": len(safe_candidates),
        "candidates": rows,
        "safe_candidates": safe_candidates,
        "notes": [
            "These are merge plans, not direct export toggles.",
            "For weighted bones, transfer vertex-group weights from source to target before disabling source deform or removing it from export.",
            "Breast, face, fingers, and mouth were intentionally not included here.",
        ],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("BONE_MERGE_PLAN_OK")
    print(f"  weighted_candidate_count={len(safe_candidates)}")
    print(f"  estimated_deform_reduction={len(safe_candidates)}")
    for row in safe_candidates[:12]:
        print(f"  {row['source']} -> {row['target']}")


if __name__ == "__main__":
    main()
