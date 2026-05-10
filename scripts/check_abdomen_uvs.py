"""Check whether the abdomen has UV overlap problems like the chest does.

For abdomen faces (z 0.95-1.20, |x|<0.25, y<0):
- What UV tile do they map to?
- What material?
- Do their UVs share space with any other body region (face, chest, etc.)?
"""
import sys
import bpy
from collections import defaultdict

body = bpy.data.objects.get("Body")
if not body:
    print("No Body")
    sys.exit(1)

me = body.data
uv = me.uv_layers["Channel0"].data  # original UV layer

# Classify all faces.
def classify(cx, cy, cz):
    if cz > 1.45:
        return "head"
    if 1.20 <= cz <= 1.45 and abs(cx) < 0.25 and cy < 0:
        return "chest"
    if 1.20 <= cz <= 1.45 and abs(cx) < 0.25 and cy >= 0:
        return "upper_back"
    if 0.95 <= cz < 1.20 and cy < 0:
        return "abdomen_front"
    if 0.95 <= cz < 1.20 and cy >= 0:
        return "abdomen_back"
    if cz < 0.95:
        return "legs"
    if abs(cx) >= 0.25:
        return "arms"
    return "other"

region_uvs = defaultdict(list)
region_mats = defaultdict(set)

for poly in me.polygons:
    verts = [body.matrix_world @ me.vertices[vi].co for vi in poly.vertices]
    cx = sum(v.x for v in verts) / len(verts)
    cy = sum(v.y for v in verts) / len(verts)
    cz = sum(v.z for v in verts) / len(verts)
    region = classify(cx, cy, cz)

    mat_name = (body.material_slots[poly.material_index].material.name
                if body.material_slots[poly.material_index].material else "?")
    region_mats[region].add(mat_name)

    for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
        u, v = uv[li].uv.x, uv[li].uv.y
        region_uvs[region].append((u, v))

print("Region info:")
for r, uvs in region_uvs.items():
    if not uvs:
        continue
    us = [a[0] for a in uvs]
    vs = [a[1] for a in uvs]
    print(f"\n  {r:18s}  faces~{len(uvs)//4}  materials: {region_mats[r]}")
    print(f"    U range: [{min(us):.3f}, {max(us):.3f}]")
    print(f"    V range: [{min(vs):.3f}, {max(vs):.3f}]")
    # Tile occupancy.
    tiles = set()
    for u, v in uvs:
        tu = int(u) if u >= 0 else int(u) - 1
        tv = int(v) if v >= 0 else int(v) - 1
        tiles.add((tu, tv))
    print(f"    UV tiles occupied: {sorted(tiles)}")

# Check if abdomen overlaps with anything else in same UV tile.
print("\n\nAbdomen vs other regions UV-tile co-occupancy:")
abd_tiles = set()
for u, v in region_uvs.get("abdomen_front", []) + region_uvs.get("abdomen_back", []):
    tu = int(u) if u >= 0 else int(u) - 1
    tv = int(v) if v >= 0 else int(v) - 1
    abd_tiles.add((tu, tv))
print(f"Abdomen tiles: {sorted(abd_tiles)}")
for r, uvs in region_uvs.items():
    if r.startswith("abdomen"):
        continue
    other_tiles = set()
    for u, v in uvs:
        tu = int(u) if u >= 0 else int(u) - 1
        tv = int(v) if v >= 0 else int(v) - 1
        other_tiles.add((tu, tv))
    overlap = abd_tiles & other_tiles
    if overlap:
        print(f"  {r:18s} shares tiles {sorted(overlap)} with abdomen")
