"""Add skirt bow decorations and import unused assets as hidden alternates.

Starts from the protected v30 visual read and saves a v31 checkpoint.
Visible change: small bow decorations on the accepted skirt.
Hidden alt collections: original Streetwear_Top FBX and Pocolov Hair 16.
"""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
ASSET_ROOT = ROOT.parent / "Asset_Addon_Library" / "New as of 5_12"

BOW_FBX = ASSET_ROOT / "bow-tie" / "source" / "bow_tie.fbx"
STREETWEAR_FBX = ASSET_ROOT / "streetwear_top" / "Streetwear_Top.fbx"
HAIR_ZIP = ASSET_ROOT / "pocolov-hair-16" / "source" / "Pocolov Hair 16.zip"
HAIR_EXTRACT_DIR = PROJECT / "import_sources" / "pocolov_hair_16"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v30_chain_outliner_cleanup.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v31_bows_alt_assets.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v31_bows_alt_assets_report.json"),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name: str, parent: bpy.types.Collection | None = None, hide=False):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        if parent:
            parent.children.link(coll)
        else:
            bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = hide
    coll.hide_render = hide
    return coll


def unlink_from_all(obj: bpy.types.Object):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def move_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection):
    if obj.name not in coll.objects:
        unlink_from_all(obj)
        coll.objects.link(obj)


def set_hidden(obj: bpy.types.Object, hidden: bool, render_hidden: bool | None = None):
    obj.hide_viewport = hidden
    obj.hide_set(hidden)
    obj.hide_render = hidden if render_hidden is None else render_hidden


def world_bounds(obj: bpy.types.Object):
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return min_v, max_v, (min_v + max_v) * 0.5


def objects_world_bounds(objects):
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        zero = Vector((0.0, 0.0, 0.0))
        return zero, zero, zero
    min_v = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    max_v = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return min_v, max_v, (min_v + max_v) * 0.5


def import_fbx(path: Path, collection: bpy.types.Collection, prefix: str):
    if not path.exists():
        raise FileNotFoundError(path)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    for obj in imported:
        if obj.type == "MESH":
            obj.name = f"{prefix}_{obj.name}"
            obj.data.name = f"{obj.name}Mesh"
        move_to_collection(obj, collection)
    return imported


def clear_parent_keep_world(obj: bpy.types.Object):
    matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_parent_inverse.identity()
    obj.matrix_world = matrix


def make_joined_bow_source(imported, collection: bpy.types.Collection):
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("bow_tie.fbx did not import a mesh")
    verts = []
    faces = []
    for obj in meshes:
        clear_parent_keep_world(obj)
        offset = len(verts)
        for vertex in obj.data.vertices:
            verts.append(obj.matrix_world @ vertex.co)
        for poly in obj.data.polygons:
            faces.append([offset + vid for vid in poly.vertices])

    mesh = bpy.data.meshes.new("SRC_BowTie_TemplateMesh")
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    source = bpy.data.objects.new("SRC_BowTie_Template", mesh)
    move_to_collection(source, collection)
    set_hidden(source, True)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return source


def make_principled_material(name: str, color, metallic=0.0, roughness=0.45):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = color
    return mat


def center_and_scale_mesh_data(obj: bpy.types.Object, target_width: float):
    """Bake size into mesh data so decoration objects keep clean scale values."""
    # FBX imports often carry the meaningful size in object scale. Bake that
    # first, then normalize the actual vertex data to the desired avatar size.
    sx, sy, sz = obj.scale
    obj.data.transform(Matrix.Diagonal((sx, sy, sz, 1.0)))
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()

    local_points = [vertex.co.copy() for vertex in obj.data.vertices]
    min_v = Vector((min(p.x for p in local_points), min(p.y for p in local_points), min(p.z for p in local_points)))
    max_v = Vector((max(p.x for p in local_points), max(p.y for p in local_points), max(p.z for p in local_points)))
    center = (min_v + max_v) * 0.5
    dims = max_v - min_v
    widest = max(dims.x, dims.y, dims.z, 0.001)
    factor = target_width / widest
    for vertex in obj.data.vertices:
        vertex.co = (vertex.co - center) * factor
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()


