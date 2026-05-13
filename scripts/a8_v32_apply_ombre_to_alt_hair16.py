"""Apply WhiteBlackOmbre.png to the hidden Pocolov Hair 16 alt collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
TEXTURE = PROJECT / "textures" / "WhiteBlackOmbre.png"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v31_bows_alt_assets.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v32_hair16_ombre_alt.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v32_hair16_ombre_alt_report.json"),
    )
    return parser.parse_known_args()[0]


def find_source_hair_material():
    source = bpy.data.objects.get("Hair_30629")
    if source:
        for slot in source.material_slots:
            if slot.material and slot.material.use_nodes:
                return slot.material
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage" and node.image:
                hay = (node.image.name + " " + node.image.filepath).lower()
                if "darksea" in hay or "darksea.png" in hay:
                    return mat
    raise RuntimeError("Could not find source hair material using DarkSea.png")


def build_image_material(image_path: Path):
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.colorspace_settings.name = "sRGB"

    source = find_source_hair_material()
    old = bpy.data.materials.get("A8_Hair16_WhiteBlackOmbre")
    if old:
        bpy.data.materials.remove(old, do_unlink=True)

    mat = source.copy()
    mat.name = "A8_Hair16_WhiteBlackOmbre"
    mat.diffuse_color = source.diffuse_color

    replaced = []
    for node in mat.node_tree.nodes:
        if node.bl_idname != "ShaderNodeTexImage":
            continue
        node.image = image
        node.extension = "REPEAT"
        node.projection = "FLAT"
        replaced.append(node.name)

    return mat, image, source, replaced


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))
    mat, image, source_mat, replaced_nodes = build_image_material(TEXTURE)

    targets = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.name.startswith("ALT_PocolovHair16_")
    ]
    if not targets:
        raise RuntimeError("No ALT_PocolovHair16 mesh objects found")

    assigned = []
    for obj in targets:
        if "Head" in obj.name:
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        assigned.append(obj.name)
        obj.hide_viewport = True
        obj.hide_set(True)
        obj.hide_render = True

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "texture": str(TEXTURE),
        "image_size": list(image.size),
        "material": mat.name,
        "source_material_copied": source_mat.name,
        "replaced_image_nodes": replaced_nodes,
        "assigned_objects": assigned,
        "all_alt_hair_objects": [obj.name for obj in targets],
        "notes": [
            "Applied WhiteBlackOmbre.png only to the hidden Hair-16 alternate.",
            "Hair-16 ombre material is a copy of the visible hair DarkSea material; only the image texture was swapped.",
            "Current accepted visible hair was not changed.",
            "Hair-16 alternate remains hidden by default; unhide ALT_PocolovHair16_Source to inspect.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
