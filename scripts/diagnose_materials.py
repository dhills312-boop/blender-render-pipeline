"""Walk every material's node graph and report image/wiring health.

For each material:
- List every TEX_IMAGE node, with its image's name, size, and whether the source
  file is reachable on disk.
- Trace from BSDF/Output back to find the diffuse/normal/roughness inputs and
  whether they're connected.
- Flag materials where the surface BSDF input is not driven (would render flat).

Run via:
    blender -b <file>.blend -P diagnose_materials.py -- --report <path>
"""

import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def image_status(img):
    if not img:
        return {"name": None, "status": "no_image"}
    fp = bpy.path.abspath(img.filepath) if img.filepath else None
    on_disk = bool(fp and os.path.exists(fp))
    return {
        "name": img.name,
        "filepath": img.filepath,
        "abs_filepath": fp,
        "size": [img.size[0], img.size[1]],
        "channels": img.channels,
        "is_packed": bool(img.packed_file),
        "on_disk": on_disk,
        "has_pixels": img.has_data,
        "source": img.source,
    }


def find_output_node(nt):
    for n in nt.nodes:
        if n.type == "OUTPUT_MATERIAL" and n.is_active_output:
            return n
    for n in nt.nodes:
        if n.type == "OUTPUT_MATERIAL":
            return n
    return None


def trace_surface_input(nt):
    """Return info about what's connected to the active output Surface input."""
    out = find_output_node(nt)
    if not out:
        return {"output": None, "surface_connected": False}
    surface = out.inputs.get("Surface")
    if not surface or not surface.is_linked:
        return {"output": out.name, "surface_connected": False}
    src = surface.links[0].from_node
    return {
        "output": out.name,
        "surface_connected": True,
        "surface_driver_node_type": src.type,
        "surface_driver_node_name": src.name,
    }


def material_report(mat):
    info = {"name": mat.name, "use_nodes": mat.use_nodes}
    if not mat.use_nodes or not mat.node_tree:
        return info
    nt = mat.node_tree
    info["node_count"] = len(nt.nodes)
    info["surface_trace"] = trace_surface_input(nt)

    tex_nodes = [n for n in nt.nodes if n.type == "TEX_IMAGE"]
    info["tex_image_nodes"] = []
    for tn in tex_nodes:
        # Is this node's color/alpha output linked to anything?
        out_links = []
        for socket in tn.outputs:
            if socket.is_linked:
                for link in socket.links:
                    out_links.append({
                        "from_socket": socket.name,
                        "to_node": link.to_node.name,
                        "to_node_type": link.to_node.type,
                        "to_socket": link.to_socket.name,
                    })
        info["tex_image_nodes"].append({
            "node_name": tn.name,
            "image": image_status(tn.image),
            "outgoing_links": out_links,
        })

    # Quick health flags.
    info["health_flags"] = []
    if not info["surface_trace"]["surface_connected"]:
        info["health_flags"].append("surface_input_disconnected")
    if tex_nodes and not any(
        any(l for l in n["outgoing_links"]) for n in info["tex_image_nodes"]
    ):
        info["health_flags"].append("all_tex_image_nodes_orphaned")
    if any(
        n["image"]["status"] == "no_image" for n in info["tex_image_nodes"]
        if "status" in n["image"]
    ):
        info["health_flags"].append("tex_image_node_with_no_image")
    missing_files = [
        n["image"]["name"] for n in info["tex_image_nodes"]
        if n["image"].get("on_disk") is False
        and n["image"].get("name") is not None
    ]
    if missing_files:
        info["health_flags"].append("missing_files_on_disk")
        info["missing_files"] = missing_files

    return info


def main():
    args = parse_args()

    report = {
        "blend_file": bpy.data.filepath,
        "materials": [],
        "summary": {},
    }

    used_materials = set()
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            if slot.material:
                used_materials.add(slot.material.name)

    for mat in bpy.data.materials:
        info = material_report(mat)
        info["is_used_in_scene"] = mat.name in used_materials
        report["materials"].append(info)

    flagged = [m for m in report["materials"] if m.get("health_flags")]
    print(f"Total materials: {len(report['materials'])}")
    print(f"Used in scene:   {len(used_materials)}")
    print(f"Flagged:         {len(flagged)}")
    print()

    # Concise stdout summary.
    for m in report["materials"]:
        if not m.get("is_used_in_scene"):
            continue
        flags = m.get("health_flags", [])
        flag_str = (" | " + ", ".join(flags)) if flags else ""
        surface = m.get("surface_trace", {})
        driver = surface.get("surface_driver_node_type", "—")
        tex_count = len(m.get("tex_image_nodes", []))
        on_disk = sum(
            1 for n in m.get("tex_image_nodes", [])
            if n["image"].get("on_disk")
        )
        print(f"  {m['name']:30s} surface=>{driver:20s} "
              f"tex={tex_count:2d} (on_disk={on_disk}){flag_str}")

    report["summary"] = {
        "total_materials": len(report["materials"]),
        "used_in_scene": len(used_materials),
        "flagged_count": len(flagged),
        "flagged_names": [m["name"] for m in flagged],
    }

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nREPORT: {args.report}")


if __name__ == "__main__":
    main()
