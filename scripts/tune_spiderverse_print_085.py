#!/usr/bin/env python3
"""Tune LO_084 into a more visible but still restrained Spider-Verse print pass."""

from __future__ import annotations

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
LIFT_OFF = ROOT / "workspace" / "project" / "blender-output" / "lift-off"
INPUT_BLEND = LIFT_OFF / "LO_084_spiderverse_tuned_print.blend"
OUTPUT_BLEND = LIFT_OFF / "LO_085_spiderverse_visible_halftone.blend"


def set_input(node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket is None:
        print(f"[LO_085] Missing input {node.name!r}.{name!r}")
        return
    socket.default_value = value
    print(f"[LO_085] {node.name}.{name} = {value}")


def set_ramp(node, stops: list[tuple[int, float, tuple[float, float, float, float] | None]]) -> None:
    ramp = getattr(node, "color_ramp", None)
    if ramp is None:
        print(f"[LO_085] Missing color ramp on {node.name!r}")
        return
    for index, position, color in stops:
        if index >= len(ramp.elements):
            print(f"[LO_085] Missing ramp element {index} on {node.name!r}")
            continue
        ramp.elements[index].position = position
        if color is not None:
            ramp.elements[index].color = color
    print(f"[LO_085] Tuned ramp {node.name}")


def tune_body(material) -> None:
    nodes = material.node_tree.nodes

    dot_screen = nodes.get("LO_083 local color Euclidean dot screen")
    if dot_screen:
        set_input(dot_screen, "Scale", 118.0)

    dot_ramp = nodes.get("LO_083 local color dot size ramp")
    if dot_ramp:
        set_ramp(
            dot_ramp,
            [
                (0, 0.018, (1.0, 1.0, 1.0, 1.0)),
                (1, 0.034, (0.0, 0.0, 0.0, 1.0)),
            ],
        )

    shadow_mask = nodes.get("LO_083 shadow/midtone print mask")
    if shadow_mask:
        set_ramp(
            shadow_mask,
            [
                (0, 0.32, (1.0, 1.0, 1.0, 1.0)),
                (1, 0.66, (0.0, 0.0, 0.0, 1.0)),
            ],
        )

    dot_limit = nodes.get("LO_083 local dots only in midtone shadow")
    if dot_limit:
        set_input(dot_limit, "Fac", 0.36)

    dot_ink = nodes.get("LO_083 local-color dot ink")
    if dot_ink:
        set_input(dot_ink, "Fac", 0.46)

    for index, scale, high in ((1, 112.0, 0.030), (2, 104.0, 0.024)):
        bleed_screen = nodes.get(f"LO_083 magenta bleed {index} Euclidean dot screen")
        if bleed_screen:
            set_input(bleed_screen, "Scale", scale)

        bleed_ramp = nodes.get(f"LO_083 magenta bleed {index} dot size ramp")
        if bleed_ramp:
            set_ramp(
                bleed_ramp,
                [
                    (0, 0.014, (1.0, 1.0, 1.0, 1.0)),
                    (1, high, (0.0, 0.0, 0.0, 1.0)),
                ],
            )


def main() -> None:
    if not INPUT_BLEND.exists():
        raise FileNotFoundError(INPUT_BLEND)

    bpy.ops.wm.open_mainfile(filepath=str(INPUT_BLEND))

    body = bpy.data.materials.get("Ch03_Body")
    if body is None or body.node_tree is None:
        raise RuntimeError("Ch03_Body material was not found")

    tune_body(body)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
    print(f"[LO_085] Saved {OUTPUT_BLEND}")


if __name__ == "__main__":
    main()
