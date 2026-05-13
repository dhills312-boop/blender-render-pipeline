"""Implement the Streetwear Puppy-Goth visual pass on vtuber-a8.

This is a look-dev pass that:
- imports a new outfit stack
- preserves v17 as the untouched baseline
- adds collar/paw/chains/muzzle/bridge jewelry/ear jewelry
- elongates the upper canines into subtle fangs

The script is intentionally conservative about destructive edits:
- `Body_Sculpt` is not touched
- old placeholder clothing is hidden in a backup collection
- v17 is not overwritten; the caller must pass a new `--out-blend`
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import zipfile
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = REPO_ROOT / "workspace" / "project" / "vtuber-a8"
DEFAULT_ASSET_ROOT = REPO_ROOT.parent / "Asset_Addon_Library" / "New as of 5_12"

TOP_FBX = DEFAULT_ASSET_ROOT / "streetwear_top" / "Streetwear_Top.fbx"
SKIRT_FBX = DEFAULT_ASSET_ROOT / "womens_pleats_skirt_fbx" / "Women's Pleats Skirt FBX.fbx"
UNDERWEAR_FBX = DEFAULT_ASSET_ROOT / "basic_underwear_02_fbx" / "Basic Underwear_02_FBX.fbx"
CHOKER_FBX = DEFAULT_ASSET_ROOT / "bird-cage-choker" / "source" / "cgae 13.fbx"
PAW_ZIP = DEFAULT_ASSET_ROOT / "cute-paw-3" / "source" / "Paw.zip"
MUZZLE_GLB = DEFAULT_ASSET_ROOT / "Muzzle" / "dog_muzzle_1K.glb"
PIERCING_FBX = DEFAULT_ASSET_ROOT / "piercing06" / "source" / "Piercing06.fbx"
CHAIN_BLEND = DEFAULT_ASSET_ROOT / "curve_to_chain_generator.blend"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--asset-root", default=str(DEFAULT_ASSET_ROOT))
    return parser.parse_args(argv)


def ensure_mode(mode: str):
    if bpy.context.object and bpy.context.object.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def ensure_collection(name: str, parent: bpy.types.Collection | None = None):
    coll = bpy.data.collections.get(name)
    if not coll:
        coll = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(coll)
    elif parent and coll not in parent.children:
        try:
            parent.children.link(coll)
        except RuntimeError:
            pass
    return coll


def move_object_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    if obj.name not in coll.objects:
        coll.objects.link(obj)


def capture_import(import_fn):
    before = {obj.name for obj in bpy.data.objects}
    import_fn()
    new_names = [name for name in bpy.data.objects.keys() if name not in before]
    return [bpy.data.objects[name] for name in new_names]


def import_fbx(path: Path):
    return capture_import(lambda: bpy.ops.import_scene.fbx(filepath=str(path)))


def import_gltf(path: Path):
    return capture_import(lambda: bpy.ops.import_scene.gltf(filepath=str(path)))


def append_object(blend_path: Path, object_name: str):
    before = {obj.name for obj in bpy.data.objects}
    bpy.ops.wm.append(
        directory=str(blend_path) + "\\Object\\",
        filename=object_name,
    )
    new_names = [name for name in bpy.data.objects.keys() if name not in before]
    if object_name in bpy.data.objects:
        return bpy.data.objects[object_name]
    if new_names:
        return bpy.data.objects[new_names[0]]
    raise RuntimeError(f"Failed to append {object_name} from {blend_path}")


def delete_objects(objects):
    for obj in list(objects):
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and getattr(mesh, "users", 0) == 0:
            bpy.data.meshes.remove(mesh)


def mesh_objects(objects):
    return [obj for obj in objects if obj.type == "MESH"]


def non_mesh_objects(objects):
    return [obj for obj in objects if obj.type != "MESH"]


def join_meshes(objects, new_name: str):
    objects = [obj for obj in objects if obj and obj.type == "MESH"]
    if not objects:
        raise RuntimeError(f"No mesh objects to join for {new_name}")
    if len(objects) == 1:
        obj = objects[0]
        obj.name = new_name
        return obj
    ensure_mode("OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = new_name
    return joined


def activate_only(obj: bpy.types.Object):
    ensure_mode("OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_rot_scale(obj: bpy.types.Object):
    activate_only(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def bbox_for_world_points(points):
    mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return {
        "min": mins,
        "max": maxs,
        "center": (mins + maxs) * 0.5,
        "size": maxs - mins,
    }


def world_bbox(obj: bpy.types.Object):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return bbox_for_world_points(points)


def body_slice_bbox(body: bpy.types.Object, z_min: float, z_max: float):
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = body.evaluated_get(deps)
    mesh = eval_obj.to_mesh()
    try:
        pts = []
        for v in mesh.vertices:
            co = eval_obj.matrix_world @ v.co
            if z_min <= co.z <= z_max:
                pts.append(co)
        if not pts:
            raise RuntimeError(f"No body verts in slice {z_min}..{z_max}")
        return bbox_for_world_points(pts)
    finally:
        eval_obj.to_mesh_clear()


def fit_object_to_target(obj: bpy.types.Object, target_size: Vector, center: Vector, bottom_z: float | None = None):
    src = world_bbox(obj)
    sx = target_size.x / max(src["size"].x, 1e-6)
    sy = target_size.y / max(src["size"].y, 1e-6)
    sz = target_size.z / max(src["size"].z, 1e-6)
    uniform = min(sx, sy, sz)
    obj.scale *= uniform
    bpy.context.view_layer.update()

    src = world_bbox(obj)
    target_center = center.copy()
    if bottom_z is not None:
        target_center.z = bottom_z + src["size"].z * 0.5
    obj.location += target_center - src["center"]
    bpy.context.view_layer.update()
    return uniform


def ensure_principled_material(name: str, base_rgba, metallic=0.0, roughness=0.5, alpha=1.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (250, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = tuple(base_rgba[:3]) + (alpha,)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if alpha < 0.999:
        mat.blend_method = "BLEND"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "HASHED"
    else:
        mat.blend_method = "OPAQUE"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "OPAQUE"
    return mat


def assign_single_material(obj: bpy.types.Object, mat: bpy.types.Material):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def body_armature(body: bpy.types.Object):
    for mod in body.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            return mod.object
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("No armature found")
    return max(armatures, key=lambda obj: len(obj.data.bones))


def ensure_armature_modifier(obj: bpy.types.Object, arm_obj: bpy.types.Object):
    for mod in obj.modifiers:
        if mod.type == "ARMATURE":
            mod.object = arm_obj
            return mod
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    return mod


def transfer_weights_from_body(body: bpy.types.Object, target: bpy.types.Object):
    ensure_mode("OBJECT")
    activate_only(target)
    for mod in list(target.modifiers):
        if mod.type == "DATA_TRANSFER":
            target.modifiers.remove(mod)
    mod = target.modifiers.new("A8WeightTransfer", "DATA_TRANSFER")
    mod.object = body
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    mod.layers_vgroup_select_src = "ALL"
    mod.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.modifier_apply(modifier=mod.name)


def bind_with_auto_weights(obj: bpy.types.Object, arm_obj: bpy.types.Object):
    ensure_mode("OBJECT")
    for mod in list(obj.modifiers):
        if mod.type == "ARMATURE":
            obj.modifiers.remove(mod)
    while obj.vertex_groups:
        obj.vertex_groups.remove(obj.vertex_groups[0])
    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)


def rigid_bind(obj: bpy.types.Object, arm_obj: bpy.types.Object, bone_name: str, extra_weights: dict[str, float] | None = None):
    ensure_armature_modifier(obj, arm_obj)
    all_indices = list(range(len(obj.data.vertices)))
    base_group = obj.vertex_groups.get(bone_name) or obj.vertex_groups.new(name=bone_name)
    base_group.add(all_indices, 1.0, "REPLACE")
    if extra_weights:
        base_group.add(all_indices, max(0.0, 1.0 - sum(extra_weights.values())), "REPLACE")
        for other, weight in extra_weights.items():
            vg = obj.vertex_groups.get(other) or obj.vertex_groups.new(name=other)
            vg.add(all_indices, weight, "REPLACE")
    obj.parent = arm_obj
    obj.parent_type = "OBJECT"


def scale_to_height(obj: bpy.types.Object, target_height: float):
    current = max(obj.dimensions.z, 1e-6)
    factor = target_height / current
    obj.scale *= factor
    bpy.context.view_layer.update()
    return factor


def scale_to_max_dimension(obj: bpy.types.Object, target_size: float):
    current = max(max(obj.dimensions), 1e-6)
    factor = target_size / current
    obj.scale *= factor
    bpy.context.view_layer.update()
    return factor


def largest_loose_part(obj: bpy.types.Object):
    dup = obj.copy()
    dup.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(dup)
    activate_only(dup)
    ensure_mode("EDIT")
    bpy.ops.mesh.separate(type="LOOSE")
    ensure_mode("OBJECT")
    pieces = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not pieces:
        raise RuntimeError("Separate by loose parts created no pieces")
    pieces.sort(key=lambda o: len(o.data.polygons), reverse=True)
    keep = pieces[0]
    delete_objects(pieces[1:])
    return keep


def extract_paw_fbx(asset_root: Path):
    extract_root = PROJECT_DIR / "_import_cache" / "paw_extract"
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PAW_ZIP, "r") as zf:
        zf.extractall(extract_root)
    paw_fbx = extract_root / "Paw" / "Mesh" / "Paw.fbx"
    if not paw_fbx.exists():
        raise RuntimeError(f"Missing extracted paw mesh: {paw_fbx}")
    return paw_fbx


def center_of_bones(arm_obj: bpy.types.Object, names: list[str]):
    bones = []
    for name in names:
        bone = arm_obj.data.bones.get(name)
        if bone:
            bones.append(arm_obj.matrix_world @ bone.head_local)
    if not bones:
        raise RuntimeError(f"No bones found for {names}")
    total = Vector((0.0, 0.0, 0.0))
    for p in bones:
        total += p
    return total / len(bones)


def bone_world(arm_obj: bpy.types.Object, name: str):
    bone = arm_obj.data.bones.get(name)
    if not bone:
        raise RuntimeError(f"Missing bone: {name}")
    return arm_obj.matrix_world @ bone.head_local


def separate_loose_mesh_objects(obj: bpy.types.Object):
    activate_only(obj)
    ensure_mode("EDIT")
    bpy.ops.mesh.separate(type="LOOSE")
    ensure_mode("OBJECT")
    return [o for o in bpy.context.selected_objects if o.type == "MESH"]


def choose_bridge_seed(parts):
    scored = []
    for obj in parts:
        dims = obj.dimensions
        max_dim = max(dims)
        face_count = len(obj.data.polygons)
        if 0.001 <= max_dim <= 0.01 and face_count >= 120:
            scored.append((face_count, obj))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    parts = sorted(parts, key=lambda o: len(o.data.polygons), reverse=True)
    return parts[0]


def duplicate_object(obj: bpy.types.Object, new_name: str):
    dup = obj.copy()
    if obj.data:
        dup.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(dup)
    dup.name = new_name
    return dup


def configure_chain_modifier(obj: bpy.types.Object, link_scale: float, link_spacing: float):
    mod = next((m for m in obj.modifiers if m.type == "NODES"), None)
    if not mod:
        raise RuntimeError(f"No geometry nodes modifier on {obj.name}")
    try:
        mod["Socket_5"] = link_scale
        mod["Socket_6"] = link_spacing
        mod["Socket_2"] = 1.0
        mod["Socket_7"] = 0
    except Exception as exc:  # pragma: no cover - defensive against socket renames
        raise RuntimeError(f"Failed to configure chain modifier on {obj.name}: {exc}") from exc
    return mod


def set_bezier_points(curve_obj: bpy.types.Object, points: list[Vector]):
    curve = curve_obj.data
    curve.dimensions = "3D"
    while curve.splines:
        curve.splines.remove(curve.splines[0])
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, point in zip(spline.bezier_points, points):
        bp.co = point
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"


def create_chain_from_template(template_obj: bpy.types.Object, name: str, points: list[Vector], link_scale: float, link_spacing: float):
    curve = duplicate_object(template_obj, name + "_Curve")
    curve.data = template_obj.data.copy()
    move_object_to_collection(curve, ensure_collection("ACC_Neck"))
    set_bezier_points(curve, points)
    configure_chain_modifier(curve, link_scale=link_scale, link_spacing=link_spacing)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = curve.evaluated_get(deps)
    mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=deps)
    mesh_obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(mesh_obj)
    mesh_obj.matrix_world = Matrix.Identity(4)
    delete_objects([curve])
    return mesh_obj


def quadratic_point(points: list[Vector], t: float):
    if len(points) != 3:
        raise ValueError("quadratic_point expects exactly three points")
    a, b, c = points
    return ((1.0 - t) ** 2) * a + (2.0 * (1.0 - t) * t) * b + (t**2) * c


def tangent_at(points: list[Vector], t: float):
    a, b, c = points
    return (2.0 * (1.0 - t) * (b - a) + 2.0 * t * (c - b)).normalized()


def create_manual_link_chain(link_source: bpy.types.Object, name: str, points: list[Vector], count: int, major_size: float):
    copies = []
    for idx in range(count):
        t = idx / max(count - 1, 1)
        pos = quadratic_point(points, t)
        tan = tangent_at(points, t)
        link = duplicate_object(link_source, f"{name}_Link_{idx:02d}")
        move_object_to_collection(link, bpy.context.scene.collection)
        scale_to_max_dimension(link, major_size)
        link.location = pos
        up = Vector((0.0, 0.0, 1.0))
        if abs(tan.dot(up)) > 0.98:
            up = Vector((1.0, 0.0, 0.0))
        quat = tan.to_track_quat("X", "Z")
        if idx % 2:
            quat = quat @ Quaternion(tan, math.radians(90.0))
        link.rotation_mode = "QUATERNION"
        link.rotation_quaternion = quat
        copies.append(link)
    chain = join_meshes(copies, name)
    return chain


def elongate_fangs(teeth: bpy.types.Object):
    upper_material_index = 0
    source = world_bbox(teeth)
    center_x = source["center"].x
    center_z = source["center"].z

    # Work in local space so the shape change survives object transforms.
    mesh = teeth.data
    upper_faces = [poly for poly in mesh.polygons if poly.material_index == upper_material_index]
    upper_verts = {vidx for poly in upper_faces for vidx in poly.vertices}

    moved = []
    for vidx in upper_verts:
        v = mesh.vertices[vidx]
        world = teeth.matrix_world @ v.co
        abs_x = abs(world.x - center_x)
        if 0.008 <= abs_x <= 0.021 and world.z <= center_z - 0.002 and world.y <= source["center"].y:
            world.z -= 0.0085
            world.y -= 0.0015
            v.co = teeth.matrix_world.inverted() @ world
            moved.append(vidx)
    return len(set(moved))


def make_hidden_backup(old_objects):
    backup = ensure_collection("A8_Backup_Hidden")
    for obj in old_objects:
        if not obj:
            continue
        move_object_to_collection(obj, backup)
        obj.hide_set(True)
        obj.hide_viewport = True
        obj.hide_render = True


def clean_imported(objects):
    meshes = [obj for obj in objects if obj and obj.type == "MESH"]
    helpers = [obj for obj in objects if obj and obj.type != "MESH"]
    delete_objects(helpers)
    return meshes


def outfit_pass(body, arm_obj, outfit_coll):
    top_objects = clean_imported(import_fbx(TOP_FBX))
    skirt_objects = clean_imported(import_fbx(SKIRT_FBX))
    underwear_objects = clean_imported(import_fbx(UNDERWEAR_FBX))

    # Strip the unrelated included character parts from the skirt import.
    skirt_meshes = [o for o in skirt_objects if "Skirt" in o.name or "skirt" in o.name]
    delete_objects([o for o in skirt_objects if o not in skirt_meshes])
    skirt_objects = skirt_meshes

    top = join_meshes(top_objects, "OUT_StreetwearTop")
    skirt = join_meshes(skirt_objects, "OUT_PleatedSkirt")
    underwear = join_meshes(underwear_objects, "OUT_Underwear")

    for obj in [top, skirt, underwear]:
        apply_rot_scale(obj)
        move_object_to_collection(obj, outfit_coll)

    torso = body_slice_bbox(body, 1.05, 1.42)
    hips = body_slice_bbox(body, 0.84, 1.07)
    pelvis = body_slice_bbox(body, 0.79, 1.05)

    fit_object_to_target(
        top,
        Vector((torso["size"].x * 1.05, torso["size"].y * 1.55, 0.39)),
        center=Vector((torso["center"].x, torso["center"].y + 0.005, 0.0)),
        bottom_z=torso["min"].z - 0.02,
    )
    fit_object_to_target(
        skirt,
        Vector((hips["size"].x * 0.66, hips["size"].y * 1.25, 0.34)),
        center=Vector((hips["center"].x, hips["center"].y + 0.005, 0.0)),
        bottom_z=hips["min"].z - 0.01,
    )
    fit_object_to_target(
        underwear,
        Vector((pelvis["size"].x * 0.53, pelvis["size"].y * 1.05, 0.27)),
        center=Vector((pelvis["center"].x, pelvis["center"].y + 0.002, 0.0)),
        bottom_z=pelvis["min"].z - 0.005,
    )

    top_mat = ensure_principled_material("A8_Top_Charcoal", (0.09, 0.09, 0.11, 1.0), metallic=0.02, roughness=0.54)
    skirt_mat = ensure_principled_material("A8_Skirt_Black", (0.05, 0.05, 0.06, 1.0), metallic=0.0, roughness=0.68)
    underwear_mat = ensure_principled_material("A8_Underwear_Black", (0.04, 0.04, 0.05, 1.0), metallic=0.0, roughness=0.74)
    assign_single_material(top, top_mat)
    assign_single_material(skirt, skirt_mat)
    assign_single_material(underwear, underwear_mat)

    for obj in [top, skirt, underwear]:
        bind_with_auto_weights(obj, arm_obj)

    return top, skirt, underwear


def collar_pass(body, arm_obj, neck_coll):
    imported = clean_imported(import_fbx(CHOKER_FBX))
    if not imported:
        raise RuntimeError("No choker mesh imported")
    choker_raw = join_meshes(imported, "A8_Choker_Work")
    apply_rot_scale(choker_raw)
    band = largest_loose_part(choker_raw)
    band.name = "ACC_Collar"
    apply_rot_scale(band)
    move_object_to_collection(band, neck_coll)

    neck = body_slice_bbox(body, 1.36, 1.48)
    fit_object_to_target(
        band,
        Vector((neck["size"].x * 0.30, neck["size"].y * 1.25, 0.06)),
        center=Vector((neck["center"].x, neck["center"].y + 0.01, 0.0)),
        bottom_z=neck["center"].z - 0.03,
    )
    collar_mat = ensure_principled_material("A8_Collar_Black", (0.02, 0.02, 0.025, 1.0), metallic=0.0, roughness=0.45)
    assign_single_material(band, collar_mat)
    rigid_bind(band, arm_obj, "DEF-spine.006")
    return band


def paw_pass(arm_obj, neck_coll, collar_bbox):
    paw_fbx = extract_paw_fbx(DEFAULT_ASSET_ROOT)
    paw_meshes = clean_imported(import_fbx(paw_fbx))
    paw = join_meshes(paw_meshes, "ACC_PawCharm")
    apply_rot_scale(paw)
    move_object_to_collection(paw, neck_coll)
    scale_to_max_dimension(paw, 0.034)
    bbox = world_bbox(paw)
    target = Vector((collar_bbox["center"].x, collar_bbox["min"].y - 0.01, collar_bbox["min"].z - 0.035))
    paw.location += target - bbox["center"]
    paw.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    bpy.context.view_layer.update()
    paw_mat = ensure_principled_material("A8_PawCharm_Silver", (0.72, 0.74, 0.78, 1.0), metallic=1.0, roughness=0.28)
    assign_single_material(paw, paw_mat)
    rigid_bind(paw, arm_obj, "DEF-spine.006")
    return paw


def muzzle_pass(arm_obj, face_coll, teeth):
    muzzle_meshes = clean_imported(import_gltf(MUZZLE_GLB))
    muzzle = join_meshes(muzzle_meshes, "ACC_Muzzle")
    apply_rot_scale(muzzle)
    move_object_to_collection(muzzle, face_coll)

    teeth_box = world_bbox(teeth)
    fit_object_to_target(
        muzzle,
        Vector((teeth_box["size"].x * 2.45, 0.065, teeth_box["size"].z * 2.35)),
        center=Vector((teeth_box["center"].x, teeth_box["center"].y - 0.02, teeth_box["center"].z + 0.004)),
    )
    muzzle_mat = ensure_principled_material("A8_Muzzle_BlackMetal", (0.03, 0.03, 0.035, 1.0), metallic=0.75, roughness=0.34)
    assign_single_material(muzzle, muzzle_mat)
    rigid_bind(muzzle, arm_obj, "DEF-nose.004", extra_weights={"DEF-spine.006": 0.2})
    return muzzle


def piercing_pass(arm_obj, face_coll):
    imported = clean_imported(import_fbx(PIERCING_FBX))
    earrings = next((o for o in imported if o.name.startswith("Earrings")), None)
    elf = next((o for o in imported if o.name.startswith("elf")), None)
    if elf:
        delete_objects([elf])
    if not earrings:
        raise RuntimeError("Piercing06 import did not include Earrings mesh")

    apply_rot_scale(earrings)
    metal = bpy.data.materials.get("Metal") or ensure_principled_material("Metal", (0.78, 0.8, 0.84, 1.0), metallic=1.0, roughness=0.24)

    # Build real-ear piercing clusters from the imported layout.
    left_cluster = duplicate_object(earrings, "ACC_EarPiercings_L")
    right_cluster = duplicate_object(earrings, "ACC_EarPiercings_R")
    delete_objects([earrings])
    for obj in [left_cluster, right_cluster]:
        move_object_to_collection(obj, face_coll)
        assign_single_material(obj, metal)
        obj.rotation_euler = (math.radians(-90.0), 0.0, 0.0)
        bpy.context.view_layer.update()
        scale_to_height(obj, 0.060)

    left_anchor = center_of_bones(arm_obj, ["DEF-ear.L", "DEF-ear.L.001", "DEF-ear.L.002", "DEF-ear.L.003"])
    right_anchor = center_of_bones(arm_obj, ["DEF-ear.R", "DEF-ear.R.001", "DEF-ear.R.002", "DEF-ear.R.003"])

    left_bbox = world_bbox(left_cluster)
    right_bbox = world_bbox(right_cluster)
    left_cluster.location += Vector((left_anchor.x - left_bbox["center"].x + 0.003, left_anchor.y - left_bbox["center"].y - 0.002, left_anchor.z - left_bbox["center"].z - 0.002))
    right_cluster.scale.x *= -1.0
    bpy.context.view_layer.update()
    right_cluster.location += Vector((right_anchor.x - right_bbox["center"].x - 0.003, right_anchor.y - right_bbox["center"].y - 0.002, right_anchor.z - right_bbox["center"].z - 0.002))
    bpy.context.view_layer.update()
    rigid_bind(left_cluster, arm_obj, "DEF-ear.L")
    rigid_bind(right_cluster, arm_obj, "DEF-ear.R")

    # Derive a small bridge stud from one loose component of the same earrings mesh.
    seed_src = duplicate_object(left_cluster, "A8_BridgeSeed_Work")
    apply_rot_scale(seed_src)
    parts = separate_loose_mesh_objects(seed_src)
    bridge_seed = choose_bridge_seed(parts)
    for obj in list(parts):
        if obj != bridge_seed:
            delete_objects([obj])
    bridge_seed.name = "A8_BridgeSeed"
    scale_to_height(bridge_seed, 0.0045)
    assign_single_material(bridge_seed, metal)

    left_stud = duplicate_object(bridge_seed, "ACC_BridgeStud_L")
    right_stud = duplicate_object(bridge_seed, "ACC_BridgeStud_R")
    move_object_to_collection(left_stud, face_coll)
    move_object_to_collection(right_stud, face_coll)

    nose_l = bone_world(arm_obj, "DEF-nose.L.001")
    nose_r = bone_world(arm_obj, "DEF-nose.R.001")
    for obj, pos, x_off in [
        (left_stud, nose_l, 0.0015),
        (right_stud, nose_r, -0.0015),
    ]:
        bbox = world_bbox(obj)
        target = Vector((pos.x + x_off, pos.y - 0.0045, pos.z + 0.017))
        obj.location += target - bbox["center"]
        rigid_bind(obj, arm_obj, "DEF-nose.001", extra_weights={"DEF-spine.006": 0.15})

    delete_objects([bridge_seed])
    return left_cluster, right_cluster, left_stud, right_stud, metal


def chain_pass(arm_obj, face_coll, neck_coll, left_bridge, right_bridge, collar, skirt, metal):
    link_source = append_object(CHAIN_BLEND, "Chain_Link.001")
    move_object_to_collection(link_source, neck_coll)
    link_source.hide_set(True)
    link_source.hide_render = True

    lbox = world_bbox(left_bridge)
    rbox = world_bbox(right_bridge)
    bridge_points = [
        lbox["center"],
        (lbox["center"] + rbox["center"]) * 0.5 + Vector((0.0, -0.0025, -0.0035)),
        rbox["center"],
    ]
    bridge_chain = create_manual_link_chain(link_source, "ACC_BridgeChain", bridge_points, count=5, major_size=0.0055)
    move_object_to_collection(bridge_chain, face_coll)
    assign_single_material(bridge_chain, metal)
    rigid_bind(bridge_chain, arm_obj, "DEF-nose.001", extra_weights={"DEF-spine.006": 0.15})

    collar_box = world_bbox(collar)
    collar_points = [
        Vector((collar_box["center"].x - 0.035, collar_box["min"].y - 0.004, collar_box["center"].z - 0.01)),
        Vector((collar_box["center"].x, collar_box["min"].y - 0.018, collar_box["center"].z - 0.045)),
        Vector((collar_box["center"].x + 0.035, collar_box["min"].y - 0.004, collar_box["center"].z - 0.01)),
    ]
    collar_chain = create_manual_link_chain(link_source, "ACC_CollarChain", collar_points, count=7, major_size=0.007)
    move_object_to_collection(collar_chain, neck_coll)
    assign_single_material(collar_chain, metal)
    rigid_bind(collar_chain, arm_obj, "DEF-spine.006")

    skirt_box = world_bbox(skirt)
    hip_points = [
        Vector((skirt_box["min"].x + 0.035, skirt_box["center"].y - 0.012, skirt_box["max"].z - 0.02)),
        Vector((skirt_box["center"].x + 0.012, skirt_box["center"].y - 0.035, skirt_box["center"].z + 0.01)),
        Vector((skirt_box["max"].x - 0.018, skirt_box["center"].y - 0.016, skirt_box["center"].z - 0.01)),
    ]
    hip_chain = create_manual_link_chain(link_source, "ACC_HipChain", hip_points, count=8, major_size=0.0085)
    move_object_to_collection(hip_chain, neck_coll)
    assign_single_material(hip_chain, metal)
    rigid_bind(hip_chain, arm_obj, "DEF-spine.003")

    delete_objects([link_source])
    return bridge_chain, collar_chain, hip_chain


def main():
    args = parse_args()
    body = bpy.data.objects.get("Body")
    teeth = bpy.data.objects.get("Teeth")
    if not body or not teeth:
        raise RuntimeError("Expected Body and Teeth objects in the base blend")

    arm_obj = body_armature(body)
    outfit_coll = ensure_collection("OUTFIT_Main")
    face_coll = ensure_collection("ACC_Face")
    neck_coll = ensure_collection("ACC_Neck")

    make_hidden_backup([bpy.data.objects.get("top_cloth"), bpy.data.objects.get("bottome")])

    top, skirt, underwear = outfit_pass(body, arm_obj, outfit_coll)
    collar = collar_pass(body, arm_obj, neck_coll)
    collar_box = world_bbox(collar)
    paw = paw_pass(arm_obj, neck_coll, collar_box)
    muzzle = muzzle_pass(arm_obj, face_coll, teeth)
    left_ear, right_ear, left_stud, right_stud, metal = piercing_pass(arm_obj, face_coll)
    bridge_chain, collar_chain, hip_chain = chain_pass(arm_obj, face_coll, neck_coll, left_stud, right_stud, collar, skirt, metal)
    fang_count = elongate_fangs(teeth)

    report = {
        "blend_file": bpy.data.filepath,
        "out_blend": args.out_blend,
        "armature": arm_obj.name,
        "created_objects": [
            top.name,
            skirt.name,
            underwear.name,
            collar.name,
            paw.name,
            muzzle.name,
            left_ear.name,
            right_ear.name,
            left_stud.name,
            right_stud.name,
            bridge_chain.name,
            collar_chain.name,
            hip_chain.name,
        ],
        "hidden_backup_objects": ["top_cloth", "bottome"],
        "collections": ["OUTFIT_Main", "ACC_Face", "ACC_Neck", "A8_Backup_Hidden"],
        "fang_vertices_adjusted": fang_count,
        "bindings": {
            "collar": "DEF-spine.006",
            "paw": "DEF-spine.006",
            "muzzle": ["DEF-nose.004", "DEF-spine.006"],
            "bridge_studs": ["DEF-nose.001", "DEF-spine.006"],
            "bridge_chain": ["DEF-nose.001", "DEF-spine.006"],
            "ear_piercings": ["DEF-ear.L", "DEF-ear.R"],
            "hip_chain": "DEF-spine.003",
        },
        "notes": [
            "Real ear piercings reuse the Piercing06 jewelry cluster and intentionally do not import the elf ear geometry.",
            "Old placeholder clothing was hidden, not deleted.",
            "This is a visual pass checkpoint; final per-piece fitting may still need interactive polish.",
        ],
    }

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("A8_VISUAL_PASS_REV3_OK")
    print(f"  out_blend={args.out_blend}")
    print(f"  created={len(report['created_objects'])}")
    print(f"  fang_vertices_adjusted={fang_count}")


if __name__ == "__main__":
    main()
