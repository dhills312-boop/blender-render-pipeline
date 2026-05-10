"""Compare Channel0 and UV_chest UVs on the chest_faces vertex group to
see which UV layer (if either) got unwrapped."""

import bpy

body = bpy.data.objects.get("Body")
if not body:
    raise SystemExit("No Body")

me = body.data
print(f"UV layers: {[u.name for u in me.uv_layers]}")
print(f"Active UV: {me.uv_layers.active.name if me.uv_layers.active else 'none'}")
print(f"Active for render UV: "
      f"{[u.name for u in me.uv_layers if u.active_render]}")

# Get chest verts via vertex group.
vg = body.vertex_groups.get("chest_faces")
if not vg:
    raise SystemExit("No chest_faces vertex group")
chest_vert_indices = set()
for v in me.vertices:
    for g in v.groups:
        if g.group == vg.index:
            chest_vert_indices.add(v.index)

# For each UV layer, sample chest face UV ranges.
for uv_layer in me.uv_layers:
    uv_data = uv_layer.data
    chest_uvs = []
    for poly in me.polygons:
        if any(vi in chest_vert_indices for vi in poly.vertices):
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                chest_uvs.append((uv_data[li].uv.x, uv_data[li].uv.y))
    if chest_uvs:
        us = [u[0] for u in chest_uvs]
        vs = [u[1] for u in chest_uvs]
        print(f"\n  Layer '{uv_layer.name}' chest UV range:")
        print(f"    U: [{min(us):.3f}, {max(us):.3f}]")
        print(f"    V: [{min(vs):.3f}, {max(vs):.3f}]")
        # In [0,1] tile = unwrapped. >1 anywhere = still UDIM original.
        unwrapped = max(us) <= 1.05 and min(us) >= -0.05
        print(f"    Unwrapped to [0,1]? {unwrapped}")
