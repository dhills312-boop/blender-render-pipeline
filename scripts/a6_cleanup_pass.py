"""Cleanup pass for a6 — strip cruft, prepare for VTuber accessory work.

Loads a6/blender file.blend, performs:
1. Save-As to a versioned working file (never edits the original).
2. Delete the existing hair mesh (will be replaced with custom hair later).
3. Identify Rigify control/widget bones (ORG-/MCH-/WGT-/.001 tweak duplicates).
   The Rigify rig has 725 bones because it includes IK/FK controls + widget meshes.
   For VRChat we only need the DEF- (deform) bones — those are the ones with
   weights baked into the mesh. We keep the full Rigify rig in this pass for now
   (it's needed for the artist's animation/posing) but report which bones are
   removable later.
4. Remove unused armatures (the file has 3; we keep the active Rigify one).
5. List large textures so we can plan downsizing in a separate pass.
6. Report before/after stats.

Run via:
    blender -b "<a6 file>.blend" -P a6_cleanup_pass.py -- --out-blend <new_path> \
        --report <report_path>

DRY_RUN mode (no save) when --dry-run is passed.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def collect_stats():
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    total_tris = 0
    for m in meshes:
        m.data.calc_loop_triangles()
        total_tris += len(m.data.loop_triangles)

    mat_set = set()
    for m in meshes:
        for slot in m.material_slots:
            if slot.material:
                mat_set.add(slot.material.name)

    primary = max(armatures, key=lambda a: len(a.data.bones)) if armatures else None
    bone_count = len(primary.data.bones) if primary else 0

    return {
        "tris": total_tris,
        "meshes": len(meshes),
        "materials": len(mat_set),
        "bones_primary": bone_count,
        "armatures": len(armatures),
        "objects_total": len(bpy.data.objects),
        "images": len(bpy.data.images),
    }


def find_hair_meshes():
    """Return only the main hair mesh — preserve any 'Scalp_*' meshes as a
    base layer for future hair-card replacements (avoids skull poke-through)."""
    candidates = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        name_lower = o.name.lower()
        # Match exact 'hair' or 'hair.001' style names; skip scalp.
        if name_lower == "hair" or name_lower.startswith("hair."):
            candidates.append(o)
    return candidates


def delete_object_and_data(obj):
    """Remove an object and orphan its mesh data."""
    me = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if me and me.users == 0:
        bpy.data.meshes.remove(me)


def find_secondary_armatures():
    """Return armatures other than the largest one (the active rig)."""
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) <= 1:
        return []
    arms_sorted = sorted(arms, key=lambda a: len(a.data.bones), reverse=True)
    return arms_sorted[1:]


def categorize_rigify_bones(armature_obj):
    """Group bones by Rigify role for reporting; we don't delete here."""
    if not armature_obj:
        return {}
    buckets = defaultdict(list)
    for bone in armature_obj.data.bones:
        n = bone.name
        if n.startswith("DEF-") or n.startswith("DEF_"):
            buckets["deform"].append(n)
        elif n.startswith("ORG-") or n.startswith("ORG_"):
            buckets["original_rigify"].append(n)
        elif n.startswith("MCH-") or n.startswith("MCH_"):
            buckets["mechanism"].append(n)
        elif n.startswith("WGT-") or n.startswith("WGT_"):
            buckets["widget"].append(n)
        elif "_ik" in n.lower() or "_fk" in n.lower():
            buckets["ik_fk_control"].append(n)
        elif "tweak" in n.lower():
            buckets["tweak"].append(n)
        elif "vis_" in n.lower():
            buckets["visualizer"].append(n)
        else:
            buckets["other_or_meta"].append(n)
    return {k: sorted(v) for k, v in buckets.items()}


def list_large_textures(threshold_pixels=4096):
    """List images at or above the given resolution on either axis."""
    large = []
    for img in bpy.data.images:
        if img.name in ("Render Result", "Viewer Node"):
            continue
        w, h = img.size[0], img.size[1]
        if max(w, h) >= threshold_pixels:
            large.append({
                "name": img.name,
                "filepath": img.filepath,
                "size": [w, h],
                "estimated_uncompressed_mb": round(w * h * 4 / (1024 * 1024), 2),
            })
    return sorted(large, key=lambda i: -i["estimated_uncompressed_mb"])


def main():
    args = parse_args()

    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print(f"DRY_RUN: {args.dry_run}")
    print("=" * 60)

    before = collect_stats()
    print(f"BEFORE: {before}")

    actions = {
        "deleted_hair_meshes": [],
        "deleted_secondary_armatures": [],
    }

    # 1. Delete hair meshes.
    hair = find_hair_meshes()
    print(f"\n[1] Found {len(hair)} hair-like mesh(es): "
          f"{[o.name for o in hair]}")
    for o in hair:
        actions["deleted_hair_meshes"].append({
            "name": o.name,
            "tris_was": len(o.data.loop_triangles),
        })
    if not args.dry_run:
        for o in list(hair):
            delete_object_and_data(o)
        print(f"    deleted {len(hair)} hair mesh(es)")

    # 2. Remove secondary armatures.
    sec_arms = find_secondary_armatures()
    print(f"\n[2] Found {len(sec_arms)} secondary armature(s): "
          f"{[a.name for a in sec_arms]}")
    for a in sec_arms:
        actions["deleted_secondary_armatures"].append({
            "name": a.name,
            "bone_count": len(a.data.bones),
        })
    if not args.dry_run:
        for a in list(sec_arms):
            arm_data = a.data
            bpy.data.objects.remove(a, do_unlink=True)
            if arm_data.users == 0:
                bpy.data.armatures.remove(arm_data)
        print(f"    removed {len(sec_arms)} armature(s)")

    # 3. Categorize Rigify bones for later cleanup planning.
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    primary = max(armatures, key=lambda a: len(a.data.bones)) if armatures else None
    bone_categories = categorize_rigify_bones(primary)
    print(f"\n[3] Rigify bone breakdown ({primary.name if primary else 'NONE'}):")
    for cat, bones in bone_categories.items():
        print(f"    {cat:20s} {len(bones):4d}")

    # 4. List large textures for the future downsize pass.
    big_tex = list_large_textures()
    total_big_mb = sum(t["estimated_uncompressed_mb"] for t in big_tex)
    print(f"\n[4] Found {len(big_tex)} texture(s) at >=4K resolution, "
          f"~{total_big_mb:.1f} MB uncompressed")
    for t in big_tex[:10]:
        print(f"    {t['name']:40s} {t['size'][0]}x{t['size'][1]} "
              f"~{t['estimated_uncompressed_mb']} MB")
    if len(big_tex) > 10:
        print(f"    ... and {len(big_tex) - 10} more")

    after = collect_stats()
    print(f"\nAFTER:  {after}")

    delta = {k: after[k] - before[k] for k in before}
    print(f"DELTA:  {delta}")

    # Save versioned working file.
    if not args.dry_run:
        os.makedirs(os.path.dirname(args.out_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
        print(f"\nSAVED: {args.out_blend}")

    # Write the structured report.
    report = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "dry_run": args.dry_run,
        "before": before,
        "after": after,
        "delta": delta,
        "actions": actions,
        "rigify_bone_breakdown": {k: len(v) for k, v in bone_categories.items()},
        "rigify_bone_breakdown_detail": bone_categories,
        "large_textures_4k_plus": big_tex,
        "large_texture_total_mb": round(total_big_mb, 1),
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
