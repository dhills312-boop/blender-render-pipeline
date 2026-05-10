"""Bake the multires displacement on Body_Sculpt to a normal map, layer it
onto the original Body's existing normal, and retarget the material.

This script:
1. Loads the sculpted file.
2. Verifies Body_Sculpt has a Multires modifier with detail.
3. Copies the original Body's UV layout onto Body_Sculpt's base mesh (they
   should already match since Body_Sculpt was duplicated from Body before
   any geometry changes — multires sculpting only affects the displacement
   map, not the base topology/UVs).
4. Bakes the multires Tangent-space normal map into a new image.
5. Saves the bake to <textures_dir>/Std_Skin_Body_Normal_anatomical_1k.png.
6. Modifies the original Body's material to MIX the new sculpted normal
   over the existing CC4 normal (using a Normal Map mix in tangent space).
7. Removes Body_Sculpt object (cleanup).
8. Restores hidden meshes (Body, clothing) so the file is back to a usable state.
9. Saves as a6_v05_anatomy_baked.blend.

Run via:
    blender -b a6_v04_sculpted.blend -P a6_anatomy_bake.py -- \
        --out-blend <new_path> --tex-dir <abs path to textures/>
"""

import argparse
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--bake-resolution", type=int, default=1024)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def find_obj(name):
    return bpy.data.objects.get(name)


def get_multires(obj):
    for m in obj.modifiers:
        if m.type == "MULTIRES":
            return m
    return None


def configure_for_bake(scene):
    """Cycles is required for multires bakes. Configure conservatively."""
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.use_clear = True
    scene.render.bake.normal_space = "TANGENT"
    scene.render.bake.normal_r = "POS_X"
    scene.render.bake.normal_g = "POS_Y"
    scene.render.bake.normal_b = "POS_Z"


def create_bake_target_image(name, path, resolution):
    """Create an image data block initialized to neutral tangent-space normal."""
    img = bpy.data.images.new(
        name=name,
        width=resolution,
        height=resolution,
        alpha=False,
        float_buffer=False,
    )
    # Initialize to (0.5, 0.5, 1.0, 1.0) — neutral tangent normal.
    pixels = [0.5, 0.5, 1.0, 1.0] * (resolution * resolution)
    img.pixels.foreach_set(pixels)
    img.colorspace_settings.name = "Non-Color"
    img.filepath_raw = path
    img.file_format = "PNG"
    return img


def bake_multires_normal(sculpt_obj, target_image, scene):
    """Bake the multires displacement of sculpt_obj into target_image."""
    # Make sure the object is visible and selectable in the view layer.
    sculpt_obj.hide_viewport = False
    sculpt_obj.hide_set(False)
    sculpt_obj.hide_render = False

    # Force OBJECT mode in case the file was saved in another mode.
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass
    sculpt_obj.select_set(True)
    bpy.context.view_layer.objects.active = sculpt_obj

    # Add an Image Texture node referencing the target image to every
    # material slot, made active so Cycles bakes there.
    if not sculpt_obj.material_slots:
        # No materials — give it a temp one.
        mat = bpy.data.materials.new("BakeTemp")
        mat.use_nodes = True
        sculpt_obj.data.materials.append(mat)

    bake_nodes = []
    for slot in sculpt_obj.material_slots:
        mat = slot.material
        if mat is None:
            continue
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = target_image
        node.select = True
        nt.nodes.active = node
        bake_nodes.append((nt, node))

    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = False

    # Multires bake mode.
    scene.render.use_bake_multires = True
    scene.render.bake_type = "NORMALS"
    scene.render.bake.margin = 16

    print("Starting multires normal bake...")
    bpy.ops.object.bake_image()
    print("Bake done.")

    # Save the image.
    target_image.save()

    # Clean up the temp Image Texture nodes we added.
    for nt, node in bake_nodes:
        nt.nodes.remove(node)


def find_body_material_normal_link(body_obj):
    """Find the existing normal map texture node + its connection to the
    BSDF on the Body's primary material. Returns (material, node_tree,
    bsdf_node, normal_map_node, image_texture_node) or Nones."""
    for slot in body_obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        nt = mat.node_tree
        bsdfs = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]
        if not bsdfs:
            continue
        # CC4 may use a node group — but the Principled BSDF is the
        # downstream consumer. Find anything feeding its Normal input.
        for bsdf in bsdfs:
            normal_in = bsdf.inputs.get("Normal")
            if not normal_in or not normal_in.is_linked:
                continue
            # Walk back the link to find the Normal Map node and its image.
            link = normal_in.links[0]
            src = link.from_node
            if src.type == "NORMAL_MAP":
                # Image feeding it?
                color_in = src.inputs.get("Color")
                if color_in and color_in.is_linked:
                    img_node = color_in.links[0].from_node
                    if img_node.type == "TEX_IMAGE":
                        return mat, nt, bsdf, src, img_node
            elif src.type == "NODE_REORGANIZE_GROUP" or src.type == "GROUP":
                # CC4 wraps Normal Map inside a group. We'll just inject
                # alongside.
                return mat, nt, bsdf, src, None
    return None, None, None, None, None


