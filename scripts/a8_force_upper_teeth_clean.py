"""Replace Upper_Teeth color with a clean flat base in-place."""

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
    parser.add_argument("--material", default="Upper_Teeth")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    mat = bpy.data.materials.get(args.material)
    if not mat or not mat.use_nodes or not mat.node_tree:
        raise RuntimeError(f"Missing node material: {args.material}")

    removed = []
    nt = mat.node_tree
    for node in list(nt.nodes):
        if node.type == "TEX_IMAGE" and node.image and "Diffuse" in node.name:
            removed.append(node.image.name)
            nt.nodes.remove(node)

    bsdf = None
    for node in nt.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if not bsdf:
        raise RuntimeError("No Principled BSDF found on Upper_Teeth")

    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.label = "Upper Teeth Base"
    rgb.location = (-900, 120)
    rgb.outputs["Color"].default_value = (0.93, 0.91, 0.88, 1.0)
    nt.links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = 0.30
    bsdf.inputs["Specular IOR Level"].default_value = 0.34

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    report = {
        "blend_file": bpy.data.filepath,
        "material": args.material,
        "removed_diffuse_images": removed,
        "new_base_color": [0.93, 0.91, 0.88, 1.0],
        "notes": "Upper teeth diffuse image was a corrupted face-like texture; replaced with flat ivory base.",
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("FORCE_UPPER_TEETH_CLEAN_OK")
    print(f"  removed_diffuse_images={removed}")


if __name__ == "__main__":
    main()
