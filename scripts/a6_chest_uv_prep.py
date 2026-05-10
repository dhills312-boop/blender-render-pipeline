"""Prep Body for chest UV unwrap.

Step A in the chest-UV workflow:
1. Add a new UV layer 'UV_chest' to Body, copying current Channel0 UVs as
   default values (so non-chest faces already have something).
2. Identify chest faces by world-space coordinates and store them in a
   new vertex group 'chest_faces' for easy re-selection.
3. Enter Edit Mode and select only the chest faces in the saved state,
   so the user opens the file and they're already selected.
4. Set the active UV map to 'UV_chest' so any unwrap operation goes there.
5. Save as a versioned file.

User then opens the file, presses U > Smart UV Project, saves.

Run:
    blender -b a6_v05_Test.blend -P a6_chest_uv_prep.py -- \
        --out-blend <path> --report <path>
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
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def is_chest_face(body, poly):
    """Classify by face centroid in world space."""
    verts = [body.matrix_world @ body.data.vertices[vi].co
             for vi in poly.vertices]
    cx = sum(v.x for v in verts) / len(verts)
    cy = sum(v.y for v in verts) / len(verts)
    cz = sum(v.z for v in verts) / len(verts)
    return (1.30 <= cz <= 1.55 and abs(cx) < 0.20 and cy < 0)


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    body = bpy.data.objects.get("Body")
    if not body:
        print("ERROR: Body not found")
        sys.exit(1)
    me = body.data
    print(f"Body: {len(me.vertices)} verts, {len(me.polygons)} faces")
    print(f"Existing UV layers: {[u.name for u in me.uv_layers]}")

    # Step 1: Add a new UV layer 'UV_chest'.
    # If it already exists, keep it.
    if "UV_chest" not in me.uv_layers:
        # Adding via API: copy current active UV layer's data as starting point.
        new_layer = me.uv_layers.new(name="UV_chest", do_init=True)
        print(f"\n[1] Created new UV layer: {new_layer.name}")
    else:
        new_layer = me.uv_layers["UV_chest"]
        print(f"\n[1] UV layer 'UV_chest' already exists, reusing.")

    # Step 2: Identify chest faces and store as vertex group.
    chest_face_indices = []
    chest_vert_indices = set()
    for poly in me.polygons:
        if is_chest_face(body, poly):
            chest_face_indices.append(poly.index)
            for vi in poly.vertices:
                chest_vert_indices.add(vi)
    print(f"\n[2] Found {len(chest_face_indices)} chest faces "
          f"({len(chest_vert_indices)} unique verts)")

    # Vertex group for re-selection later.
    if "chest_faces" in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups["chest_faces"])
    vg = body.vertex_groups.new(name="chest_faces")
    vg.add(list(chest_vert_indices), 1.0, "REPLACE")
    print(f"    Added to vertex group 'chest_faces'")

    # Step 3: Mark chest polygons as selected in saved state, so when
    # the user opens in Edit Mode the chest faces are pre-selected.
    # First deselect all polygons.
    for poly in me.polygons:
        poly.select = False
    for fi in chest_face_indices:
        me.polygons[fi].select = True
    print(f"    Marked {len(chest_face_indices)} faces as selected in saved state")

    # Step 4: Set 'UV_chest' as the active UV layer.
    me.uv_layers.active_index = me.uv_layers.find("UV_chest")
    me.uv_layers.active.active_render = True  # ensure it's the render UV too
    print(f"\n[3] Set active UV layer to: {me.uv_layers.active.name}")

    # Step 5: Make Body the only selected and active object so when user
    # opens, they tab into edit mode on Body directly.
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    # Report.
    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "chest_face_count": len(chest_face_indices),
        "chest_vert_count": len(chest_vert_indices),
        "uv_layer_added": "UV_chest",
        "vertex_group_added": "chest_faces",
        "active_uv_layer": me.uv_layers.active.name,
        "uv_layers_after": [u.name for u in me.uv_layers],
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")

    print("\n--- USER STEPS (in interactive Blender) ---")
    print(f"1. Open {args.out_blend}")
    print("2. Body should be active. Press Tab to enter Edit Mode.")
    print("3. Chest faces should already be selected (light orange).")
    print("   If not, find vertex group 'chest_faces', click 'Select'.")
    print("4. Hover over the 3D Viewport, press 'U' for unwrap menu.")
    print("5. Choose 'Smart UV Project'. Defaults are fine. Click OK.")
    print("6. Tab back to Object Mode.")
    print("7. File > Save (Ctrl+S, overwrite).")
    print("8. Tell the assistant — Step C will wire texture + bake.")


if __name__ == "__main__":
    main()
