"""Dump Scalp1_Transparency material's node graph to understand what's
making the head render rainbow."""
import bpy

mat_names = ["Scalp1_Transparency", "Eye_Occlusion_L", "Eye_Occlusion_R",
             "Eyelash", "Eye_L", "Eye_R", "Cornea_L", "Cornea_R",
             "Tearline_L", "Tearline_R"]

for mat_name in mat_names:
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        print(f"\n[{mat_name}] NOT FOUND")
        continue
    if not mat.use_nodes:
        print(f"\n[{mat_name}] use_nodes=False")
        continue
    nt = mat.node_tree
    print(f"\n=== {mat_name} ({len(nt.nodes)} nodes) ===")

    # Find output and walk back from Surface input.
    out = None
    for n in nt.nodes:
        if n.type == "OUTPUT_MATERIAL" and n.is_active_output:
            out = n
            break
    if not out:
        for n in nt.nodes:
            if n.type == "OUTPUT_MATERIAL":
                out = n
                break

    if out:
        surface = out.inputs.get("Surface")
        if surface and surface.is_linked:
            src = surface.links[0].from_node
            print(f"  Surface <- {src.type} '{src.name}'")
        else:
            print(f"  Surface: NOT LINKED (this is why it renders weird)")

    # List all texture nodes and what they point at.
    print(f"  TEX_IMAGE nodes:")
    for n in nt.nodes:
        if n.type == "TEX_IMAGE":
            img = n.image.name if n.image else "(none)"
            cs = n.image.colorspace_settings.name if n.image else "—"
            connected = any(s.is_linked for s in n.outputs)
            print(f"    '{n.name}' label='{n.label}' image='{img}' "
                  f"cs='{cs}' connected={connected}")
