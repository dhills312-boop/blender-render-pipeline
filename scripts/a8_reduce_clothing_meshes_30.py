"""Create a lighter clothing-edit checkpoint by decimating clothing meshes ~30%.

This is for interactive Blender editing comfort, not final VRChat optimization.
It avoids the avatar body, face, hair, rig, and accessories.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v19_clothing_fit_prep.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v20_clothing_fit_light_30.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v20_clothing_fit_light_30_report.json"),
    )
    parser.add_argument("--ratio", type=float, default=0.70)
    return parser.parse_known_args()[0]


def find_visible_fit_clothing():
    targets = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        name = obj.name.lower()
        if not obj.name.startswith("FIT_"):
            continue
        if obj.hide_viewport:
            continue
        if not any(token in name for token in ("skirt", "underwear", "top", "streetwear")):
            continue
        targets.append(obj)
    return sorted(targets, key=lambda item: item.name)


def mesh_stats(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        tris = sum(len(poly.vertices) - 2 for poly in mesh.polygons)
        return {
            "verts": len(mesh.vertices),
            "polys": len(mesh.polygons),
            "tris": tris,
        }
    finally:
        eval_obj.to_mesh_clear()


def base_stats(obj):
    tris = sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
    return {
        "verts": len(obj.data.vertices),
        "polys": len(obj.data.polygons),
        "tris": tris,
    }


def apply_decimate(obj, ratio):
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    disabled_cloth = []
    for existing in obj.modifiers:
        if existing.type == "CLOTH":
            existing.show_viewport = False
            existing.show_render = False
            disabled_cloth.append(existing.name)

    if obj.data.shape_keys:
        return {
            "applied": False,
            "reason": "shape_keys_present",
            "disabled_cloth": disabled_cloth,
        }

    mod = obj.modifiers.new("A8_EDIT_Decimate_30pct_lighten", "DECIMATE")
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    mod.use_symmetry = False
    mod.show_viewport = True
    mod.show_render = False

    try:
        bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=0)
    except Exception:
        pass

    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        for remaining in obj.modifiers:
            if remaining.type == "CLOTH":
                remaining.point_cache.frame_start = bpy.context.scene.frame_start
                remaining.point_cache.frame_end = bpy.context.scene.frame_end
                try:
                    remaining.point_cache.reset()
                except Exception:
                    pass
        return {
            "applied": True,
            "reason": None,
            "disabled_cloth": disabled_cloth,
        }
    except Exception as exc:
        mod.show_viewport = True
        return {
            "applied": False,
            "reason": f"apply_failed: {exc}",
            "disabled_cloth": disabled_cloth,
        }


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "ratio": args.ratio,
        "targets": {},
        "skipped": {},
        "notes": [
            "This pass is for editing comfort, not final optimization.",
            "Only named FIT clothing meshes are targeted.",
            "v19 remains intact as the source checkpoint.",
        ],
    }

    targets = find_visible_fit_clothing()
    if not targets:
        report["skipped"]["FIT_*"] = "no_visible_fit_clothing_found"

    for obj in targets:
        name = obj.name
        before_base = base_stats(obj)
        before_eval = mesh_stats(obj)

        # Tiny objects are not worth decimating; keep small breast-panel/top helper clean.
        if before_base["verts"] < 1000:
            report["skipped"][name] = f"small_mesh:{before_base['verts']}_verts"
            continue

        result = apply_decimate(obj, args.ratio)
        after_base = base_stats(obj)
        after_eval = mesh_stats(obj)

        report["targets"][name] = {
            "before_base": before_base,
            "before_evaluated": before_eval,
            "after_base": after_base,
            "after_evaluated": after_eval,
            "decimate": result,
            "remaining_modifiers": [f"{m.name}:{m.type}" for m in obj.modifiers],
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
