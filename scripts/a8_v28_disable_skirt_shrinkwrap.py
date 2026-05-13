"""Disable live skirt shrinkwrap in the restored full preview file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(PROJECT / "a6_v27_full_preview_restored.blend"))
    parser.add_argument("--output", default=str(PROJECT / "a6_v28_full_preview_skirt_base.blend"))
    parser.add_argument(
        "--report",
        default=str(PROJECT / "audit_reports" / "a6_v28_full_preview_skirt_base_report.json"),
    )
    return parser.parse_known_args()[0]


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
        "changed": {},
        "notes": [
            "Disables live skirt shrinkwrap so viewport matches the rough/base skirt state.",
            "Does not alter skirt vertices.",
        ],
    }

    skirt = bpy.data.objects.get("FIT_PleatedSkirt_Shrinkwrap")
    if skirt is None:
        raise RuntimeError("FIT_PleatedSkirt_Shrinkwrap not found")

    before = [(m.name, m.type, m.show_viewport, m.show_render) for m in skirt.modifiers]
    for mod in skirt.modifiers:
        if mod.type in {"SHRINKWRAP", "CORRECTIVE_SMOOTH"}:
            mod.show_viewport = False
            mod.show_render = False
    after = [(m.name, m.type, m.show_viewport, m.show_render) for m in skirt.modifiers]

    report["changed"][skirt.name] = {
        "before": before,
        "after": after,
        "scale": list(skirt.scale),
        "verts": len(skirt.data.vertices),
        "polys": len(skirt.data.polygons),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == "__main__":
    main()
