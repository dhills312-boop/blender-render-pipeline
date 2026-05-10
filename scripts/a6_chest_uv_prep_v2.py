"""Re-prep chest UV unwrap with CORRECTED chest coordinates.

The earlier prep used wrong Z range (1.30-1.55) which is actually face/neck
height. Real chest is z 1.20-1.38 with Y<0 and 0.04 < |X| < 0.20.

This script:
1. Removes the old (incorrect) UV_chest layer and chest_faces vertex group.
2. Recomputes chest faces with correct coords.
3. Adds a fresh UV_chest UV layer.
4. Adds chest_faces vertex group with corrected verts.
5. Sets active UV layer to UV_chest.
6. Selects ONLY chest faces in saved state (script verifies counts before save).
7. Saves to a new versioned file.

Run:
    blender -b a6_v05_Test.blend -P a6_chest_uv_prep_v2.py -- \
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
    """CORRECTED: Chest is z 1.20-1.38, not 1.30-1.55."""
    verts = [body.matrix_world @ body.data.vertices[vi].co
             for vi in poly.vertices]
    cx = sum(v.x for v in verts) / len(verts)
    cy = sum(v.y for v in verts) / len(verts)
    cz = sum(v.z for v in verts) / len(verts)
    # Chest height: 1.20 to 1.38 (verified by full-body bounds).
    # Front half: y < 0 (depth axis points forward = -y in this model).
    # Excluding sternum: 0.04 < |x| < 0.25 (a bit wider than before to
    # capture full breast).
    return (1.20 <= cz <= 1.38
            and 0.04 < abs(cx) < 0.25
            and cy < 0)


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
    print(f"Existing UV layers before cleanup: {[u.name for u in me.uv_layers]}")

    # Step 1: Remove stale UV_chest layer if it exists.
    if "UV_chest" in me.uv_layers:
        me.uv_layers.remove(me.uv_layers["UV_chest"])
        print("[1] Removed stale UV_chest layer")

    # Step 2: Remove stale chest_faces vertex group.
    if "chest_faces" in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups["chest_faces"])
        print("    Removed stale chest_faces vertex group")

    # Step 3: Find chest faces with corrected coords.
    chest_face_indices = []
    chest_vert_indices = set()
    for poly in me.polygons:
        if is_chest_face(body, poly):
            chest_face_indices.append(poly.index)
            for vi in poly.vertices:
                chest_vert_indices.add(vi)
    print(f"\n[2] Found {len(chest_face_indices)} chest faces "
          f"({len(chest_vert_indices)} unique verts)")

    if len(chest_face_indices) == 0:
        print("ERROR: No chest faces found! Coords may still be off.")
        sys.exit(1)

    # Sanity: check the world-space bounds of the chest verts.
    chest_z_values = []
    for vi in chest_vert_indices:
        wc = body.matrix_world @ me.vertices[vi].co
        chest_z_values.append(wc.z)
    print(f"    Chest verts actual Z range: "
          f"[{min(chest_z_values):.3f}, {max(chest_z_values):.3f}]")

    # Step 4: Add fresh UV_chest layer.
    new_layer = me.uv_layers.new(name="UV_chest", do_init=True)
    print(f"\n[3] Created fresh UV layer: {new_layer.name}")

    # Step 5: Add chest_faces vertex group.
    vg = body.vertex_groups.new(name="chest_faces")
    vg.add(list(chest_vert_indices), 1.0, "REPLACE")
    print(f"[4] Added vertex group 'chest_faces' with {len(chest_vert_indices)} verts")

    # Step 6: Mark only chest polygons as selected; deselect everything else.
    for poly in me.polygons:
        poly.select = False
    for v in me.vertices:
        v.select = False
    for e in me.edges:
        e.select = False
    for fi in chest_face_indices:
        me.polygons[fi].select = True
    # Also mark verts/edges of chest faces as selected (Blender's edit mode
    # selection state requires all three to align).
    for fi in chest_face_indices:
        poly = me.polygons[fi]
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            me.vertices[me.loops[li].vertex_index].select = True
            me.edges[me.loops[li].edge_index].select = True
    print(f"[5] Marked {len(chest_face_indices)} faces as selected, "
          f"others deselected")

    # Step 7: Set UV_chest as active and active for render.
    me.uv_layers.active_index = me.uv_layers.find("UV_chest")
    me.uv_layers.active.active_render = True
    print(f"\n[6] Active UV layer: {me.uv_layers.active.name}")

    # Make Body selected/active.
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass
    body.select_set(True)
    bpy.context.view_layer.objects.active = body

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "chest_face_count": len(chest_face_indices),
        "chest_vert_count": len(chest_vert_indices),
        "chest_z_range": [min(chest_z_values), max(chest_z_values)],
        "uv_layer_added": "UV_chest",
        "vertex_group_added": "chest_faces",
        "active_uv_layer": me.uv_layers.active.name,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")

    print("\n--- USER STEPS ---")
    print(f"1. Open {args.out_blend}")
    print("2. Body is selected. Tab to Edit Mode.")
    print("3. Verify ONLY chest faces are highlighted (not whole body).")
    print("4. Hover viewport, U > Smart UV Project, OK with defaults.")
    print("5. Tab to Object Mode.")
    print("6. File > Save (Ctrl+S, overwrite).")
    print("7. Tell me when done.")


if __name__ == "__main__":
    main()
