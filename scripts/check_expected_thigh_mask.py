"""Check expected Body_Sculpt thigh mask count from raw vertex positions."""

import bpy

obj = bpy.data.objects["Body_Sculpt"]
count = 0
examples = []
for vertex in obj.data.vertices:
    p = obj.matrix_world @ vertex.co
    if p.z > 0.45 and p.z < 0.94 and abs(p.x) < 0.08 and abs(p.y) < 0.16:
        count += 1
        if len(examples) < 5:
            examples.append((round(p.x, 4), round(p.y, 4), round(p.z, 4)))

print(f"EXPECTED_MASK_COUNT {count}")
print(f"EXPECTED_MASK_EXAMPLES {examples}")
