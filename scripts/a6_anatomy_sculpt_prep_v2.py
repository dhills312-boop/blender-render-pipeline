"""Prepare a hand-sculpting session for nipple/areola anatomy on the CC4 body.

Simplified workflow (no Multires modifier — sculpt strokes go directly into
the base mesh of a duplicate). This avoids Multires save-state weirdness:
1. Duplicate Body -> Body_Sculpt.
2. Apply all shape keys as basis on the duplicate (so future sculpting
   directly modifies the base mesh without breaking shape key state).
3. Hide clothing meshes and the original Body.
4. Append SuperSkin S_* brushes.
5. Save as a versioned working file.

Caller:
    blender -b a6_v02_textures_1k.blend -P a6_anatomy_sculpt_prep_v2.py -- \
        --out-blend <new_path> \
        --super-skin "<absolute path to SuperSkin.blend>"
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
    p.add_argument("--super-skin", required=True)
    return p.parse_args(argv)


def find_body_mesh():
    return bpy.data.objects.get("Body")


def duplicate_body(body):
    new_mesh = body.data.copy()
    new_mesh.name = "Body_Sculpt_data"
    new_obj = body.copy()
    new_obj.data = new_mesh
    new_obj.name = "Body_Sculpt"
    bpy.context.collection.objects.link(new_obj)
    new_obj.modifiers.clear()
    return new_obj


def bake_shape_keys_to_basis(obj):
    """Apply all shape keys to the basis (so subsequent edits modify the
    actual mesh and don't get masked by shape key blending)."""
    if obj.data.shape_keys is None:
        return 0
    n = len(obj.data.shape_keys.key_blocks)
    # Strip — they were duplicated from Body but for the sculpt copy we
    # don't need them; basis mesh becomes the live mesh.
    obj.shape_key_clear()
    return n


def hide_clothing_and_body(body):
    body.hide_viewport = True
    body.hide_render = True
    hidden = []
    for name in CLOTHING_MESH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = True
            obj.hide_render = True
            hidden.append(name)
    return hidden


def append_super_skin_brushes(super_skin_path):
    if not os.path.isfile(super_skin_path):
        print(f"  SKIP: SuperSkin path not found: {super_skin_path}")
        return []
    appended = []
    with bpy.data.libraries.load(super_skin_path, link=False) as (data_from, _):
        brush_names = [n for n in data_from.brushes if n.startswith("S_")]
    if not brush_names:
        return []
    with bpy.data.libraries.load(super_skin_path, link=False) as (data_from, data_to):
        data_to.brushes = brush_names
    for b in data_to.brushes:
        if b is not None:
            try:
                b.asset_mark()
            except Exception:
                pass
            appended.append(b.name)
    return appended


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT:  {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    body = find_body_mesh()
    if not body:
        print("ERROR: Body mesh not found.")
        sys.exit(1)
    n_keys = (len(body.data.shape_keys.key_blocks)
              if body.data.shape_keys else 0)
    print(f"Body: {len(body.data.vertices)} verts, "
          f"{n_keys} shape keys (will be stripped from duplicate only)")

    # 1. Duplicate.
    sculpt = duplicate_body(body)
    print(f"\n[1] Duplicated -> {sculpt.name}")

    # 2. Strip shape keys from duplicate (basis becomes the live mesh).
    n = bake_shape_keys_to_basis(sculpt)
    print(f"[2] Stripped {n} shape keys from duplicate "
          f"(NO multires this time — sculpt directly on base)")

    # 3. Hide clothing + original body.
    hidden = hide_clothing_and_body(body)
    print(f"[3] Hid: {body.name}, {hidden}")

    # 4. Append brushes.
    appended = append_super_skin_brushes(args.super_skin)
    print(f"[4] Appended {len(appended)} SuperSkin brush(es)")

    # 5. Make Body_Sculpt active and selected.
    bpy.ops.object.select_all(action="DESELECT")
    sculpt.select_set(True)
    bpy.context.view_layer.objects.active = sculpt
    print(f"[5] Active object set to {sculpt.name}")

    # 6. Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    print("\n--- NEXT STEPS ---")
    print("1. Open the saved .blend in interactive Blender")
    print("2. Body_Sculpt should be selected. Press Tab to enter Sculpt Mode.")
    print("3. Use Inflate or Crease brush, low strength, small radius.")
    print("4. Sculpt subtle nipple peaks. ~1-2mm projection is ideal.")
    print("5. Tab BACK to Object Mode (commits sculpt strokes).")
    print("6. File > Save (Ctrl+S) — keep same filename.")
    print("7. Tell the assistant you're done — bake will run next.")


if __name__ == "__main__":
    main()
