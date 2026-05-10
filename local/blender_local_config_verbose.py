"""
Low-memory Blender local config.

Run from the repo root, for example:
    blender --background blender-output/toon_technique_trials.blend --python blender_local_config.py

In background mode this saves the opened .blend after applying scene/object settings.
In the Blender UI it applies settings to the current session and prints a report, but
does not auto-save the file.
"""

import bpy


TARGET_SAMPLES = 16
UNDO_MEMORY_LIMIT_MB = 256
MAX_SUBSURF_VIEWPORT_LEVEL = 1
PARTICLE_VIEWPORT_PERCENTAGE = 15


APPLIED = []
SKIPPED = []


def applied(message):
    APPLIED.append(message)


def skipped(message):
    SKIPPED.append(message)


def set_if_present(owner, attr, value, label):
    if not hasattr(owner, attr):
        skipped(f"{label}: missing property {attr}")
        return False
    old_value = getattr(owner, attr)
    setattr(owner, attr, value)
    applied(f"{label}: {attr} {old_value!r} -> {value!r}")
    return True


def set_samples():
    scene_count = 0
    sample_settings = 0
    for scene in bpy.data.scenes:
        scene_count += 1
        if hasattr(scene, "eevee"):
            eevee = scene.eevee
            sample_settings += int(set_if_present(eevee, "taa_samples", TARGET_SAMPLES, f"{scene.name} EEVEE viewport"))
            sample_settings += int(set_if_present(eevee, "taa_render_samples", TARGET_SAMPLES, f"{scene.name} EEVEE render"))
        else:
            skipped(f"{scene.name}: no EEVEE settings found")

        if hasattr(scene, "cycles"):
            cycles = scene.cycles
            sample_settings += int(set_if_present(cycles, "preview_samples", TARGET_SAMPLES, f"{scene.name} Cycles viewport"))
            sample_settings += int(set_if_present(cycles, "samples", TARGET_SAMPLES, f"{scene.name} Cycles render"))
        else:
            skipped(f"{scene.name}: no Cycles settings found")

    if scene_count == 0:
        skipped("Samples: no scenes found")
    elif sample_settings == 0:
        skipped("Samples: no sample settings were changed")


def set_undo_memory():
    edit_prefs = getattr(bpy.context.preferences, "edit", None)
    if not edit_prefs:
        skipped("Undo memory: edit preferences unavailable")
        return

    if not set_if_present(edit_prefs, "undo_memory_limit", UNDO_MEMORY_LIMIT_MB, "User preferences undo memory"):
        return

    try:
        bpy.ops.wm.save_userpref()
        applied("User preferences: saved undo memory limit")
    except Exception as exc:  # noqa: BLE001 - Blender preference save errors vary by environment.
        skipped(f"User preferences: could not save preferences ({exc})")


def reduce_subsurf_viewport_levels():
    modifiers_seen = 0
    modifiers_changed = 0
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type != "SUBSURF":
                continue
            modifiers_seen += 1
            if not hasattr(modifier, "levels"):
                skipped(f"{obj.name}.{modifier.name}: SUBSURF has no viewport levels property")
                continue
            old_level = modifier.levels
            new_level = min(old_level, MAX_SUBSURF_VIEWPORT_LEVEL)
            modifier.levels = new_level
            modifiers_changed += int(old_level != new_level)
            applied(f"{obj.name}.{modifier.name}: viewport levels {old_level} -> {new_level}")

    if modifiers_seen == 0:
        skipped("SUBSURF: no subdivision surface modifiers found")
    elif modifiers_changed == 0:
        applied(f"SUBSURF: {modifiers_seen} modifiers already at {MAX_SUBSURF_VIEWPORT_LEVEL} or lower")


def reduce_particle_viewport_percentage():
    systems_seen = 0
    for obj in bpy.data.objects:
        for particle_system in obj.particle_systems:
            systems_seen += 1
            settings = particle_system.settings
            if not hasattr(settings, "display_percentage"):
                skipped(f"{obj.name}.{particle_system.name}: no display_percentage property")
                continue
            old_percentage = settings.display_percentage
            settings.display_percentage = PARTICLE_VIEWPORT_PERCENTAGE
            applied(
                f"{obj.name}.{particle_system.name}: viewport display "
                f"{old_percentage}% -> {PARTICLE_VIEWPORT_PERCENTAGE}%"
            )

    if systems_seen == 0:
        skipped("Particles: no particle systems found")


def disable_viewport_compositor():
    viewports_seen = 0
    viewports_changed = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D":
                    continue
                viewports_seen += 1
                shading = getattr(space, "shading", None)
                if not shading or not hasattr(shading, "use_compositor"):
                    skipped(f"{screen.name}: View3D compositor setting unavailable")
                    continue
                old_mode = shading.use_compositor
                shading.use_compositor = "DISABLED"
                viewports_changed += int(old_mode != "DISABLED")
                applied(f"{screen.name}: viewport compositor {old_mode!r} -> 'DISABLED'")

    if viewports_seen == 0:
        skipped("Viewport compositor: no View3D spaces found")
    elif viewports_changed == 0:
        applied(f"Viewport compositor: {viewports_seen} View3D spaces already disabled")


def save_background_blend():
    if not bpy.app.background:
        skipped("Blend save: running in UI, file not auto-saved")
        return
    if not bpy.data.filepath:
        skipped("Blend save: no open .blend filepath")
        return
    try:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
        applied(f"Blend save: saved {bpy.data.filepath}")
    except Exception as exc:  # noqa: BLE001 - Blender save errors vary by environment.
        skipped(f"Blend save: could not save file ({exc})")


def print_report():
    print("")
    print("=== Blender local low-memory config report ===")
    print(f"Target samples: {TARGET_SAMPLES}")
    print(f"Undo memory limit: {UNDO_MEMORY_LIMIT_MB} MB")
    print(f"Max SUBSURF viewport level: {MAX_SUBSURF_VIEWPORT_LEVEL}")
    print(f"Particle viewport display: {PARTICLE_VIEWPORT_PERCENTAGE}%")
    print("")
    print("Applied:")
    for item in APPLIED:
        print(f"  - {item}")
    if not APPLIED:
        print("  - None")
    print("")
    print("Skipped:")
    for item in SKIPPED:
        print(f"  - {item}")
    if not SKIPPED:
        print("  - None")
    print("=== End Blender local low-memory config report ===")
    print("")


def main():
    set_samples()
    set_undo_memory()
    reduce_subsurf_viewport_levels()
    reduce_particle_viewport_percentage()
    disable_viewport_compositor()
    save_background_blend()
    print_report()


if __name__ == "__main__":
    main()
