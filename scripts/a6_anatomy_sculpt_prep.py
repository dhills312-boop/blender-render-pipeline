"""Prepare a hand-sculpting session for nipple/areola anatomy on the CC4 body.

Workflow (this script):
1. Duplicate `Body` -> `Body_Sculpt` (scratch surface).
2. Strip shape keys from the duplicate (Multires requires no shape keys).
3. Add Multires modifier and subdivide to a target level.
4. Hide clothing meshes so the chest is visually clear in the viewport.
5. Append SuperSkin sculpt brushes from the asset library.
6. Switch the active object to Body_Sculpt and select it for sculpt mode.
7. Save as a new versioned working file.

After this script the user:
- Opens the saved file in interactive Blender
- Switches to Sculpt Mode (Tab)
- Sculpts subtle nipple peaks + areola detail using the appended S_* brushes
- Saves with a new version (e.g. a6_v04_sculpted.blend)

A separate bake script then converts the multires displacement to a normal
map, layers it onto the original body normal, and retargets the material —
leaving the original Body mesh's geometry, weights, UVs, and shape keys
completely untouched.

Run via:
    blender -b a6_v02_textures_1k.blend -P a6_anatomy_sculpt_prep.py -- \
        --out-blend <new_path> --multires-level 2 \
        --supe-rskin "<absolute path to SuperSkin.blend>"
"""

import argparse
import os
import sys

import bpy


CLOTHING_MESH_NAMES = [
    "Bra",
    "Underwear_Bottoms",
    "Breast_Panels",
    "top_cloth",
    "bottome",
    "Waista_",
]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--multires-level", type=int, default=2)
    p.add_argument("--super-skin", required=True,
                   help="Absolute path to SuperSkin.blend")
    return p.parse_args(argv)


def find_body_mesh():
    """Locate the primary body mesh by exact name."""
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name == "Body":
            return obj
    # Fallback: largest mesh with 'body' in the name.
    candidates = [
        o for o in bpy.data.objects
        if o.type == "MESH" and "body" in o.name.lower()
    ]
    if candidates:
        return max(candidates, key=lambda o: len(o.data.vertices))
    return None


def duplicate_body(body):
    """Create a sculpt-target duplicate of the body mesh."""
    new_mesh = body.data.copy()
    new_mesh.name = "Body_Sculpt_data"
    new_obj = body.copy()
    new_obj.data = new_mesh
    new_obj.name = "Body_Sculpt"
    bpy.context.collection.objects.link(new_obj)
    # Make sure modifiers are independent copies.
    new_obj.modifiers.clear()
    return new_obj


def strip_shape_keys(obj):
    """Remove all shape keys from a mesh — required before adding Multires."""
    if obj.data.shape_keys is None:
        return 0
    count = len(obj.data.shape_keys.key_blocks)
    obj.shape_key_clear()
    return count


def add_multires(obj, level):
    """Add a Multires modifier and subdivide to the target level."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mod = obj.modifiers.new("Multires", "MULTIRES")
    # Subdivide.
    for _ in range(level):
        bpy.ops.object.multires_subdivide(modifier=mod.name, mode="CATMULL_CLARK")
    return mod


def hide_clothing():
    """Hide common clothing meshes so the chest is visible."""
    hidden = []
    for name in CLOTHING_MESH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True
            hidden.append(name)
    return hidden


def hide_original_body(body):
    """Hide the original Body mesh in viewport so we sculpt unobstructed."""
    body.hide_viewport = True
    body.hide_render = True


def append_super_skin_brushes(super_skin_path):
    """Append all brushes whose names start with S_ from SuperSkin.blend."""
    if not os.path.isfile(super_skin_path):
        print(f"  SKIP: SuperSkin path not found: {super_skin_path}")
        return []

    appended = []
    # First, peek at the source file to find brush names.
    with bpy.data.libraries.load(super_skin_path, link=False) as (data_from, _):
        brush_names = [n for n in data_from.brushes if n.startswith("S_")]

    if not brush_names:
        print(f"  WARN: No S_*-prefixed brushes found in {super_skin_path}")
        return []

    # Append them.
    with bpy.data.libraries.load(super_skin_path, link=False) as (data_from, data_to):
        data_to.brushes = brush_names

    for b in data_to.brushes:
        if b is not None:
            # Set asset metadata so they show up in the brush picker.
            try:
                b.asset_mark()
            except Exception:
                pass
            appended.append(b.name)
    return appended


def select_for_sculpt(obj):
    """Make the sculpt target the active and only-selected object."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def main():
    args = parse_args()

    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print(f"MULTIRES LEVEL: {args.multires_level}")
    print(f"SUPER SKIN: {args.super_skin}")
    print("=" * 60)

    body = find_body_mesh()
    if not body:
        print("ERROR: Could not find Body mesh.")
        sys.exit(1)
    print(f"Found body mesh: {body.name} "
          f"({len(body.data.vertices)} verts, "
          f"{len(body.data.shape_keys.key_blocks) if body.data.shape_keys else 0} shape keys)")

    # 1. Duplicate.
    sculpt = duplicate_body(body)
    print(f"\n[1] Duplicated -> {sculpt.name}")

    # 2. Strip shape keys from duplicate.
    n_keys = strip_shape_keys(sculpt)
    print(f"[2] Stripped {n_keys} shape keys from duplicate")

    # 3. Add Multires.
    mod = add_multires(sculpt, args.multires_level)
    print(f"[3] Added Multires modifier '{mod.name}' "
          f"at level {args.multires_level}")

    # 4. Hide clothing + original body.
    hidden_clothes = hide_clothing()
    print(f"[4] Hid clothing meshes: {hidden_clothes}")
    hide_original_body(body)
    print(f"    Hid original {body.name} (visibility off)")

    # 5. Append SuperSkin brushes.
    appended = append_super_skin_brushes(args.super_skin)
    print(f"[5] Appended {len(appended)} SuperSkin brush(es): "
          f"{appended[:5]}{'...' if len(appended) > 5 else ''}")

    # 6. Make Body_Sculpt the active object.
    select_for_sculpt(sculpt)
    print(f"[6] Active object set to {sculpt.name}")

    # 7. Save.
    bpy.ops.file.make_paths_relative()
    os.makedirs(os.path.dirname(args.out_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    print("\n--- NEXT STEPS (manual in interactive Blender) ---")
    print(f"1. Open {args.out_blend}")
    print("2. With Body_Sculpt selected, switch to Sculpt Mode (Tab)")
    print("3. Pick an S_* brush from the asset shelf, sculpt nipple peaks")
    print("4. Save As: a6_v04_sculpted.blend")
    print("5. Tell the assistant you're done — bake script will run next")


if __name__ == "__main__":
    main()
