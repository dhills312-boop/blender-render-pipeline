"""Inspect Skin_Head's material to find which diffuse texture actually
drives the chest area's color."""
import bpy

print("=" * 60)
print("Skin_Head material inspection (chest is on this material):")
print("=" * 60)

mat = bpy.data.materials.get("Skin_Head")
if not mat:
    print("Skin_Head not found")
    raise SystemExit
nt = mat.node_tree
print(f"\nAll TEX_IMAGE nodes in Skin_Head:")
for n in nt.nodes:
    if n.type == "TEX_IMAGE":
        img = n.image.name if n.image else "(none)"
        cs = n.image.colorspace_settings.name if n.image else "—"
        size = list(n.image.size) if n.image else [0, 0]
        print(f"  '{n.name}' label='{n.label}' image='{img}' "
              f"size={size} cs='{cs}'")

print("\n" + "=" * 60)
print("Skin_Body for comparison:")
print("=" * 60)
mat2 = bpy.data.materials.get("Skin_Body")
if mat2:
    nt2 = mat2.node_tree
    for n in nt2.nodes:
        if n.type == "TEX_IMAGE":
            img = n.image.name if n.image else "(none)"
            cs = n.image.colorspace_settings.name if n.image else "—"
            size = list(n.image.size) if n.image else [0, 0]
            print(f"  '{n.name}' label='{n.label}' image='{img}' "
                  f"size={size} cs='{cs}'")
