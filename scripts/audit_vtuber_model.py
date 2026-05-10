"""Headless audit of a VTuber-candidate .blend file.

Outputs a JSON report covering: object inventory, mesh stats (tris, UVs, vgroups,
shape keys, materials), armature topology (bones, hierarchy depth, humanoid
mapping clues), texture inventory (size, resolution, total memory), and a verdict
on VRChat performance rank readiness.

Usage:
    blender -b <file>.blend -P audit_vtuber_model.py -- --out report.json
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


VRCHAT_RANK_LIMITS = {
    "excellent": {"tris": 32_000, "materials": 4, "skinned_meshes": 1, "bones": 75},
    "good":      {"tris": 70_000, "materials": 8, "skinned_meshes": 2, "bones": 150},
    "medium":    {"tris": 70_000, "materials": 16, "skinned_meshes": 8, "bones": 256},
}

HUMANOID_BONE_HINTS = [
    "hips", "pelvis", "spine", "chest", "neck", "head",
    "shoulder", "upperarm", "arm", "forearm", "hand",
    "upperleg", "thigh", "leg", "calf", "foot", "toe",
    "breast", "bust",
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="Path to write JSON report")
    return p.parse_args(argv)


def mesh_tris(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def texture_inventory():
    images = []
    total_bytes = 0
    for img in bpy.data.images:
        if img.name == "Render Result" or img.name == "Viewer Node":
            continue
        w, h = img.size[0], img.size[1]
        # Estimate uncompressed RGBA size; matches VRChat texture mem heuristic.
        bytes_est = w * h * 4 if w and h else 0
        total_bytes += bytes_est
        images.append({
            "name": img.name,
            "filepath": img.filepath,
            "size": [w, h],
            "channels": img.channels,
            "estimated_bytes": bytes_est,
            "is_packed": bool(img.packed_file),
        })
    return images, total_bytes


def detect_humanoid(armature_obj):
    if not armature_obj or armature_obj.type != "ARMATURE":
        return {}
    arm = armature_obj.data
    bone_names_lower = {b.name.lower(): b.name for b in arm.bones}

    # Heuristic match — looks for any bone whose lowercase name CONTAINS the hint.
    matches = defaultdict(list)
    for hint in HUMANOID_BONE_HINTS:
        for lower, original in bone_names_lower.items():
            if hint in lower:
                matches[hint].append(original)

    # Crude humanoid score: how many key parts found.
    key_parts = ["hips", "spine", "head", "shoulder", "hand", "foot"]
    score = sum(1 for k in key_parts if matches.get(k))
    return {
        "bone_count": len(arm.bones),
        "humanoid_score": f"{score}/{len(key_parts)}",
        "humanoid_matches": dict(matches),
    }


def material_inventory(meshes):
    mat_set = set()
    for m in meshes:
        for slot in m.material_slots:
            if slot.material:
                mat_set.add(slot.material.name)
    return sorted(mat_set)


def shape_key_summary(obj):
    if not obj.data.shape_keys:
        return {"count": 0, "names": []}
    keys = [k.name for k in obj.data.shape_keys.key_blocks]
    return {"count": len(keys), "names": keys}


def viseme_blendshape_check(all_shape_key_names):
    # Common VRChat viseme names (Oculus naming).
    visemes = ["sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR",
               "aa", "E", "I", "O", "U"]
    flat = " ".join(all_shape_key_names).lower()
    found = [v for v in visemes if v.lower() in flat]
    return {"found_count": len(found), "found": found}


def rank_verdict(total_tris, mat_count, skinned_count, bone_count):
    for rank in ("excellent", "good", "medium"):
        lim = VRCHAT_RANK_LIMITS[rank]
        if (total_tris <= lim["tris"]
                and mat_count <= lim["materials"]
                and skinned_count <= lim["skinned_meshes"]
                and bone_count <= lim["bones"]):
            return rank
    return "poor_or_worse"


def main():
    args = parse_args()
    blend_path = bpy.data.filepath

    report = {
        "blend_file": blend_path,
        "blend_size_bytes": os.path.getsize(blend_path) if blend_path else None,
        "blender_version": bpy.app.version_string,
        "scenes": [s.name for s in bpy.data.scenes],
        "objects": {"total": len(bpy.data.objects), "by_type": defaultdict(int)},
        "meshes": [],
        "armatures": [],
        "totals": {},
        "textures": {},
        "vrchat_rank_verdict": None,
        "humanoid_analysis": {},
        "viseme_check": {},
        "warnings": [],
    }

    for o in bpy.data.objects:
        report["objects"]["by_type"][o.type] += 1

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    total_tris = 0
    all_shape_keys = []

    for m in meshes:
        tris = mesh_tris(m)
        total_tris += tris
        sk = shape_key_summary(m)
        all_shape_keys.extend(sk["names"])
        report["meshes"].append({
            "name": m.name,
            "tris": tris,
            "verts": len(m.data.vertices),
            "uv_maps": [u.name for u in m.data.uv_layers],
            "vertex_groups": len(m.vertex_groups),
            "material_slots": len(m.material_slots),
            "shape_keys": sk,
            "modifiers": [
                {"name": mod.name, "type": mod.type} for mod in m.modifiers
            ],
            "has_armature_modifier": any(
                mod.type == "ARMATURE" for mod in m.modifiers
            ),
        })

    for a in armatures:
        report["armatures"].append({
            "name": a.name,
            **detect_humanoid(a),
        })

    if armatures:
        # Pick the largest armature for the headline humanoid analysis.
        primary = max(armatures, key=lambda a: len(a.data.bones))
        report["humanoid_analysis"] = {
            "primary_armature": primary.name,
            **detect_humanoid(primary),
        }
        bone_count = len(primary.data.bones)
    else:
        bone_count = 0
        report["warnings"].append("No armature found — model is not rigged.")

    images, total_tex_bytes = texture_inventory()
    report["textures"] = {
        "count": len(images),
        "total_estimated_bytes": total_tex_bytes,
        "total_estimated_mb": round(total_tex_bytes / (1024 * 1024), 2),
        "list": images,
    }

    mats = material_inventory(meshes)
    skinned_count = sum(
        1 for m in meshes if any(mod.type == "ARMATURE" for mod in m.modifiers)
    )

    report["totals"] = {
        "total_tris": total_tris,
        "total_meshes": len(meshes),
        "total_skinned_meshes": skinned_count,
        "total_armatures": len(armatures),
        "total_materials_unique": len(mats),
        "material_names": mats,
        "total_bones_primary_armature": bone_count,
        "total_shape_keys": len(all_shape_keys),
    }
    report["objects"]["by_type"] = dict(report["objects"]["by_type"])
    report["vrchat_rank_verdict"] = rank_verdict(
        total_tris, len(mats), skinned_count, bone_count
    )
    report["viseme_check"] = viseme_blendshape_check(all_shape_keys)

    # Heuristic warnings.
    if total_tris > 70_000:
        report["warnings"].append(
            f"Tris ({total_tris:,}) exceed VRChat Good limit (70,000) — "
            "decimation or LOD will be required."
        )
    if len(mats) > 8:
        report["warnings"].append(
            f"Materials ({len(mats)}) exceed VRChat Good limit (8) — "
            "atlasing required."
        )
    if skinned_count > 2:
        report["warnings"].append(
            f"Skinned meshes ({skinned_count}) exceed VRChat Good limit (2) — "
            "merge required."
        )
    if not report["viseme_check"]["found"]:
        report["warnings"].append(
            "No common viseme blendshape names detected — VRChat lipsync "
            "may need manual mapping or new shape keys."
        )
    if total_tex_bytes > 75 * 1024 * 1024:
        report["warnings"].append(
            f"Texture memory estimate ({report['textures']['total_estimated_mb']} MB) "
            "exceeds VRChat Good limit (75 MB)."
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Brief stdout summary so the audit shows progress.
    print(f"AUDIT_OK file={blend_path}")
    print(f"  tris={total_tris:,} meshes={len(meshes)} mats={len(mats)} "
          f"bones={bone_count} verdict={report['vrchat_rank_verdict']}")


if __name__ == "__main__":
    main()
