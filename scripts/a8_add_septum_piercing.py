"""Add a simple septum piercing to the active vtuber blend in-place."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import bpy


OBJECT_NAME = "Septum_Piercing"
MATERIAL_NAME = "Septum_Metal"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--armature")
    parser.add_argument("--bone", default="DEF-nose")
    parser.add_argument("--major-radius", type=float, default=0.0085)
    parser.add_argument("--minor-radius", type=float, default=0.0011)
    parser.add_argument("--offset-y", type=float, default=-0.0035)
    parser.add_argument("--offset-z", type=float, default=-0.028)
    return parser.parse_args(argv)


def pick_armature(name: str | None) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "ARMATURE":
            raise RuntimeError(f"Missing armature: {name}")
        return obj
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("No armatures found")
    return max(armatures, key=lambda obj: len(obj.data.bones))


def ensure_material() -> bpy.types.Material:
    mat = bpy.data.materials.get(MATERIAL_NAME)
    if not mat:
        mat = bpy.data.materials.new(MATERIAL_NAME)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (240, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = (0.78, 0.80, 0.84, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.24
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def remove_existing():
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj:
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def tri_count(obj: bpy.types.Object) -> int:
    return sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons)


def build_torus_mesh(
    mesh: bpy.types.Mesh,
    major_radius: float,
    minor_radius: float,
    major_segments: int = 24,
    minor_segments: int = 12,
):
    verts = []
    faces = []

    for i in range(major_segments):
        theta = (2.0 * math.pi * i) / major_segments
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        for j in range(minor_segments):
            phi = (2.0 * math.pi * j) / minor_segments
            cos_p = math.cos(phi)
            sin_p = math.sin(phi)

            ring = major_radius + minor_radius * cos_p

            x = ring * cos_t
            y = minor_radius * sin_p
            z = ring * sin_t
            verts.append((x, y, z))

    for i in range(major_segments):
        next_i = (i + 1) % major_segments
        for j in range(minor_segments):
            next_j = (j + 1) % minor_segments

            a = i * minor_segments + j
            b = next_i * minor_segments + j
            c = next_i * minor_segments + next_j
            d = i * minor_segments + next_j
            faces.append((a, b, c, d))

    mesh.from_pydata(verts, [], faces)
    mesh.update()


def main():
    args = parse_args()
    arm_obj = pick_armature(args.armature)
    bone = arm_obj.data.bones.get(args.bone)
    if not bone:
        raise RuntimeError(f"Missing bone: {args.bone}")

    remove_existing()

    nose_head = arm_obj.matrix_world @ bone.head_local
    location = (
        nose_head.x,
        nose_head.y + args.offset_y,
        nose_head.z + args.offset_z,
    )

    mesh = bpy.data.meshes.new(OBJECT_NAME)
    obj = bpy.data.objects.new(OBJECT_NAME, mesh)
    bpy.context.scene.collection.objects.link(obj)

    build_torus_mesh(
        mesh,
        major_radius=args.major_radius,
        minor_radius=args.minor_radius,
        major_segments=24,
        minor_segments=12,
    )
    obj.location = location
    obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)

    mat = ensure_material()
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    mod = obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = arm_obj

    vg = obj.vertex_groups.new(name=args.bone)
    vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")

    obj.parent = arm_obj
    obj.parent_type = "OBJECT"

    report = {
        "blend_file": bpy.data.filepath,
        "object": obj.name,
        "material": mat.name,
        "armature": arm_obj.name,
        "bone": args.bone,
        "location_world": [round(v, 6) for v in obj.location],
        "rotation_euler": [round(v, 6) for v in obj.rotation_euler],
        "major_radius_m": args.major_radius,
        "minor_radius_m": args.minor_radius,
        "offsets_m": {"y": args.offset_y, "z": args.offset_z},
        "verts": len(obj.data.vertices),
        "tris": tri_count(obj),
        "notes": "Simple metallic septum ring added as a separate skinned accessory for easy future adjustment.",
    }

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("ADD_SEPTUM_PIERCING_OK")
    print(f"  object={obj.name}")
    print(f"  location={tuple(round(v, 6) for v in obj.location)}")
    print(f"  tris={report['tris']}")


if __name__ == "__main__":
    main()
