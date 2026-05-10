#!/usr/bin/env python3
"""Apply low-RAM local Blender settings for a 3GB machine."""

from __future__ import annotations

import bpy


scene = bpy.context.scene

if hasattr(scene, "eevee"):
    for attr, value in (("taa_render_samples", 16), ("taa_samples", 16)):
        if hasattr(scene.eevee, attr):
            setattr(scene.eevee, attr, value)

preferences = bpy.context.preferences
preferences.edit.undo_memory_limit = 256

subsurf = particles = 0
for obj in bpy.data.objects:
    for modifier in obj.modifiers:
        if modifier.type == "SUBSURF":
            modifier.levels = min(modifier.levels, 1)
            subsurf += 1
    for particle_system in obj.particle_systems:
        particle_system.settings.display_percentage = min(particle_system.settings.display_percentage, 20)
        particles += 1

if hasattr(scene, "compositing_node_group"):
    scene.compositing_node_group = None

print("[local_config] Low-RAM Blender settings applied")
print(f"[local_config] Undo memory: {preferences.edit.undo_memory_limit} MB")
print(f"[local_config] Subsurf viewport modifiers reduced: {subsurf}")
print(f"[local_config] Particle systems capped: {particles}")
