"""Rebuild the 5 CC4 skin materials (Skin_Head/Body/Arm/Leg/Nails) as
clean Principled BSDF graphs.

Replaces CC4's proprietary rl_skin_shader node groups (which carry
Reallusion IP and prevent redistribution) with vanilla Principled BSDF
that uses only:
- Existing Normal/Roughness/SSS/AO texture maps from CC4 export
- A flat porcelain base color (#f0d8c8) as the skin diffuse stand-in
- The existing Torso_Decals image as a Multiply layer on top of Base Color
  (so our paintable decal infrastructure carries forward)

For each material:
1. Inventory existing TEX_IMAGE nodes by role (DIFFUSE/NORMAL/ROUGHNESS/etc.)
2. Find the Torso_Decals node we added in v08 + its UV Map node
3. Delete the entire existing graph
4. Build fresh graph:
   [base_color RGB] -> [Mix Multiply with AO] -> [Mix Multiply with TorsoDecals via UV_chest] -> BSDF.Base Color
   [Normal img] -> [Normal Map node] -> BSDF.Normal
   [Roughness img] -> BSDF.Roughness
   [SSS img] -> BSDF.Subsurface Weight (and/or Subsurface Color tint)
5. Wire BSDF -> Material Output

Run:
    blender -b a6_v09_diffuse_fixed.blend -P a6_rebuild_skin_shaders.py -- \
        --out-blend <path> --report <path>
"""

import argparse
import json
import os
import re
import sys

import bpy

ROLE_RE = re.compile(r"cc3iid_\(([A-Z_]+)\)_v")

# Material name -> texture name prefix on disk.
MAT_PREFIX = {
    "Skin_Head": "Std_Skin_Head",
    "Skin_Body": "Std_Skin_Body",
    "Skin_Arm":  "Std_Skin_Arm",
    "Skin_Leg":  "Std_Skin_Leg",
    "Nails":     "Std_Nails",
}

# Porcelain pink base color.
PORCELAIN = (0.941, 0.847, 0.784, 1.0)  # #f0d8c8 in linear approx

