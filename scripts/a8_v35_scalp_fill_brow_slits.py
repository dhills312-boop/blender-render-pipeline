"""Create localized scalp filler cards and right eyebrow slit decals.

Starts from the user's Hair-16 positioning stage (v33), avoiding the failed
free-floating v34 filler approach.
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
    parser.add_argument("--output", default=str(PROJECT / "a6_v35_scalp_fill_brow_slits.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v35_scalp_fill_brow_slits_report.json"),
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


def material_copy_from_hair():
    for name in ("ALT_PocolovHair16_SRC_PocolovHair16_Hair_16.001", "ALT_PocolovHair16_SRC_PocolovHair16_Hair_16"):
        obj = bpy.data.objects.get(name)
        if obj and obj.type == "MESH" and obj.data.materials:
            return obj.data.materials[0]
    mat = bpy.data.materials.get("A8_Hair16_WhiteBlackOmbre")
    if mat:
        return mat
    raise RuntimeError("Could not find Hair-16 ombre material")


def make_principled(name: str, color, roughness=0.45):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Alpha"].default_value = color[3]
    mat.blend_method = "HASHED"
    return mat


def scalp_point(x: float, y: float, crown_center: Vector):
    """Approximate upper skull surface in avatar coordinates."""
    rx, ry, rz = 0.118, 0.126, 0.168
    nx = x / rx
    ny = (y - crown_center.y) / ry
    inside = max(0.0, 1.0 - nx * nx - ny * ny)
    z = crown_center.z + math.sqrt(inside) * rz
    return Vector((x, y, z))


def make_card(name: str, p0: Vector, p1: Vector, width: float, mat, coll, uv_span):
    tangent = (p1 - p0).normalized()
    side = Vector((-tangent.y, tangent.x, 0.0))
    if side.length < 0.001:
        side = Vector((1.0, 0.0, 0.0))
    side.normalize()
    # Push just outward/toward camera/top, enough to avoid z-fighting.
    lift = Vector((0.0, -0.006, 0.006))
    verts = [
        p0 - side * width * 0.5 + lift,
        p0 + side * width * 0.5 + lift,
        p1 + side * width * 0.5 + lift,
        p1 - side * width * 0.5 + lift,
    ]
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata([tuple(v) for v in verts], [], [[0, 1, 2, 3]])
    mesh.update()
    uv = mesh.uv_layers.new(name="UVChannel_1")
    u0, u1 = uv_span
    coords = [(u0, 0.08), (u1, 0.08), (u1, 0.92), (u0, 0.92)]
    for loop, co in zip(mesh.polygons[0].loop_indices, coords):
        uv.data[loop].uv = co
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    coll.objects.link(obj)
    set_visible(obj, True)
    return obj


def make_scalp_fillers(coll):
    mat = material_copy_from_hair()
    crown_center = Vector((0.0, -0.010, 1.485))

    # Cards localized to crown/fringe gaps. These stay on the upper skull shell;
    # none descend over the face like the failed v34 rod pass.
    specs = [
        ("ACC_ScalpFillCard_Top_L_01", -0.088, -0.030, -0.082, 0.055, 0.012, (0.63, 0.66)),
        ("ACC_ScalpFillCard_Top_L_02", -0.072, -0.018, -0.066, 0.074, 0.011, (0.66, 0.69)),
        ("ACC_ScalpFillCard_Top_C_01", -0.045, -0.055, 0.020, 0.065, 0.011, (0.69, 0.72)),
        ("ACC_ScalpFillCard_Top_C_02", -0.015, -0.070, 0.052, 0.042, 0.010, (0.72, 0.75)),
        ("ACC_ScalpFillCard_Top_R_01", 0.034, -0.062, 0.088, 0.018, 0.011, (0.75, 0.78)),
        ("ACC_ScalpFillCard_Fringe_L_01", -0.090, -0.115, -0.040, -0.060, 0.010, (0.78, 0.81)),
        ("ACC_ScalpFillCard_Fringe_C_01", -0.035, -0.125, 0.025, -0.070, 0.010, (0.81, 0.84)),
        ("ACC_ScalpFillCard_Fringe_R_01", 0.035, -0.115, 0.088, -0.055, 0.010, (0.84, 0.87)),
        ("ACC_ScalpFillCard_Crown_Back_L", -0.070, 0.020, -0.015, 0.105, 0.011, (0.87, 0.90)),
        ("ACC_ScalpFillCard_Crown_Back_R", 0.018, 0.025, 0.072, 0.102, 0.011, (0.90, 0.93)),
    ]
    created = []
    for name, x0, y0, x1, y1, width, uv_span in specs:
        p0 = scalp_point(x0, y0, crown_center)
        p1 = scalp_point(x1, y1, crown_center)
        created.append(make_card(name, p0, p1, width, mat, coll, uv_span))
    return created


def make_brow_slit(name: str, center: Vector, length: float, width: float, angle_deg: float, mat, coll):
    angle = math.radians(angle_deg)
    axis = Vector((math.cos(angle), 0.0, math.sin(angle)))
    side = Vector((-math.sin(angle), 0.0, math.cos(angle)))
    p0 = center - axis * length * 0.5
    p1 = center + axis * length * 0.5
    lift = Vector((0.0, -0.004, 0.0))
    verts = [
        p0 - side * width * 0.5 + lift,
        p0 + side * width * 0.5 + lift,
        p1 + side * width * 0.5 + lift,
        p1 - side * width * 0.5 + lift,
    ]
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata([tuple(v) for v in verts], [], [[0, 1, 2, 3]])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    coll.objects.link(obj)
    set_visible(obj, True)
    return obj


def add_right_eyebrow_slits(coll):
    # Right eyebrow from model perspective: negative X in this scene's front view.
    skin_mat = make_principled("A8_EyebrowSlit_SkinTone", (0.86, 0.72, 0.86, 1.0), 0.55)
    brow_mat = make_principled("A8_EyebrowSlit_BrowDark", (0.025, 0.022, 0.030, 1.0), 0.50)

    # A short dark brow guide makes the skin-tone double cuts readable even if
    # the base eyebrow texture is hidden by lighting or hair.
    brow = make_brow_slit(
        "ACC_RightEyebrow_DarkGuide",
        Vector((-0.048, -0.122, 1.514)),
        0.060,
        0.006,
        7.0,
        brow_mat,
        coll,
    )
    slit_a = make_brow_slit(
        "ACC_RightEyebrowSlit_01",
        Vector((-0.060, -0.126, 1.516)),
        0.020,
        0.0045,
        63.0,
        skin_mat,
        coll,
    )
    slit_b = make_brow_slit(
        "ACC_RightEyebrowSlit_02",
        Vector((-0.047, -0.126, 1.518)),
        0.020,
        0.0045,
        63.0,
        skin_mat,
        coll,
    )
    return [brow, slit_a, slit_b]


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=str(args.input))

    coll = ensure_collection("A8_SCALP_FILL_AND_BROW_SLITS")
    for obj in list(bpy.data.objects):
        if obj.name.startswith("ACC_ScalpFillCard_") or obj.name.startswith("ACC_RightEyebrow"):
            bpy.data.objects.remove(obj, do_unlink=True)

    fillers = make_scalp_fillers(coll)
    brow = add_right_eyebrow_slits(coll)

    # Keep Scalp_Male hidden; it is not aligned enough to render, but the new
    # filler cards follow an upper-head scalp shell rather than free-floating.
    scalp = bpy.data.objects.get("Scalp_Male")
    if scalp:
        set_visible(scalp, False)

    report = {
        "input": str(args.input),
        "output": str(args.output),
        "generated_scalp_fillers": [obj.name for obj in fillers],
        "generated_right_brow": [obj.name for obj in brow],
        "notes": [
            "Built from v33, not the failed v34 filler.",
            "Scalp filler cards are localized to the upper skull/fringe shell.",
            "Right eyebrow slits are separate ACC objects and can be repositioned/deleted.",
        ],
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))


if __name__ == "__main__":
    main()
