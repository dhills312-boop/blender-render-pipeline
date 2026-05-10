"""Bake the v04 sculpt to a normal map by APPLYING the multires modifier
to a temporary copy first, then doing standard high-to-low bake.

The previous approaches failed because:
- Multires bake mode reads displacement-vs-base, but the v04 basis has
  the entire body shape encoded as multires displacement, not just the
  sculpt deltas.
- Selected_to_active bake on Body_Sculpt-with-multires-modifier sees the
  evaluated mesh which includes the smooth subdivision of the entire body,
  not just localized sculpt detail.

Fix: apply the multires modifier to a temp duplicate of Body_Sculpt so
the high-poly has the actual sculpted geometry baked into vertices, then
bake that temp mesh against the original Body. Standard high-to-low.

After bake, run a "diff vs flat" check on the output to confirm the
normal map has localized chest detail (not whole-body distortion).

Run:
    blender -b a6_v04_sculpted.blend -P a6_anatomy_bake_v3.py -- \
        --out-blend <new> --tex-dir <abs> --report <path>
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
    p.add_argument("--bake-resolution", type=int, default=2048)
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


def apply_modifiers_to_copy(source_obj, new_name):
    """Duplicate source_obj and apply all modifiers to the duplicate.
    Returns the new evaluated-mesh object."""
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = source_obj.evaluated_get(deps)
    me = bpy.data.meshes.new_from_object(eval_obj, depsgraph=deps)
    me.name = f"{new_name}_data"
    new_obj = bpy.data.objects.new(new_name, me)
    new_obj.matrix_world = source_obj.matrix_world.copy()
    bpy.context.collection.objects.link(new_obj)
    return new_obj


def create_bake_image(name, path, resolution):
    img = bpy.data.images.new(name, resolution, resolution, alpha=False)
    pixels = [0.5, 0.5, 1.0, 1.0] * (resolution * resolution)
    img.pixels.foreach_set(pixels)
    img.colorspace_settings.name = "Non-Color"
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def configure_bake(scene):
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
    scene.render.bake.cage_extrusion = 0.005
    scene.render.bake.max_ray_distance = 0.01
    scene.render.bake.margin = 16
    scene.render.use_bake_multires = False


def add_target_node(material, image):
    if not material.use_nodes:
        material.use_nodes = True
    nt = material.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.select = True
    nt.nodes.active = node
    return node


def remove_node(material, node):
    if node and material.node_tree:
        try:
            material.node_tree.nodes.remove(node)
        except Exception:
            pass


def find_skin_body_material(body):
    for slot in body.material_slots:
        if slot.material and slot.material.name == "Skin_Body":
            return slot.material
    return body.material_slots[0].material if body.material_slots else None


def find_skin_body_bsdf(body):
    mat = find_skin_body_material(body)
    if not mat or not mat.use_nodes:
        return None, None, None
    nt = mat.node_tree
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return mat, nt, n
    return mat, nt, None


def inject_normal_into_skin_body(body, sculpted_image, factor):
    mat, nt, bsdf = find_skin_body_bsdf(body)
    if not (mat and nt and bsdf):
        print("WARN: Skin_Body BSDF not found.")
        return None

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
    mix_node.inputs["Factor"].default_value = factor
    mix_node.location = (bsdf.location.x - 250, bsdf.location.y - 200)

    nin = bsdf.inputs["Normal"]
    if nin.is_linked:
        existing = nin.links[0]
        src_socket = existing.from_socket
        nt.links.remove(existing)
        nt.links.new(src_socket, mix_node.inputs[4])
    nt.links.new(nm_node.outputs["Normal"], mix_node.inputs[5])
    nt.links.new(mix_node.outputs[1], nin)
    return mat.name


def report_image(img):
    pixels = list(img.pixels)
    n = len(pixels) // 4
    deviation_count = 0
    max_dev = 0.0
    for i in range(0, n, 25):
        r, g, b = pixels[i*4], pixels[i*4+1], pixels[i*4+2]
        dev = abs(r - 0.5) + abs(g - 0.5) + abs(b - 1.0)
        if dev > 0.05:
            deviation_count += 1
        max_dev = max(max_dev, dev)
    return {
        "size": list(img.size),
        "non_neutral_count": deviation_count,
        "max_deviation": round(max_dev, 4),
    }


def cleanup_temp(temp_obj):
    me = temp_obj.data
    bpy.data.objects.remove(temp_obj, do_unlink=True)
    if me.users == 0:
        bpy.data.meshes.remove(me)


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
        print("ERROR: Missing Body or Body_Sculpt")
        sys.exit(1)

    # Step 1: bake multires into a regular mesh by applying modifiers.
    print("\n[1] Applying multires + all modifiers to a temp copy of Body_Sculpt...")
    temp = apply_modifiers_to_copy(sculpt, "Body_Sculpt_Applied")
    print(f"    Created {temp.name} with {len(temp.data.vertices)} verts")

    # Step 2: isolate — hide everything except Body and the temp.
    visibility_stash = {}
    for obj in bpy.data.objects:
        visibility_stash[obj.name] = (obj.hide_viewport, obj.hide_render)
        if obj.name in ("Body", temp.name):
            make_visible(obj)
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            try:
                obj.hide_set(True)
            except Exception:
                pass
    print(f"\n[2] Hidden everything except Body and {temp.name} "
          f"({len(visibility_stash) - 2} hidden)")

    # Step 3: bake target image.
    os.makedirs(args.tex_dir, exist_ok=True)
    tex_path = os.path.join(
        args.tex_dir, "Std_Skin_Body_Normal_anatomical_1k.png"
    )
    img = create_bake_image(
        "Std_Skin_Body_Normal_anatomical",
        tex_path, args.bake_resolution
    )
    print(f"\n[3] Bake target: {tex_path} ({args.bake_resolution}x{args.bake_resolution})")

    # Add bake target node to ALL of Body's material slots.
    bake_nodes = []
    for slot in body.material_slots:
        if slot.material:
            n = add_target_node(slot.material, img)
            bake_nodes.append((slot.material, n))

    configure_bake(bpy.context.scene)

    # Step 4: select temp (source), then body (target), bake.
    deselect_all()
    temp.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    print(f"\n[4] Baking {temp.name} -> Body...")
    try:
        bpy.ops.object.bake(
            type="NORMAL",
            use_selected_to_active=True,
            cage_extrusion=0.005,
            max_ray_distance=0.01,
            normal_space="TANGENT",
            margin=16,
            use_clear=True,
        )
    except Exception as e:
        print(f"BAKE FAILED: {e}")
        for mat, n in bake_nodes:
            remove_node(mat, n)
        cleanup_temp(temp)
        sys.exit(1)

    img.save()
    img.reload()
    stats = report_image(img)
    print(f"    Bake stats: {stats}")

    # Cleanup temp bake nodes.
    for mat, n in bake_nodes:
        remove_node(mat, n)

    # Step 5: cleanup temp object.
    cleanup_temp(temp)

    # Step 6: keep Body_Sculpt in the file (don't delete — user may iterate).
    # Just make sure it's still there visible alongside Body.
    make_visible(sculpt)
    make_visible(body)
    # Restore other meshes' visibility.
    for name, (hv, hr) in visibility_stash.items():
        obj = bpy.data.objects.get(name)
        if obj and name not in ("Body", "Body_Sculpt"):
            obj.hide_viewport = hv
            obj.hide_render = hr

    # Step 7: inject normal into Skin_Body.
    injected = inject_normal_into_skin_body(body, img, factor=0.5)
    print(f"\n[7] Injected into material: {injected}")

    # Step 8: save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "bake_target": tex_path,
        "bake_stats": stats,
        "injected_into": injected,
        "mix_factor": 0.5,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
