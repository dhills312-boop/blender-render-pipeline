"""Prepare v04 for the user to run the bake in interactive Blender.

This script does ONLY the prep steps — no actual bake (which has been
crashing headlessly):
1. Duplicate Body_Sculpt and apply all modifiers (collapses multires
   displacement into real mesh geometry).
2. Hide every other mesh in the scene EXCEPT Body and the new applied copy.
3. Create the bake target Image (initialized to neutral tangent normal),
   save to disk so the file knows about it.
4. Add an active TEX_IMAGE node referencing the bake target on every
   material slot of Body — Cycles will write here.
5. Set scene render engine to Cycles + bake settings (selected_to_active,
   tangent normal, tight cage).
6. Select source then active=target so the user just hits "Bake".
7. Save to a new versioned file.

The user then:
- Opens the saved file
- In Render Properties (camera icon) > Bake panel, click the "Bake" button
- Saves
- Tells me when done; I run a separate "post-bake injection" script that
  wires the freshly-baked normal map into the Skin_Body material.

Run:
    blender -b a6_v04_sculpted.blend -P a6_anatomy_bake_prep_for_ui.py -- \
        --out-blend <new> --tex-dir <abs> --bake-resolution 1024
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
    """Hide an object only if it's in the active view layer."""
    obj.hide_viewport = True
    obj.hide_render = True
    try:
        obj.hide_set(True)
    except RuntimeError:
        # Object isn't in this view layer — viewport hide is enough.
        pass


def apply_modifiers_to_copy(source_obj, new_name):
    """Duplicate source_obj's evaluated mesh (with all modifiers applied)
    into a new standalone object."""
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


def add_target_node(material, image):
    if not material.use_nodes:
        material.use_nodes = True
    nt = material.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.label = "BAKE_TARGET (anatomical normal)"
    node.select = True
    nt.nodes.active = node
    # Position it off to the side so it doesn't overlap real shader nodes.
    node.location = (-1500, -800)
    return node


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


def deselect_all():
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print(f"BAKE RES: {args.bake_resolution}")
    print("=" * 60)

    body = get_obj("Body")
    sculpt = get_obj("Body_Sculpt")
    if not body or not sculpt:
        print("ERROR: Body or Body_Sculpt missing.")
        sys.exit(1)

    # Step 1: apply modifiers (incl. multires) on a copy of Body_Sculpt.
    print("\n[1] Applying modifiers to a temp copy of Body_Sculpt...")
    temp = apply_modifiers_to_copy(sculpt, "Body_Sculpt_Applied")
    print(f"    Created {temp.name} with {len(temp.data.vertices)} verts "
          f"(vs source {len(sculpt.data.vertices)})")

    # Step 2: hide everything except Body and the temp.
    print("\n[2] Hiding everything except Body and Body_Sculpt_Applied...")
    hidden_count = 0
    for obj in bpy.data.objects:
        if obj.name in ("Body", temp.name):
            make_visible(obj)
        else:
            safe_hide(obj)
            hidden_count += 1
    print(f"    Hidden {hidden_count} object(s)")

    # Step 3: create bake target image and save to disk.
    os.makedirs(args.tex_dir, exist_ok=True)
    tex_path = os.path.join(
        args.tex_dir, "Std_Skin_Body_Normal_anatomical_1k.png"
    )
    img = create_bake_image(
        "Std_Skin_Body_Normal_anatomical",
        tex_path, args.bake_resolution
    )
    print(f"\n[3] Bake target image saved: {tex_path}")

    # Step 4: attach target image node to ALL of Body's material slots.
    print("\n[4] Attaching bake target to Body's materials...")
    attached = 0
    for slot in body.material_slots:
        if slot.material:
            add_target_node(slot.material, img)
            attached += 1
    print(f"    Attached to {attached} material slot(s)")

    # Step 5: configure render/bake settings.
    print("\n[5] Configuring bake settings (Cycles, tangent, tight cage)...")
    configure_bake(bpy.context.scene)

    # Step 6: select source then target so user can just hit Bake.
    deselect_all()
    temp.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    print(f"\n[6] Selection: source={temp.name}, active=Body")

    # Step 7: save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    print("\n--- USER STEPS ---")
    print(f"1. Open {args.out_blend}")
    print("2. Render Properties (camera icon) > scroll to Bake panel")
    print("3. Confirm: Bake Type = Normal, Selected to Active = ON")
    print(f"4. Click 'Bake' button")
    print("5. Wait for it to finish (1-3 minutes)")
    print(f"6. Image should auto-update at {tex_path}")
    print("7. File > Save (Ctrl+S, overwrite)")
    print("8. Tell the assistant — post-bake script wires it into Skin_Body")


if __name__ == "__main__":
    main()
