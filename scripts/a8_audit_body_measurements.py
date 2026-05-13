"""Audit evaluated Body proportions for the vtuber-a8 avatar."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from statistics import mean

import bpy


TORSO_MATERIALS = {"Skin_Body"}
BODY_MATERIALS = {"Skin_Body", "Skin_Leg", "Skin_Arm"}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", default="Body")
    parser.add_argument("--out", required=True)
    parser.add_argument("--band-half-height", type=float, default=0.012)
    parser.add_argument("--torso-half-width", type=float, default=0.32)
    return parser.parse_args(argv)


def cm(value: float) -> float:
    return value * 100.0


def inches(value_m: float) -> float:
    return value_m * 39.37007874


def material_names_for_vertex(obj: bpy.types.Object) -> dict[int, set[str]]:
    slot_names = [slot.material.name if slot.material else "" for slot in obj.material_slots]
    vertex_materials: dict[int, set[str]] = defaultdict(set)
    for poly in obj.data.polygons:
        mat_name = slot_names[poly.material_index] if poly.material_index < len(slot_names) else ""
        for vi in poly.vertices:
            vertex_materials[vi].add(mat_name)
    return vertex_materials


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    points = sorted(set(points))
    if len(points) <= 1:
        return points

    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def perimeter(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        total += math.dist(p, q)
    return total


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_slice(points: list[tuple[float, float, float]]) -> dict[str, float | int]:
    if not points:
        return {
            "count": 0,
            "width_cm": 0.0,
            "depth_cm": 0.0,
            "circumference_cm": 0.0,
            "front_y_cm": 0.0,
            "back_y_cm": 0.0,
        }
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    hull = convex_hull([(p[0], p[1]) for p in points])
    return {
        "count": len(points),
        "width_cm": cm(max(xs) - min(xs)),
        "depth_cm": cm(max(ys) - min(ys)),
        "circumference_cm": cm(perimeter(hull)),
        "front_y_cm": cm(min(ys)),
        "back_y_cm": cm(max(ys)),
    }


def collect_slice(
    rows: list[dict],
    z: float,
    half_height: float,
    materials: set[str],
    torso_half_width: float | None,
) -> list[tuple[float, float, float]]:
    points = []
    for row in rows:
        if abs(row["z"] - z) > half_height:
            continue
        if not row["materials"].intersection(materials):
            continue
        if torso_half_width is not None and abs(row["x"]) > torso_half_width:
            continue
        points.append((row["x"], row["y"], row["z"]))
    return points


def scan_range(
    rows: list[dict],
    z_min: float,
    z_max: float,
    mode: str,
    half_height: float,
    materials: set[str],
    torso_half_width: float | None,
) -> dict:
    best = None
    steps = int(round((z_max - z_min) / 0.005))
    for i in range(steps + 1):
        z = z_min + i * 0.005
        points = collect_slice(rows, z, half_height, materials, torso_half_width)
        summary = summarize_slice(points)
        if summary["count"] < 12:
            continue
        candidate = {"z_m": z, **summary}
        if best is None:
            best = candidate
        elif mode == "max_circumference" and candidate["circumference_cm"] > best["circumference_cm"]:
            best = candidate
        elif mode == "min_circumference" and candidate["circumference_cm"] < best["circumference_cm"]:
            best = candidate
        elif mode == "max_width" and candidate["width_cm"] > best["width_cm"]:
            best = candidate
    return best or {"z_m": 0.0, **summarize_slice([])}


def estimate_us_bra_size(underbust_cm: float, bust_cm: float) -> dict[str, float | str]:
    under_in = underbust_cm / 2.54
    bust_in = bust_cm / 2.54
    band = int(round(under_in / 2.0) * 2)
    band = max(24, band)
    return {
        "underbust_in": under_in,
        "bust_in": bust_in,
        "rounded_band": band,
        "cup_delta_in": bust_in - band,
        "rough_us_size": size_for_band(bust_in, band),
        "common_band_equivalents": {
            str(common_band): size_for_band(bust_in, common_band)
            for common_band in (28, 30, 32)
        },
    }


def size_for_band(bust_in: float, band: int) -> str:
    diff = bust_in - band
    cups = [
        (0, "AA"),
        (1, "A"),
        (2, "B"),
        (3, "C"),
        (4, "D"),
        (5, "DD/E"),
        (6, "DDD/F"),
        (7, "G"),
        (8, "H"),
        (9, "I"),
        (10, "J"),
        (11, "K"),
        (12, "L"),
        (13, "M"),
        (14, "N"),
    ]
    cup = "AA"
    for threshold, label in cups:
        if diff >= threshold - 0.5:
            cup = label
    return f"{band}{cup}"


def main() -> None:
    args = parse_args()
    body = bpy.data.objects.get(args.body)
    if not body or body.type != "MESH":
        raise RuntimeError(f"Missing mesh object: {args.body}")

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    body_eval = body.evaluated_get(depsgraph)
    mesh = body_eval.to_mesh()
    mats_by_vertex = material_names_for_vertex(body)

    try:
        rows = []
        for vertex in mesh.vertices:
            world = body_eval.matrix_world @ vertex.co
            rows.append(
                {
                    "index": vertex.index,
                    "x": world.x,
                    "y": world.y,
                    "z": world.z,
                    "materials": mats_by_vertex.get(vertex.index, set()),
                }
            )

        body_rows = [r for r in rows if r["materials"].intersection(BODY_MATERIALS)]
        xs = [r["x"] for r in body_rows]
        ys = [r["y"] for r in body_rows]
        zs = [r["z"] for r in body_rows]

        bust = scan_range(
            rows,
            1.08,
            1.26,
            "max_circumference",
            args.band_half_height,
            TORSO_MATERIALS,
            args.torso_half_width,
        )
        underbust = scan_range(
            rows,
            1.00,
            1.10,
            "min_circumference",
            args.band_half_height,
            TORSO_MATERIALS,
            args.torso_half_width,
        )
        waist = scan_range(
            rows,
            0.86,
            1.02,
            "min_circumference",
            args.band_half_height,
            TORSO_MATERIALS,
            args.torso_half_width,
        )
        hip = scan_range(
            rows,
            0.72,
            0.92,
            "max_circumference",
            args.band_half_height,
            {"Skin_Body", "Skin_Leg"},
            args.torso_half_width,
        )
        shoulder = scan_range(
            rows,
            1.24,
            1.38,
            "max_width",
            args.band_half_height,
            {"Skin_Body", "Skin_Arm"},
            0.55,
        )

        report = {
            "blend_file": bpy.data.filepath,
            "object": body.name,
            "mesh_stats": {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
                "triangles": sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons),
            },
            "shape_keys": {
                block.name: block.value
                for block in body.data.shape_keys.key_blocks
                if block.value != 0.0
            }
            if body.data.shape_keys
            else {},
            "body_vertex_count": len(body_rows),
            "bbox_cm": {
                "height_z": cm(max(zs) - min(zs)) if zs else 0.0,
                "width_x": cm(max(xs) - min(xs)) if xs else 0.0,
                "depth_y": cm(max(ys) - min(ys)) if ys else 0.0,
                "min_z": cm(min(zs)) if zs else 0.0,
                "max_z": cm(max(zs)) if zs else 0.0,
            },
            "measurements": {
                "bust": bust,
                "underbust": underbust,
                "waist": waist,
                "hip": hip,
                "shoulder": shoulder,
            },
            "ratios": {
                "bust_to_waist": bust["circumference_cm"] / waist["circumference_cm"]
                if waist["circumference_cm"]
                else 0.0,
                "hip_to_waist": hip["circumference_cm"] / waist["circumference_cm"]
                if waist["circumference_cm"]
                else 0.0,
            },
            "bra_size_estimate": estimate_us_bra_size(
                underbust["circumference_cm"], bust["circumference_cm"]
            ),
            "notes": [
                "Circumferences use convex hulls of horizontal mesh slices, so they are costume/proportion estimates.",
                "The avatar is in a T pose; torso-half-width filtering is used to avoid arm contamination.",
            ],
        }
    finally:
        body_eval.to_mesh_clear()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    measurements = report["measurements"]
    bra = report["bra_size_estimate"]
    print("BODY_MEASUREMENTS_OK")
    print(f"  height_cm={report['bbox_cm']['height_z']:.1f}")
    print(f"  bust_cm={measurements['bust']['circumference_cm']:.1f}")
    print(f"  underbust_cm={measurements['underbust']['circumference_cm']:.1f}")
    print(f"  waist_cm={measurements['waist']['circumference_cm']:.1f}")
    print(f"  hip_cm={measurements['hip']['circumference_cm']:.1f}")
    print(f"  rough_us_bra={bra['rough_us_size']} delta_in={bra['cup_delta_in']:.1f}")


if __name__ == "__main__":
    main()
