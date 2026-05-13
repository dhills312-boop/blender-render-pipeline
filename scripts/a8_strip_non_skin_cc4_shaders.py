"""Rebuild non-skin CC4 materials as simple Principled BSDF graphs.

Targets:
- Eye_L / Eye_R
- Cornea_L / Cornea_R
- Tearline_L / Tearline_R
- Tongue
- Upper_Teeth / Lower_Teeth

The script reads the textures already wired into each material's current
Reallusion graph, then replaces the node tree with a simple Principled setup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import bpy


ROLE_RE = re.compile(r"\(([^)]+)\)")

TARGETS = (
    "Eye_L",
    "Eye_R",
    "Cornea_L",
    "Cornea_R",
    "Tearline_L",
    "Tearline_R",
    "Tongue",
    "Upper_Teeth",
    "Lower_Teeth",
)

EYE = {"Eye_L", "Eye_R"}
CORNEA = {"Cornea_L", "Cornea_R"}
TEARLINE = {"Tearline_L", "Tearline_R"}
TEETH = {"Upper_Teeth", "Lower_Teeth"}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def role_for_tex_node(node: bpy.types.Node) -> str | None:
    match = ROLE_RE.search(node.name)
    if match:
        return match.group(1).upper()
    label = (node.label or "").upper()
    if label:
        return label
    return None


def ensure_non_color(image):
    if image and image.colorspace_settings.name != "Non-Color":
        image.colorspace_settings.name = "Non-Color"


def ensure_srgb(image):
    if image and image.colorspace_settings.name != "sRGB":
        image.colorspace_settings.name = "sRGB"


def set_alpha_material_defaults(mat: bpy.types.Material) -> None:
    mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "HASHED"
    mat.use_backface_culling = False


def gather_role_images(mat: bpy.types.Material) -> dict[str, bpy.types.Image]:
    roles = {}
    if not mat.use_nodes or not mat.node_tree:
        return roles
    for node in mat.node_tree.nodes:
        if node.type != "TEX_IMAGE" or not node.image:
            continue
        role = role_for_tex_node(node)
        if role and role not in roles:
            roles[role] = node.image
    return roles


def new_image_node(nt, image, label, location, non_color=False):
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.label = label
    node.location = location
    if non_color:
        ensure_non_color(image)
    else:
        ensure_srgb(image)
    return node


def wire_principled_output(nt):
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (1000, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (700, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return bsdf


def build_eye(mat, roles):
    nt = mat.node_tree
    nt.nodes.clear()
    mat.blend_method = "OPAQUE"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "OPAQUE"
    bsdf = wire_principled_output(nt)
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    bsdf.inputs["Roughness"].default_value = 0.18

    base_socket = None
    if roles.get("DIFFUSE"):
        diffuse = new_image_node(nt, roles["DIFFUSE"], "Diffuse", (-1000, 140))
        base_socket = diffuse.outputs["Color"]
    if roles.get("SCLERA"):
        sclera = new_image_node(nt, roles["SCLERA"], "Sclera", (-1000, -40))
        if base_socket is None:
            base_socket = sclera.outputs["Color"]
        else:
            fac_source = None
            if roles.get("EYEBLEND"):
                blend = new_image_node(nt, roles["EYEBLEND"], "Blend Mask", (-1000, -240), non_color=True)
                fac_source = blend.outputs["Color"]
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MIX"
            mix.location = (-650, 70)
            mix.inputs["Fac"].default_value = 0.5
            nt.links.new(sclera.outputs["Color"], mix.inputs["Color1"])
            nt.links.new(base_socket, mix.inputs["Color2"])
            if fac_source:
                nt.links.new(fac_source, mix.inputs["Fac"])
            base_socket = mix.outputs["Color"]
    if roles.get("AO") and base_socket is not None:
        ao = new_image_node(nt, roles["AO"], "AO", (-650, -180), non_color=True)
        ao_mix = nt.nodes.new("ShaderNodeMixRGB")
        ao_mix.blend_type = "MULTIPLY"
        ao_mix.location = (-280, 40)
        ao_mix.inputs["Fac"].default_value = 0.35
        nt.links.new(base_socket, ao_mix.inputs["Color1"])
        nt.links.new(ao.outputs["Color"], ao_mix.inputs["Color2"])
        base_socket = ao_mix.outputs["Color"]
    if base_socket is not None:
        nt.links.new(base_socket, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)

    # The imported CC4 eye/cornea stacks sometimes point this role at an
    # unrelated micro-normal image. Keep the eye base clean unless we have an
    # explicit eye normal.
    normal_image = roles.get("NORMAL")
    if normal_image:
        normal = new_image_node(nt, normal_image, "Normal", (-280, -280), non_color=True)
        normal_map = nt.nodes.new("ShaderNodeNormalMap")
        normal_map.location = (80, -280)
        normal_map.inputs["Strength"].default_value = 0.35
        nt.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        nt.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])


def build_cornea(mat, roles):
    nt = mat.node_tree
    nt.nodes.clear()
    set_alpha_material_defaults(mat)
    bsdf = wire_principled_output(nt)
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.02
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.38
    bsdf.inputs["Alpha"].default_value = 0.12
    bsdf.inputs["Coat Weight"].default_value = 1.0
    bsdf.inputs["Coat Roughness"].default_value = 0.02

    if roles.get("DIFFUSE"):
        diffuse = new_image_node(nt, roles["DIFFUSE"], "Cornea Diffuse", (-500, 120))
        tint_mix = nt.nodes.new("ShaderNodeMixRGB")
        tint_mix.blend_type = "MIX"
        tint_mix.location = (-180, 80)
        tint_mix.inputs["Fac"].default_value = 0.08
        tint_mix.inputs["Color1"].default_value = (1.0, 1.0, 1.0, 1.0)
        nt.links.new(diffuse.outputs["Color"], tint_mix.inputs["Color2"])
        nt.links.new(tint_mix.outputs["Color"], bsdf.inputs["Base Color"])

    # Cornea should stay simple and clean here; the imported sclera normal was
    # not trustworthy in this file and can produce visual garbage.


def build_tearline(mat):
    nt = mat.node_tree
    nt.nodes.clear()
    set_alpha_material_defaults(mat)
    bsdf = wire_principled_output(nt)
    bsdf.inputs["Base Color"].default_value = (0.98, 0.90, 0.92, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.01
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.333
    bsdf.inputs["Alpha"].default_value = 0.28
    bsdf.inputs["Coat Weight"].default_value = 1.0
    bsdf.inputs["Coat Roughness"].default_value = 0.01


def build_tongue(mat, roles):
    nt = mat.node_tree
    nt.nodes.clear()
    mat.blend_method = "OPAQUE"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "OPAQUE"
    bsdf = wire_principled_output(nt)
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Specular IOR Level"].default_value = 0.45
    bsdf.inputs["Subsurface Weight"].default_value = 0.18
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.25)

    # The saved tongue diffuse in this project is not reliable for the cleanup
    # pass, so start from a flesh tone and use AO/normal maps for form.
    base_rgb = nt.nodes.new("ShaderNodeRGB")
    base_rgb.label = "Tongue Base"
    base_rgb.location = (-1100, 180)
    base_rgb.outputs["Color"].default_value = (0.80, 0.42, 0.47, 1.0)
    base_socket = base_rgb.outputs["Color"]
    if roles.get("AO") and base_socket is not None:
        ao = new_image_node(nt, roles["AO"], "AO", (-1100, -30), non_color=True)
        ao_mix = nt.nodes.new("ShaderNodeMixRGB")
        ao_mix.blend_type = "MULTIPLY"
        ao_mix.location = (-760, 110)
        ao_mix.inputs["Fac"].default_value = 0.45
        nt.links.new(base_socket, ao_mix.inputs["Color1"])
        nt.links.new(ao.outputs["Color"], ao_mix.inputs["Color2"])
        base_socket = ao_mix.outputs["Color"]
    if base_socket is not None:
        nt.links.new(base_socket, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.82, 0.42, 0.48, 1.0)

    if roles.get("ROUGHNESS"):
        rough = new_image_node(nt, roles["ROUGHNESS"], "Roughness", (-400, -250), non_color=True)
        nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    if roles.get("NORMAL") or roles.get("MICRONORMAL"):
        normal = new_image_node(
            nt,
            roles.get("NORMAL") or roles.get("MICRONORMAL"),
            "Normal",
            (-760, -350),
            non_color=True,
        )
        normal_map = nt.nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-400, -350)
        normal_map.inputs["Strength"].default_value = 0.55
        nt.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        nt.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])


def build_teeth(mat, roles):
    nt = mat.node_tree
    nt.nodes.clear()
    mat.blend_method = "OPAQUE"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "OPAQUE"
    bsdf = wire_principled_output(nt)
    bsdf.inputs["Roughness"].default_value = 0.28
    bsdf.inputs["Specular IOR Level"].default_value = 0.4
    bsdf.inputs["Subsurface Weight"].default_value = 0.08
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.55, 0.35)

    base_socket = None
    if roles.get("DIFFUSE"):
        diffuse = new_image_node(nt, roles["DIFFUSE"], "Diffuse", (-1000, 140))
        base_socket = diffuse.outputs["Color"]
    if roles.get("AO") and base_socket is not None:
        ao = new_image_node(nt, roles["AO"], "AO", (-1000, -50), non_color=True)
        ao_mix = nt.nodes.new("ShaderNodeMixRGB")
        ao_mix.blend_type = "MULTIPLY"
        ao_mix.location = (-660, 80)
        ao_mix.inputs["Fac"].default_value = 0.28
        nt.links.new(base_socket, ao_mix.inputs["Color1"])
        nt.links.new(ao.outputs["Color"], ao_mix.inputs["Color2"])
        base_socket = ao_mix.outputs["Color"]
    if base_socket is not None:
        nt.links.new(base_socket, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.94, 0.92, 0.89, 1.0)

    if roles.get("ROUGHNESS"):
        rough = new_image_node(nt, roles["ROUGHNESS"], "Roughness", (-320, -180), non_color=True)
        nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    if roles.get("NORMAL") or roles.get("MICRONORMAL"):
        normal = new_image_node(
            nt,
            roles.get("NORMAL") or roles.get("MICRONORMAL"),
            "Normal",
            (-680, -300),
            non_color=True,
        )
        normal_map = nt.nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-320, -300)
        normal_map.inputs["Strength"].default_value = 0.4
        nt.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        nt.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])


def rebuild_material(mat_name):
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        return {"material": mat_name, "status": "not_found"}

    if not mat.use_nodes:
        mat.use_nodes = True
    roles = gather_role_images(mat)
    original = {
        "blend_method": mat.blend_method,
        "surface_render_method": getattr(mat, "surface_render_method", None),
        "shadow_method": getattr(mat, "shadow_method", None),
        "role_images": {role: image.name for role, image in sorted(roles.items())},
    }

    if mat_name in EYE:
        build_eye(mat, roles)
    elif mat_name in CORNEA:
        build_cornea(mat, roles)
    elif mat_name in TEARLINE:
        build_tearline(mat)
    elif mat_name == "Tongue":
        build_tongue(mat, roles)
    elif mat_name in TEETH:
        build_teeth(mat, roles)
    else:
        return {"material": mat_name, "status": "skipped_unknown", "original": original}

    return {"material": mat_name, "status": "rebuilt", "original": original}


def main():
    args = parse_args()
    results = [rebuild_material(name) for name in TARGETS]
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    report = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "targets": list(TARGETS),
        "results": results,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    rebuilt = [row["material"] for row in results if row["status"] == "rebuilt"]
    print("NON_SKIN_SHADER_STRIP_OK")
    print(f"  rebuilt={len(rebuilt)}")
    for name in rebuilt:
        print(f"  {name}")


if __name__ == "__main__":
    main()
