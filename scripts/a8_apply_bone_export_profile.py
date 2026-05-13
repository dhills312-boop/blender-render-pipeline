"""Apply a named export bone profile by toggling use_deform on selected bones."""

from __future__ import annotations

import argparse
import json
import os
import sys

import bpy


PROFILES = {
    "toes_first": [
        "DEF-toe.L",
        "DEF-toe.R",
        "DEF-toe_big.L",
        "DEF-toe_big.R",
        "DEF-toe_index.L",
        "DEF-toe_index.R",
        "DEF-toe_mid.L",
        "DEF-toe_mid.R",
        "DEF-toe_pinky.L",
        "DEF-toe_pinky.R",
        "DEF-toe_ring.L",
        "DEF-toe_ring.R",
    ],
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out-blend")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--armature")
    return parser.parse_args(argv)


def pick_armature(name: str | None) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "ARMATURE":
            raise RuntimeError(f"Missing armature: {name}")
        return obj
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("No armatures found")
    return max(armatures, key=lambda obj: len(obj.data.bones))


def count_deform_bones(armature: bpy.types.Armature) -> int:
    return sum(1 for bone in armature.bones if bone.use_deform)


def main():
    args = parse_args()
    arm_obj = pick_armature(args.armature)
    arm = arm_obj.data
    targets = PROFILES[args.profile]

    before = count_deform_bones(arm)
    changed = []
    missing = []

    for name in targets:
        bone = arm.bones.get(name)
        if not bone:
            missing.append(name)
            continue
        if bone.use_deform:
            changed.append(name)
            if not args.dry_run:
                bone.use_deform = False

    after = before - len(changed) if args.dry_run else count_deform_bones(arm)

    if args.out_blend and not args.dry_run:
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    report = {
        "blend_file": bpy.data.filepath,
        "armature": arm_obj.name,
        "profile": args.profile,
        "dry_run": bool(args.dry_run),
        "before_deform_bones": before,
        "after_deform_bones": after,
        "removed_from_deform": changed,
        "missing": missing,
    }

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("BONE_EXPORT_PROFILE_OK")
    print(f"  profile={args.profile}")
    print(f"  before={before}")
    print(f"  after={after}")
    print(f"  changed={len(changed)}")


if __name__ == "__main__":
    main()
