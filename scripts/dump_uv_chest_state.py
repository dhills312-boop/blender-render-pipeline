"""Dump the current state of UV_chest layer: which faces are inside [0,1]
and which are outside, broken down by region (chest vs non-chest)."""

import sys
import bpy
from collections import defaultdict


def main():
    body = bpy.data.objects.get("Body")
    if not body:
        print("No Body")
        sys.exit(1)
    me = body.data
    if "UV_chest" not in me.uv_layers:
        print("No UV_chest layer")
        sys.exit(1)
    uv = me.uv_layers["UV_chest"].data

    # Get chest_faces vertex group members.
    vg = body.vertex_groups.get("chest_faces")
    chest_verts = set()
    if vg:
        for v in me.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    chest_verts.add(v.index)
                    break

    # For each face, classify as chest or non-chest, and check if any of its
    # UVs are inside [0,1].
    counts = defaultdict(lambda: {"in_01": 0, "out_01": 0, "total": 0})
    sample_in_01 = defaultdict(list)

    for poly in me.polygons:
        is_chest = all(vi in chest_verts for vi in poly.vertices)
        category = "chest" if is_chest else "non_chest"

        # Get the face's UV bounds.
        loop_uvs = []
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            loop_uvs.append((uv[li].uv.x, uv[li].uv.y))
        u_min = min(u[0] for u in loop_uvs)
        u_max = max(u[0] for u in loop_uvs)
        v_min = min(u[1] for u in loop_uvs)
        v_max = max(u[1] for u in loop_uvs)

        # Is ANY part of this face inside [0,1]?
        any_in = (u_min < 1.0 and u_max > 0.0 and v_min < 1.0 and v_max > 0.0)

        counts[category]["total"] += 1
        if any_in:
            counts[category]["in_01"] += 1
            if len(sample_in_01[category]) < 5:
                sample_in_01[category].append({
                    "face_idx": poly.index,
                    "u": [round(u_min, 3), round(u_max, 3)],
                    "v": [round(v_min, 3), round(v_max, 3)],
                })
        else:
            counts[category]["out_01"] += 1

    print(f"chest_faces vertex group: {len(chest_verts)} verts")
    print()
    print("UV_chest layer face distribution:")
    for cat, c in counts.items():
        print(f"\n  {cat}:")
        print(f"    total faces:   {c['total']}")
        print(f"    inside [0,1]:  {c['in_01']}")
        print(f"    outside [0,1]: {c['out_01']}")

    print("\nSample non-chest faces inside [0,1] (these are the leakage):")
    for s in sample_in_01.get("non_chest", []):
        print(f"  face {s['face_idx']}: U={s['u']} V={s['v']}")

    print("\nSample chest faces inside [0,1] (these are correct):")
    for s in sample_in_01.get("chest", []):
        print(f"  face {s['face_idx']}: U={s['u']} V={s['v']}")


if __name__ == "__main__":
    main()
