"""Add curve-driven bridge chain and tidy vtuber-a8 scene collections.

Uses the chain generator correctly: a curve with the "Customizable Chain Links"
Geometry Nodes modifier, a Chain Collection, and a Set Material input.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
ASSET_ROOT = ROOT.parent / "Asset_Addon_Library"
CHAIN_BLEND = ASSET_ROOT / "New as of 5_12" / "curve_to_chain_generator.blend"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v29_full_clothing_contact.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v30_chain_outliner_cleanup.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v30_chain_outliner_cleanup_report.json"),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name: str, parent: bpy.types.Collection | None = None, hide: bool = False):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        if parent is None:
            bpy.context.scene.collection.children.link(coll)
        else:
            parent.children.link(coll)
    coll.hide_viewport = hide
    coll.hide_render = hide
    return coll


def unlink_from_all_collections(obj: bpy.types.Object):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def move_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection):
    if obj.name not in coll.objects:
        unlink_from_all_collections(obj)
        coll.objects.link(obj)


def world_bounds_center(obj: bpy.types.Object):
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (min_v + max_v) * 0.5, min_v, max_v


def append_chain_assets():
    if not CHAIN_BLEND.exists():
        raise FileNotFoundError(CHAIN_BLEND)

    need_collection = "A8_BridgeChain_Links" not in bpy.data.collections
    need_group = "Geometry Nodes" not in bpy.data.node_groups
    need_material = "Procedural Smooth Metal" not in bpy.data.materials
    need_template = "A8_Chain_Template_Curve" not in bpy.data.objects

    with bpy.data.libraries.load(str(CHAIN_BLEND), link=False) as (data_from, data_to):
        if need_template and "Customizable Chain Links" in data_from.objects:
            data_to.objects = ["Customizable Chain Links"]
        if need_collection and "Chain Links" in data_from.collections:
            data_to.collections = ["Chain Links"]
        if need_group and "Geometry Nodes" in data_from.node_groups:
            data_to.node_groups = ["Geometry Nodes"]
        if need_material and "Procedural Smooth Metal" in data_from.materials:
            data_to.materials = ["Procedural Smooth Metal"]

    source_coll = bpy.data.collections.get("Chain Links")
    if source_coll is None:
        source_coll = bpy.data.collections.get("A8_BridgeChain_Links")
    if source_coll is None:
        raise RuntimeError("Could not load Chain Links collection")

    source_coll.name = "A8_BridgeChain_Links"
    if source_coll.name not in bpy.context.scene.collection.children:
        try:
            bpy.context.scene.collection.children.link(source_coll)
        except RuntimeError:
            pass

    mat = bpy.data.materials.get("Septum_Metal") or bpy.data.materials.get("Procedural Smooth Metal")
    if mat is None:
        mat = bpy.data.materials.new("Chain_Silver")
        mat.diffuse_color = (0.8, 0.78, 0.72, 1.0)

    node_group = bpy.data.node_groups.get("Geometry Nodes")
    if node_group is None:
        raise RuntimeError("Geometry Nodes chain modifier group not loaded")

    template = bpy.data.objects.get("Customizable Chain Links") or bpy.data.objects.get("A8_Chain_Template_Curve")
    if template is None:
        raise RuntimeError("Chain template curve not loaded")
    template.name = "A8_Chain_Template_Curve"
    template.hide_viewport = False
    template.hide_render = False

    # Geometry Nodes Collection Info can be sensitive to hidden source objects.
    # Keep source links technically visible for the modifier, but tuck them into
    # the source collection and move them to the bridge area at very small scale
    # so they do not read as loose, random links in the scene.
    for obj in source_coll.objects:
        obj.hide_viewport = False
        obj.hide_render = True

    return source_coll, node_group, mat, template


def create_bridge_curve(collection: bpy.types.Collection, node_group, chain_collection, material, template):
    left = bpy.data.objects.get("ACC_BridgeStud_L")
    right = bpy.data.objects.get("ACC_BridgeStud_R")
    if left is None or right is None:
        raise RuntimeError("Bridge studs not found")

    left_center, _, _ = world_bounds_center(left)
    right_center, _, _ = world_bounds_center(right)
    if left_center.x > right_center.x:
        left_center, right_center = right_center, left_center

    mid = (left_center + right_center) * 0.5
    # Add a tiny sag and forward bias so the chain reads as draped between studs.
    mid.z -= 0.010
    mid.y -= 0.004

    obj = template
    obj.name = "ACC_BridgeChain_Curve"
    obj.data.name = "ACC_BridgeChain_CurveData"
    obj.animation_data_clear()
    obj.hide_viewport = False
    obj.hide_render = False
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)

    curve_data = obj.data
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 16
    curve_data.bevel_depth = 0.0

    while len(curve_data.splines) > 1:
        curve_data.splines.remove(curve_data.splines[-1])
    spline = curve_data.splines[0] if curve_data.splines else curve_data.splines.new("BEZIER")
    if spline.type != "BEZIER":
        curve_data.splines.clear()
        spline = curve_data.splines.new("BEZIER")
    while len(spline.bezier_points) < 3:
        spline.bezier_points.add(1)
    while len(spline.bezier_points) > 3:
        spline.bezier_points.remove(spline.bezier_points[-1])
    for point, co in zip(spline.bezier_points, (left_center, mid, right_center)):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    mod = obj.modifiers.get("Customizable Chain Links")
    if mod is None:
        mod = obj.modifiers.new("Customizable Chain Links", "NODES")
        mod.node_group = node_group
    elif mod.node_group is None:
        mod.node_group = node_group

    def set_socket(socket_id, value):
        try:
            mod[socket_id] = value
            return
        except TypeError:
            existing = mod.get(socket_id)
            if hasattr(existing, "__len__") and not isinstance(existing, (str, bytes)):
                if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
                    values = list(value)
                else:
                    values = [value] * len(existing)
                for index, item in enumerate(values[: len(existing)]):
                    existing[index] = item
                return
            raise

    # The template generator expects original link meshes around unit scale.
    # This is the final chain size in avatar units.
    set_socket("Socket_2", 0.018)
    set_socket("Socket_3", chain_collection)
    set_socket("Socket_4", material)
    set_socket("Socket_5", 0.010)
    set_socket("Socket_6", 0.04)
    set_socket("Socket_7", 3)

    for link in chain_collection.objects:
        link.location = mid
        link.rotation_euler = (0.0, 0.0, 0.0)
        link.scale = (0.018, 0.018, 0.018)
        link.hide_viewport = False
        link.hide_render = True

    return obj, {
        "left_center": list(left_center),
        "mid": list(mid),
        "right_center": list(right_center),
        "modifier_keys": {key: str(mod[key]) for key in mod.keys()},
    }


def bezier_point(a: Vector, b: Vector, c: Vector, t: float):
    return ((1.0 - t) ** 2) * a + (2.0 * (1.0 - t) * t) * b + (t**2) * c


def bezier_tangent(a: Vector, b: Vector, c: Vector, t: float):
    return (2.0 * (1.0 - t) * (b - a) + 2.0 * t * (c - b)).normalized()


def make_orientation(tangent: Vector, roll_radians: float):
    x_axis = tangent.normalized()
    up = Vector((0.0, 0.0, 1.0))
    if abs(x_axis.dot(up)) > 0.96:
        up = Vector((0.0, 1.0, 0.0))
    y_axis = up.cross(x_axis).normalized()
    z_axis = x_axis.cross(y_axis).normalized()
    base = Matrix(
        (
            (x_axis.x, y_axis.x, z_axis.x, 0.0),
            (x_axis.y, y_axis.y, z_axis.y, 0.0),
            (x_axis.z, y_axis.z, z_axis.z, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    return base @ Matrix.Rotation(roll_radians, 4, "X")


def realize_bridge_chain_mesh(collection, material, curve_report):
    """Create a durable mesh chain for renders from the placed Chain_Link.002 scale."""
    source = bpy.data.objects.get("Chain_Link.002")
    if source is None or source.type != "MESH":
        source = next((obj for obj in bpy.data.objects if obj.name.startswith("Chain_Link") and obj.type == "MESH"), None)
    if source is None:
        raise RuntimeError("No Chain_Link mesh source available for realized bridge chain")

    for stale_name in ("ACC_BridgeChain", "ACC_BridgeChain_Realized"):
        stale = bpy.data.objects.get(stale_name)
        if stale:
            bpy.data.objects.remove(stale, do_unlink=True)

    left = Vector(curve_report["left_center"])
    mid = Vector(curve_report["mid"])
    right = Vector(curve_report["right_center"])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_source = source.evaluated_get(depsgraph)
    source_mesh = eval_source.to_mesh()
    if source_mesh is None or not source_mesh.vertices or not source_mesh.polygons:
        raise RuntimeError(f"{source.name} did not evaluate to usable mesh")

    local_center = Vector((0.0, 0.0, 0.0))
    for vertex in source_mesh.vertices:
        local_center += vertex.co
    local_center /= len(source_mesh.vertices)

    scale = max(abs(source.scale.x), abs(source.scale.y), abs(source.scale.z), 0.006)
    verts = []
    faces = []
    link_count = 6
    for index in range(link_count):
        t = (index + 0.5) / link_count
        point = bezier_point(left, mid, right, t)
        tangent = bezier_tangent(left, mid, right, t)
        roll = math.radians(90.0 if index % 2 else 0.0)
        matrix = Matrix.Translation(point) @ make_orientation(tangent, roll) @ Matrix.Scale(scale, 4)
        offset = len(verts)
        for vertex in source_mesh.vertices:
            verts.append(matrix @ (vertex.co - local_center))
        for poly in source_mesh.polygons:
            faces.append([offset + vid for vid in poly.vertices])

    eval_source.to_mesh_clear()

    mesh = bpy.data.meshes.new("ACC_BridgeChainMesh")
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new("ACC_BridgeChain", mesh)
    if material:
        mesh.materials.append(material)
    collection.objects.link(obj)
    obj.hide_viewport = False
    obj.hide_render = False
    return obj, {
        "source": source.name,
        "links": link_count,
        "scale": scale,
        "vertices": len(mesh.vertices),
        "polygons": len(mesh.polygons),
    }


def collection_for_object(obj: bpy.types.Object, collections):
    name = obj.name
    if name.startswith("Chain_Link"):
        return None
    if name in {"Body"}:
        return collections["A8_ACTIVE_BODY"]
    if name.startswith("FINAL_") or name.startswith("CLEAN_") or name.startswith("FIT_"):
        return collections["A8_ACTIVE_CLOTHING"]
    if name.startswith("Hair") or name.startswith("Scalp"):
        return collections["A8_ACTIVE_HAIR"]
    if name in {"Eye", "EyeOcclusion", "TearLine", "Teeth", "Tongue"}:
        return collections["A8_ACTIVE_FACE_MOUTH_EYES"]
    if name.startswith("ACC_") or name in {"Septum_Piercing", "A8_Choker_Work"}:
        return collections["A8_ACTIVE_ACCESSORIES"]
    if obj.type == "ARMATURE":
        return collections["A8_RIG"]
    if name == "Body_Sculpt" or obj.hide_viewport or obj.hide_render:
        return collections["A8_HIDDEN_SOURCE_BACKUPS"]
    return collections["Need to Organize"]


def base_duplicate_key(name: str):
    parts = name.rsplit(".", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return name


def organize_scene():
    root = ensure_collection("A8_SCENE_ORGANIZED")
    collections = {
        name: ensure_collection(name, root)
        for name in (
            "A8_ACTIVE_BODY",
            "A8_ACTIVE_CLOTHING",
            "A8_ACTIVE_HAIR",
            "A8_ACTIVE_FACE_MOUTH_EYES",
            "A8_ACTIVE_ACCESSORIES",
            "A8_RIG",
            "A8_HIDDEN_SOURCE_BACKUPS",
            "Need to Organize",
        )
    }
    collections["A8_HIDDEN_SOURCE_BACKUPS"].hide_viewport = True
    collections["A8_HIDDEN_SOURCE_BACKUPS"].hide_render = True

    moved = defaultdict(list)
    for obj in list(bpy.data.objects):
        coll = collection_for_object(obj, collections)
        if coll is None:
            continue
        move_to_collection(obj, coll)
        moved[coll.name].append(obj.name)

    # If duplicate base names exist and none of the duplicates are visible, group
    # them into Need to Organize. If one is visible, leave the visible one active.
    by_base = defaultdict(list)
    for obj in bpy.data.objects:
        by_base[base_duplicate_key(obj.name)].append(obj)
    duplicate_groups = {}
    for base, objs in by_base.items():
        if len(objs) < 2:
            continue
        visible = [obj for obj in objs if not obj.hide_viewport and not obj.hide_render]
        duplicate_groups[base] = {
            "objects": [obj.name for obj in objs],
            "visible": [obj.name for obj in visible],
        }
        if not visible:
            for obj in objs:
                move_to_collection(obj, collections["Need to Organize"])

    return moved, duplicate_groups


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    source_coll, node_group, material, template = append_chain_assets()

    acc_coll = ensure_collection("A8_ACTIVE_ACCESSORIES")
    curve, curve_report = create_bridge_curve(acc_coll, node_group, source_coll, material, template)
    chain_mesh, chain_mesh_report = realize_bridge_chain_mesh(acc_coll, material, curve_report)
    curve.hide_viewport = True
    curve.hide_render = True

    moved, duplicates = organize_scene()
    # Move curve back into active accessories after root organization exists.
    final_acc = bpy.data.collections.get("A8_ACTIVE_ACCESSORIES")
    if final_acc:
        move_to_collection(curve, final_acc)
        move_to_collection(chain_mesh, final_acc)
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Chain_Link"):
            unlink_from_all_collections(obj)
            source_coll.objects.link(obj)
    for obj in source_coll.objects:
        obj.hide_viewport = True
        obj.hide_render = True

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "chain_blend": str(CHAIN_BLEND),
        "chain_curve": curve.name,
        "chain_collection": source_coll.name,
        "chain_material": material.name,
        "chain": curve_report,
        "realized_chain_mesh": chain_mesh_report,
        "organized_collections": {key: len(value) for key, value in moved.items()},
        "duplicate_groups": duplicates,
        "visible_meshes": [
            obj.name for obj in bpy.data.objects if obj.type == "MESH" and not obj.hide_viewport
        ],
        "notes": [
            "Bridge chain keeps the intended curve + Customizable Chain Links modifier workflow as hidden authoring source.",
            "A realized ACC_BridgeChain mesh is visible for reliable Blender headless rendering.",
            "Chain source link collection is hidden after the realized chain is built.",
            "Scene objects were moved into organized A8_* collections.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
