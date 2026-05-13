"""Audit likely viewport-cost sources in a vtuber-a8 blend."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", default=str(PROJECT / "a6_v20_clothing_fit_light_30.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v20_viewport_cost_audit.json"),
    )
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    return parser.parse_args(argv)


def image_bytes(img):
    try:
        w, h = img.size
        channels = img.channels or 4
        return int(w * h * channels)
    except Exception:
        return 0


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.blend)

    objects = list(bpy.data.objects)
    meshes = [o for o in objects if o.type == "MESH"]
    visible_meshes = [o for o in meshes if not o.hide_viewport]

    heavy_meshes = []
    for obj in meshes:
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        heavy_meshes.append(
            {
                "name": obj.name,
                "verts": len(obj.data.vertices),
                "polys": len(obj.data.polygons),
                "tris": tris,
                "hide_viewport": obj.hide_viewport,
                "hide_render": obj.hide_render,
                "modifiers": [f"{m.name}:{m.type}:view={m.show_viewport}" for m in obj.modifiers],
                "collections": [c.name for c in obj.users_collection],
            }
        )

    modifier_objects = []
    for obj in meshes:
        live = [m for m in obj.modifiers if m.show_viewport]
        if live:
            modifier_objects.append(
                {
                    "name": obj.name,
                    "hide_viewport": obj.hide_viewport,
                    "mods": [f"{m.name}:{m.type}" for m in live],
                    "verts": len(obj.data.vertices),
                }
            )

    report = {
        "blend": args.blend,
        "counts": {
            "objects": len(objects),
            "meshes": len(meshes),
            "visible_meshes": len(visible_meshes),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
            "collections": len(bpy.data.collections),
        },
        "modifiers_all": dict(Counter(m.type for o in objects for m in o.modifiers)),
        "modifiers_visible_objects": dict(Counter(m.type for o in visible_meshes for m in o.modifiers if m.show_viewport)),
        "top_meshes_by_vertices": sorted(heavy_meshes, key=lambda r: r["verts"], reverse=True)[:40],
        "visible_meshes_by_vertices": sorted(
            [r for r in heavy_meshes if not r["hide_viewport"]],
            key=lambda r: r["verts"],
            reverse=True,
        )[:40],
        "visible_modifier_objects": sorted(
            [r for r in modifier_objects if not r["hide_viewport"]],
            key=lambda r: r["verts"],
            reverse=True,
        )[:60],
        "largest_images": sorted(
            [
                {
                    "name": img.name,
                    "filepath": img.filepath,
                    "size": list(img.size),
                    "channels": img.channels,
                    "approx_bytes": image_bytes(img),
                }
                for img in bpy.data.images
            ],
            key=lambda r: r["approx_bytes"],
            reverse=True,
        )[:30],
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print("Top visible modifier objects:")
    for row in report["visible_modifier_objects"][:20]:
        print(row["name"], row["verts"], row["mods"])


if __name__ == "__main__":
    main()
