"""Map every UV tile (UDIM-style integer-indexed regions) to which body
region(s) live in it, for the Body mesh.

Output: a JSON report listing each UV tile (e.g. tile (0,0) = U[0,1]xV[0,1]),
the body regions whose faces map into it, the material(s) assigned to those
faces, and how many faces.

Body regions are classified by face centroid Z-position in world space:
- head      z > 1.55
- chest     z 1.30-1.55, |x| < 0.20, y < 0
- torso     z 0.95-1.30, |x| < 0.25
- arms      |x| > 0.25
- legs      z < 0.95
- hands_feet (sub-region of legs/arms based on radius)

Run:
    blender -b a6_v05_Test.blend -P map_uv_tiles_to_body_regions.py -- \
        --report <path>
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def classify_region(x, y, z):
    if z > 1.55:
        return "head"
    if 1.30 <= z <= 1.55 and abs(x) < 0.20 and y < 0:
        return "chest"
    if 1.30 <= z <= 1.55 and abs(x) < 0.20 and y >= 0:
        return "upper_back"
    if 0.95 <= z < 1.30 and abs(x) < 0.25:
        return "torso_front" if y < 0 else "torso_back"
    if abs(x) >= 0.25 and z > 0.95:
        return "arm_left" if x > 0 else "arm_right"
    if z < 0.95 and abs(x) < 0.25:
        return "leg_front" if y < 0 else "leg_back"
    if z < 0.95:
        return "leg_left" if x > 0 else "leg_right"
    return "other"


def main():
    args = parse_args()
    body = bpy.data.objects.get("Body")
    if not body:
        print("ERROR: Body not found")
        sys.exit(1)

    me = body.data
    if not me.uv_layers:
        print("ERROR: no UV layers")
        sys.exit(1)
    uv_layer = me.uv_layers.active.data
    print(f"UV layer: {me.uv_layers.active.name}")
    print(f"Body: {len(me.vertices)} verts, {len(me.polygons)} faces")
    print(f"Material slots:")
    for i, slot in enumerate(body.material_slots):
        n = slot.material.name if slot.material else "(none)"
        print(f"  slot {i}: {n}")
    print()

    # tile_data[(u_tile, v_tile)] = {region: {material: face_count}}
    tile_data = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # Also a global region->materials map for convenience.
    region_materials = defaultdict(lambda: defaultdict(int))

    # Per-region UV centroid examples for quick reference.
    region_uv_samples = defaultdict(list)

    for poly in me.polygons:
        # Centroid in world space.
        verts = [body.matrix_world @ me.vertices[vi].co for vi in poly.vertices]
        cx = sum(v.x for v in verts) / len(verts)
        cy = sum(v.y for v in verts) / len(verts)
        cz = sum(v.z for v in verts) / len(verts)
        region = classify_region(cx, cy, cz)

        # Material slot.
        mat_idx = poly.material_index
        mat_name = (body.material_slots[mat_idx].material.name
                    if mat_idx < len(body.material_slots)
                    and body.material_slots[mat_idx].material
                    else "(none)")

        # UV centroid of poly.
        u_total, v_total = 0.0, 0.0
        n_loops = poly.loop_total
        for li in range(poly.loop_start, poly.loop_start + n_loops):
            uv = uv_layer[li].uv
            u_total += uv.x
            v_total += uv.y
        u_avg = u_total / n_loops
        v_avg = v_total / n_loops

        u_tile = int(u_avg) if u_avg >= 0 else int(u_avg) - 1
        v_tile = int(v_avg) if v_avg >= 0 else int(v_avg) - 1

        tile_data[(u_tile, v_tile)][region][mat_name] += 1
        region_materials[region][mat_name] += 1

        # Keep a few sample UVs per region for reference.
        if len(region_uv_samples[region]) < 3:
            region_uv_samples[region].append({
                "world_xyz": [round(cx, 3), round(cy, 3), round(cz, 3)],
                "uv": [round(u_avg, 3), round(v_avg, 3)],
                "tile": [u_tile, v_tile],
                "material": mat_name,
            })

    # Pretty print to stdout.
    print("=" * 60)
    print("UV TILES (each tile is U=[u, u+1] x V=[v, v+1]):")
    print("=" * 60)
    for (u, v), region_dict in sorted(tile_data.items()):
        total = sum(sum(m.values()) for m in region_dict.values())
        print(f"\nTile ({u}, {v})  total {total} faces:")
        for region, mats in region_dict.items():
            face_total = sum(mats.values())
            mat_summary = ", ".join(f"{m}({c})" for m, c in mats.items())
            print(f"  {region:15s}: {face_total:5d} faces  ({mat_summary})")

    print("\n" + "=" * 60)
    print("REGION -> MATERIAL summary:")
    print("=" * 60)
    for region, mats in sorted(region_materials.items()):
        total = sum(mats.values())
        print(f"\n{region} ({total} faces):")
        for m, c in sorted(mats.items(), key=lambda x: -x[1]):
            print(f"  {m:25s} {c:5d} faces")

    # Save JSON report.
    out = {
        "body_object": "Body",
        "uv_layer_name": me.uv_layers.active.name,
        "vertex_count": len(me.vertices),
        "face_count": len(me.polygons),
        "material_slots": [
            slot.material.name if slot.material else None
            for slot in body.material_slots
        ],
        "uv_tiles": {
            f"({u},{v})": {
                region: dict(mats)
                for region, mats in regions.items()
            }
            for (u, v), regions in tile_data.items()
        },
        "region_materials": {
            r: dict(m) for r, m in region_materials.items()
        },
        "region_uv_examples": dict(region_uv_samples),
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nREPORT: {args.report}")


if __name__ == "__main__":
    main()
