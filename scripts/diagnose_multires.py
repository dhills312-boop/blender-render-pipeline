"""Diagnose whether sculpt strokes on Body_Sculpt are stored as multires
displacement (bakeable to normal map) or as base-mesh deformation
(needs different handling).

For the multires modifier on Body_Sculpt, this script:
1. Reports modifier state (levels, sculpt level, render level).
2. Reads the base mesh vertex coordinates.
3. Applies the modifier visually at level 0 and at level 2 to a temp mesh
   and computes per-vertex deltas.
4. Compares the original Body's base mesh vertices against Body_Sculpt's
   base — to detect if user sculpted in Object/Edit mode (which would
   move base verts).
5. Identifies the chest region by Z-coordinate and reports the max delta
   there (where nipple work would be).

Run:
    blender -b a6_v04_sculpted.blend -P diagnose_multires.py
"""

import sys
import bpy
from mathutils import Vector


def get_obj(name):
    return bpy.data.objects.get(name)


def get_multires(obj):
    for m in obj.modifiers:
        if m.type == "MULTIRES":
            return m
    return None


def evaluated_vertices_at_level(obj, level):
    """Return world-space coords of the evaluated mesh after multires at
    a given level. Temporarily sets viewport_levels to that level."""
    multi = get_multires(obj)
    saved = multi.levels
    multi.levels = level
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(deps)
    me = eval_obj.to_mesh()
    coords = [obj.matrix_world @ v.co.copy() for v in me.vertices]
    eval_obj.to_mesh_clear()
    multi.levels = saved
    return coords


def compare_base_to_original(sculpt_obj, body_obj):
    """Compare base-level (level 0) vertices between Body_Sculpt and Body.
    A non-zero max delta means user moved base mesh verts."""
    if len(sculpt_obj.data.vertices) != len(body_obj.data.vertices):
        return None  # topologies diverged, can't compare
    deltas = []
    for vs, vb in zip(sculpt_obj.data.vertices, body_obj.data.vertices):
        d = (sculpt_obj.matrix_world @ vs.co
             - body_obj.matrix_world @ vb.co).length
        deltas.append(d)
    deltas.sort(reverse=True)
    return {
        "max_delta_m": round(deltas[0], 6),
        "top10_deltas": [round(d, 6) for d in deltas[:10]],
        "nonzero_count": sum(1 for d in deltas if d > 1e-5),
        "total_verts": len(deltas),
    }


def chest_region_displacement(coords_low, coords_high):
    """Of all evaluated vertices, find chest region (z 1.3-1.5m, x near 0,
    y < 0 = front) and report max displacement between low and high."""
    if len(coords_low) != len(coords_high):
        return {"error": "vertex count mismatch", "low": len(coords_low),
                "high": len(coords_high)}

    chest = []
    for lo, hi in zip(coords_low, coords_high):
        if 1.25 < lo.z < 1.55 and lo.y < 0.0 and abs(lo.x) < 0.25:
            chest.append((lo, hi, (hi - lo).length))

    if not chest:
        return {"error": "no chest verts found"}

    chest.sort(key=lambda x: -x[2])
    return {
        "chest_vert_count": len(chest),
        "max_chest_delta_m": round(chest[0][2], 6),
        "top5_chest_deltas": [round(c[2], 6) for c in chest[:5]],
    }


def main():
    print("=" * 60)
    print(f"FILE: {bpy.data.filepath}")
    print("=" * 60)

    body = get_obj("Body")
    sculpt = get_obj("Body_Sculpt")
    if not sculpt:
        print("ERROR: Body_Sculpt not found.")
        sys.exit(1)
    if not body:
        print("WARN: Body not found, skipping base-comparison check.")

    multi = get_multires(sculpt)
    if not multi:
        print("ERROR: No Multires modifier on Body_Sculpt.")
        sys.exit(1)

    print("\n[1] Multires modifier state:")
    print(f"    levels (viewport):     {multi.levels}")
    print(f"    sculpt_levels:         {multi.sculpt_levels}")
    print(f"    render_levels:         {multi.render_levels}")
    print(f"    total_levels:          {multi.total_levels}")
    print(f"    base mesh vertices:    {len(sculpt.data.vertices)}")

    if body and len(body.data.vertices) == len(sculpt.data.vertices):
        print("\n[2] Base-mesh comparison (Body_Sculpt vs Body):")
        cmp = compare_base_to_original(sculpt, body)
        print(f"    max delta: {cmp['max_delta_m']} m")
        print(f"    nonzero verts: {cmp['nonzero_count']} / {cmp['total_verts']}")
        if cmp['max_delta_m'] > 0.0001:
            print("    >>> base mesh has moved verts (sculpt may be on base, "
                  "not multires)")
        else:
            print("    base mesh is unchanged (sculpt should be in multires)")

    print("\n[3] Multires displacement check (low vs high level):")
    coords_low = evaluated_vertices_at_level(sculpt, 0)
    coords_high = evaluated_vertices_at_level(sculpt, multi.total_levels)
    print(f"    level 0 verts: {len(coords_low)}")
    print(f"    level {multi.total_levels} verts: {len(coords_high)}")

    if len(coords_low) == len(coords_high):
        deltas = [(a - b).length for a, b in zip(coords_low, coords_high)]
        deltas.sort(reverse=True)
        print(f"    max delta:    {round(deltas[0], 6)} m")
        print(f"    nonzero:      {sum(1 for d in deltas if d > 1e-5)} / {len(deltas)}")
    else:
        # Compare against subdivided low-res by upsampling indices.
        # Simpler heuristic: count how many high-res verts are far from
        # the bounding box of low-res — if high res is just smooth subdivision,
        # all high verts will be inside the low-res convex hull.
        print("    (vertex counts differ — multires has actual subdivision)")

    print("\n[4] Chest region displacement:")
    cr = chest_region_displacement(coords_low, coords_high)
    print(f"    {cr}")

    print("\n=== INTERPRETATION ===")
    print("If [2] shows base verts moved >> sculpt is on BASE mesh.")
    print("   FIX: We can transfer base→multires displacement, OR re-bake using")
    print("        the sculpt object directly without multires-bake mode.")
    print("If [3] max_delta near 0 + [2] base unchanged >> NO sculpt happened.")
    print("If [3] max_delta > 0.001 + [4] chest delta > 0.001 >> sculpt is in")
    print("   multires AND in chest area. Multires bake should work; check why")
    print("   the bake came out flat (likely modifier state during bake).")


if __name__ == "__main__":
    main()
