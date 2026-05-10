"""Find which object actually has the sculpted nipple geometry.

Walks every mesh in the scene, evaluates it through the depsgraph (so
modifiers apply), and finds vertices in the chest region that are
displaced from a smooth baseline. Reports per-object stats so we can
identify where the sculpt strokes actually live.
"""

import sys
import bpy
from mathutils import Vector


def main():
    print("=" * 60)
    print(f"FILE: {bpy.data.filepath}")
    print("=" * 60)

    print("\nAll mesh objects:")
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        mods = [(m.type, m.name) for m in obj.modifiers]
        sk_count = (len(obj.data.shape_keys.key_blocks)
                    if obj.data.shape_keys else 0)
        hidden = obj.hide_viewport or obj.hide_get()
        print(f"  {obj.name:30s} verts={len(obj.data.vertices):6d} "
              f"shape_keys={sk_count:3d} hidden={hidden} "
              f"mods={[m[0] for m in mods]}")

    print("\nFor each mesh in chest region, evaluate via depsgraph and check"
          " for displacement:")
    deps = bpy.context.evaluated_depsgraph_get()

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        # Evaluated geometry includes all modifiers (including multires).
        eval_obj = obj.evaluated_get(deps)
        try:
            me = eval_obj.to_mesh()
        except Exception as e:
            print(f"  {obj.name}: cannot evaluate ({e})")
            continue

        chest_verts = []
        for v in me.vertices:
            world = obj.matrix_world @ v.co
            if 1.25 < world.z < 1.55 and world.y < 0.0 and abs(world.x) < 0.25:
                chest_verts.append((world, v.co.copy()))

        eval_obj.to_mesh_clear()

        if not chest_verts:
            continue

        # If any chest vert has |y| > local-mean-y by more than ~3mm, it's
        # bumpy (nipple-like).
        ys = [c[0].y for c in chest_verts]
        mean_y = sum(ys) / len(ys)
        max_protrusion = min(ys)  # most negative = most forward
        protrusion_amount = mean_y - max_protrusion

        # Find max distance from chest centroid for any vert (catches localized
        # bumps even if mean is averaged out).
        cx = sum(c[0].x for c in chest_verts) / len(chest_verts)
        cz = sum(c[0].z for c in chest_verts) / len(chest_verts)
        # For each chest vert, distance from local-fit-plane = how much it
        # bumps out from a smooth chest. We approximate by computing distance
        # from each vert to its 3-nearest-neighbors' average — too expensive
        # to do precisely; instead just report y-axis stats.

        print(f"\n  {obj.name}:")
        print(f"    chest verts: {len(chest_verts)}")
        print(f"    y range: [{min(ys):.4f}, {max(ys):.4f}] (forward = -y)")
        print(f"    y mean: {mean_y:.4f}")
        print(f"    most forward vertex: y={max_protrusion:.4f} "
              f"(protrudes {protrusion_amount*1000:.2f}mm beyond mean)")

        # Tag dramatic protrusions (>4mm) as nipple-like.
        if protrusion_amount > 0.004:
            print(f"    >>> SHOWS DETAIL: chest has >4mm protrusion. "
                  f"Likely contains nipple sculpt.")


if __name__ == "__main__":
    main()
