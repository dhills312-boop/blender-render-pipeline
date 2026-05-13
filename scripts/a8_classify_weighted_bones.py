"""Classify weighted deform bones into coarse reduction buckets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def classify(name: str) -> str:
    lower = name.lower()
    if any(key in lower for key in ("tongue", "teeth", "jaw")):
        return "mouth"
    if any(key in lower for key in ("lid.", "brow", "nose", "lip", "chin", "cheek", "forehead", "temple", "ear", "eye.")):
        return "face"
    if "breast" in lower:
        return "breast"
    if any(key in lower for key in ("thumb", "f_index", "f_middle", "f_ring", "f_pinky", "palm", "hand")):
        return "fingers_hands"
    if any(key in lower for key in ("toe", "foot")):
        return "toes_feet"
    if any(key in lower for key in ("shoulder", "upper_arm", "forearm", "elbow")):
        return "arms"
    if any(key in lower for key in ("thigh", "shin", "knee")):
        return "legs"
    if any(key in lower for key in ("spine", "pelvis", "hips", "chest", "neck", "head")):
        return "core"
    return "other"


def main():
    args = parse_args()
    arm_obj = max((obj for obj in bpy.data.objects if obj.type == "ARMATURE"), key=lambda obj: len(obj.data.bones))
    used_vertex_groups = set()

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
                    used_vertex_groups.add(name)

    buckets = defaultdict(list)
    for bone in arm_obj.data.bones:
        if bone.use_deform and bone.name in used_vertex_groups:
            buckets[classify(bone.name)].append(bone.name)

    report = {
        "blend_file": bpy.data.filepath,
        "armature": arm_obj.name,
        "bucket_counts": {key: len(sorted(vals)) for key, vals in sorted(buckets.items())},
        "buckets": {key: sorted(vals) for key, vals in sorted(buckets.items())},
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("WEIGHTED_BONE_BUCKETS_OK")
    for key, vals in sorted(buckets.items()):
        print(f"  {key}: {len(vals)}")


if __name__ == "__main__":
    main()
