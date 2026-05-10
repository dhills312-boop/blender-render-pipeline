"""Sanity-check what Body_Sculpt actually looks like in v04 by exporting
its evaluated geometry to OBJ and reading the bounds."""

import sys
import bpy
from mathutils import Vector


def main():
    sculpt = bpy.data.objects.get("Body_Sculpt")
    body = bpy.data.objects.get("Body")
    if not sculpt or not body:
        print("MISSING")
        sys.exit(1)

    deps = bpy.context.evaluated_depsgraph_get()
    eval_s = sculpt.evaluated_get(deps)
    eval_b = body.evaluated_get(deps)
    me_s = eval_s.to_mesh()
    me_b = eval_b.to_mesh()

    # Bounding box of both.
    if len(me_s.vertices) == 0 or len(me_b.vertices) == 0:
        print("Empty mesh")
        sys.exit(1)

    sx = [v.co.x for v in me_s.vertices]
    sy = [v.co.y for v in me_s.vertices]
    sz = [v.co.z for v in me_s.vertices]
    bx = [v.co.x for v in me_b.vertices]
    by = [v.co.y for v in me_b.vertices]
    bz = [v.co.z for v in me_b.vertices]

    print("Body_Sculpt evaluated bounds:")
    print(f"  X: [{min(sx):.4f}, {max(sx):.4f}]  width={max(sx)-min(sx):.4f}")
    print(f"  Y: [{min(sy):.4f}, {max(sy):.4f}]  depth={max(sy)-min(sy):.4f}")
    print(f"  Z: [{min(sz):.4f}, {max(sz):.4f}]  height={max(sz)-min(sz):.4f}")
    print()
    print("Body evaluated bounds:")
    print(f"  X: [{min(bx):.4f}, {max(bx):.4f}]  width={max(bx)-min(bx):.4f}")
    print(f"  Y: [{min(by):.4f}, {max(by):.4f}]  depth={max(by)-min(by):.4f}")
    print(f"  Z: [{min(bz):.4f}, {max(bz):.4f}]  height={max(bz)-min(bz):.4f}")
    print()

    # Per-vertex delta in evaluated space — but using nearest-neighbor
    # not index-paired (because multires reorders verts).
    # Instead, just compare the silhouettes.
    s_volume_verts = sum(1 for v in me_s.vertices)
    b_volume_verts = sum(1 for v in me_b.vertices)
    print(f"Evaluated vert counts: sculpt={s_volume_verts}, body={b_volume_verts}")

    # Find the chest region max-Y-forward extreme on both meshes.
    chest_s_y = []
    chest_b_y = []
    for v in me_s.vertices:
        wc = sculpt.matrix_world @ v.co
        if 1.30 <= wc.z <= 1.45 and abs(wc.x) < 0.20 and wc.y < 0:
            chest_s_y.append(wc.y)
    for v in me_b.vertices:
        wc = body.matrix_world @ v.co
        if 1.30 <= wc.z <= 1.45 and abs(wc.x) < 0.20 and wc.y < 0:
            chest_b_y.append(wc.y)
    print(f"\nChest region (z=1.30-1.45m, x near center, y<0):")
    print(f"  Body_Sculpt forward extreme: {min(chest_s_y):.5f}m"
          f" ({len(chest_s_y)} verts)")
    print(f"  Body forward extreme:        {min(chest_b_y):.5f}m"
          f" ({len(chest_b_y)} verts)")
    print(f"  Difference (sculpt forward of body): "
          f"{(min(chest_b_y) - min(chest_s_y)) * 1000:.2f}mm")

    eval_s.to_mesh_clear()
    eval_b.to_mesh_clear()


if __name__ == "__main__":
    main()
