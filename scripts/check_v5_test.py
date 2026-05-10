"""Single check: does v5_test's Body_Sculpt have readable multires displacement?

The previous diagnostic checked evaluated mesh against base mesh and got
zero — meaning headless depsgraph wasn't returning displaced geometry.
This check tries multiple approaches:

1. Force the depsgraph to use viewport multires level (not render).
2. Directly inspect mesh's multires CustomData via low-level access.
3. Try evaluating at each subdivision level.
4. Compare against Body to find "where is the sculpt actually in space."
"""

import sys
import bpy
from mathutils import Vector


def main():
    s = bpy.data.objects.get("Body_Sculpt")
    b = bpy.data.objects.get("Body")
    if not s or not b:
        print("MISSING Body or Body_Sculpt")
        sys.exit(1)

    # Find multires modifier.
    multi = None
    for m in s.modifiers:
        if m.type == "MULTIRES":
            multi = m
            break
    if not multi:
        print("No multires modifier")
        sys.exit(1)

    print(f"Body_Sculpt base verts: {len(s.data.vertices)}")
    print(f"Multires: viewport={multi.levels} sculpt={multi.sculpt_levels} "
          f"render={multi.render_levels} total={multi.total_levels}")
    print()

    # Method 1: standard depsgraph eval at current viewport level.
    deps = bpy.context.evaluated_depsgraph_get()
    eval_s = s.evaluated_get(deps)
    me1 = eval_s.to_mesh()
    print(f"[Method 1] Standard depsgraph eval verts: {len(me1.vertices)}")

    # Compare evaluated to base.
    if len(me1.vertices) == len(s.data.vertices):
        deltas = [
            (m1v.co - bv.co).length
            for m1v, bv in zip(me1.vertices, s.data.vertices)
        ]
        print(f"  max delta from base: {max(deltas):.6f}m")
        nonzero = sum(1 for d in deltas if d > 1e-5)
        print(f"  nonzero verts: {nonzero}")

    eval_s.to_mesh_clear()

    # Method 2: try setting viewport level higher first, then re-eval.
    print()
    saved_level = multi.levels
    multi.levels = multi.total_levels  # force max
    bpy.context.view_layer.update()
    deps2 = bpy.context.evaluated_depsgraph_get()
    eval_s2 = s.evaluated_get(deps2)
    me2 = eval_s2.to_mesh()
    print(f"[Method 2] After setting levels=total ({multi.total_levels}): "
          f"{len(me2.vertices)} verts")
    eval_s2.to_mesh_clear()
    multi.levels = saved_level

    # Method 3: scan ALL meshes for chest-region forward extreme.
    print()
    print("[Method 3] All meshes' chest forward extreme:")
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        deps3 = bpy.context.evaluated_depsgraph_get()
        try:
            ev = obj.evaluated_get(deps3)
            me = ev.to_mesh()
        except Exception:
            continue
        chest_y = []
        for v in me.vertices:
            wc = obj.matrix_world @ v.co
            if 1.30 <= wc.z <= 1.45 and abs(wc.x) < 0.20 and wc.y < 0:
                chest_y.append(wc.y)
        ev.to_mesh_clear()
        if chest_y and len(chest_y) > 10:  # only "real" body-like meshes
            print(f"  {obj.name:35s} verts={len(me.vertices):6d} "
                  f"chest_min_y={min(chest_y):.5f}m")


if __name__ == "__main__":
    main()
