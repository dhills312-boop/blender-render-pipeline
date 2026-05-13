import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
SRC = PROJECT / "a6_v38_alt_hair_nodes_fixed.blend"
DST = PROJECT / "a6_v39_alt_hair_ribbon_wiring.blend"
REPORT = PROJECT / "a6_v39_alt_hair_ribbon_wiring_report.json"

ALT_HAIR = "ALT_Hair"
RIBBON_MAT = "N00_000_Hair_00_HAIR_02.001"


def first_node(mat, node_type, name=None):
    for node in mat.node_tree.nodes:
        if node.type == node_type and (name is None or node.name == name):
            return node
    return None


def group_with_input(mat, input_name):
    for node in mat.node_tree.nodes:
        if node.type == "GROUP" and input_name in node.inputs:
            return node
    return None


def clear_input_links(tree, socket):
    for link in list(socket.links):
        tree.links.remove(link)


def link(tree, from_socket, to_socket):
    clear_input_links(tree, to_socket)
    tree.links.new(from_socket, to_socket)


def image_label(node):
    if not node or not getattr(node, "image", None):
        return None
    return node.image.name


def is_base_candidate(node):
    name = (image_label(node) or "").lower()
    if not name:
        return False
    blocked = ["normal", "nml", "matcap", "noneblack", "nonenormal", "shader_none"]
    return not any(part in name for part in blocked)


def node_linked_to_input(mat, input_name):
    group = group_with_input(mat, input_name)
    if not group:
        return None
    socket = group.inputs[input_name]
    if not socket.links:
        return None
    return socket.links[0].from_node


def material_face_count(obj, slot_index):
    return sum(1 for poly in obj.data.polygons if poly.material_index == slot_index)


bpy.ops.wm.open_mainfile(filepath=str(SRC))

obj = bpy.data.objects.get(ALT_HAIR)
if not obj:
    raise RuntimeError(f"Missing {ALT_HAIR}")

slot_summary = []
for i, slot in enumerate(obj.material_slots):
    mat = slot.material
    slot_summary.append(
        {
            "slot": i,
            "material": mat.name if mat else None,
            "faces": material_face_count(obj, i),
        }
    )

ribbon_slot = None
ribbon_mat = None
for i, slot in enumerate(obj.material_slots):
    if slot.material and slot.material.name == RIBBON_MAT:
        ribbon_slot = i
        ribbon_mat = slot.material
        break

if ribbon_mat is None:
    raise RuntimeError(f"Missing visible ribbon/streak material {RIBBON_MAT}")

tree = ribbon_mat.node_tree
group = group_with_input(ribbon_mat, "MainTexture")
if not group:
    raise RuntimeError(f"{RIBBON_MAT} has no MToon-style group MainTexture input")

base = node_linked_to_input(ribbon_mat, "MainTexture")
if not base or base.type != "TEX_IMAGE" or not is_base_candidate(base):
    base = next((n for n in tree.nodes if n.type == "TEX_IMAGE" and is_base_candidate(n)), None)
if not base:
    raise RuntimeError(f"Could not identify base texture for {RIBBON_MAT}")

emission = node_linked_to_input(ribbon_mat, "Emission_Texture")
if not emission or emission.type != "TEX_IMAGE":
    emission = next(
        (
            n
            for n in tree.nodes
            if n.type == "TEX_IMAGE"
            and n is not base
            and is_base_candidate(n)
        ),
        None,
    )

link(tree, base.outputs["Color"], group.inputs["MainTexture"])
if "Alpha" in base.outputs and "MainTextureAlpha" in group.inputs:
    link(tree, base.outputs["Alpha"], group.inputs["MainTextureAlpha"])
if emission and "Emission_Texture" in group.inputs:
    link(tree, emission.outputs["Color"], group.inputs["Emission_Texture"])

principled = first_node(ribbon_mat, "BSDF_PRINCIPLED")
if principled:
    if "Base Color" in principled.inputs:
        link(tree, base.outputs["Color"], principled.inputs["Base Color"])
    if "Alpha" in base.outputs and "Alpha" in principled.inputs:
        link(tree, base.outputs["Alpha"], principled.inputs["Alpha"])
    if "Roughness" in principled.inputs:
        principled.inputs["Roughness"].default_value = 0.38
    if "Metallic" in principled.inputs:
        principled.inputs["Metallic"].default_value = 0.0

ribbon_mat.blend_method = "BLEND"
ribbon_mat.use_screen_refraction = False
ribbon_mat.show_transparent_back = True

unused_feather = bpy.data.materials.get("羽.001")
unused_feather_faces = None
if unused_feather:
    unused_feather_faces = sum(
        material_face_count(obj, i)
        for i, slot in enumerate(obj.material_slots)
        if slot.material == unused_feather
    )

report = {
    "source": str(SRC),
    "saved": str(DST),
    "alt_hair_object": ALT_HAIR,
    "slot_summary": slot_summary,
    "visible_ribbon_slot": ribbon_slot,
    "visible_ribbon_material": ribbon_mat.name,
    "base_texture_node": base.name,
    "base_texture_image": image_label(base),
    "emission_texture_node": emission.name if emission else None,
    "emission_texture_image": image_label(emission) if emission else None,
    "unused_feather_material_faces": unused_feather_faces,
    "notes": [
        "The visible ribbon/streak geometry is inside ALT_Hair, not a separate object.",
        "Material 羽.001 exists but has zero assigned faces in ALT_Hair, so wiring it would not affect the visible model.",
    ],
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(DST))
print(json.dumps(report, indent=2))