def create_skirt_bows(source_mesh: bpy.types.Object, collection: bpy.types.Collection):
    skirt = bpy.data.objects.get("FINAL_PleatedSkirt_Contact")
    if skirt is None:
        raise RuntimeError("FINAL_PleatedSkirt_Contact not found")

    min_v, max_v, center = world_bounds(skirt)
    bow_mat = make_principled_material("A8_SkirtBow_BlackPink", (0.34, 0.025, 0.25, 1.0), 0.0, 0.34)

    # Keep these just proud of the skirt front. The model's face/front reads as
    # negative Y in the current scene.
    front_y = min_v.y - 0.010
    waist_z = max_v.z - (max_v.z - min_v.z) * 0.17
    upper_pleat_z = max_v.z - (max_v.z - min_v.z) * 0.34
    width = max_v.x - min_v.x
    placements = [
        ("CenterWaist", Vector((center.x, front_y, waist_z)), 0.100, 0.0),
        ("LeftPleat", Vector((center.x - width * 0.22, front_y - 0.003, upper_pleat_z)), 0.075, math.radians(-8.0)),
        ("RightPleat", Vector((center.x + width * 0.22, front_y - 0.003, upper_pleat_z)), 0.075, math.radians(8.0)),
    ]

    created = []
    for suffix, location, target_width, roll in placements:
        bow = source_mesh.copy()
        bow.data = source_mesh.data.copy()
        bow.name = f"ACC_SkirtBow_{suffix}"
        bow.data.name = f"{bow.name}Mesh"
        clear_parent_keep_world(bow)
        collection.objects.link(bow)
        bow.hide_viewport = False
        bow.hide_set(False)
        bow.hide_render = False
        bow.data.materials.clear()
        bow.data.materials.append(bow_mat)
        bow.location = location
        bow.rotation_euler = (math.radians(90.0), 0.0, roll)
        center_and_scale_mesh_data(bow, target_width)
        created.append(bow)
    return created


def extract_hair_zip():
    HAIR_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    fbx = HAIR_EXTRACT_DIR / "Pocolov Hair 16.fbx"
    if not fbx.exists():
        with zipfile.ZipFile(HAIR_ZIP, "r") as archive:
            archive.extractall(HAIR_EXTRACT_DIR)
    return fbx


def bake_current_scale(obj: bpy.types.Object):
    sx, sy, sz = obj.scale
    obj.data.transform(Matrix.Diagonal((sx, sy, sz, 1.0)))
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()


def fit_alt_asset_to_target(imported, label: str, target_name: str, extra_scale: float = 1.0):
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        return []

    target = bpy.data.objects.get(target_name)
    if target is None:
        for obj in meshes:
            obj.name = f"ALT_{label}_{obj.name}"
            set_hidden(obj, True)
        return [obj.name for obj in meshes]

    bpy.context.view_layer.update()
    src_min, src_max, src_center = objects_world_bounds(meshes)
    tgt_min, tgt_max, tgt_center = world_bounds(target)
    src_dims = src_max - src_min
    tgt_dims = tgt_max - tgt_min
    src_ref = max(src_dims.x, src_dims.y, src_dims.z, 0.001)
    tgt_ref = max(tgt_dims.x, tgt_dims.y, tgt_dims.z, 0.001)
    factor = (tgt_ref / src_ref) * extra_scale

    for obj in meshes:
        obj.name = f"ALT_{label}_{obj.name}"
        obj.location = tgt_center + (obj.location - src_center) * factor
        bake_current_scale(obj)
        obj.data.transform(Matrix.Scale(factor, 4))
        obj.data.update()
        set_hidden(obj, True)
    return [obj.name for obj in meshes]


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    root = ensure_collection("A8_ALT_AND_DECOR_PASS")
    bow_coll = ensure_collection("A8_ACTIVE_SKIRT_BOWS", root, hide=False)
    alt_root = ensure_collection("A8_ALT_ASSETS_UNUSED", root, hide=True)
    alt_top_coll = ensure_collection("ALT_StreetwearTop_Source", alt_root, hide=True)
    alt_hair_coll = ensure_collection("ALT_PocolovHair16_Source", alt_root, hide=True)
    bow_source_coll = ensure_collection("A8_HIDDEN_BOW_SOURCE", root, hide=True)

    # Clean prior v31 decorations if re-running.
    for obj in list(bpy.data.objects):
        if obj.name.startswith("ACC_SkirtBow_") or obj.name.startswith("SRC_BowTie_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    bow_imported = import_fbx(BOW_FBX, bow_source_coll, "SRC_BowTie")
    bow_mesh = make_joined_bow_source(bow_imported, bow_source_coll)
    bow_objects = create_skirt_bows(bow_mesh, bow_coll)

    top_imported = import_fbx(STREETWEAR_FBX, alt_top_coll, "SRC_StreetwearTop")
    alt_top_names = fit_alt_asset_to_target(top_imported, "StreetwearTop", "FINAL_StreetwearTop_Contact")

    hair_fbx = extract_hair_zip()
    hair_imported = import_fbx(hair_fbx, alt_hair_coll, "SRC_PocolovHair16")
    alt_hair_names = fit_alt_asset_to_target(hair_imported, "PocolovHair16", "Hair_30629")

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "visible_bows": [
            {
                "name": obj.name,
                "location": [round(v, 6) for v in obj.location],
                "scale": [round(v, 6) for v in obj.scale],
                "rotation_euler": [round(v, 6) for v in obj.rotation_euler],
            }
            for obj in bow_objects
        ],
        "alt_streetwear_top_objects": alt_top_names,
        "alt_hair16_objects": alt_hair_names,
        "collections": {
            "visible_bows": bow_coll.name,
            "hidden_alt_top": alt_top_coll.name,
            "hidden_alt_hair": alt_hair_coll.name,
        },
        "notes": [
            "Skirt bows are visible by default.",
            "Streetwear top FBX and Pocolov Hair 16 are imported into hidden alternate collections.",
            "Protected v30 visual read remains untouched.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
