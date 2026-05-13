"""Replace the Tongue material with a simple flat Principled setup."""

from __future__ import annotations

import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--material", default="Tongue")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    mat = bpy.data.materials.get(args.material)
    if not mat:
        raise RuntimeError(f"Missing material: {args.material}")
    if not mat.use_nodes:
        mat.use_nodes = True

    original_images = []
    if mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                original_images.append(node.image.name)

    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (520, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (220, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.label = "Tongue Base"
    rgb.location = (-120, 100)
    rgb.outputs["Color"].default_value = (0.78, 0.40, 0.46, 1.0)
    nt.links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = 0.46
    bsdf.inputs["Specular IOR Level"].default_value = 0.38
    bsdf.inputs["Subsurface Weight"].default_value = 0.14
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.25)

    mat.blend_method = "OPAQUE"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "OPAQUE"

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    report = {
        "blend_file": bpy.data.filepath,
        "material": args.material,
        "original_images": original_images,
        "new_base_color": [0.78, 0.40, 0.46, 1.0],
        "notes": "Tongue rebuilt as flat Principled with no image textures to eliminate color contamination.",
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("FORCE_TONGUE_FLAT_OK")
    print(f"  material={args.material}")
    print(f"  removed_images={len(original_images)}")


if __name__ == "__main__":
    main()
