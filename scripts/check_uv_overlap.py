"""Check whether Body's UV layout has chest/face overlaps.

For each face on the Body mesh:
1. Determine which body region it belongs to (by 3D vertex Z position).
   - head: z > 1.55
   - chest: 1.30-1.55, x near center, y < 0
   - torso: 0.95-1.30
   - legs: < 0.95
   - arms: |x| > 0.25
2. Read its UV coordinates.
3. Build a per-region UV bounding box.
4. Report whether bounding boxes overlap.

Also dump per-region UV-space pixel coverage as a 256x256 boolean grid
to see where each region maps to in UV space.
"""

import sys
import bpy
from collections import defaultdict


def main():
    body = bpy.data.objects.get("Body")
    if not body:
        print("No Body")
        sys.exit(1)

    me = body.data
    if not me.uv_layers:
        print("No UV layers")
        sys.exit(1)
    uv_layer = me.uv_layers.active.data

    # Get average vert Z per face for region classification.
    region_uvs = defaultdict(list)
    for poly in me.polygons:
        # Average vert position in world space.
        vs = [body.matrix_world @ me.vertices[vi].co for vi in poly.vertices]
        ax = sum(v.x for v in vs) / len(vs)
        ay = sum(v.y for v in vs) / len(vs)
        az = sum(v.z for v in vs) / len(vs)

        if az > 1.55:
            region = "head"
        elif 1.30 <= az <= 1.55 and abs(ax) < 0.25 and ay < 0:
            region = "chest"
        elif 0.95 <= az < 1.30 and abs(ax) < 0.25:
            region = "torso"
        elif abs(ax) >= 0.25:
            region = "arms"
        else:
            region = "legs"

        # Get UV for each loop in this poly.
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            uv = uv_layer[li].uv
            region_uvs[region].append((uv.x, uv.y))

    print("Region UV bounding boxes:")
    for region, uvs in region_uvs.items():
        if not uvs:
            continue
        xs = [u[0] for u in uvs]
        ys = [u[1] for u in uvs]
        print(f"  {region:8s}: U=[{min(xs):.3f}, {max(xs):.3f}] "
              f"V=[{min(ys):.3f}, {max(ys):.3f}] "
              f"(n={len(uvs)} loops)")

    # Now check pairwise overlap between head and chest specifically.
    print("\nHead vs Chest UV overlap analysis:")
    head_uvs = set()
    chest_uvs = set()
    for u, v in region_uvs.get("head", []):
        head_uvs.add((round(u, 3), round(v, 3)))
    for u, v in region_uvs.get("chest", []):
        chest_uvs.add((round(u, 3), round(v, 3)))
    overlap = head_uvs & chest_uvs
    print(f"  head UV samples: {len(head_uvs)}")
    print(f"  chest UV samples: {len(chest_uvs)}")
    print(f"  exact overlap (rounded to 0.001): {len(overlap)}")
    if overlap:
        print(f"    example overlapping UVs: {list(overlap)[:5]}")

    # Bounding box overlap?
    if region_uvs.get("head") and region_uvs.get("chest"):
        h_xs = [u[0] for u in region_uvs["head"]]
        h_ys = [u[1] for u in region_uvs["head"]]
        c_xs = [u[0] for u in region_uvs["chest"]]
        c_ys = [u[1] for u in region_uvs["chest"]]
        h_bb = (min(h_xs), min(h_ys), max(h_xs), max(h_ys))
        c_bb = (min(c_xs), min(c_ys), max(c_xs), max(c_ys))
        print(f"\n  Head bbox:  ({h_bb[0]:.3f}, {h_bb[1]:.3f}) -> "
              f"({h_bb[2]:.3f}, {h_bb[3]:.3f})")
        print(f"  Chest bbox: ({c_bb[0]:.3f}, {c_bb[1]:.3f}) -> "
              f"({c_bb[2]:.3f}, {c_bb[3]:.3f})")
        bb_overlap = (
            h_bb[0] < c_bb[2] and h_bb[2] > c_bb[0]
            and h_bb[1] < c_bb[3] and h_bb[3] > c_bb[1]
        )
        print(f"  bbox overlap: {bb_overlap}")

    # Also check material assignment per region — are head and chest on
    # the same material? If so they DO share texture space; if different
    # materials, the bake-target image only writes to one of them.
    print("\nMaterial assignment per region (sample):")
    for region in ("head", "chest", "torso"):
        if region not in region_uvs:
            continue
        # Find first poly in this region.
        for poly in me.polygons:
            vs = [body.matrix_world @ me.vertices[vi].co for vi in poly.vertices]
            ax = sum(v.x for v in vs) / len(vs)
            ay = sum(v.y for v in vs) / len(vs)
            az = sum(v.z for v in vs) / len(vs)
            poly_region = None
            if az > 1.55:
                poly_region = "head"
            elif 1.30 <= az <= 1.55 and abs(ax) < 0.25 and ay < 0:
                poly_region = "chest"
            elif 0.95 <= az < 1.30 and abs(ax) < 0.25:
                poly_region = "torso"
            if poly_region == region:
                mat_idx = poly.material_index
                mat_name = (body.material_slots[mat_idx].material.name
                            if mat_idx < len(body.material_slots)
                            and body.material_slots[mat_idx].material
                            else "(none)")
                print(f"  {region:8s} -> material slot {mat_idx}: {mat_name}")
                break


if __name__ == "__main__":
    main()
