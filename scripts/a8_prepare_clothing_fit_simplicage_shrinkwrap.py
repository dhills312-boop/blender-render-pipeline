"""Prepare vtuber-a8 v18 for an interactive clothing fit pass.

This script does not try to solve the fit automatically. It creates a clean
working checkpoint with duplicated garments, shrinkwrap modifiers, body region
groups, and visible cage/collision guide meshes so the next pass can be done
interactively in Blender 4.5.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = DEFAULT_ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(DEFAULT_PROJECT / "a6_v18_streetwear_visual_pass.blend"),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_PROJECT / "a6_v19_clothing_fit_prep.blend"),
    )
    parser.add_argument(
        "--report",
        default=str(
            DEFAULT_PROJECT
            / "audit_reports"
            / "a6_v19_clothing_fit_prep_report.json"
        ),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name: str, hide: bool = False) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = hide
    coll.hide_render = hide
    return coll


def move_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection) -> None:
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)


def make_material(name: str, color: tuple[float, float, float, float]):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = color
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Alpha"].default_value = color[3]
            bsdf.inputs["Roughness"].default_value = 0.55
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
    return mat


def duplicate_for_fit(src_names: tuple[str, ...], dst_name: str, coll: bpy.types.Collection):
    src = None
    for src_name in src_names:
        candidate = bpy.data.objects.get(src_name)
        if candidate is not None and candidate.type == "MESH":
            src = candidate
            break
    if src is None or src.type != "MESH":
        return None
    existing = bpy.data.objects.get(dst_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    dup = src.copy()
    dup.data = src.data.copy()
    dup.animation_data_clear()
    dup.name = dst_name
    dup.data.name = f"{dst_name}_Mesh"
    coll.objects.link(dup)
    dup.hide_viewport = False
    dup.hide_render = False
    src.hide_viewport = True
    src.hide_render = True
    return dup


def assign_group_by_z_fraction(obj: bpy.types.Object, name: str, z_min_frac: float, z_max_frac: float):
    group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
    z_values = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
    if not z_values:
        return 0
    z_min = min(z_values)
    z_max = max(z_values)
    low = z_min + (z_max - z_min) * z_min_frac
    high = z_min + (z_max - z_min) * z_max_frac
    indices = [
        v.index
        for v in obj.data.vertices
        if low <= (obj.matrix_world @ v.co).z <= high
    ]
    if indices:
        group.add(indices, 1.0, "REPLACE")
    return len(indices)


def assign_all_group(obj: bpy.types.Object, name: str):
    group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
    indices = [v.index for v in obj.data.vertices]
    if indices:
        group.add(indices, 1.0, "REPLACE")
    return len(indices)


def add_shrinkwrap(obj: bpy.types.Object, body: bpy.types.Object, group: str, offset: float):
    mod = obj.modifiers.get("A8_FIT_Shrinkwrap_to_Body")
    if mod is None:
        mod = obj.modifiers.new("A8_FIT_Shrinkwrap_to_Body", "SHRINKWRAP")
    mod.target = body
    mod.vertex_group = group
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    mod.offset = offset
    mod.show_viewport = True
    mod.show_render = False

    smooth = obj.modifiers.get("A8_FIT_CorrectiveSmooth_preview")
    if smooth is None:
        smooth = obj.modifiers.new("A8_FIT_CorrectiveSmooth_preview", "CORRECTIVE_SMOOTH")
    smooth.factor = 0.18
    smooth.iterations = 2
    smooth.show_viewport = False
    smooth.show_render = False
    return mod


def body_bounds(body: bpy.types.Object):
    coords = [body.matrix_world @ v.co for v in body.data.vertices]
    min_v = Vector((min(v.x for v in coords), min(v.y for v in coords), min(v.z for v in coords)))
    max_v = Vector((max(v.x for v in coords), max(v.y for v in coords), max(v.z for v in coords)))
    return min_v, max_v


def assign_body_region_group(body: bpy.types.Object, name: str, z_low: float, z_high: float):
    group = body.vertex_groups.get(name) or body.vertex_groups.new(name=name)
    indices = []
    for vert in body.data.vertices:
        world = body.matrix_world @ vert.co
        if z_low <= world.z <= z_high:
            indices.append(vert.index)
    if indices:
        group.add(indices, 1.0, "REPLACE")
    return len(indices)


def create_ellipsoid(name: str, loc, scale, coll: bpy.types.Collection, mat):
    existing = bpy.data.objects.get(name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=16, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj.show_wire = True
    obj.show_in_front = True
    obj.data.materials.append(mat)
    move_to_collection(obj, coll)
    return obj


def hide_manual_chain_objects():
    backup = ensure_collection("A8_Manual_Chain_Backup", hide=True)
    hidden = []
    for obj in bpy.data.objects:
        if obj.name.startswith(("ACC_BridgeChain", "ACC_CollarChain", "ACC_HipChain")):
            obj.hide_viewport = True
            obj.hide_render = True
            move_to_collection(obj, backup)
            hidden.append(obj.name)
    return hidden


def add_notes_text():
    text = bpy.data.texts.get("A8_CLOTHING_FIT_NOTES")
    if text is None:
        text = bpy.data.texts.new("A8_CLOTHING_FIT_NOTES")
    text.clear()
    text.write(
        "a6_v19_clothing_fit_prep\n"
        "\n"
        "Goal: clothing-only fit pass from v18. Chains are hidden for manual placement later.\n"
        "\n"
        "Primary workflow:\n"
        "1. Work on FIT_StreetwearTop_Shrinkwrap and FIT_PleatedSkirt_Shrinkwrap.\n"
        "2. Keep the A8_FIT_Shrinkwrap_to_Body modifiers live while rough fitting.\n"
        "3. Use Edit Mode + Proportional Editing/Sculpt Grab to create bust, waist, and butt clearance.\n"
        "4. Edit the SW_* vertex groups if shrinkwrap pulls hems, pleats, or straps too much.\n"
        "5. Use the SC_Guide_* wire cages as collision/volume references or Simplicage targets.\n"
        "6. Do not work on chains until the final clothing silhouette is accepted.\n"
    )


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    body = bpy.data.objects.get("Body")
    if body is None:
        raise RuntimeError("Body object not found")
    body.hide_viewport = False
    body.hide_render = False

    fit_coll = ensure_collection("CLOTHING_FIT_PREP")
    cage_coll = ensure_collection("SIMPLICAGE_SHRINKWRAP_GUIDES")
    backup = ensure_collection("A8_Original_Clothing_Backup", hide=True)

    top = duplicate_for_fit(("OUT_StreetwearTop", "top_cloth"), "FIT_StreetwearTop_Shrinkwrap", fit_coll)
    skirt = duplicate_for_fit(("OUT_PleatedSkirt", "bottome"), "FIT_PleatedSkirt_Shrinkwrap", fit_coll)
    underwear = duplicate_for_fit(("OUT_Underwear",), "FIT_Underwear_Support", fit_coll)

    # Preserve source clothing out of the way after duplicating it.
    for name in ("OUT_StreetwearTop", "top_cloth", "OUT_PleatedSkirt", "bottome", "OUT_Underwear"):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True
            move_to_collection(obj, backup)

    created_fit = {}
    if top:
        created_fit[top.name] = {
            "contact_vertices": assign_all_group(top, "SW_Top_BodyContact"),
            "offset": 0.014,
        }
        add_shrinkwrap(top, body, "SW_Top_BodyContact", 0.014)
    if skirt:
        created_fit[skirt.name] = {
            "contact_vertices": assign_group_by_z_fraction(skirt, "SW_Skirt_WaistHipContact", 0.62, 1.0),
            "offset": 0.02,
        }
        add_shrinkwrap(skirt, body, "SW_Skirt_WaistHipContact", 0.02)
    if underwear:
        created_fit[underwear.name] = {
            "contact_vertices": assign_all_group(underwear, "SW_Underwear_BodyContact"),
            "offset": 0.01,
        }
        add_shrinkwrap(underwear, body, "SW_Underwear_BodyContact", 0.01)

    min_v, max_v = body_bounds(body)
    height = max_v.z - min_v.z
    center_x = (min_v.x + max_v.x) / 2
    center_y = (min_v.y + max_v.y) / 2

    regions = {
        "A8_Fit_Bust": (min_v.z + height * 0.66, min_v.z + height * 0.78),
        "A8_Fit_Underbust": (min_v.z + height * 0.61, min_v.z + height * 0.68),
        "A8_Fit_Waist": (min_v.z + height * 0.54, min_v.z + height * 0.63),
        "A8_Fit_HipsButt": (min_v.z + height * 0.43, min_v.z + height * 0.56),
    }
    body_groups = {
        name: assign_body_region_group(body, name, low, high)
        for name, (low, high) in regions.items()
    }

    mat = make_material("A8_Fit_Cage_Guide_Transparent", (0.1, 0.75, 1.0, 0.22))
    cages = [
        create_ellipsoid(
            "SC_Guide_BustCollision",
            (center_x, center_y - 0.02, min_v.z + height * 0.71),
            (0.245, 0.145, 0.115),
            cage_coll,
            mat,
        ).name,
        create_ellipsoid(
            "SC_Guide_UnderbustCollision",
            (center_x, center_y - 0.005, min_v.z + height * 0.635),
            (0.205, 0.105, 0.055),
            cage_coll,
            mat,
        ).name,
        create_ellipsoid(
            "SC_Guide_WaistCollision",
            (center_x, center_y, min_v.z + height * 0.585),
            (0.185, 0.095, 0.07),
            cage_coll,
            mat,
        ).name,
        create_ellipsoid(
            "SC_Guide_HipsButtCollision",
            (center_x, center_y + 0.025, min_v.z + height * 0.49),
            (0.285, 0.165, 0.13),
            cage_coll,
            mat,
        ).name,
    ]

    hidden_chains = hide_manual_chain_objects()
    add_notes_text()

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "body": body.name,
        "fit_objects": created_fit,
        "body_region_groups": body_groups,
        "guide_cages": cages,
        "hidden_chain_objects": hidden_chains,
        "notes": [
            "This is a prep checkpoint, not an automatic clothing fix.",
            "Use Shrinkwrap modifiers and SC_Guide_* cages interactively in Blender.",
            "Simplicage remains available for cage/collision work once enabled in the UI.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
