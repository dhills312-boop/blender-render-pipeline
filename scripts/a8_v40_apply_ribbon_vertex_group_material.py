import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
SRC = PROJECT / "a6_v39_alt_hair_ribbon_wiring.blend"
DST = PROJECT / "a6_v40_ribbon_vertex_group_material.blend"
REPORT = PROJECT / "a6_v40_ribbon_vertex_group_material_report.json"

OBJ_NAME = "ALT_Hair"
GROUP_NAME = "Ribbons"
SOURCE_RIBBON_MAT = "羽.001"
FALLBACK_TEXTURE_MAT = "N00_000_Hair_00_HAIR_02.001"
NEW_MAT = "ALT_Ribbon_Silk_Sparkle"


def socket(node, name):
    return node.inputs.get(name) or node.outputs.get(name)


def clear_input_links(tree, sock):
    for link in list(sock.links):
        tree.links.remove(link)


def link(tree, from_sock, to_sock):
    clear_input_links(tree, to_sock)
    tree.links.new(from_sock, to_sock)


def find_mtoon_group(mat):
    if not mat or not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "GROUP" and "MainTexture" in node.inputs and "DiffuseColor" in node.inputs:
            return node
    return None


def find_base_image_node(mat):
    if not mat or not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type != "TEX_IMAGE" or not node.image:
            continue
        lname = node.image.name.lower()
        if any(bad in lname for bad in ("normal", "nml", "matcap", "noneblack", "nonenormal", "shader_none")):
            continue
        return node
    return None


def copy_node_tree_material(src, name):
    mat = src.copy()
    mat.name = name
    return mat


def ensure_principled_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.96, 0.75, 1.0, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.32
        bsdf.inputs["Metallic"].default_value = 0.0
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = 0.94
    mat.blend_method = "BLEND"
    mat.show_transparent_back = True
    return mat


def set_default_if_exists(node, input_name, value):
    if node and input_name in node.inputs:
        node.inputs[input_name].default_value = value


def weighted_vertices(obj, vg_index):
    result = set()
    for v in obj.data.vertices:
        for group in v.groups:
            if group.group == vg_index and group.weight > 0.001:
                result.add(v.index)
                break
    return result


def face_material_distribution(obj, faces):
    counts = {}
    for poly in faces:
        mat = obj.material_slots[poly.material_index].material
        key = mat.name if mat else "<none>"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


bpy.ops.wm.open_mainfile(filepath=str(SRC))
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode="OBJECT")

obj = bpy.data.objects.get(OBJ_NAME)
if not obj:
    raise RuntimeError(f"Missing object {OBJ_NAME}")
vg = obj.vertex_groups.get(GROUP_NAME)
if not vg:
    raise RuntimeError(f"Missing vertex group {GROUP_NAME} on {OBJ_NAME}")

weighted = weighted_vertices(obj, vg.index)
if not weighted:
    raise RuntimeError(f"Vertex group {GROUP_NAME} has no weighted vertices")

mesh = obj.data
selected_faces = [p for p in mesh.polygons if p.select]
group_faces_all = [p for p in mesh.polygons if all(vi in weighted for vi in p.vertices)]
group_faces_any = [p for p in mesh.polygons if any(vi in weighted for vi in p.vertices)]

# The user made the ribbon group in edit mode, and Blender preserved the face selection.
# Use selected faces when present, intersecting with the group if possible; this respects
# the manual selection while avoiding accidental whole-head assignment.
if selected_faces:
    selected_group_faces = [p for p in selected_faces if any(vi in weighted for vi in p.vertices)]
    target_faces = selected_group_faces or selected_faces
    target_method = "saved_selected_faces_intersect_ribbons"
else:
    target_faces = group_faces_all or group_faces_any
    target_method = "ribbons_vertex_group"

if not target_faces:
    raise RuntimeError("No ribbon faces could be resolved from selection or vertex group")

source = bpy.data.materials.get(SOURCE_RIBBON_MAT)
fallback = bpy.data.materials.get(FALLBACK_TEXTURE_MAT)
if source and source.use_nodes:
    ribbon_mat = copy_node_tree_material(source, NEW_MAT)
elif fallback and fallback.use_nodes:
    ribbon_mat = copy_node_tree_material(fallback, NEW_MAT)
else:
    ribbon_mat = ensure_principled_material(NEW_MAT)

ribbon_mat.blend_method = "BLEND"
ribbon_mat.show_transparent_back = True
ribbon_mat.use_nodes = True
tree = ribbon_mat.node_tree
group = find_mtoon_group(ribbon_mat)
base = find_base_image_node(ribbon_mat)

if group:
    # Keep texture wiring if the source has a real image, otherwise make it a soft silk pink.
    if base:
        if "MainTexture" in group.inputs:
            link(tree, base.outputs["Color"], group.inputs["MainTexture"])
        if "Alpha" in base.outputs and "MainTextureAlpha" in group.inputs:
            link(tree, base.outputs["Alpha"], group.inputs["MainTextureAlpha"])
    if "DiffuseColor" in group.inputs:
        group.inputs["DiffuseColor"].default_value = (0.95, 0.62, 1.0, 1.0)
    if "ShadeColor" in group.inputs:
        group.inputs["ShadeColor"].default_value = (0.48, 0.22, 0.58, 1.0)
    if "EmissionColor" in group.inputs:
        group.inputs["EmissionColor"].default_value = (0.08, 0.025, 0.12, 1.0)
    if "RimColor" in group.inputs:
        group.inputs["RimColor"].default_value = (1.0, 0.82, 1.0, 1.0)
    if "RimLightingMix" in group.inputs:
        group.inputs["RimLightingMix"].default_value = 0.42
    if "RimFresnelPower" in group.inputs:
        group.inputs["RimFresnelPower"].default_value = 2.2
else:
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    set_default_if_exists(bsdf, "Base Color", (0.95, 0.62, 1.0, 1.0))
    set_default_if_exists(bsdf, "Roughness", 0.32)
    set_default_if_exists(bsdf, "Metallic", 0.0)
    set_default_if_exists(bsdf, "Alpha", 0.94)

slot_index = len(obj.material_slots)
obj.data.materials.append(ribbon_mat)

before_distribution = face_material_distribution(obj, target_faces)
for poly in target_faces:
    poly.material_index = slot_index
after_distribution = face_material_distribution(obj, target_faces)

report = {
    "source": str(SRC),
    "saved": str(DST),
    "object": OBJ_NAME,
    "mesh_data": mesh.name,
    "vertex_group": GROUP_NAME,
    "weighted_vertices": len(weighted),
    "saved_selected_faces": len(selected_faces),
    "group_faces_all_vertices": len(group_faces_all),
    "group_faces_any_vertex": len(group_faces_any),
    "target_faces": len(target_faces),
    "target_method": target_method,
    "new_material_slot": slot_index,
    "new_material": ribbon_mat.name,
    "source_material_used": source.name if source else (fallback.name if fallback else None),
    "base_texture_image": base.image.name if base and base.image else None,
    "before_distribution": before_distribution,
    "after_distribution": after_distribution,
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(DST))
print(json.dumps(report, indent=2))
