#!/usr/bin/env python3
"""Print a compact inventory of the active Blender scene."""

import bpy


scene = bpy.context.scene
print(f"FRAME {scene.frame_current} RANGE {scene.frame_start}-{scene.frame_end}")

print("COLLECTIONS")
for collection in bpy.data.collections:
    print(f"{collection.name} objects={len(collection.objects)} children={len(collection.children)}")

print("OBJECTS")
for obj in bpy.data.objects:
    collections = ",".join(collection.name for collection in obj.users_collection)
    print(f"{obj.name} type={obj.type} collections={collections}")
