import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
DECALS = PROJECT / "textures" / "decals"
SRC = PROJECT / "a6_v40_ribbon_vertex_group_material.blend"
DST = PROJECT / "a6_v41_decals_fur_prep.blend"
REPORT = PROJECT / "a6_v41_decals_fur_prep_report.json"


def clean_name(name):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def load_image(path):
    image = bpy.data.images.get(path.name)
    if not image:
        image = bpy.data.images.load(str(path))
        image.name = path.name
    image.filepath = str(path)
    return image


def make_alpha_image_material(name, image_path, base_alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.show_transparent_back = True
    mat.use_screen_refraction = False
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = load_image(image_path)
    tex.extension = "CLIP"
    bsdf.inputs["Alpha"].default_value = base_alpha
    bsdf.inputs["Roughness"].default_value = 0.42
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def make_tattoo_material(name, atlas_path, ink=(0.012, 0.012, 0.016, 1.0)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.show_transparent_back = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tex = tree.nodes.new("ShaderNodeTexImage")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    mix = tree.nodes.new("ShaderNodeMixShader")
    tex.image = load_image(atlas_path)
    tex.extension = "CLIP"
    bsdf.inputs["Base Color"].default_value = ink
    bsdf.inputs["Roughness"].default_value = 0.58
    ramp.color_ramp.elements[0].position = 0.015
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].position = 0.22
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    tree.links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], mix.inputs["Fac"])
    tree.links.new(transparent.outputs["BSDF"], mix.inputs[1])
    tree.links.new(bsdf.outputs["BSDF"], mix.inputs[2])
    tree.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def make_fur_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    bump_noise = tree.nodes.new("ShaderNodeTexNoise")
    bump = tree.nodes.new("ShaderNodeBump")

    noise.inputs["Scale"].default_value = 42.0
    noise.inputs["Detail"].default_value = 13.0
    noise.inputs["Roughness"].default_value = 0.62
    ramp.color_ramp.elements[0].position = 0.17
    ramp.color_ramp.elements[0].color = (0.58, 0.56, 0.52, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.96, 0.94, 0.88, 1.0)
    bump_noise.inputs["Scale"].default_value = 115.0
    bump_noise.inputs["Detail"].default_value = 9.0
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.018

    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 1.0

    tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(bump_noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def make_plane(name, center, u_axis, v_axis, width, height, mat, collection, uv_box=None, parent=None):
    c = Vector(center)
    u = Vector(u_axis).normalized() * (width * 0.5)
    v = Vector(v_axis).normalized() * (height * 0.5)
    verts = [c - u - v, c + u - v, c + u + v, c - u + v]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata([tuple(vtx) for vtx in verts], [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    if uv_box:
        x0, y0, x1, y1 = uv_box
        uv_values = [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]
    else:
        uv_values = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for loop, value in zip(mesh.polygons[0].loop_indices, uv_values):
        uv.data[loop].uv = value
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    collection.objects.link(obj)
    if parent:
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.show_transparent = True
    return obj


def uv_box_px(x0, y0, x1, y1, image_width=1600, image_height=2048):
    return (x0 / image_width, 1.0 - y1 / image_height, x1 / image_width, 1.0 - y0 / image_height)


bpy.ops.wm.open_mainfile(filepath=str(SRC))
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode="OBJECT")

decals_col = ensure_collection("DECALS_Locked_v41")

athena_mat = make_alpha_image_material("DECAL_Athena_TankTop", DECALS / "athena_decal.PNG")
pomp_mat = make_alpha_image_material("DECAL_Pompompurrin_Underwear", DECALS / "pompompurrin.png")
tattoo_mat = make_tattoo_material("DECAL_Tattoo_Atlas_Ink", DECALS / "tattoo_atlas.png")
fur_mat = make_fur_material("A8_Realistic_PuppyFur_EEVEE")

top = bpy.data.objects.get("ALT_StreetwearTop_Smoothed")
underwear = bpy.data.objects.get("FINAL_Underwear_Contact")
body = bpy.data.objects.get("Body")

created = []

# Tank top front, just above cloth surface.
created.append(
    make_plane(
        "DECAL_Athena_TankTop_Front",
        (0.0, -0.206, 0.995),
        (1, 0, 0),
        (0, 0, 1),
        0.165,
        0.165,
        athena_mat,
        decals_col,
        parent=top,
    )
)

# Tattoo atlas crops, placed as separate small transparent planes.
tattoos = [
    {
        "name": "DECAL_Tattoo_BigSun_LeftHip",
        "center": (-0.155, -0.134, 0.735),
        "u": (1, 0, 0),
        "v": (0, 0, 1),
        "w": 0.135,
        "h": 0.135,
        "uv": uv_box_px(1190, 790, 1395, 1005),
    },
    {
        "name": "DECAL_Tattoo_BehindEar_MoonStar",
        "center": (-0.104, 0.0, 1.488),
        "u": (0, 1, 0),
        "v": (0, 0, 1),
        "w": 0.045,
        "h": 0.055,
        "uv": uv_box_px(535, 120, 650, 240),
    },
    {
        "name": "DECAL_Tattoo_RightAnkle_Planet",
        "center": (0.058, -0.121, 0.155),
        "u": (1, 0, 0),
        "v": (0, 0, 1),
        "w": 0.052,
        "h": 0.052,
        "uv": uv_box_px(1080, 1125, 1220, 1265),
    },
    {
        "name": "DECAL_Tattoo_LeftWrist_Crescent",
        "center": (-0.545, -0.018, 1.098),
        "u": (0, 1, 0),
        "v": (0, 0, 1),
        "w": 0.048,
        "h": 0.058,
        "uv": uv_box_px(1420, 1060, 1515, 1170),
    },
    {
        "name": "DECAL_Tattoo_Hidden_UnderButtHeart",
        "center": (0.055, 0.174, 0.705),
        "u": (1, 0, 0),
        "v": (0, 0, 1),
        "w": 0.038,
        "h": 0.038,
        "uv": uv_box_px(1180, 1685, 1245, 1745),
    },
]
for item in tattoos:
    created.append(
        make_plane(
            item["name"],
            item["center"],
            item["u"],
            item["v"],
            item["w"],
            item["h"],
            tattoo_mat,
            decals_col,
            uv_box=item["uv"],
            parent=body,
        )
    )

# Pompompurrin as small underwear decals, irregularly placed.
pomp_decals = [
    ("DECAL_Pomp_Underwear_FrontLeft", (-0.060, -0.101, 0.807), 0.052, 0.037, -8),
    ("DECAL_Pomp_Underwear_FrontRight", (0.058, -0.101, 0.778), 0.047, 0.034, 12),
    ("DECAL_Pomp_Underwear_Back", (0.070, 0.180, 0.800), 0.055, 0.039, -15),
    ("DECAL_Pomp_Underwear_Side", (-0.165, 0.025, 0.794), 0.044, 0.032, 18),
]
for name, center, width, height, degrees in pomp_decals:
    angle = math.radians(degrees)
    u = (math.cos(angle), 0, math.sin(angle) * 0.12)
    v = (-math.sin(angle) * 0.12, 0, math.cos(angle))
    created.append(make_plane(name, center, u, v, width, height, pomp_mat, decals_col, parent=underwear))

fur_targets = []
for name in ("Dog Ears", "Tail"):
    obj = bpy.data.objects.get(name)
    if obj:
        old_mats = [slot.material.name if slot.material else None for slot in obj.material_slots]
        assign_material(obj, fur_mat)
        fur_targets.append({"object": name, "old_materials": old_mats, "new_material": fur_mat.name})

report = {
    "source": str(SRC),
    "saved": str(DST),
    "decal_sources": {
        "athena": str(DECALS / "athena_decal.PNG"),
        "pompompurrin": str(DECALS / "pompompurrin.png"),
        "tattoo_atlas": str(DECALS / "tattoo_atlas.png"),
    },
    "created_decals": [
        {
            "name": obj.name,
            "parent": obj.parent.name if obj.parent else None,
            "material": obj.data.materials[0].name if obj.data.materials else None,
            "location_hint": tuple(round(v, 4) for v in obj.location),
        }
        for obj in created
    ],
    "fur_asset_studied": "Hair_And_Fur_EEVEE_v01.blend: shader concepts used; direct append avoided because file is Blender 5.1-era and curve-hair oriented.",
    "fur_targets": fur_targets,
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(DST))
print(json.dumps(report, indent=2))
