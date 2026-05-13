"""Make the hidden top_cloth source visible next to the avatar for inspection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", default=str(PROJECT / "a6_v19_clothing_fit_prep.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v19_top_cloth_inspection_report.json"),
    )
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


def bounds_world(obj):
    if not obj.bound_box:
        return None
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return min_v, max_v


def make_inspection_material():
    mat = bpy.data.materials.get("A8_Inspection_Magenta")
    if mat is None:
        mat = bpy.data.materials.new("A8_Inspection_Magenta")
        mat.diffuse_color = (1.0, 0.15, 0.85, 1.0)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (1.0, 0.15, 0.85, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.4
    return mat


def main():
    args = parse_args()
    blend = Path(args.blend)
    report_path = Path(args.report)

    bpy.ops.wm.open_mainfile(filepath=str(blend))

    source = bpy.data.objects.get("top_cloth")
    if source is None:
        raise RuntimeError("top_cloth was not found in the blend")

    body = bpy.data.objects.get("Body")
    body_bounds = bounds_world(body) if body else None
    source_bounds = bounds_world(source)

    coll = ensure_collection("A8_Inspection_Objects")
    existing = bpy.data.objects.get("INSPECT_top_cloth_source_side")
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    inspect = source.copy()
    inspect.data = source.data.copy()
    inspect.animation_data_clear()
    inspect.name = "INSPECT_top_cloth_source_side"
    inspect.data.name = "INSPECT_top_cloth_source_side_Mesh"
    coll.objects.link(inspect)
    inspect.hide_viewport = False
    inspect.hide_render = False
    inspect.show_name = True
    inspect.show_in_front = True

    mat = make_inspection_material()
    inspect.data.materials.clear()
    inspect.data.materials.append(mat)

    # Keep the same transform as the visible source and just offset it sideways.
    # This avoids the imported clothing's odd internal coordinate scale.
    inspect.location.x = source.location.x + 0.75
    inspect.location.y = source.location.y
    inspect.location.z = source.location.z

    # Also unhide the original in its current location, but keep it named source.
    source.hide_viewport = False
    source.hide_render = True
    source.show_name = True

    report = {
        "blend": str(blend),
        "source_found": source.name,
        "inspection_copy": inspect.name,
        "inspection_location": list(inspect.location),
        "source_vertex_count": len(source.data.vertices),
        "source_polygon_count": len(source.data.polygons),
        "source_materials": [slot.material.name if slot.material else None for slot in source.material_slots],
        "note": "INSPECT_top_cloth_source_side is a raw visible copy placed beside the avatar.",
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))


if __name__ == "__main__":
    main()
