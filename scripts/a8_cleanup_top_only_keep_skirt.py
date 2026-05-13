"""Top-only cleanup pass from the user's rough clothing checkpoint.

Creates a new checkpoint where the shirt is baked and polished, while skirt and
underwear are left exactly as they were in the rough pass. This avoids baking
the skirt shrinkwrap state into a new mesh.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v23_manual_clothing_fit_rough.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v25_top_cleanup_keep_skirt.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v25_top_cleanup_keep_skirt_report.json"),
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


def bake_top(src, clean_name, coll):
    existing = bpy.data.objects.get(clean_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = src.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph, preserve_all_data_layers=True)
    clean = bpy.data.objects.new(clean_name, mesh)
    clean.matrix_world = src.matrix_world.copy()
    clean.show_name = True
    coll.objects.link(clean)
    copy_materials(src, clean)

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = clean
    clean.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    clean.select_set(False)
    return clean


def boundary_loops(bm):
    edges = [edge for edge in bm.edges if edge.is_boundary]
    edge_by_vert = defaultdict(list)
    for edge in edges:
        for vert in edge.verts:
            edge_by_vert[vert].append(edge)

    visited = set()
    loops = []
    for edge in edges:
        if edge in visited:
            continue
        loop_edges = []
        loop_verts = []
        current = edge
        current_vert = edge.verts[0]
        while current and current not in visited:
            visited.add(current)
            loop_edges.append(current)
            next_vert = current.other_vert(current_vert)
            loop_verts.append(current_vert)
            candidates = [e for e in edge_by_vert[next_vert] if e not in visited]
            current_vert = next_vert
            current = candidates[0] if candidates else None
        if current_vert not in loop_verts:
            loop_verts.append(current_vert)
        if len(loop_verts) >= 3:
            loops.append(loop_verts)
    return loops


def smooth_top_geometry(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    boundary_verts = {v for v in bm.verts if any(e.is_boundary for e in v.link_edges)}
    interior_verts = [v for v in bm.verts if v not in boundary_verts]

    # Smooth the whole shirt surface gently but keep boundary work separate.
    for _ in range(7):
        updates = {}
        for vert in interior_verts:
            neighbors = [edge.other_vert(vert) for edge in vert.link_edges]
            if not neighbors:
                continue
            avg = sum((n.co for n in neighbors), vert.co * 0.0) / len(neighbors)
            updates[vert] = vert.co.lerp(avg, 0.24)
        for vert, co in updates.items():
            vert.co = co

    loop_report = []
    for loop in boundary_loops(bm):
        xs = [v.co.x for v in loop]
        ys = [v.co.y for v in loop]
        zs = [v.co.z for v in loop]
        size = Vector((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
        loop_report.append({"verts": len(loop), "size": list(size)})

        # Smooth jagged open outlines along their own curve.
        for _ in range(10):
            updates = {}
            count = len(loop)
            for index, vert in enumerate(loop):
                prev_v = loop[(index - 1) % count]
                next_v = loop[(index + 1) % count]
                target = (prev_v.co + next_v.co) * 0.5
                updates[vert] = vert.co.lerp(target, 0.20)
            for vert, co in updates.items():
                vert.co = co

        # If this is a mostly horizontal hem/band edge, make it read straighter.
        if size.z < max(size.x, size.y) * 0.22:
            median_z = sorted(v.co.z for v in loop)[len(loop) // 2]
            for vert in loop:
                vert.co.z = vert.co.z * 0.55 + median_z * 0.45

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    for poly in mesh.polygons:
        poly.use_smooth = True
    return loop_report


def add_top_polish_modifiers(obj):
    corr = obj.modifiers.new("A8_TOP_CorrectiveSmooth_polish", "CORRECTIVE_SMOOTH")
    corr.factor = 0.20
    corr.iterations = 4
    corr.show_viewport = True
    corr.show_render = True

    weighted = obj.modifiers.new("A8_TOP_WeightedNormals", "WEIGHTED_NORMAL")
    weighted.keep_sharp = True
    weighted.weight = 50


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))

    clean_coll = ensure_collection("TOP_CLEANUP_KEEP_SKIRT")
    backup_coll = ensure_collection("A8_Rough_Top_Backup", hide=True)

    top = bpy.data.objects.get("FIT_StreetwearTop")
    if top is None or top.type != "MESH":
        raise RuntimeError("FIT_StreetwearTop was not found")

    clean = bake_top(top, "CLEAN_StreetwearTop_v25", clean_coll)
    before = mesh_stats(clean)
    loop_report = smooth_top_geometry(clean)
    add_top_polish_modifiers(clean)
    after = mesh_stats(clean)

    # Hide only the rough top. Leave skirt and underwear exactly as-is.
    top.hide_viewport = True
    top.hide_render = True
    for mod in top.modifiers:
        if mod.type in {"SHRINKWRAP", "CLOTH", "CORRECTIVE_SMOOTH"}:
            mod.show_viewport = False
            mod.show_render = False
    move_to_collection(top, backup_coll)

    for name in ("FIT_PleatedSkirt_Shrinkwrap", "FIT_Underwear_Support.001", "Body"):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_viewport = False
            obj.hide_render = False

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "top_source": "FIT_StreetwearTop",
        "top_clean": clean.name,
        "top_before": before,
        "top_after": after,
        "top_scale": list(clean.scale),
        "top_modifiers": [f"{m.name}:{m.type}:view={m.show_viewport}" for m in clean.modifiers],
        "boundary_loops": loop_report,
        "left_unmodified": [
            "FIT_PleatedSkirt_Shrinkwrap",
            "FIT_PleatedSkirt_Shrinkwrap_fitTest",
            "FIT_Underwear_Support.001",
        ],
        "notes": [
            "Only the top was baked and cleaned.",
            "Skirt and underwear were left as they existed in the rough pass.",
            "Rough FIT_StreetwearTop is hidden as backup, not deleted.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
