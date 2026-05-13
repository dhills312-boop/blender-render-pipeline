"""Restore full avatar visibility around the accepted clothing pass."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


HIDE_EXACT = {
    "Body_Sculpt",
    "FIT_StreetwearTop",
    "FIT_PleatedSkirt_Shrinkwrap_fitTest",
    "OUT_StreetwearTop",
    "OUT_PleatedSkirt",
    "OUT_Underwear",
    "top_cloth",
    "bottome",
    "INSPECT_top_cloth_source_side",
    "ACC_BridgeChain",
    "ACC_CollarChain",
    "ACC_HipChain",
}


HIDE_PREFIXES = (
    "WGT-",
    "WGTS_",
    "SC_Guide_",
    "EDIT_",
    "CLEAN_StreetwearTop_v24",
)


KEEP_EXACT = {
    "Body",
    "CLEAN_StreetwearTop_v25",
    "FIT_PleatedSkirt_Shrinkwrap",
    "FIT_Underwear_Support.001",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v26_clothing_cleanup_pruned.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v27_full_preview_restored.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v27_full_preview_restored_report.json"),
    )
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    return parser.parse_args(argv)


def should_hide(obj: bpy.types.Object) -> bool:
    if obj.name in HIDE_EXACT:
        return True
    if any(obj.name.startswith(prefix) for prefix in HIDE_PREFIXES):
        return True
    if obj.name.startswith("FIT_") and obj.name not in KEEP_EXACT:
        return True
    if obj.name.startswith("CLEAN_") and obj.name not in KEEP_EXACT:
        return True
    return False


def mesh_stats(obj):
    tris = sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
    return {
        "verts": len(obj.data.vertices),
        "polys": len(obj.data.polygons),
        "tris": tris,
    }


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    # Collection-level hidden flags from the workroom must be cleared, then
    # object visibility is controlled explicitly below.
    for coll in bpy.data.collections:
        if coll.name.startswith("WGTS_"):
            coll.hide_viewport = True
            coll.hide_render = True
        else:
            coll.hide_viewport = False
            coll.hide_render = False

    hidden = []
    shown = []
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            obj.hide_viewport = False
            obj.hide_render = True
            shown.append(obj.name)
            continue
        hide = should_hide(obj)
        obj.hide_viewport = hide
        obj.hide_render = hide
        if hide:
            hidden.append(obj.name)
            for mod in obj.modifiers:
                if mod.type in {"SHRINKWRAP", "CLOTH", "CORRECTIVE_SMOOTH"}:
                    mod.show_viewport = False
                    mod.show_render = False
        else:
            shown.append(obj.name)

    # Keep current accepted clothing visible.
    for name in KEEP_EXACT:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = False
            obj.hide_render = False

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "shown_count": len(shown),
        "hidden_count": len(hidden),
        "visible_meshes": [
            {
                "name": obj.name,
                **mesh_stats(obj),
                "modifiers": [f"{m.name}:{m.type}:view={m.show_viewport}" for m in obj.modifiers],
            }
            for obj in bpy.data.objects
            if obj.type == "MESH" and not obj.hide_viewport
        ],
        "intentionally_hidden": sorted(
            [name for name in hidden if name in HIDE_EXACT or name.startswith(("FIT_", "WGT-", "SC_Guide_"))]
        ),
        "notes": [
            "Restores full avatar visibility around v25 clothing.",
            "Broken/manual chain objects remain hidden for later manual placement.",
            "Body_Sculpt and rig widget meshes remain hidden.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
