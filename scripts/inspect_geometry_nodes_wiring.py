"""Inspect Geometry Nodes wiring on an object.

Read-only helper for checking whether a Set Position node has:
- Selection driven by Boolean Math / Compare nodes
- Offset driven by an outward X vector chain
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", default="Body_Sculpt")
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def node_label(node: bpy.types.Node) -> str:
    return f"{node.name} [{node.bl_idname}]"


def socket_links(socket: bpy.types.NodeSocket):
    return [
        {
            "from_node": link.from_node.name,
            "from_type": link.from_node.bl_idname,
            "from_socket": link.from_socket.name,
            "to_node": link.to_node.name,
            "to_type": link.to_node.bl_idname,
            "to_socket": link.to_socket.name,
        }
        for link in socket.links
    ]


def input_default(socket: bpy.types.NodeSocket):
    if not hasattr(socket, "default_value"):
        return None
    value = socket.default_value
    try:
        return list(value)
    except TypeError:
        return value


def upstream_nodes(group: bpy.types.NodeTree, target_node: bpy.types.Node, input_name: str, limit: int = 80):
    start_socket = target_node.inputs.get(input_name)
    if not start_socket:
        return []
    seen = set()
    result = []
    queue = deque(link.from_node for link in start_socket.links)
    while queue and len(result) < limit:
        node = queue.popleft()
        if node.name in seen:
            continue
        seen.add(node.name)
        item = {
            "name": node.name,
            "type": node.bl_idname,
            "label": node.label,
            "mute": getattr(node, "mute", None),
            "operation": getattr(node, "operation", None),
            "data_type": getattr(node, "data_type", None),
            "mode": getattr(node, "mode", None),
            "inputs": [
                {
                    "name": socket.name,
                    "default": input_default(socket),
                    "links": socket_links(socket),
                }
                for socket in node.inputs
            ],
            "outputs": [socket.name for socket in node.outputs],
        }
        result.append(item)
        for socket in node.inputs:
            for link in socket.links:
                queue.append(link.from_node)
    return result


def summarize_group(group: bpy.types.NodeTree):
    set_position_nodes = [
        node for node in group.nodes if node.bl_idname == "GeometryNodeSetPosition"
    ]
    compare_nodes = [
        node for node in group.nodes if node.bl_idname == "FunctionNodeCompare"
    ]
    boolean_nodes = [
        node for node in group.nodes if node.bl_idname == "FunctionNodeBooleanMath"
    ]
    math_nodes = [
        node for node in group.nodes if node.bl_idname == "ShaderNodeMath"
    ]

    return {
        "name": group.name,
        "node_count": len(group.nodes),
        "link_count": len(group.links),
        "all_links": [
            {
                "from_node": link.from_node.name,
                "from_type": link.from_node.bl_idname,
                "from_socket": link.from_socket.name,
                "to_node": link.to_node.name,
                "to_type": link.to_node.bl_idname,
                "to_socket": link.to_socket.name,
            }
            for link in group.links
        ],
        "set_position_nodes": [
            {
                "name": node.name,
                "mute": getattr(node, "mute", None),
                "selection_linked": bool(node.inputs.get("Selection") and node.inputs["Selection"].links),
                "position_linked": bool(node.inputs.get("Position") and node.inputs["Position"].links),
                "offset_linked": bool(node.inputs.get("Offset") and node.inputs["Offset"].links),
                "selection_upstream": upstream_nodes(group, node, "Selection"),
                "offset_upstream": upstream_nodes(group, node, "Offset"),
                "position_upstream": upstream_nodes(group, node, "Position"),
            }
            for node in set_position_nodes
        ],
        "compare_nodes": [
            {
                "name": node.name,
                "mute": getattr(node, "mute", None),
                "operation": getattr(node, "operation", None),
                "data_type": getattr(node, "data_type", None),
                "mode": getattr(node, "mode", None),
                "inputs": [
                    {
                        "name": socket.name,
                        "default": input_default(socket),
                        "linked": bool(socket.links),
                        "links": socket_links(socket),
                    }
                    for socket in node.inputs
                ],
            }
            for node in compare_nodes
        ],
        "boolean_nodes": [
            {
                "name": node.name,
                "mute": getattr(node, "mute", None),
                "operation": getattr(node, "operation", None),
                "inputs": [
                    {
                        "name": socket.name,
                        "default": input_default(socket),
                        "linked": bool(socket.links),
                        "links": socket_links(socket),
                    }
                    for socket in node.inputs
                ],
            }
            for node in boolean_nodes
        ],
        "math_nodes": [
            {
                "name": node.name,
                "mute": getattr(node, "mute", None),
                "operation": getattr(node, "operation", None),
                "inputs": [
                    {"name": socket.name, "default": input_default(socket), "linked": bool(socket.links)}
                    for socket in node.inputs
                ],
            }
            for node in math_nodes
        ],
    }


def main() -> None:
    args = parse_args()
    obj = bpy.data.objects.get(args.object)
    if not obj:
        raise RuntimeError(f"Object not found: {args.object}")

    groups = []
    for mod in obj.modifiers:
        if mod.type == "NODES" and mod.node_group:
            groups.append(
                {
                    "modifier": mod.name,
                    "modifier_show_viewport": mod.show_viewport,
                    "modifier_show_render": mod.show_render,
                    **summarize_group(mod.node_group),
                }
            )

    report = {
        "blend_file": bpy.data.filepath,
        "object": obj.name,
        "geometry_node_modifier_count": len(groups),
        "groups": groups,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("GEONODES_INSPECT_OK")
    print(f"  object={obj.name}")
    print(f"  geometry_node_modifier_count={len(groups)}")
    for group in groups:
        print(f"  modifier={group['modifier']} group={group['name']}")
        print(f"    set_position_nodes={len(group['set_position_nodes'])}")
        for node in group["set_position_nodes"]:
            print(
                "    "
                f"{node['name']}: selection_linked={node['selection_linked']} "
                f"offset_linked={node['offset_linked']} "
                f"position_linked={node['position_linked']}"
            )
        print(f"    compare_nodes={len(group['compare_nodes'])}")
        print(f"    boolean_nodes={len(group['boolean_nodes'])}")
        print(f"    math_nodes={len(group['math_nodes'])}")


if __name__ == "__main__":
    main()
