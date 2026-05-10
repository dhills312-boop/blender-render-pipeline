"""Install VTuber-project addons + register asset library in Blender 4.5.

Copies Simplicage and SpeedRetopo into the user addons folder, enables them,
and registers Asset_Addon_Library as a Blender Asset Library entry so the
Sanctus decals, SuperSkin alphas, and HairCards show up in the Asset Browser.

Run via:
    blender -b -P setup_vtuber_addons.py
"""

import os
import shutil
import sys

import bpy
import addon_utils


PROJECT_ROOT = (
    "C:/Users/14047/Documents/VS Code Scripts/blender-render-pipeline"
)
ASSET_LIB_DIR = os.path.join(PROJECT_ROOT, "Asset_Addon_Library")

ADDON_SOURCES = {
    "simplicage": os.path.join(ASSET_LIB_DIR, "simplicage"),
    "speedretopo": os.path.join(
        ASSET_LIB_DIR, "speedretopo_v_0_3_8_blender_4_4_3", "speedretopo"
    ),
    "Sanctus-Library": os.path.join(
        ASSET_LIB_DIR, "Sanctus-Library", "Sanctus-Library"
    ),
    # CC/iC Blender Tools — interprets Reallusion CC4 shader node groups so
    # CC4-exported models render correctly without rebuilding the materials.
    "cc_blender_tools": os.path.join(ASSET_LIB_DIR, "cc_blender_tools-2_4_0"),
}

USER_ADDONS_DIR = os.path.join(
    os.environ["APPDATA"],
    "Blender Foundation", "Blender", "4.5", "scripts", "addons",
)

ASSET_LIBRARY_NAME = "VTuber_Asset_Library"


def install_addon(name, src):
    if not os.path.isdir(src):
        print(f"SKIP {name}: source not found at {src}")
        return False
    dst = os.path.join(USER_ADDONS_DIR, name)
    if os.path.isdir(dst):
        print(f"  {name}: removing existing install at {dst}")
        shutil.rmtree(dst)
    print(f"  {name}: copying {src} -> {dst}")
    shutil.copytree(src, dst)
    return True


def enable_addon(module_name):
    try:
        addon_utils.enable(module_name, default_set=True, persistent=True)
        print(f"  enabled: {module_name}")
        return True
    except Exception as e:
        print(f"  FAILED to enable {module_name}: {e}")
        return False


def register_asset_library():
    prefs = bpy.context.preferences
    libs = prefs.filepaths.asset_libraries
    existing = [lib for lib in libs if lib.name == ASSET_LIBRARY_NAME]
    if existing:
        print(f"  asset lib already registered: {ASSET_LIBRARY_NAME}")
        # Update the path in case it moved.
        existing[0].path = ASSET_LIB_DIR
        return
    bpy.ops.preferences.asset_library_add(directory=ASSET_LIB_DIR)
    new_lib = libs[-1]
    new_lib.name = ASSET_LIBRARY_NAME
    print(f"  registered asset lib: {ASSET_LIBRARY_NAME} -> {ASSET_LIB_DIR}")


def main():
    os.makedirs(USER_ADDONS_DIR, exist_ok=True)

    print(f"USER ADDONS DIR: {USER_ADDONS_DIR}")
    print(f"ASSET LIB DIR:   {ASSET_LIB_DIR}")

    # Step 1: copy addons.
    print("\n[1/3] Installing addons...")
    for name, src in ADDON_SOURCES.items():
        install_addon(name, src)

    # Refresh Blender's addon scan so newly-copied modules are visible.
    addon_utils.modules_refresh()

    # Step 2: enable them.
    print("\n[2/3] Enabling addons...")
    for name in ADDON_SOURCES:
        enable_addon(name)

    # Step 3: register asset library entry.
    print("\n[3/3] Registering asset library...")
    register_asset_library()

    # Persist preferences so the user's normal Blender session sees it.
    bpy.ops.wm.save_userpref()
    print("\nUser preferences saved.")
    print("DONE")


if __name__ == "__main__":
    main()