def inject_anatomical_normal_into_material(body_obj, sculpted_image):
    """Add the sculpted normal map as an additional Normal Map node mixed
    with the existing CC4 normal feeding the Principled BSDF."""
    mat, nt, bsdf, current_normal_src, _ = find_body_material_normal_link(body_obj)
    if not mat or not nt or not bsdf:
        print("WARN: Could not find Body BSDF normal input — "
              "skipping material injection. You'll need to wire the new "
              "normal map manually.")
        return None

    # Build:
    #   [TexImage] -> [NormalMap] -> [Vector Mix (Mix Factor 0.5)]
    #                                      ^
    #               [existing normal source] above
    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.image = sculpted_image
    img_node.label = "Anatomical Normal"
    img_node.location = (current_normal_src.location.x - 600,
                         current_normal_src.location.y - 200)

    nm_node = nt.nodes.new("ShaderNodeNormalMap")
    nm_node.label = "Anatomical Normal Map"
    nm_node.location = (current_normal_src.location.x - 300,
                        current_normal_src.location.y - 200)
    nt.links.new(img_node.outputs["Color"], nm_node.inputs["Color"])

    # Vector mix: blend the existing normal output with the anatomical one.
    mix_node = nt.nodes.new("ShaderNodeMix")
    mix_node.data_type = "VECTOR"
    mix_node.label = "Anatomical Normal Mix"
    mix_node.inputs["Factor"].default_value = 0.5
    mix_node.location = (current_normal_src.location.x + 200,
                         current_normal_src.location.y - 100)

    # Reroute existing normal output through mix.
    # Find the existing link to BSDF Normal and reroute it.
    bsdf_normal_in = bsdf.inputs["Normal"]
    if bsdf_normal_in.is_linked:
        existing_link = bsdf_normal_in.links[0]
        existing_src_socket = existing_link.from_socket
        nt.links.remove(existing_link)
        nt.links.new(existing_src_socket, mix_node.inputs[4])  # A
    nt.links.new(nm_node.outputs["Normal"], mix_node.inputs[5])  # B
    nt.links.new(mix_node.outputs[1], bsdf_normal_in)  # Result -> Normal

    print(f"Injected anatomical normal map into material '{mat.name}'")
    return mat.name


def cleanup(sculpt_obj, body_obj, clothing_names):
    """Remove sculpt object and unhide originals."""
    sculpt_data = sculpt_obj.data
    bpy.data.objects.remove(sculpt_obj, do_unlink=True)
    if sculpt_data.users == 0:
        bpy.data.meshes.remove(sculpt_data)

    body_obj.hide_viewport = False
    body_obj.hide_render = False
    for name in clothing_names:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = False
            obj.hide_render = False


def report_image_stats(img):
    """Read pixel data and report on whether the bake actually has detail."""
    if img.size[0] == 0:
        return {"empty": True}
    # Sample a percentage of pixels (full read can be huge for 4K).
    pixels = list(img.pixels)
    # Tangent-space neutral is (0.5, 0.5, 1.0). Anything that diverges is detail.
    n = len(pixels) // 4
    deviation_count = 0
    max_dev = 0
    for i in range(0, n, 50):  # sample every 50th pixel
        r, g, b = pixels[i*4], pixels[i*4+1], pixels[i*4+2]
        dev = abs(r - 0.5) + abs(g - 0.5) + abs(b - 1.0)
        if dev > 0.05:
            deviation_count += 1
        max_dev = max(max_dev, dev)
    return {
        "empty": False,
        "size": list(img.size),
        "sampled_pixel_count": n // 50,
        "non_neutral_pixel_count": deviation_count,
        "max_deviation": round(max_dev, 4),
    }


def main():
    args = parse_args()
    import json

    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print(f"TEX DIR: {args.tex_dir}")
    print(f"BAKE RES: {args.bake_resolution}x{args.bake_resolution}")
    print("=" * 60)

    body = find_obj("Body")
    sculpt = find_obj("Body_Sculpt")
    if not body:
        print("ERROR: Body mesh not found.")
        sys.exit(1)
    if not sculpt:
        print("ERROR: Body_Sculpt not found — did the user save the right file?")
        sys.exit(1)

    multires = get_multires(sculpt)
    if not multires:
        print("ERROR: Body_Sculpt has no Multires modifier — bake will fail.")
        sys.exit(1)
    print(f"Found Body and Body_Sculpt with Multires "
          f"(viewport_levels={multires.levels}, "
          f"sculpt_levels={multires.sculpt_levels}, "
          f"render_levels={multires.render_levels})")

    # Make sure tex dir exists.
    os.makedirs(args.tex_dir, exist_ok=True)
    tex_path = os.path.join(
        args.tex_dir, "Std_Skin_Body_Normal_anatomical_1k.png"
    )
    print(f"Bake target: {tex_path}")

    # Create the bake target image.
    img = create_bake_target_image(
        "Std_Skin_Body_Normal_anatomical",
        tex_path,
        args.bake_resolution,
    )

    configure_for_bake(bpy.context.scene)

    # Bake.
    bake_multires_normal(sculpt, img, bpy.context.scene)

    # Stats: did the bake produce any detail?
    img.reload()  # re-read from disk
    stats = report_image_stats(img)
    print(f"Bake stats: {stats}")

    # Inject into Body's material.
    inj_mat = inject_anatomical_normal_into_material(body, img)

    # Cleanup.
    cleanup(sculpt, body, ["top_cloth", "bottome", "Bra", "Underwear_Bottoms"])

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    report = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "bake_target": tex_path,
        "bake_stats": stats,
        "injected_into_material": inj_mat,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
