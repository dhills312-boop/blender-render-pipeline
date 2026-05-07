#!/usr/bin/env python3
"""Tune the LO_083 Spider-Verse print pass into a lighter LO_084 pass."""

from __future__ import annotations

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
LIFT_OFF = ROOT / "workspace" / "project" / "blender-output" / "lift-off"
INPUT_BLEND = LIFT_OFF / "LO_083_spiderverse_downloaded_recipe.blend"
OUTPUT_BLEND = LIFT_OFF / "LO_084_spiderverse_tuned_print.blend"


def node_input(node, name: str):
    socket = node.inputs.get(name)
    if socket is None:
        print(f"[LO_084] Missing input {node.name!r}.{name!r}")
    return socket


def set_input(node, name: str, value) -> None:
    socket = node_input(node, name)
    if socket is None:
        return
    socket.default_value = value
    print(f"[LO_084] {node.name}.{name} = {value}")


def set_ramp(node, stops: list[tuple[int, float, tuple[float, float, float, float] | None]]) -> None:
    ramp = getattr(node, "color_ramp", None)
    if ramp is None:
        print(f"[LO_084] Missing color ramp on {node.name!r}")
        return
    for index, position, color in stops:
        if index >= len(ramp.elements):
            print(f"[LO_084] Missing ramp element {index} on {node.name!r}")
            continue
        ramp.elements[index].position = position
        if color is not None:
            ramp.elements[index].color = color
    print(f"[LO_084] Tuned ramp {node.name}")


def tune_material(material_name: str, *, body: bool = False, roof: bool = False) -> None:
    material = bpy.data.materials.get(material_name)
    if material is None or material.node_tree is None:
        return

    nodes = material.node_tree.nodes

    if body:
        dot_screen = nodes.get("LO_083 local color Euclidean dot screen")
        if dot_screen:
            set_input(dot_screen, "Scale", 132.0)

        dot_ramp = nodes.get("LO_083 local color dot size ramp")
        if dot_ramp:
            set_ramp(
                dot_ramp,
                [
                    (0, 0.014, (1.0, 1.0, 1.0, 1.0)),
                    (1, 0.026, (0.0, 0.0, 0.0, 1.0)),
                ],
            )

        shadow_mask = nodes.get("LO_083 shadow/midtone print mask")
        if shadow_mask:
            set_ramp(
                shadow_mask,
                [
                    (0, 0.28, (1.0, 1.0, 1.0, 1.0)),
                    (1, 0.56, (0.0, 0.0, 0.0, 1.0)),
                ],
            )

        dot_limit = nodes.get("LO_083 local dots only in midtone shadow")
        if dot_limit:
            set_input(dot_limit, "Fac", 0.12)

        dot_ink = nodes.get("LO_083 local-color dot ink")
        if dot_ink:
            set_input(dot_ink, "Fac", 0.34)

        hatch_ink = nodes.get("LO_083 local dark hatch ink")
        if hatch_ink:
            set_input(hatch_ink, "Fac", 0.52)

        hatch_mask = nodes.get("LO_083 hatch constrained by downloaded shadow mask")
        if hatch_mask:
            set_input(hatch_mask, "Fac", 0.48)

        for index, scale in ((1, 126.0), (2, 112.0)):
            bleed_screen = nodes.get(f"LO_083 magenta bleed {index} Euclidean dot screen")
            if bleed_screen:
                set_input(bleed_screen, "Scale", scale)

            bleed_ramp = nodes.get(f"LO_083 magenta bleed {index} dot size ramp")
            if bleed_ramp:
                set_ramp(
                    bleed_ramp,
                    [
                        (0, 0.010, (1.0, 1.0, 1.0, 1.0)),
                        (1, 0.020 if index == 1 else 0.016, (0.0, 0.0, 0.0, 1.0)),
                    ],
                )

    if roof:
        hatch_ink = nodes.get("LO_083 local dark hatch ink")
        if hatch_ink:
            set_input(hatch_ink, "Fac", 0.58)

        hatch_mask = nodes.get("LO_083 hatch constrained by downloaded shadow mask")
        if hatch_mask:
            set_input(hatch_mask, "Fac", 0.62)


def main() -> None:
    if not INPUT_BLEND.exists():
        raise FileNotFoundError(INPUT_BLEND)

    bpy.ops.wm.open_mainfile(filepath=str(INPUT_BLEND))

    tuned_materials = 0
    for material in bpy.data.materials:
        name = material.name.lower()
        if material.name == "Ch03_Body":
            tune_material(material.name, body=True)
            tuned_materials += 1
        elif "roof" in name:
            tune_material(material.name, roof=True)
            tuned_materials += 1

    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
    print(f"[LO_084] Saved {OUTPUT_BLEND}")
    print(f"[LO_084] Tuned {tuned_materials} material(s)")


if __name__ == "__main__":
    main()
