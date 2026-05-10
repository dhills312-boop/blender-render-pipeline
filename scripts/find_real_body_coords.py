"""Find the actual world-space coordinate ranges of the Body mesh,
broken down by visual region heuristics that don't depend on my assumed
absolute coordinates.

Output: for the Body mesh, the world-space bounding box, and a
percentage-based region split (top 10% z-range = head, etc.) so we can
see where chest is in this model's actual coordinate system."""

import sys
import bpy

body = bpy.data.objects.get("Body")
if not body:
    print("No Body")
    sys.exit(1)

# Collect all world-space verts.
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
xs = [v.x for v in verts_world]
ys = [v.y for v in verts_world]
zs = [v.z for v in verts_world]

print(f"Body verts: {len(verts_world)}")
print(f"X range (left-right): [{min(xs):.4f}, {max(xs):.4f}]  width={max(xs)-min(xs):.4f}")
print(f"Y range (front-back): [{min(ys):.4f}, {max(ys):.4f}]  depth={max(ys)-min(ys):.4f}")
print(f"Z range (down-up):    [{min(zs):.4f}, {max(zs):.4f}]  height={max(zs)-min(zs):.4f}")

z_min = min(zs)
z_max = max(zs)
z_range = z_max - z_min

# Height-relative regions (0% = feet, 100% = top of head).
# Chest is roughly 75-85% up from the floor on a standing T-pose model.
chest_top_z = z_min + z_range * 0.85
chest_bot_z = z_min + z_range * 0.75
print(f"\nIf chest is 75-85% up from floor:")
print(f"  chest Z range: [{chest_bot_z:.4f}, {chest_top_z:.4f}]")

# Front (most negative Y) bound for chest area.
y_front = min(ys)
y_back = max(ys)
y_range = y_back - y_front
y_chest_front = y_front + y_range * 0.0   # full forward
y_chest_max = y_front + y_range * 0.5     # only front half

# X bound: chest is within central 40% of width.
x_min = min(xs)
x_max = max(xs)
x_center = (x_min + x_max) / 2
x_half_width = (x_max - x_min) * 0.20  # 40% total = 20% each side of center

print(f"\nProposed chest filter:")
print(f"  Z in [{chest_bot_z:.4f}, {chest_top_z:.4f}]")
print(f"  Y in [{y_chest_front:.4f}, {y_chest_max:.4f}] (front half)")
print(f"  X in [{x_center - x_half_width:.4f}, {x_center + x_half_width:.4f}]")

# How many verts match this filter?
chest_count = 0
chest_z_min = float('inf')
chest_z_max = float('-inf')
for v in verts_world:
    if (chest_bot_z <= v.z <= chest_top_z
            and y_chest_front <= v.y <= y_chest_max
            and x_center - x_half_width <= v.x <= x_center + x_half_width):
        chest_count += 1
        chest_z_min = min(chest_z_min, v.z)
        chest_z_max = max(chest_z_max, v.z)

print(f"\n  matches: {chest_count} verts")
print(f"  chest verts actual Z range: [{chest_z_min:.4f}, {chest_z_max:.4f}]")
