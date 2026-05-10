"""Honest forensics on a6_v04_sculpted.blend.

Lists every mesh, evaluates it through depsgraph, and for each computes the
displacement signature: max distance any vertex moved from its position in
a smoothed (subdivided) version of the same mesh.

Goal: find where the sculpt strokes ACTUALLY live, not where I assumed.
"""

import sys
import bpy
from mathutils import Vector


def main():
    print("=" * 60)
    print(f"FILE: {bpy.data.filepath}")
    print("=" * 60)

    body = bpy.data.objects.get("Body")
    sculpt = bpy.data.objects.get("Body_Sculpt")

    if not body or not sculpt:
        print("Body or Body_Sculpt missing.")
        sys.exit(1)

    # 1. Are Body and Body_Sculpt's BASE mesh vertices identical?
    same = True
    max_d = 0.0
    moved_indices = []
    for i, (vs, vb) in enumerate(zip(sculpt.data.vertices, body.data.vertices)):
        d = (vs.co - vb.co).length
        if d > max_d:
            max_d = d
        if d > 1e-5:
            moved_indices.append((i, d, vs.co.copy(), vb.co.copy()))
            same = False
    print(f"\n[1] Base mesh comparison:")
    print(f"    Body verts:        {len(body.data.vertices)}")
    print(f"    Body_Sculpt verts: {len(sculpt.data.vertices)}")
    print(f"    Identical: {same}, max delta: {max_d:.6f}m")
    print(f"    Moved verts: {len(moved_indices)}")
    if moved_indices:
        moved_indices.sort(key=lambda x: -x[1])
        print(f"    Top 5 moved verts (idx, delta, sculpt_co, body_co):")
        for i, (idx, d, sc, bc) in enumerate(moved_indices[:5]):
            print(f"      {idx:6d} {d:.6f}m  sc={list(sc)}  body={list(bc)}")

    # 2. Multires modifier on Body_Sculpt?
    multi = None
    for m in sculpt.modifiers:
        if m.type == "MULTIRES":
            multi = m
    if multi:
        print(f"\n[2] Multires on Body_Sculpt:")
        print(f"    levels (viewport): {multi.levels}")
        print(f"    sculpt_levels:     {multi.sculpt_levels}")
        print(f"    render_levels:     {multi.render_levels}")
        print(f"    total_levels:      {multi.total_levels}")
    else:
        print(f"\n[2] No multires on Body_Sculpt")

    # 3. Evaluate Body_Sculpt through depsgraph (with all modifiers) and
    # report per-region displacement vs Body.
    print(f"\n[3] Evaluated geometry comparison:")
    deps = bpy.context.evaluated_depsgraph_get()

    eval_sculpt = sculpt.evaluated_get(deps)
    eval_body = body.evaluated_get(deps)

    me_sculpt = eval_sculpt.to_mesh()
    me_body = eval_body.to_mesh()
    print(f"    Evaluated Body_Sculpt verts: {len(me_sculpt.vertices)}")
    print(f"    Evaluated Body verts:        {len(me_body.vertices)}")

    # If counts match (likely true post-multires-subdivision, since both
    # would have the same multires applied — but Body has no multires) we
    # can compare.
    if len(me_sculpt.vertices) == len(me_body.vertices):
        deltas = [
            (vs.co - vb.co).length
            for vs, vb in zip(me_sculpt.vertices, me_body.vertices)
        ]
        deltas.sort(reverse=True)
        print(f"    Max evaluated delta: {deltas[0]:.6f}m")
        nonzero = sum(1 for d in deltas if d > 1e-5)
        print(f"    Nonzero verts: {nonzero}/{len(deltas)}")
    else:
        print(f"    Vertex counts differ — multires subdivision applied to "
              f"sculpt but not body. Comparing volumetric bounds:")

    # 4. Region distribution of moved verts.
    print(f"\n[4] Where are moved verts located?")
    if len(me_sculpt.vertices) == len(me_body.vertices):
        regions = {"head": [], "chest": [], "torso": [], "legs": [], "arms": [], "other": []}
        for i, (vs, vb) in enumerate(zip(me_sculpt.vertices, me_body.vertices)):
            d = (vs.co - vb.co).length
            if d <= 1e-5:
                continue
            wsv = sculpt.matrix_world @ vs.co
            x, y, z = wsv.x, wsv.y, wsv.z
            if z > 1.55:
                regions["head"].append((i, d, [x, y, z]))
            elif 1.25 <= z <= 1.55 and abs(x) < 0.25:
                regions["chest"].append((i, d, [x, y, z]))
            elif 0.95 <= z < 1.25 and abs(x) < 0.25:
                regions["torso"].append((i, d, [x, y, z]))
            elif z < 0.95:
                regions["legs"].append((i, d, [x, y, z]))
            elif abs(x) >= 0.25:
                regions["arms"].append((i, d, [x, y, z]))
            else:
                regions["other"].append((i, d, [x, y, z]))
        for region, verts in regions.items():
            verts.sort(key=lambda v: -v[1])
            top_d = verts[0][1] if verts else 0
            print(f"    {region:10s}: {len(verts):5d} moved, max delta={top_d:.6f}m")

    eval_sculpt.to_mesh_clear()
    eval_body.to_mesh_clear()

    # 5. Quick sanity: the BASE mesh of Body_Sculpt — are the chest verts
    # actually moved relative to Body?
    print(f"\n[5] BASE mesh chest region check (no modifiers, raw verts):")
    chest_moved = 0
    chest_max = 0.0
    for vs, vb in zip(sculpt.data.vertices, body.data.vertices):
        ws = sculpt.matrix_world @ vs.co
        if 1.25 <= ws.z <= 1.55 and abs(ws.x) < 0.25 and ws.y < 0:
            d = (vs.co - vb.co).length
            if d > 1e-5:
                chest_moved += 1
            chest_max = max(chest_max, d)
    print(f"    chest verts moved on base mesh: {chest_moved}, max={chest_max:.6f}m")


if __name__ == "__main__":
    main()
