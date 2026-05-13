"""Polish the user's manual clothing fit into a cleaned checkpoint.

The script preserves the rough FIT_* clothing as hidden backup, bakes the
current evaluated clothing result into CLEAN_* meshes, and applies light
geometry/normals cleanup. It is intentionally conservative.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy
import bmesh


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


TARGETS = {
    "FIT_StreetwearTop": {
        "clean_name": "CLEAN_StreetwearTop",
        "smooth_iterations": 5,
        "smooth_factor": 0.22,
        "corrective_factor": 0.18,
        "corrective_iterations": 3,
    },
    "FIT_PleatedSkirt_Shrinkwrap": {
        "clean_name": "CLEAN_PleatedSkirt",
        "smooth_iterations": 2,
        "smooth_factor": 0.08,
        "corrective_factor": 0.08,
        "corrective_iterations": 2,
    },
    "FIT_Underwear_Support.001": {
        "clean_name": "CLEAN_UnderwearSupport",
        "smooth_iterations": 3,
        "smooth_factor": 0.12,
        "corrective_factor": 0.10,
        "corrective_iterations": 2,
    },
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v23_manual_clothing_fit_rough.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v24_manual_clothing_cleanup.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v24_manual_clothing_cleanup_report.json"),
    )
    return parser.parse_known_args()[0]


def ensure_collection(name: str, hide: bool = False):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = hide
    coll.hide_render = hide
    return coll


def move_to_collection(obj, coll):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)


def mesh_stats(obj):
    tris = sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
    return {
        "verts": len(obj.data.vertices),
        "polys": len(obj.data.polygons),
        "tris": tris,
    }


def copy_materials(src, dst):
    dst.data.materials.clear()
    for slot in src.material_slots:
        if slot.material:
            dst.data.materials.append(slot.material)


def bake_evaluated_mesh(src, clean_name, coll):
    existing = bpy.data.objects.get(clean_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = src.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        eval_obj,
        depsgraph=depsgraph,
        preserve_all_data_layers=True,
    )
    clean = bpy.data.objects.new(clean_name, mesh)
    clean.matrix_world = src.matrix_world.copy()
    clean.show_name = True
    coll.objects.link(clean)
    copy_materials(src, clean)
    return clean


def gentle_bmesh_smooth(obj, iterations: int, factor: float):
    if iterations <= 0 or factor <= 0:
        return

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()

    boundary = {v for v in bm.verts if any(e.is_boundary for e in v.link_edges)}
    verts = [v for v in bm.verts if v not in boundary]

    for _ in range(iterations):
        new_positions = {}
        for vert in verts:
            neighbors = [e.other_vert(vert) for e in vert.link_edges]
            if not neighbors:
                continue
            avg = sum((n.co for n in neighbors), vert.co * 0.0) / len(neighbors)
            new_positions[vert] = vert.co.lerp(avg, factor)
        for vert, co in new_positions.items():
            vert.co = co

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def add_cleanup_modifiers(obj, factor: float, iterations: int):
    # Keep this as a live, removable polish layer.
    corr = obj.modifiers.new("A8_CLEAN_CorrectiveSmooth_light", "CORRECTIVE_SMOOTH")
    corr.factor = factor
    corr.iterations = iterations
    corr.show_render = True
    corr.show_viewport = True

    try:
        weighted = obj.modifiers.new("A8_CLEAN_WeightedNormals", "WEIGHTED_NORMAL")
        weighted.keep_sharp = True
        weighted.weight = 50
    except Exception:
        weighted = None

    for poly in obj.data.polygons:
        poly.use_smooth = True


def apply_scale_only(obj):
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.select_set(False)


def hide_live_fit_objects(backup):
    hidden = []
    for obj in bpy.data.objects:
        if obj.name.startswith("FIT_"):
            obj.hide_viewport = True
            obj.hide_render = True
            for mod in obj.modifiers:
                if mod.type in {"SHRINKWRAP", "CLOTH", "CORRECTIVE_SMOOTH"}:
                    mod.show_viewport = False
                    mod.show_render = False
            move_to_collection(obj, backup)
            hidden.append(obj.name)
    return hidden


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    clean_coll = ensure_collection("CLOTHING_CLEANUP")
    backup_coll = ensure_collection("A8_Rough_FIT_Backup", hide=True)

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "cleaned": {},
        "missing": [],
        "hidden_fit_objects": [],
        "notes": [
            "This is a visual cleanup checkpoint from the manual rough clothing fit.",
            "CLEAN_* meshes are baked from the evaluated FIT_* state.",
            "Live FIT_* objects are hidden as backup, not deleted.",
        ],
    }

    for src_name, settings in TARGETS.items():
        src = bpy.data.objects.get(src_name)
        if src is None or src.type != "MESH":
            report["missing"].append(src_name)
            continue

        clean = bake_evaluated_mesh(src, settings["clean_name"], clean_coll)
        before = mesh_stats(clean)
        gentle_bmesh_smooth(
            clean,
            settings["smooth_iterations"],
            settings["smooth_factor"],
        )
        apply_scale_only(clean)
        add_cleanup_modifiers(
            clean,
            settings["corrective_factor"],
            settings["corrective_iterations"],
        )
        after = mesh_stats(clean)

        report["cleaned"][clean.name] = {
            "source": src.name,
            "before": before,
            "after": after,
            "scale": list(clean.scale),
            "modifiers": [f"{m.name}:{m.type}:view={m.show_viewport}" for m in clean.modifiers],
            "settings": settings,
        }

    report["hidden_fit_objects"] = hide_live_fit_objects(backup_coll)

    body = bpy.data.objects.get("Body")
    if body:
        body.hide_viewport = False
        body.hide_render = False

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
