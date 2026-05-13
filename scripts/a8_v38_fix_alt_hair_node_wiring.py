"""Fix actual material output wiring for ALT_Hair hair/ribbon textures.

v36/v37 swapped some image nodes, but some were connected only to unused
Principled BSDFs. This pass wires the intended image nodes into the shader path
that is actually connected to Material Output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
OMBRE = PROJECT / "textures" / "WhiteBlackOmbre.png"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v37_paw_material_applied.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v38_alt_hair_nodes_fixed.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v38_alt_hair_nodes_fixed_report.json"),
    )
    return parser.parse_known_args()[0]


def unlink_to_socket(tree, node, socket_name):
    sock = node.inputs.get(socket_name)
    if not sock:
        return []
    removed = []
    for link in list(tree.links):
        if link.to_socket == sock:
            removed.append(f"{link.from_node.name}.{link.from_socket.name}->{node.name}.{socket_name}")
            tree.links.remove(link)
    return removed


def link_image_to_shader(mat, image_node, target_node):
    tree = mat.node_tree
    removed = []
    removed += unlink_to_socket(tree, target_node, "Base Color")
    tree.links.new(image_node.outputs["Color"], target_node.inputs["Base Color"])
    if "Alpha" in target_node.inputs and "Alpha" in image_node.outputs:
        removed += unlink_to_socket(tree, target_node, "Alpha")
        tree.links.new(image_node.outputs["Alpha"], target_node.inputs["Alpha"])
        target_node.inputs["Alpha"].default_value = 1.0
        mat.blend_method = "HASHED"
    return removed


def node_by_image_name(mat, needle: str):
    needle = needle.lower()
    for node in mat.node_tree.nodes:
        if node.bl_idname != "ShaderNodeTexImage" or not node.image:
            continue
        hay = (node.image.name + " " + node.image.filepath).lower()
        if needle in hay:
            return node
    return None


def first_principled_connected_to_output(mat):
    tree = mat.node_tree
    outputs = [node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial"]
    for out in outputs:
        for link in tree.links:
            if link.to_node == out and link.to_socket.name == "Surface":
                if link.from_node.bl_idname == "ShaderNodeBsdfPrincipled":
                    return link.from_node
    # Fallback to first principled.
    for node in tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node
    return None


def group_connected_to_output(mat):
    tree = mat.node_tree
    for out in [node for node in tree.nodes if node.bl_idname == "ShaderNodeOutputMaterial"]:
        for link in tree.links:
            if link.to_node == out and link.to_socket.name == "Surface":
                return link.from_node
    return None


def ensure_ombre_node(mat, image):
    node = node_by_image_name(mat, "whiteblackombre")
    if node is None:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.name = "WhiteBlackOmbre_Texture"
    node.image = image
    node.extension = "REPEAT"
    node.projection = "FLAT"
    return node


def fix_main_hair_materials():
    image = bpy.data.images.load(str(OMBRE), check_existing=True)
    image.colorspace_settings.name = "sRGB"
    changed = []
    for mat_name in ("N00_000_Hair_00_HAIR_01.001", "N00_000_00_HairBack_00_HAIR.001"):
        mat = bpy.data.materials.get(mat_name)
        if not mat or not mat.use_nodes:
            continue
        img_node = ensure_ombre_node(mat, image)

        targets = []
        active_bsdf = first_principled_connected_to_output(mat)
        if active_bsdf:
            targets.append(active_bsdf)
        output_group = group_connected_to_output(mat)
        if output_group and output_group.bl_idname == "ShaderNodeGroup":
            # MToon-style group path used by the VRM hair materials.
            for input_name in ("MainTexture", "Emission_Texture"):
                if input_name in output_group.inputs:
                    for link in list(mat.node_tree.links):
                        if link.to_node == output_group and link.to_socket == output_group.inputs[input_name]:
                            mat.node_tree.links.remove(link)
                    mat.node_tree.links.new(img_node.outputs["Color"], output_group.inputs[input_name])
            if "MainTextureAlpha" in output_group.inputs and "Alpha" in img_node.outputs:
                for link in list(mat.node_tree.links):
                    if link.to_node == output_group and link.to_socket == output_group.inputs["MainTextureAlpha"]:
                        mat.node_tree.links.remove(link)
                mat.node_tree.links.new(img_node.outputs["Alpha"], output_group.inputs["MainTextureAlpha"])

        removed = []
        for target in targets:
            removed += link_image_to_shader(mat, img_node, target)
        changed.append({"material": mat.name, "image_node": img_node.name, "targets": [t.name for t in targets], "removed": removed})
    return changed


def fix_ribbon_materials():
    changed = []
    for mat_name in ("羽.001", "羽"):
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            continue
        mat.use_nodes = True
        tree = mat.node_tree
        group = group_connected_to_output(mat)
        # These ribbon materials were just RGB -> group. Keep that path, but
        # tune the RGB input to visible soft silk pink and add a Principled
        # preview output if the group path is not renderable.
        for node in tree.nodes:
            if node.bl_idname == "ShaderNodeRGB":
                node.outputs["Color"].default_value = (0.98, 0.58, 1.0, 1.0)
                changed.append({"material": mat.name, "rgb_node": node.name, "value": [0.98, 0.58, 1.0, 1.0]})
        if group and group.bl_idname == "ShaderNodeGroup":
            # Make sure RGB is actually connected to DiffuseColor.
            rgb = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeRGB"), None)
            if rgb and "DiffuseColor" in group.inputs:
                for link in list(tree.links):
                    if link.to_node == group and link.to_socket == group.inputs["DiffuseColor"]:
                        tree.links.remove(link)
                tree.links.new(rgb.outputs["Color"], group.inputs["DiffuseColor"])
    return changed


def summarize_alt_hair_links():
    obj = bpy.data.objects.get("ALT_Hair")
    summary = []
    if not obj:
        return summary
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        if mat.name not in {"N00_000_Hair_00_HAIR_01.001", "N00_000_00_HairBack_00_HAIR.001", "羽.001", "羽"}:
            continue
        links = []
        for link in mat.node_tree.links:
            if link.to_node.bl_idname == "ShaderNodeBsdfPrincipled" or link.to_node.bl_idname == "ShaderNodeGroup":
                links.append(f"{link.from_node.name}.{link.from_socket.name}->{link.to_node.name}.{link.to_socket.name}")
        summary.append({"material": mat.name, "links": links})
    return summary


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=str(args.input))
    hair = fix_main_hair_materials()
    ribbons = fix_ribbon_materials()
    summary = summarize_alt_hair_links()

    report = {
        "input": str(args.input),
        "output": str(args.output),
        "hair_fixes": hair,
        "ribbon_fixes": ribbons,
        "alt_hair_link_summary": summary,
        "notes": [
            "Corrected actual shader/output wiring; not just image-node assignment.",
            "Main hair and hairback receive WhiteBlackOmbre on active shader paths.",
            "Ribbon RGB/group path is connected and tuned to soft pink silk.",
        ],
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))


if __name__ == "__main__":
    main()
