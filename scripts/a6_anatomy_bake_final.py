"""Final anatomy bake — works on a6_v05_Test.blend where the user has
already applied the multires modifier on Body_Sculpt.

State this script expects:
- Body: original CC4 body, 14,164 verts, with shape keys, UVs, and the
  Skin_Body material assigned to chest faces.
- Body_Sculpt: high-poly version with sculpt detail baked into vertex
  positions. No modifiers, ~225k verts.

Action:
1. Hide every other mesh in scene (no Rigify widgets, no Eye/Eyelash/
   TearLine/Tongue/Teeth/clothing — they confuse ray casts).
2. Create bake target image initialized to neutral tangent normal.
3. Attach the target image as a TEX_IMAGE node, selected & active, on
   every Body material slot.
4. Configure Cycles + tangent normal + selected_to_active + tight cage.
5. Select Body_Sculpt then Body (active=Body), bake.
6. Save image to disk.
7. Inject the new normal map into the Skin_Body material's BSDF Normal
   input, mixed with the existing CC4 normal at 50%.
8. Restore visibility and save .blend as a6_v06_anatomy_done.blend.

Run:
    blender -b a6_v05_Test.blend -P a6_anatomy_bake_final.py -- \
        --out-blend <path> --tex-dir <abs> --bake-resolution 1024 \
        --report <path>
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
    p.add_argument("--mix-factor", type=float, default=0.5)
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


def safe_hide(obj):
    obj.hide_viewport = True
    obj.hide_render = True
    try:
        obj.hide_set(True)
    except RuntimeError:
        pass


def deselect_all():
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass


def create_bake_image(name, path, resolution):
    img = bpy.data.images.new(name, resolution, resolution, alpha=False)
    px = [0.5, 0.5, 1.0, 1.0] * (resolution * resolution)
    img.pixels.foreach_set(px)
    img.colorspace_settings.name = "Non-Color"
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def add_target_node(material, image):
    if not material.use_nodes:
        material.use_nodes = True
    nt = material.node_tree
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = image
    n.label = "BAKE_TARGET"
    n.select = True
    nt.nodes.active = n
    n.location = (-1500, -800)
    return n


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
    return None


def find_skin_body_bsdf(mat):
    if not mat or not mat.use_nodes:
        return None, None
    nt = mat.node_tree
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return nt, n
    return nt, None


def inject_normal_into_skin_body(body, sculpted_image, factor):
    mat = find_skin_body_material(body)
    if not mat:
        print("WARN: Skin_Body material not found.")
        return None
    nt, bsdf = find_skin_body_bsdf(mat)
    if not bsdf:
        print("WARN: Principled BSDF not found in Skin_Body.")
        return mat.name

    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.image = sculpted_image
    img_node.label = "Anatomical Normal"
    img_node.location = (bsdf.location.x - 900, bsdf.location.y - 300)

    nm_node = nt.nodes.new("ShaderNodeNormalMap")
    nm_node.label = "Anatomical Normal Map"
    nm_node.location = (bsdf.location.x - 600, bsdf.location.y - 300)
    nt.links.new(img_node.outputs["Color"], nm_node.inputs["Color"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "VECTOR"
    mix.label = "Anatomical Normal Mix"
    mix.inputs["Factor"].default_value = factor
    mix.location = (bsdf.location.x - 250, bsdf.location.y - 200)

    nin = bsdf.inputs["Normal"]
    if nin.is_linked:
        ln = nin.links[0]
        src = ln.from_socket
        nt.links.remove(ln)
        nt.links.new(src, mix.inputs[4])
    nt.links.new(nm_node.outputs["Normal"], mix.inputs[5])
    nt.links.new(mix.outputs[1], nin)
    return mat.name


def report_image(img):
    px = list(img.pixels)
    n = len(px) // 4
    nn = 0
    md = 0.0
    for i in range(0, n, 25):
        r, g, b = px[i*4], px[i*4+1], px[i*4+2]
        d = abs(r - 0.5) + abs(g - 0.5) + abs(b - 1.0)
        if d > 0.05:
            nn += 1
        md = max(md, d)
    return {
        "size": list(img.size),
        "non_neutral_count": nn,
        "max_deviation": round(md, 4),
    }


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print(f"BAKE RES: {args.bake_resolution}")
    print(f"MIX FACTOR: {args.mix_factor}")
    print("=" * 60)

    body = get_obj("Body")
    sculpt = get_obj("Body_Sculpt")
    if not (body and sculpt):
        print("ERROR: Body or Body_Sculpt missing.")
        sys.exit(1)
    print(f"\nBody verts: {len(body.data.vertices)}")
    print(f"Body_Sculpt verts: {len(sculpt.data.vertices)}")
    print(f"Body_Sculpt modifiers: {[m.type for m in sculpt.modifiers]}")
    if sculpt.modifiers:
        print("  WARN: Body_Sculpt still has modifiers — unexpected for v5_test")

    # Step 1: isolate.
    visibility_stash = {}
    for obj in bpy.data.objects:
        visibility_stash[obj.name] = (obj.hide_viewport, obj.hide_render)
        if obj.name in ("Body", "Body_Sculpt"):
            make_visible(obj)
        else:
            safe_hide(obj)
    print(f"\n[1] Isolated Body+Body_Sculpt; hid {len(visibility_stash) - 2} others")

    # Step 2: create bake image.
    os.makedirs(args.tex_dir, exist_ok=True)
    tex_path = os.path.join(
        args.tex_dir, "Std_Skin_Body_Normal_anatomical_1k.png"
    )
    img = create_bake_image(
        "Std_Skin_Body_Normal_anatomical",
        tex_path, args.bake_resolution
    )
    print(f"\n[2] Bake target: {tex_path}")

    # Step 3: attach target node to ALL Body materials.
    bake_nodes = []
    for slot in body.material_slots:
        if slot.material:
            n = add_target_node(slot.material, img)
            bake_nodes.append((slot.material, n))
    print(f"\n[3] Attached bake target to {len(bake_nodes)} material slot(s)")

    # Step 4: configure bake.
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.render.bake.use_selected_to_active = True
    sc.render.bake.use_clear = True
    sc.render.bake.normal_space = "TANGENT"
    sc.render.bake.normal_r = "POS_X"
    sc.render.bake.normal_g = "POS_Y"
    sc.render.bake.normal_b = "POS_Z"
    sc.render.bake.cage_extrusion = 0.005
    sc.render.bake.max_ray_distance = 0.01
    sc.render.bake.margin = 16
    sc.render.use_bake_multires = False
    print("\n[4] Bake settings configured")

    # Step 5: select source then target, bake.
    deselect_all()
    sculpt.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    print("\n[5] Baking Body_Sculpt -> Body...")
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
        sys.exit(1)

    img.save()
    img.reload()
    stats = report_image(img)
    print(f"    Bake stats: {stats}")

    # Step 6: cleanup temp bake nodes.
    for mat, n in bake_nodes:
        remove_node(mat, n)

    # Step 7: inject into Skin_Body.
    injected = inject_normal_into_skin_body(body, img, args.mix_factor)
    print(f"\n[6] Injected normal map into: {injected}")

    # Step 8: restore visibility.
    for name, (hv, hr) in visibility_stash.items():
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = hv
            obj.hide_render = hr
    make_visible(body)
    make_visible(sculpt)
    print("\n[7] Restored visibility of all other meshes")

    # Step 9: save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "bake_target": tex_path,
        "bake_stats": stats,
        "injected_into": injected,
        "mix_factor": args.mix_factor,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
