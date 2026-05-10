"""Re-import the original FBX (a6/fbx clean.fbx) with FBX's 'Use Anim'
disabled and 'Manual Orientation' off, into a fresh Blender scene.
Then dump every image data block's name + size + first-pixel-color so we
can see if the FBX has REAL skin diffuse textures vs the 128x128
placeholders we got in the .blend.

This is plan-mode-friendly: read-only investigation, doesn't write
anything to the project.
"""
import bpy
import os

fbx_path = "C:/Users/14047/Documents/VS Code Scripts/blender-render-pipeline/workspace/project/vtuber-a8/a6/fbx clean.fbx"

# Clear scene first.
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import FBX. Use_image_search may help find external textures too.
print(f"Importing: {fbx_path}")
print(f"  size: {os.path.getsize(fbx_path):,} bytes")

# Note: FBX importer in 4.5 is now an extension, but should still be
# accessible via bpy.ops.import_scene.fbx.
try:
    bpy.ops.import_scene.fbx(filepath=fbx_path, use_image_search=True)
except Exception as e:
    print(f"FBX import failed: {e}")
    raise SystemExit(1)

print(f"\n=== Imported. Scanning images ===")

skin_diffuse = []
all_imgs = []
for img in bpy.data.images:
    if img.name in ("Render Result", "Viewer Node"):
        continue
    w, h = img.size
    is_packed = bool(img.packed_file)
    all_imgs.append((img.name, w, h, is_packed))
    if "skin" in img.name.lower() and "diffuse" in img.name.lower():
        skin_diffuse.append((img.name, w, h, is_packed))

print(f"\nAll {len(all_imgs)} imported images, sorted by size:")
for n, w, h, p in sorted(all_imgs, key=lambda x: -(x[1]*x[2])):
    print(f"  {n:50s} {w}x{h:<6} packed={p}")

print(f"\nSKIN DIFFUSE specifically:")
for n, w, h, p in skin_diffuse:
    print(f"  {n}: {w}x{h} packed={p}")
