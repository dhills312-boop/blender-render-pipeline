"""Bake the anatomy sculpt from Body_Sculpt to a normal map by comparing
against the original Body mesh, then layer onto the existing CC4 body
normal in the Skin_Body material.

This version uses the standard 'selected to active' high-to-low bake
workflow instead of multires bake — appropriate when sculpt strokes are
on the base mesh rather than stored as multires displacement.

Workflow:
1. Identify Body (low poly target) and Body_Sculpt (high poly source).
2. Verify Body_Sculpt has more vertex displacement than Body (i.e. there
   is something to bake).
3. Make Body visible/selectable.
4. Add a fresh Image Texture node referencing the bake target on Body's
   active material — Cycles bakes there.
5. Configure Cycles bake: NORMAL, TANGENT space, selected_to_active=True.
6. Select Body_Sculpt then Body (active=Body), bake.
7. Save the image to textures/Std_Skin_Body_Normal_anatomical_1k.png.
8. Inject the new normal map into the Skin_Body material specifically
   (mixed with the existing CC4 normal at 0.5 factor).
9. Remove Body_Sculpt and clean up.

Run via:
    blender -b a6_v04_sculpted.blend -P a6_anatomy_bake_v2.py -- \
        --out-blend <new_path> --tex-dir <abs_path> \
        --bake-resolution 1024 --report <report_path>
"""

import argparse
import json
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


def get_obj(name):
    return bpy.data.objects.get(name)


def make_visible(obj):
    obj.hide_viewport = False
    obj.hide_render = False
    try:
        obj.hide_set(False)
    except Exception:
        pass


def deselect_all():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass


def find_skin_body_material(body):
    """Return the material on Body that drives the chest area: Skin_Body."""
    for slot in body.material_slots:
        if slot.material and slot.material.name == "Skin_Body":
            return slot.material
    # Fallback: largest-poly-coverage material — print and return first.
    print("WARN: Skin_Body material not found; falling back to first material.")
    return body.material_slots[0].material if body.material_slots else None


def create_bake_target_image(name, path, resolution):
    """Create a tangent-normal-neutral image, save its initial state to disk,
    so Cycles can write to it."""
    img = bpy.data.images.new(
        name=name,
        width=resolution,
        height=resolution,
        alpha=False,
        float_buffer=False,
    )
    pixels = [0.5, 0.5, 1.0, 1.0] * (resolution * resolution)
    img.pixels.foreach_set(pixels)
    img.colorspace_settings.name = "Non-Color"
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def configure_bake(scene, target_image):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_clear = True
    scene.render.bake.normal_space = "TANGENT"
    scene.render.bake.normal_r = "POS_X"
    scene.render.bake.normal_g = "POS_Y"
    scene.render.bake.normal_b = "POS_Z"
    # Tight cage: only sample sculpt detail within 5mm of base mesh.
    scene.render.bake.cage_extrusion = 0.005
    scene.render.bake.max_ray_distance = 0.01
    scene.render.bake.margin = 16
    scene.render.use_bake_multires = False


def add_target_image_node(material, image):
    """Inject a temporary TEX_IMAGE node referencing the bake target,
    selected and active, so Cycles writes to it."""
    if not material.use_nodes:
        material.use_nodes = True
    nt = material.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.select = True
    nt.nodes.active = node
    return node


def remove_node_safe(material, node):
    if node and material.node_tree:
        try:
            material.node_tree.nodes.remove(node)
        except Exception:
            pass


def find_skin_body_normal_for_injection(body):
    """Find Skin_Body's BSDF + Normal input so we can inject the new map."""
    mat = find_skin_body_material(body)
    if not mat or not mat.use_nodes:
        return None, None, None
    nt = mat.node_tree
    bsdfs = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]
    for bsdf in bsdfs:
        norm_in = bsdf.inputs.get("Normal")
        if norm_in:
            return mat, nt, bsdf
    return mat, nt, None


def inject_anatomical_normal(body, sculpted_image):
    mat, nt, bsdf = find_skin_body_normal_for_injection(body)
    if not (mat and nt and bsdf):
        print("WARN: Could not find Skin_Body BSDF — material injection skipped.")
        return None

    # Build the chain: TexImage -> NormalMap -> Mix(Vector) -> BSDF.Normal
    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.image = sculpted_image
    img_node.label = "Anatomical Normal"
    img_node.location = (bsdf.location.x - 900, bsdf.location.y - 300)

    nm_node = nt.nodes.new("ShaderNodeNormalMap")
    nm_node.label = "Anatomical Normal Map"
    nm_node.location = (bsdf.location.x - 600, bsdf.location.y - 300)
    nt.links.new(img_node.outputs["Color"], nm_node.inputs["Color"])

    mix_node = nt.nodes.new("ShaderNodeMix")
    mix_node.data_type = "VECTOR"
    mix_node.label = "Anatomical Normal Mix"
    mix_node.inputs["Factor"].default_value = 0.7
    mix_node.location = (bsdf.location.x - 250, bsdf.location.y - 200)

    norm_in = bsdf.inputs["Normal"]
    if norm_in.is_linked:
        existing_link = norm_in.links[0]
        existing_src_socket = existing_link.from_socket
        nt.links.remove(existing_link)
        nt.links.new(existing_src_socket, mix_node.inputs[4])  # A
    nt.links.new(nm_node.outputs["Normal"], mix_node.inputs[5])  # B
    nt.links.new(mix_node.outputs[1], norm_in)

    print(f"Injected anatomical normal into '{mat.name}'")
    return mat.name


