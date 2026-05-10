"""Fix the 5 known CC4 DIFFUSE node misroutings on Body's materials.

Mismatches identified by diagnose_texture_misrouting.py:
- Skin_Head  DIFFUSE -> should reference Std_Skin_Head_Diffuse
- Skin_Body  DIFFUSE -> should reference Std_Skin_Body_Diffuse
- Skin_Arm   DIFFUSE -> should reference Std_Skin_Arm_Diffuse
- Skin_Leg   DIFFUSE -> should reference Std_Skin_Leg_Diffuse
- Nails      DIFFUSE -> should reference Std_Nails_Diffuse

For each, find the CC4 (DIFFUSE) Image Texture node in the material and
swap its image to the correct one. Skip if the correct image isn't loaded.

Run:
    blender -b a6_v08_torso_decal_ready.blend -P fix_diffuse_mismatches.py -- \
        --out-blend <path> --report <path>
"""

import argparse
import json
import os
import re
import sys

import bpy

ROLE_RE = re.compile(r"cc3iid_\(([A-Z_]+)\)_v")

FIXES = [
    ("Skin_Head", "DIFFUSE", "Std_Skin_Head_Diffuse"),
    ("Skin_Body", "DIFFUSE", "Std_Skin_Body_Diffuse"),
    ("Skin_Arm",  "DIFFUSE", "Std_Skin_Arm_Diffuse"),
    ("Skin_Leg",  "DIFFUSE", "Std_Skin_Leg_Diffuse"),
    ("Nails",     "DIFFUSE", "Std_Nails_Diffuse"),
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def find_cc4_role_node(mat, role):
    if not mat or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE":
            m = ROLE_RE.search(n.name)
            if m and m.group(1) == role:
                return n
    return None


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    actions = []
    for mat_name, role, target_image_name in FIXES:
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            print(f"[SKIP] {mat_name}: material not found")
            actions.append({"material": mat_name, "status": "material_not_found"})
            continue

        node = find_cc4_role_node(mat, role)
        if not node:
            print(f"[SKIP] {mat_name}.{role}: node not found")
            actions.append({"material": mat_name, "role": role,
                           "status": "node_not_found"})
            continue

        target_img = bpy.data.images.get(target_image_name)
        if not target_img:
            # Try finding it with various extensions.
            candidates = [
                n for n in bpy.data.images.keys()
                if n == target_image_name
                or n.startswith(target_image_name + ".")
            ]
            if candidates:
                target_img = bpy.data.images[candidates[0]]

        if not target_img:
            print(f"[SKIP] {mat_name}.{role}: target image "
                  f"'{target_image_name}' not in bpy.data.images")
            actions.append({
                "material": mat_name, "role": role,
                "status": "target_image_missing",
                "target_name": target_image_name,
            })
            continue

        old_image = node.image.name if node.image else "(none)"
        node.image = target_img
        print(f"[FIXED] {mat_name}.{role}: {old_image} -> {target_img.name}")
        actions.append({
            "material": mat_name,
            "role": role,
            "node_name": node.name,
            "old_image": old_image,
            "new_image": target_img.name,
            "status": "fixed",
        })

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "fixes_attempted": len(FIXES),
        "fixes_applied": sum(1 for a in actions if a.get("status") == "fixed"),
        "actions": actions,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
