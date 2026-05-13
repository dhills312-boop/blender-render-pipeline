"""Build a full preview file using accepted v25 clothing and fix body clipping.

The skirt/underwear are copied from their base rough-pass meshes rather than
baking live shrinkwrap. The top is copied from the cleaned v25 top. New FINAL_*
clothing objects are nudged outward from Body with a closest-point test so the
clothing touches/clears the body instead of clipping through it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


INPUT = PROJECT / "a6_v26_clothing_cleanup_pruned.blend"
OUTPUT = PROJECT / "a6_v29_full_clothing_contact.blend"
REPORT = PROJECT / "audit_reports" / "a6_v29_full_clothing_contact_report.json"


SOURCE_TO_FINAL = {
    "CLEAN_StreetwearTop_v25": "FINAL_StreetwearTop_Contact",
    "FIT_PleatedSkirt_Shrinkwrap": "FINAL_PleatedSkirt_Contact",
    "FIT_Underwear_Support.001": "FINAL_UnderwearSupport_Contact",
}


HIDE_EXACT = {
    "Body_Sculpt",
    "CLEAN_StreetwearTop_v25",
    "FIT_PleatedSkirt_Shrinkwrap",
    "FIT_Underwear_Support.001",
    "FIT_StreetwearTop",
    "FIT_PleatedSkirt_Shrinkwrap_fitTest",
    "OUT_StreetwearTop",
    "OUT_PleatedSkirt",
    "OUT_Underwear",
    "top_cloth",
    "bottome",
    "ACC_BridgeChain",
    "ACC_CollarChain",
    "ACC_HipChain",
}


HIDE_PREFIXES = (
    "WGT-",
    "WGTS_",
    "SC_Guide_",
    "EDIT_",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--target-gap", type=float, default=0.003)
    parser.add_argument("--max-search", type=float, default=0.045)
    parser.add_argument("--max-push", type=float, default=0.028)
    parser.add_argument("--passes", type=int, default=4)
    return parser.parse_known_args()[0]


def ensure_collection(name: str):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_viewport = False
    coll.hide_render = False
    return coll


def move_to_collection(obj, coll):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)


def copy_materials(src, dst):
    dst.data.materials.clear()
    for slot in src.material_slots:
        if slot.material:
            dst.data.materials.append(slot.material)


def should_hide(obj):
    if obj.name in HIDE_EXACT:
        return True
    return any(obj.name.startswith(prefix) for prefix in HIDE_PREFIXES)


def restore_avatar_visibility():
    for coll in bpy.data.collections:
        if coll.name.startswith("WGTS_"):
            coll.hide_viewport = True
            coll.hide_render = True
        else:
            coll.hide_viewport = False
            coll.hide_render = False

    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            obj.hide_viewport = False
            obj.hide_render = True
            continue
        hide = should_hide(obj)
        obj.hide_viewport = hide
        obj.hide_render = hide


def make_final_copy(src, final_name, coll):
    existing = bpy.data.objects.get(final_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    copy = src.copy()
    copy.data = src.data.copy()
    copy.animation_data_clear()
    copy.name = final_name
    copy.data.name = f"{final_name}_Mesh"
    copy.modifiers.clear()
    copy_materials(src, copy)
    coll.objects.link(copy)
    copy.hide_viewport = False
    copy.hide_render = False
    copy.show_name = True
    return copy


def build_body_bvh(body):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_body = body.evaluated_get(depsgraph)
    mesh = eval_body.to_mesh()
    verts = [eval_body.matrix_world @ v.co for v in mesh.vertices]
    polys = [[vi for vi in poly.vertices] for poly in mesh.polygons]
    bvh = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    eval_body.to_mesh_clear()
    return bvh


def signed_gap_to_body(bvh, world_co, max_search):
    hit = bvh.find_nearest(world_co, max_search)
    if hit is None or hit[0] is None:
        return None
    loc, normal, _index, dist = hit
    if normal.length == 0:
        return None
    normal.normalize()
    signed = (world_co - loc).dot(normal)
    return signed, normal, dist


def push_clothing_outside_body(obj, bvh, target_gap, max_search, max_push, passes):
    inv = obj.matrix_world.inverted()
    per_pass = []
    total_moved = 0
    max_move_seen = 0.0

    for _ in range(passes):
        moved = 0
        move_sum = 0.0
        max_move = 0.0
        for vert in obj.data.vertices:
            world = obj.matrix_world @ vert.co
            gap = signed_gap_to_body(bvh, world, max_search)
            if gap is None:
                continue
            signed, normal, _dist = gap
            if signed >= target_gap:
                continue
            amount = min(target_gap - signed, max_push)
            if amount <= 0:
                continue
            new_world = world + normal * amount
            vert.co = inv @ new_world
            moved += 1
            move_sum += amount
            max_move = max(max_move, amount)
        obj.data.update()
        per_pass.append(
            {
                "moved_vertices": moved,
                "mean_move": move_sum / moved if moved else 0.0,
                "max_move": max_move,
            }
        )
        total_moved += moved
        max_move_seen = max(max_move_seen, max_move)
        if moved == 0:
            break

    after_gaps = []
    for vert in obj.data.vertices:
        gap = signed_gap_to_body(bvh, obj.matrix_world @ vert.co, max_search)
        if gap is not None:
            after_gaps.append(gap[0])

    return {
        "verts": len(obj.data.vertices),
        "passes": per_pass,
        "total_moved_events": total_moved,
        "max_move_seen": max_move_seen,
        "after_min_signed_gap": min(after_gaps) if after_gaps else None,
        "after_vertices_under_target": sum(1 for gap in after_gaps if gap < target_gap),
        "after_checked_vertices": len(after_gaps),
    }


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
    restore_avatar_visibility()

    body = bpy.data.objects.get("Body")
    if body is None:
        raise RuntimeError("Body not found")
    body.hide_viewport = False
    body.hide_render = False

    coll = ensure_collection("FINAL_CLOTHING_CONTACT")
    final_objects = {}
    for src_name, final_name in SOURCE_TO_FINAL.items():
        src = bpy.data.objects.get(src_name)
        if src is None:
            raise RuntimeError(f"Missing clothing source: {src_name}")
        final = make_final_copy(src, final_name, coll)
        final_objects[final_name] = final
        src.hide_viewport = True
        src.hide_render = True

    bvh = build_body_bvh(body)
    contact = {}
    for final_name, obj in final_objects.items():
        # More conservative on skirt to preserve pleat shape.
        max_push = args.max_push * (0.55 if "Skirt" in final_name else 1.0)
        contact[final_name] = {
            "source_stats": mesh_stats(obj),
            "contact_repair": push_clothing_outside_body(
                obj,
                bvh,
                args.target_gap,
                args.max_search,
                max_push,
                args.passes,
            ),
            "final_stats": mesh_stats(obj),
        }

    visible_meshes = [
        obj.name
        for obj in bpy.data.objects
        if obj.type == "MESH" and not obj.hide_viewport
    ]

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "source_to_final": SOURCE_TO_FINAL,
        "target_gap": args.target_gap,
        "max_search": args.max_search,
        "max_push": args.max_push,
        "contact": contact,
        "visible_mesh_count": len(visible_meshes),
        "visible_meshes": visible_meshes,
        "notes": [
            "Uses v25/v26 accepted clothing sources.",
            "Skirt/underwear are copied from base rough-pass mesh state, not live shrinkwrap bake.",
            "Closest-point body contact repair moves clothing vertices outward only when under the target gap.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
