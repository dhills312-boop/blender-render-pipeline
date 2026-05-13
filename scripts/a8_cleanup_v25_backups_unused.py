"""Remove backup/intermediate objects and purge unused materials from v25.

This keeps the hidden full-avatar objects intact. It only deletes old clothing
backups, inspection helpers, cage guides, broken/manual chain attempts, and
unused datablocks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


DELETE_EXACT = {
    "FIT_StreetwearTop",
    "FIT_PleatedSkirt_Shrinkwrap_fitTest",
    "top_cloth",
    "bottome",
    "OUT_StreetwearTop",
    "OUT_PleatedSkirt",
    "OUT_Underwear",
    "INSPECT_top_cloth_source_side",
    "ACC_BridgeChain",
    "ACC_CollarChain",
    "ACC_HipChain",
}


DELETE_PREFIXES = (
    "SC_Guide_",
    "EDIT_",
)


DELETE_COLLECTIONS = {
    "A8_Backup_Hidden",
    "A8_Inspection_Objects",
    "A8_Manual_Chain_Backup",
    "A8_Original_Clothing_Backup",
    "A8_Rough_Top_Backup",
    "CLOTHING_FIT_PREP",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v25_top_cleanup_keep_skirt.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v26_clothing_cleanup_pruned.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v26_clothing_cleanup_pruned_report.json"),
    )
    return parser.parse_known_args()[0]


def should_delete_object(obj: bpy.types.Object) -> bool:
    if obj.name in DELETE_EXACT:
        return True
    return any(obj.name.startswith(prefix) for prefix in DELETE_PREFIXES)


def remove_object(obj: bpy.types.Object):
    data = getattr(obj, "data", None)
    info = {
        "name": obj.name,
        "type": obj.type,
        "data": data.name if data else None,
    }
    bpy.data.objects.remove(obj, do_unlink=True)
    return info


def count_unused_materials():
    return sum(1 for mat in bpy.data.materials if mat.users == 0)


def count_unused_images():
    return sum(1 for img in bpy.data.images if img.users == 0)


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    before = {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "collections": len(bpy.data.collections),
        "unused_materials": count_unused_materials(),
        "unused_images": count_unused_images(),
    }

    removed_objects = []
    for obj in list(bpy.data.objects):
        if should_delete_object(obj):
            removed_objects.append(remove_object(obj))

    removed_collections = []
    for coll in list(bpy.data.collections):
        if coll.name in DELETE_COLLECTIONS and len(coll.objects) == 0 and len(coll.children) == 0:
            removed_collections.append(coll.name)
            bpy.data.collections.remove(coll)

    # Purge orphaned meshes/materials/images left by backup object removal.
    for _ in range(8):
        try:
            bpy.ops.outliner.orphans_purge(do_recursive=True)
        except Exception:
            break

    after = {
        "objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "collections": len(bpy.data.collections),
        "unused_materials": count_unused_materials(),
        "unused_images": count_unused_images(),
    }

    # Preserve the current clothing visibility state.
    for name in ("Body", "CLEAN_StreetwearTop_v25", "FIT_PleatedSkirt_Shrinkwrap", "FIT_Underwear_Support.001"):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = False
            obj.hide_render = False

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "before": before,
        "after": after,
        "removed_objects": removed_objects,
        "removed_collections": removed_collections,
        "notes": [
            "Hidden full-avatar objects were preserved.",
            "Only backup/intermediate clothing helpers, inspection helpers, guide cages, and broken chain attempts were deleted.",
            "Unused materials/images/datablocks were purged after deletion.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
