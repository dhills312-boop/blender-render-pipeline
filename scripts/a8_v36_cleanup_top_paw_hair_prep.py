"""Cleanup/smoothing pass before deeper hair exploration.

From current v35:
- smooth the new ALT_StreetwearTop similarly to the first top cleanup,
- remove hidden objects from Need to Organize,
- copy/apply Paw_1k_Color texture to the collar paw charm/decal if present,
- connect WhiteBlackOmbre to empty/black hair texture nodes only for main hair
  materials, leaving ears, streaks, and ribbon materials alone,
- give ribbon materials a soft silk/sparkle starting point.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
PAW_SOURCE = (
    ROOT.parent
    / "Asset_Addon_Library"
    / "New as of 5_12"
    / "cute-paw-3"
    / "source"
    / "Paw"
    / "Paw"
    / "Textures"
    / "Paw_1k_Color.png"
)
PAW_DEST = PROJECT / "textures" / "Paw_1k_Color.png"
OMBRE = PROJECT / "textures" / "WhiteBlackOmbre.png"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v35_scalp_fill_brow_slits.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v36_cleanup_top_paw_hair_prep.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v36_cleanup_top_paw_hair_prep_report.json"),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name: str):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = False
    coll.hide_render = False
    return coll


def set_visible(obj: bpy.types.Object, visible: bool):
    obj.hide_viewport = not visible
    obj.hide_set(not visible)
    obj.hide_render = not visible


def smooth_alt_top():
    obj = bpy.data.objects.get("ALT_StreetwearTop")
    if obj is None or obj.type != "MESH":
        return None

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for poly in obj.data.polygons:
        poly.use_smooth = True

    # Keep this modifier non-destructive for manual review.
    if not obj.modifiers.get("A8_Top_SoftSmooth"):
        mod = obj.modifiers.new("A8_Top_SoftSmooth", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
        mod.weight = 50
    if not obj.modifiers.get("A8_Top_GentleSurfaceRelax"):
        smooth = obj.modifiers.new("A8_Top_GentleSurfaceRelax", "SMOOTH")
        smooth.factor = 0.22
        smooth.iterations = 2

    obj.name = "ALT_StreetwearTop_Smoothed"
    return {
        "object": obj.name,
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "modifiers": [mod.name for mod in obj.modifiers],
    }


def remove_hidden_need_to_organize():
    coll = bpy.data.collections.get("Need to Organize")
    if coll is None:
        return []
    removed = []
    for obj in list(coll.objects):
        if obj.hide_get() or obj.hide_viewport or obj.hide_render:
            removed.append({"name": obj.name, "type": obj.type})
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def image_material(name: str, image_path: Path, color=(1, 1, 1, 1), roughness=0.45):
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    image = bpy.data.images.load(str(image_path), check_existing=True)
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        if node.name != "Material Output":
            nodes.remove(node)
    output = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    mat.diffuse_color = color
    return mat


def apply_paw_texture():
    PAW_DEST.parent.mkdir(parents=True, exist_ok=True)
    if PAW_SOURCE.exists():
        shutil.copy2(PAW_SOURCE, PAW_DEST)
    mat = image_material("A8_CollarPaw_1k_Texture", PAW_DEST, (1, 1, 1, 1), 0.5)

    candidates = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and ("paw" in obj.name.lower() or "charm" in obj.name.lower())
    ]
    applied = []
    for obj in candidates:
        if obj.name.startswith("ACC_PawCharm") or "paw" in obj.name.lower():
            obj.data.materials.clear()
            obj.data.materials.append(mat)
            applied.append(obj.name)
    return {"texture": str(PAW_DEST), "material": mat.name, "objects": applied}


def is_main_hair_material(mat_name: str):
    lower = mat_name.lower()
    if "catear" in lower or "ear" in lower or "ribbon" in lower or "羽" in mat_name:
        return False
    if "streak" in lower:
        return False
    return "hair" in lower


def connect_ombre_nodes():
    if not OMBRE.exists():
        raise FileNotFoundError(OMBRE)
    ombre = bpy.data.images.load(str(OMBRE), check_existing=True)
    changed = []
    skipped = []
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        if not is_main_hair_material(mat.name):
            if any(token in mat.name.lower() for token in ("hair", "ear", "ribbon")) or "羽" in mat.name:
                skipped.append(mat.name)
            continue
        local_changes = []
        for node in mat.node_tree.nodes:
            if node.bl_idname != "ShaderNodeTexImage":
                continue
            img = node.image
            hay = ((img.name if img else "") + " " + (img.filepath if img else "")).lower()
            if img is None or "shader_noneblack" in hay or "noneblack" in hay:
                node.image = ombre
                node.extension = "REPEAT"
                local_changes.append(node.name)
        if local_changes:
            changed.append({"material": mat.name, "nodes": local_changes})
    return {"changed": changed, "skipped": skipped}


def tune_ribbon_materials():
    tuned = []
    for mat in bpy.data.materials:
        lower = mat.name.lower()
        if "ribbon" not in lower and "羽" not in mat.name:
            continue
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.98, 0.58, 1.0, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.28
            bsdf.inputs["Metallic"].default_value = 0.0
            if "Coat Weight" in bsdf.inputs:
                bsdf.inputs["Coat Weight"].default_value = 0.35
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = 1.0
        mat.diffuse_color = (0.98, 0.58, 1.0, 1.0)
        tuned.append(mat.name)
    return tuned


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=str(args.input))

    top = smooth_alt_top()
    removed = remove_hidden_need_to_organize()
    paw = apply_paw_texture()
    hair_nodes = connect_ombre_nodes()
    ribbons = tune_ribbon_materials()

    # Keep working objects organized enough for the user to find.
    alt_coll = ensure_collection("A8_ACTIVE_ALT_HAIR_AND_TOP")
    for name in ("ALT_Hair", "ALT_StreetwearTop_Smoothed"):
        obj = bpy.data.objects.get(name)
        if obj:
            if obj.name not in alt_coll.objects:
                for coll in list(obj.users_collection):
                    coll.objects.unlink(obj)
                alt_coll.objects.link(obj)
            set_visible(obj, True)

    report = {
        "input": str(args.input),
        "output": str(args.output),
        "top_smoothing": top,
        "need_to_organize_hidden_removed_count": len(removed),
        "need_to_organize_hidden_removed_sample": removed[:25],
        "paw_texture": paw,
        "hair_ombre_connections": hair_nodes,
        "ribbon_materials_tuned": ribbons,
        "fur_asset_note": "Hair_And_Fur_EEVEE_v01.blend is Blender 5-era and was inspected only; no node groups imported in this 4.5 pass.",
        "notes": [
            "This pass intentionally does not reshape cat ears to puppy ears yet.",
            "WhiteBlackOmbre was assigned only to main hair materials with empty/black placeholder texture nodes.",
            "Ear/streak/ribbon materials were skipped for ombre replacement.",
        ],
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))


if __name__ == "__main__":
    main()