def report_image_stats(img):
    if img.size[0] == 0:
        return {"empty": True}
    pixels = list(img.pixels)
    n = len(pixels) // 4
    deviation_count = 0
    max_dev = 0.0
    for i in range(0, n, 50):
        r, g, b = pixels[i*4], pixels[i*4+1], pixels[i*4+2]
        dev = abs(r - 0.5) + abs(g - 0.5) + abs(b - 1.0)
        if dev > 0.05:
            deviation_count += 1
        max_dev = max(max_dev, dev)
    return {
        "empty": False,
        "size": list(img.size),
        "sampled_pixels": n // 50,
        "non_neutral_count": deviation_count,
        "max_deviation": round(max_dev, 4),
    }


def cleanup(sculpt_obj, body, clothing_names):
    sculpt_data = sculpt_obj.data
    bpy.data.objects.remove(sculpt_obj, do_unlink=True)
    if sculpt_data.users == 0:
        bpy.data.meshes.remove(sculpt_data)
    make_visible(body)
    for name in clothing_names:
        obj = get_obj(name)
        if obj:
            make_visible(obj)


def main():
    args = parse_args()

    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print(f"BAKE RES: {args.bake_resolution}")
    print("=" * 60)

    body = get_obj("Body")
    sculpt = get_obj("Body_Sculpt")
    if not (body and sculpt):
        print("ERROR: missing Body or Body_Sculpt.")
        sys.exit(1)

    # Isolate: hide every other mesh in the scene so the ray cast only
    # sees Body (target) and Body_Sculpt (source). Stash original visibility
    # so we can restore after the bake.
    visibility_stash = {}
    for obj in bpy.data.objects:
        visibility_stash[obj.name] = (obj.hide_viewport, obj.hide_render,
                                      obj.hide_get())
        if obj.name in ("Body", "Body_Sculpt"):
            make_visible(obj)
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            try:
                obj.hide_set(True)
            except Exception:
                pass
    print(f"Isolated bake: hidden all but Body and Body_Sculpt "
          f"({len(visibility_stash) - 2} other objects hidden)")

    # Bake target image.
    os.makedirs(args.tex_dir, exist_ok=True)
    tex_path = os.path.join(
        args.tex_dir, "Std_Skin_Body_Normal_anatomical_1k.png"
    )
    img = create_bake_target_image(
        "Std_Skin_Body_Normal_anatomical",
        tex_path,
        args.bake_resolution,
    )
    print(f"Bake target image created: {tex_path}")

    # On the LOW POLY (Body, the active object), add the bake target node
    # to its primary skin material so Cycles knows where to write.
    skin_body_mat = find_skin_body_material(body)
    if not skin_body_mat:
        print("ERROR: Skin_Body material not found on Body — cannot bake.")
        sys.exit(1)

    # Add bake target node to ALL of Body's material slots — Cycles writes
    # to the active image of the active material slot per face.
    bake_nodes = []
    for slot in body.material_slots:
        if slot.material:
            node = add_target_image_node(slot.material, img)
            bake_nodes.append((slot.material, node))

    configure_bake(bpy.context.scene, img)

    # Select source then active=target.
    deselect_all()
    sculpt.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    print("Starting selected-to-active normal bake (Body_Sculpt -> Body)...")
    try:
        bpy.ops.object.bake(
            type="NORMAL",
            use_selected_to_active=True,
            cage_extrusion=0.02,
            max_ray_distance=0.05,
            normal_space="TANGENT",
            margin=16,
            use_clear=True,
        )
    except Exception as e:
        print(f"BAKE FAILED: {e}")
        for mat, node in bake_nodes:
            remove_node_safe(mat, node)
        sys.exit(1)
    print("Bake complete.")

    # Save image to disk.
    img.save()
    img.reload()
    stats = report_image_stats(img)
    print(f"Bake stats: {stats}")

    # Remove the temporary bake nodes.
    for mat, node in bake_nodes:
        remove_node_safe(mat, node)

    # Inject the new normal map into Skin_Body material.
    injected = inject_anatomical_normal(body, img)

    # Cleanup the sculpt mesh.
    cleanup(sculpt, body, ["top_cloth", "bottome", "Bra", "Underwear_Bottoms"])

    # Save out.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    report = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "bake_target": tex_path,
        "bake_stats": stats,
        "injected_into": injected,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
