"""Check a4's .blend for embedded skin textures we could extract."""
import bpy
import os

print(f"FILE: {bpy.data.filepath}")
print(f"\nAll images in this blend:")
print(f"{'Name':<50} {'Size':<15} {'Packed?':<10} {'Filepath'}")
print("=" * 120)

skin_imgs = []
empty_imgs = []
real_imgs = []

for img in bpy.data.images:
    if img.name in ("Render Result", "Viewer Node"):
        continue
    w, h = img.size
    is_packed = bool(img.packed_file)
    fp = img.filepath
    print(f"{img.name:<50} {w}x{h:<10} {is_packed!s:<10} {fp}")

    # Estimate: empty if w==0 or w==1 or named with _Diffuse but obviously empty.
    if w <= 1 or h <= 1:
        empty_imgs.append(img.name)
    elif "skin" in img.name.lower() and "diffuse" in img.name.lower():
        skin_imgs.append((img.name, w, h, is_packed))
    elif w > 32 and h > 32:
        real_imgs.append((img.name, w, h, is_packed))

print(f"\nSummary:")
print(f"  Skin diffuse images: {len(skin_imgs)}")
for n, w, h, p in skin_imgs:
    print(f"    {n}: {w}x{h} packed={p}")
print(f"  Other real-sized images: {len(real_imgs)}")
print(f"  Empty/zero-size: {len(empty_imgs)}")