# Map our preferred BSDF input from each role.
ROLE_KEYWORDS = {
    "NORMAL": ["Normal"],
    "ROUGHNESS": ["roughness", "Roughness"],
    "AO": ["ao"],
    "SSS": ["SSSMap"],
    "MICRONORMAL": ["MicroN"],
    "MICRONMASK": ["MicroNMask"],
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def find_image(prefix, role_keywords):
    """Find a loaded image whose name starts with prefix and contains
    any of the role keywords."""
    for name, img in bpy.data.images.items():
        if name.startswith(prefix) and any(k in name for k in role_keywords):
            # Skip 0-byte placeholders.
            if img.size[0] >= 64 and img.size[1] >= 64:
                return img
    return None


def get_torso_decals_image():
    return bpy.data.images.get("Torso_Decals")


def rebuild_material(mat_name):
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        return {"material": mat_name, "status": "not_found"}

    if not mat.use_nodes:
        mat.use_nodes = True

    prefix = MAT_PREFIX[mat_name]

    # Find the texture images we need.
    images = {
        "NORMAL": find_image(prefix, ROLE_KEYWORDS["NORMAL"]),
        "ROUGHNESS": find_image(prefix, ROLE_KEYWORDS["ROUGHNESS"]),
        "AO": find_image(prefix, ROLE_KEYWORDS["AO"]),
        "SSS": find_image(prefix, ROLE_KEYWORDS["SSS"]),
    }
    found_textures = {k: (v.name if v else None) for k, v in images.items()}

    # Get torso decals image (shared across materials).
    decals_img = get_torso_decals_image()

    # CLEAR the entire node tree.
    nt = mat.node_tree
    nt.nodes.clear()

    # Build fresh graph.
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (1100, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (700, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # === Base color chain ===
    # Step 1: porcelain RGB.
    base_rgb = nt.nodes.new("ShaderNodeRGB")
    base_rgb.label = "Porcelain Base"
    base_rgb.outputs["Color"].default_value = PORCELAIN
    base_rgb.location = (-1200, 200)

    bc_source = base_rgb.outputs["Color"]

    # Step 2: optional AO multiply (subtle).
    if images["AO"]:
        ao_node = nt.nodes.new("ShaderNodeTexImage")
        ao_node.image = images["AO"]
        ao_node.label = "AO"
        ao_node.location = (-1200, -100)
        # AO maps don't need sRGB, set Non-Color.
        if images["AO"].colorspace_settings.name != "Non-Color":
            images["AO"].colorspace_settings.name = "Non-Color"

        # Mix (Multiply) at low factor (0.5) so AO gently darkens crevices.
        ao_mix = nt.nodes.new("ShaderNodeMixRGB")
        ao_mix.blend_type = "MULTIPLY"
        ao_mix.label = "AO Multiply"
        ao_mix.inputs["Fac"].default_value = 0.5
        ao_mix.location = (-700, 100)
        nt.links.new(bc_source, ao_mix.inputs["Color1"])
        nt.links.new(ao_node.outputs["Color"], ao_mix.inputs["Color2"])
        bc_source = ao_mix.outputs["Color"]

    # Step 3: Torso_Decals multiply (only on materials that touch torso).
    if decals_img and mat_name in ("Skin_Head", "Skin_Body"):
        # UV Map node — sources from UV_chest.
        uv_decal = nt.nodes.new("ShaderNodeUVMap")
        uv_decal.uv_map = "UV_chest"
        uv_decal.label = "Torso Decal UV"
        uv_decal.location = (-1200, -400)

        decal_node = nt.nodes.new("ShaderNodeTexImage")
        decal_node.image = decals_img
        decal_node.label = "Torso Decal Image"
        decal_node.location = (-900, -400)
        nt.links.new(uv_decal.outputs["UV"], decal_node.inputs["Vector"])
        if decals_img.colorspace_settings.name != "sRGB":
            decals_img.colorspace_settings.name = "sRGB"

        decal_mix = nt.nodes.new("ShaderNodeMixRGB")
        decal_mix.blend_type = "MULTIPLY"
        decal_mix.label = "Torso Decal Multiply"
        decal_mix.inputs["Fac"].default_value = 1.0
        decal_mix.location = (-300, 0)
        nt.links.new(bc_source, decal_mix.inputs["Color1"])
        nt.links.new(decal_node.outputs["Color"], decal_mix.inputs["Color2"])
        bc_source = decal_mix.outputs["Color"]

    # Final: BC chain to BSDF Base Color.
    nt.links.new(bc_source, bsdf.inputs["Base Color"])

    # === Roughness ===
    if images["ROUGHNESS"]:
        rough_node = nt.nodes.new("ShaderNodeTexImage")
        rough_node.image = images["ROUGHNESS"]
        rough_node.label = "Roughness"
        rough_node.location = (-700, -300)
        if images["ROUGHNESS"].colorspace_settings.name != "Non-Color":
            images["ROUGHNESS"].colorspace_settings.name = "Non-Color"
        nt.links.new(rough_node.outputs["Color"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.55  # plausible skin default

    # === Normal ===
    if images["NORMAL"]:
        norm_node = nt.nodes.new("ShaderNodeTexImage")
        norm_node.image = images["NORMAL"]
        norm_node.label = "Normal"
        norm_node.location = (-700, -550)
        if images["NORMAL"].colorspace_settings.name != "Non-Color":
            images["NORMAL"].colorspace_settings.name = "Non-Color"

        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.label = "Normal Map"
        nm.location = (-300, -550)
        nm.inputs["Strength"].default_value = 1.0
        nt.links.new(norm_node.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    # === Subsurface ===
    if images["SSS"]:
        sss_node = nt.nodes.new("ShaderNodeTexImage")
        sss_node.image = images["SSS"]
        sss_node.label = "SSS"
        sss_node.location = (-700, -800)
        if images["SSS"].colorspace_settings.name != "Non-Color":
            images["SSS"].colorspace_settings.name = "Non-Color"
        nt.links.new(sss_node.outputs["Color"], bsdf.inputs["Subsurface Weight"])
        # Set SSS color to a warm flesh tint.
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.2, 0.1)
        # Subsurface Scale = how far light travels under skin (mm).
        if "Subsurface Scale" in [s.name for s in bsdf.inputs]:
            bsdf.inputs["Subsurface Scale"].default_value = 0.005
    else:
        bsdf.inputs["Subsurface Weight"].default_value = 0.1

    # Specular (small bump for skin sheen).
    if "Specular IOR Level" in [s.name for s in bsdf.inputs]:
        bsdf.inputs["Specular IOR Level"].default_value = 0.5

    return {
        "material": mat_name,
        "status": "rebuilt",
        "found_textures": found_textures,
        "decals_wired": decals_img is not None and mat_name in ("Skin_Head", "Skin_Body"),
    }


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    results = []
    for mat_name in ("Skin_Head", "Skin_Body", "Skin_Arm", "Skin_Leg", "Nails"):
        print(f"\n[Rebuilding {mat_name}]")
        r = rebuild_material(mat_name)
        results.append(r)
        print(f"  status: {r['status']}")
        if "found_textures" in r:
            for role, name in r["found_textures"].items():
                print(f"    {role}: {name or '(none — using BSDF default)'}")

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "porcelain_color_hex": "#f0d8c8",
        "porcelain_color_linear_rgb": list(PORCELAIN),
        "results": results,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
