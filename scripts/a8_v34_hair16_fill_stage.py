"""Add non-destructive Hair-16 strand fillers to the positioning stage.

Keeps the user's visible Hair-16 placement and adds:
- a small scalp/under-cap so sparse card gaps do not show bare skull,
- thin curve strands for side/front density.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v33_hair16_position_stage.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v34_hair16_fill_stage.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v34_hair16_fill_stage_report.json"),
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


def unlink_from_all(obj: bpy.types.Object):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def move_to_collection(obj: bpy.types.Object, coll: bpy.types.Collection):
    if obj.name not in coll.objects:
        unlink_from_all(obj)
        coll.objects.link(obj)


def set_visible(obj: bpy.types.Object, visible: bool):
    obj.hide_viewport = not visible
    obj.hide_set(not visible)
    obj.hide_render = not visible


def world_bounds(obj: bpy.types.Object):
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return min_v, max_v, (min_v + max_v) * 0.5


def objects_bounds(objects):
    pts = []
    for obj in objects:
        pts.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return min_v, max_v, (min_v + max_v) * 0.5


def make_material(name: str, color, roughness=0.48):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Alpha"].default_value = color[3]
    mat.blend_method = "BLEND"
    mat.use_screen_refraction = False
    return mat


def make_scalp_cap(body: bpy.types.Object, hair_objects, coll):
    _, _, hair_center = objects_bounds(hair_objects)
    body_min, body_max, _ = world_bounds(body)
    mat = make_material("A8_Hair16_ScalpFill_SoftWhiteBlack", (0.62, 0.60, 0.66, 0.72), 0.62)

    verts = []
    faces = []
    # A light upper cap only. Keep it above the brow so it cannot cover the face.
    rx, ry, rz = 0.105, 0.112, 0.118
    center = Vector((0.0, -0.004, min(body_max.z - 0.050, hair_center.z + 0.060)))
    lat_steps = 7
    lon_steps = 24
    theta_start = 0.0
    theta_end = math.radians(68.0)
    for i in range(lat_steps + 1):
        theta = theta_start + (theta_end - theta_start) * (i / lat_steps)
        z = math.cos(theta) * rz
        ring_r = math.sin(theta)
        for j in range(lon_steps):
            phi = (math.tau * j) / lon_steps
            x = math.cos(phi) * ring_r * rx
            y = math.sin(phi) * ring_r * ry
            verts.append(center + Vector((x, y, z)))
    for i in range(lat_steps):
        for j in range(lon_steps):
            a = i * lon_steps + j
            b = i * lon_steps + ((j + 1) % lon_steps)
            c = (i + 1) * lon_steps + ((j + 1) % lon_steps)
            d = (i + 1) * lon_steps + j
            faces.append([a, b, c, d])

    mesh = bpy.data.meshes.new("ACC_Hair16ScalpFillMesh")
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new("ACC_Hair16ScalpFill", mesh)
    obj.data.materials.append(mat)
    coll.objects.link(obj)
    # Optional helper only. It was too easy for a cap to read as a face mask,
    # so keep it hidden unless manually toggled on for inspection.
    set_visible(obj, False)
    return obj


def make_curve_strand(name: str, points, mat, coll, bevel=0.0022):
    curve = bpy.data.curves.new(f"{name}Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = bevel
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (co.x, co.y, co.z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    curve.materials.append(mat)
    coll.objects.link(obj)
    set_visible(obj, True)
    return obj


def make_filler_strands(coll):
    created = []
    light = make_material("A8_Hair16_Filler_LightStrands", (0.82, 0.80, 0.86, 1.0), 0.44)
    shadow = make_material("A8_Hair16_Filler_ShadowStrands", (0.12, 0.11, 0.14, 1.0), 0.50)
    silver = make_material("A8_Hair16_Filler_MidStrands", (0.48, 0.47, 0.54, 1.0), 0.48)

    # Hand-authored guide strands around the sparse areas. These are deliberately
    # thin independent curves, not duplicate alpha cards.
    specs = []
    for i, x in enumerate([-0.078, -0.058, -0.038, -0.018, 0.020, 0.040, 0.060, 0.080]):
        y = -0.126 - 0.004 * (i % 3)
        z0 = 1.650 - 0.006 * (i % 2)
        z1 = 1.485 - 0.018 * (i % 3)
        specs.append((f"ACC_Hair16Filler_Bang_{i+1:02d}", [Vector((x, y, z0)), Vector((x * 0.76, y - 0.010, 1.565)), Vector((x * 0.66, y - 0.002, z1))], [light, silver, shadow][i % 3], 0.00045))

    for side, sign in (("L", -1.0), ("R", 1.0)):
        for i in range(7):
            x0 = sign * (0.105 + 0.011 * i)
            x1 = sign * (0.128 + 0.015 * i)
            y0 = -0.080 + 0.010 * (i % 3)
            z0 = 1.600 - 0.018 * i
            z1 = 1.250 - 0.030 * (i % 4)
            specs.append((f"ACC_Hair16Filler_{side}_Side_{i+1:02d}", [Vector((x0, y0, z0)), Vector((x1, y0 - 0.014, (z0 + z1) * 0.5)), Vector((x1 * 1.05, y0 + 0.006, z1))], [light, silver, shadow][(i + (0 if sign < 0 else 1)) % 3], 0.00058))

    for name, points, mat, bevel in specs:
        created.append(make_curve_strand(name, points, mat, coll, bevel))
    return created


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    body = bpy.data.objects.get("Body")
    if body is None:
        raise RuntimeError("Body not found")

    # Clean prior generated filler if re-running.
    for obj in list(bpy.data.objects):
        if obj.name.startswith("ACC_Hair16Filler_") or obj.name.startswith("ACC_Hair16ScalpFill"):
            bpy.data.objects.remove(obj, do_unlink=True)

    coll = ensure_collection("A8_HAIR16_FILLERS")
    hair_objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and obj.name.startswith("ALT_PocolovHair16_SRC_PocolovHair16_Hair_16")
        and not obj.hide_get()
        and not obj.hide_render
    ]
    if not hair_objects:
        raise RuntimeError("No visible Hair-16 hair object found")

    # Prefer the user's transformed duplicate if present; otherwise use the base alt hair.
    source = sorted(hair_objects, key=lambda obj: obj.name.endswith(".001"), reverse=True)[0]
    scalp = make_scalp_cap(body, hair_objects, coll)
    fillers = make_filler_strands(coll)

    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)
    bpy.context.view_layer.objects.active = source

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "source_hair_for_fillers": source.name,
        "generated": [scalp.name] + [obj.name for obj in fillers],
        "source_transform": {
            "location": [round(v, 6) for v in source.location],
            "rotation": [round(v, 6) for v in source.rotation_euler],
            "scale": [round(v, 6) for v in source.scale],
        },
        "notes": [
            "Filler objects are separate ACC_* curves/meshes and can be deleted without touching Hair-16.",
            "Scalp fill is present but hidden by default; toggle it only if bare scalp is still distracting.",
            "Filler strands are thin independent curves, not duplicate alpha cards.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
