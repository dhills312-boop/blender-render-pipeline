"""Apply Paw_1k_Color.png to the existing collar paw material."""

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


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v36_cleanup_top_paw_hair_prep.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v37_paw_material_applied.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v37_paw_material_applied_report.json"),
    )
    return parser.parse_known_args()[0]


def apply_paw_material():
    PAW_DEST.parent.mkdir(parents=True, exist_ok=True)
    if PAW_SOURCE.exists():
        shutil.copy2(PAW_SOURCE, PAW_DEST)
    if not PAW_DEST.exists():
        raise FileNotFoundError(PAW_DEST)

    image = bpy.data.images.load(str(PAW_DEST), check_existing=True)
    image.colorspace_settings.name = "sRGB"

    mat = bpy.data.materials.get("Paw_Painted") or bpy.data.materials.new("Paw_Painted")
    mat.use_nodes = True
    mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        if node.name != "Material Output":
            nodes.remove(node)
    output = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
    tex = nodes.new("ShaderNodeTexImage")
    tex.name = "Paw_1k_Color_Texture"
    tex.image = image
    tex.extension = "EXTEND"
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.48
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs and "Alpha" in tex.outputs:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    assigned_slots = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name == "A8_Choker_Work":
            for index, slot in enumerate(obj.material_slots):
                if slot.material and slot.material.name == "Paw_Painted":
                    slot.material = mat
                    assigned_slots.append({"object": obj.name, "slot": index})
    return mat, image, assigned_slots


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=str(args.input))
    mat, image, assigned_slots = apply_paw_material()

    report = {
        "input": str(args.input),
        "output": str(args.output),
        "texture": str(PAW_DEST),
        "image_size": list(image.size),
        "material": mat.name,
        "assigned_slots": assigned_slots,
        "notes": [
            "Applied Paw_1k_Color.png to existing Paw_Painted material.",
            "A8_Choker_Work already had a Paw_Painted material slot, so no floating decal plane was added.",
        ],
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))


if __name__ == "__main__":
    main()
