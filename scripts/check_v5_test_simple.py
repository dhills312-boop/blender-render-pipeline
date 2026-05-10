"""Simple check: read Body and Body_Sculpt base mesh vertex positions
and report chest region differences."""
import sys
import bpy

s = bpy.data.objects.get("Body_Sculpt")
b = bpy.data.objects.get("Body")
if not s or not b:
    print("MISSING")
    sys.exit(1)

print(f"Body verts:        {len(b.data.vertices)}")
print(f"Body_Sculpt verts: {len(s.data.vertices)}")
print(f"Body_Sculpt mods: {[m.type for m in s.modifiers]}")
print()

# If vertex counts match, do per-vertex delta on base mesh data.
if len(s.data.vertices) == len(b.data.vertices):
    deltas = []
    for vs, vb in zip(s.data.vertices, b.data.vertices):
        d = (vs.co - vb.co).length
        deltas.append(d)
    nz = sum(1 for d in deltas if d > 1e-5)
    print(f"Base-mesh-to-base-mesh delta:")
    print(f"  max: {max(deltas):.6f}m")
    print(f"  nonzero: {nz} / {len(deltas)}")

    # Distribution by region.
    chest = []
    for i, (vs, vb) in enumerate(zip(s.data.vertices, b.data.vertices)):
        ws = s.matrix_world @ vs.co
        if 1.25 <= ws.z <= 1.55 and abs(ws.x) < 0.25 and ws.y < 0:
            d = (vs.co - vb.co).length
            chest.append((i, d, ws.x, ws.z))
    chest.sort(key=lambda x: -x[1])
    print(f"  chest verts: {len(chest)}")
    moved_chest = sum(1 for c in chest if c[1] > 1e-5)
    print(f"  chest moved: {moved_chest}")
    print(f"  top 5 chest deltas:")
    for i, (idx, d, x, z) in enumerate(chest[:5]):
        print(f"    vert {idx:5d}  delta={d:.6f}m  x={x:.3f} z={z:.3f}")
else:
    print(f"Vertex counts differ — Body_Sculpt was applied at higher subdiv:")
    print(f"  Body had {len(b.data.vertices)} base verts")
    print(f"  Body_Sculpt now has {len(s.data.vertices)} verts")
    print("  (this is normal if Apply was clicked on a level-2 multires)")
