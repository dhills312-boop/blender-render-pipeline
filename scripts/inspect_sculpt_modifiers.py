"""List Body_Sculpt's modifier stack and shape keys verbatim."""
import bpy

s = bpy.data.objects.get("Body_Sculpt")
if not s:
    print("NO Body_Sculpt"); exit(1)

print(f"Body_Sculpt verts: {len(s.data.vertices)}")
print(f"Modifiers ({len(s.modifiers)}):")
for m in s.modifiers:
    print(f"  - {m.type:15s} '{m.name}'")
    if m.type == "MULTIRES":
        print(f"      levels={m.levels} sculpt={m.sculpt_levels} "
              f"render={m.render_levels} total={m.total_levels}")
        # Check if there's actual displacement data.
        # Multires data lives on the mesh, not the modifier.
        me = s.data
        # Loops have multires_face_data in some versions.
        print(f"      mesh has {len(me.vertices)} base verts, "
              f"{len(me.polygons)} faces")

print(f"\nShape keys: ", end="")
if s.data.shape_keys:
    print(f"{len(s.data.shape_keys.key_blocks)}")
    for kb in s.data.shape_keys.key_blocks:
        if kb.value != 0:
            print(f"  ACTIVE: {kb.name} = {kb.value}")
else:
    print("none")

# Try multiple ways to get the evaluated mesh.
print("\nDepsgraph evaluation methods:")
deps = bpy.context.evaluated_depsgraph_get()
ev = s.evaluated_get(deps)
print(f"  evaluated_get verts: {len(ev.data.vertices)}")
me1 = ev.to_mesh()
print(f"  to_mesh() verts: {len(me1.vertices)}")
ev.to_mesh_clear()

# Compare a known sculpt vert location vs base location.
ymin_base = min(v.co.y for v in s.data.vertices)
me2 = ev.to_mesh()
ymin_eval = min(v.co.y for v in me2.vertices)
print(f"  base mesh min Y: {ymin_base:.5f}")
print(f"  evaluated min Y: {ymin_eval:.5f}")
print(f"  diff: {(ymin_base - ymin_eval) * 1000:.2f}mm "
      f"(positive = sculpt protrudes more)")
ev.to_mesh_clear()
