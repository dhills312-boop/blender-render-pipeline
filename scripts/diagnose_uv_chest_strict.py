"""Strict UV diagnostic: only sample faces where ALL vertices are in
the chest_faces vertex group. Earlier diagnostic used 'any vertex in
group' which captured faces straddling the chest boundary."""

import bpy

body = bpy.data.objects["Body"]
me = body.data
vg = body.vertex_groups["chest_faces"]
chest_verts = set()
for v in me.vertices:
    for g in v.groups:
        if g.group == vg.index:
            chest_verts.add(v.index)
            break

print(f"chest_faces vertex group has {len(chest_verts)} verts")
print()

for layer in me.uv_layers:
    uv = layer.data
    # Strict: faces where ALL verts are in chest group.
    strict_uvs = []
    # Lenient: faces where ANY vert is in chest group.
    lenient_uvs = []
    strict_face_count = 0
    lenient_face_count = 0
    for poly in me.polygons:
        all_in = all(vi in chest_verts for vi in poly.vertices)
        any_in = any(vi in chest_verts for vi in poly.vertices)
        if all_in:
            strict_face_count += 1
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                strict_uvs.append((uv[li].uv.x, uv[li].uv.y))
        if any_in:
            lenient_face_count += 1
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                lenient_uvs.append((uv[li].uv.x, uv[li].uv.y))

    print(f"=== Layer: {layer.name} ===")
    if strict_uvs:
        us = [u[0] for u in strict_uvs]
        vs = [u[1] for u in strict_uvs]
        print(f"  STRICT (all-vert-in-group, {strict_face_count} faces):")
        print(f"    U: [{min(us):.3f}, {max(us):.3f}]  V: [{min(vs):.3f}, {max(vs):.3f}]")
        print(f"    Packed in [0,1]? {max(us) <= 1.05 and min(us) >= -0.05}")
    if lenient_uvs:
        us = [u[0] for u in lenient_uvs]
        vs = [u[1] for u in lenient_uvs]
        print(f"  LENIENT (any-vert-in-group, {lenient_face_count} faces):")
        print(f"    U: [{min(us):.3f}, {max(us):.3f}]  V: [{min(vs):.3f}, {max(vs):.3f}]")
        print(f"    Packed in [0,1]? {max(us) <= 1.05 and min(us) >= -0.05}")
    print()
