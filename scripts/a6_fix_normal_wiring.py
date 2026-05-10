"""Fix the green-wash issue caused by wiring the anatomical normal into
the Principled BSDF's Normal input, which conflicts with the CC4
rl_skin_shader group's existing Normal output.

Approach: Remove our Mix node + Normal Map node + Anatomical Image Texture
node injection. Then re-wire so the anatomical normal map goes INTO the
CC4 rl_skin_shader group's Normal input port (replacing or mixing with
the existing Std_Skin_Body_Normal feed).

Also: investigate the existing 'Nipples' texture node found in the graph.

Run:
    blender -b a6_v06_anatomy_done.blend -P a6_fix_normal_wiring.py -- \
        --out-blend <path> --report <path>
"""

import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--mix-factor", type=float, default=0.6)
    return p.parse_args(argv)


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    mat = bpy.data.materials.get("Skin_Body")
    if not mat or not mat.node_tree:
        print("ERROR: Skin_Body not found.")
        sys.exit(1)
    nt = mat.node_tree

    actions = []

    # 1. Find and remove our previous wiring artifacts:
    #    - The Mix node we labeled 'Anatomical Normal Mix' (or 'Mix' with vec type)
    #    - The Normal Map node feeding it
    #    - Restore the original BSDF Normal connection.
    bsdfs = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]
    if not bsdfs:
        print("ERROR: No Principled BSDF found.")
        sys.exit(1)
    bsdf = bsdfs[0]

    # Identify our injected nodes by label.
    nodes_to_remove = []
    anatomical_img_node = None
    for n in nt.nodes:
        if n.type == "MIX" and n.label in ("Anatomical Normal Mix", "Mix"):
            # Make sure it's our mix (vector type, factor 0.5).
            if n.data_type == "VECTOR":
                nodes_to_remove.append(n)
        if n.type == "NORMAL_MAP" and (
            n.label == "Anatomical Normal Map" or n.name == "Normal Map"
        ):
            nodes_to_remove.append(n)
        if n.type == "TEX_IMAGE" and n.image and (
            n.image.name == "Std_Skin_Body_Normal_anatomical"
        ):
            anatomical_img_node = n  # keep this — we'll re-wire

    print(f"\n[1] Will remove {len(nodes_to_remove)} previously-injected node(s):")
    for n in nodes_to_remove:
        print(f"    - {n.type} '{n.name}' (label: '{n.label}')")

    # Before removing, find what the BSDF Normal was originally connected to.
    # Mix.A was wired from rl_skin_shader group's Normal output. We want to
    # restore that direct connection.
    original_normal_source = None
    if bsdf.inputs["Normal"].is_linked:
        link = bsdf.inputs["Normal"].links[0]
        if link.from_node in nodes_to_remove:
            # Walk into the mix node to find what was on input 4 (A).
            mix = link.from_node
            if mix.type == "MIX":
                a_in = mix.inputs[4]  # vector A
                if a_in.is_linked:
                    original_normal_source = a_in.links[0].from_socket
                    print(f"\n[2] Original normal source: "
                          f"{original_normal_source.node.name}.{original_normal_source.name}")

    # Remove the mix and normal map nodes (but keep the image texture).
    for n in nodes_to_remove:
        node_type = n.type  # capture before remove
        nt.nodes.remove(n)
        actions.append(f"removed {node_type}")

    # Restore direct connection if we found one.
    if original_normal_source and bsdf.inputs["Normal"]:
        nt.links.new(original_normal_source, bsdf.inputs["Normal"])
        print(f"\n[3] Restored direct connection: "
              f"{original_normal_source.node.name} -> BSDF.Normal")
        actions.append("restored direct normal connection")

    # 4. Inspect the rl_skin_shader group to find a Normal *input*.
    skin_group = None
    for n in nt.nodes:
        if n.type == "GROUP" and "rl_skin_shader" in (n.node_tree.name if n.node_tree else ""):
            if "tiling" not in n.node_tree.name:
                skin_group = n
                break
    if skin_group:
        print(f"\n[4] Found CC4 skin shader group: '{skin_group.node_tree.name}'")
        normal_inputs = [s for s in skin_group.inputs if "normal" in s.name.lower()]
        print(f"    Normal-related inputs: {[s.name for s in normal_inputs]}")

    # 5. Find the existing CC4 Normal texture (Std_Skin_Body_Normal).
    cc4_normal_tex = None
    for n in nt.nodes:
        if n.type == "TEX_IMAGE" and n.image and (
            n.image.name == "Std_Skin_Body_Normal"
        ):
            cc4_normal_tex = n
            break
    if cc4_normal_tex:
        print(f"\n[5] CC4 base normal texture: '{cc4_normal_tex.name}'")
        # What was it connected to?
        for sock in cc4_normal_tex.outputs:
            for link in sock.links:
                print(f"    output '{sock.name}' -> "
                      f"{link.to_node.type} '{link.to_node.name}'.{link.to_socket.name}")

    # 6. Where to inject the anatomical normal:
    #    Option A: replace cc4_normal_tex's image with a baked combination
    #              (composite the anatomical normal over Std_Skin_Body_Normal
    #              externally, then point CC4 normal at the combined image).
    #    Option B: insert a Mix RGB between cc4_normal_tex and its destination.
    #    Option C: bypass CC4 group, wire anatomical_img -> Normal Map -> BSDF.Normal
    #              (lose CC4 base detail, get clean sculpt).
    #
    # I'll do Option C for now since it produces clean results — we lose the
    # base normal detail but gain proper rendering. We can switch to Option A
    # later if base detail matters.
    if anatomical_img_node:
        print(f"\n[6] Wiring anatomical normal directly to BSDF.Normal "
              f"(Option C — bypass CC4 group)")
        # Disconnect current BSDF.Normal.
        nin = bsdf.inputs["Normal"]
        for link in list(nin.links):
            nt.links.remove(link)

        # Add a fresh Normal Map node.
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.label = "Anatomical Normal Map (clean)"
        nm.location = (anatomical_img_node.location.x + 250,
                       anatomical_img_node.location.y)
        nt.links.new(anatomical_img_node.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], nin)
        actions.append("wired anatomical -> NormalMap -> BSDF.Normal")
    else:
        print("\n[6] Anatomical image node not found in graph — nothing to wire.")

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "actions": actions,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
