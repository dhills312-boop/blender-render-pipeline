"""Print the Skin_Body material node graph in v06 to diagnose the green tint."""
import bpy

mat = bpy.data.materials.get("Skin_Body")
if not mat:
    print("Skin_Body not found")
    raise SystemExit

nt = mat.node_tree
print("Skin_Body node graph:")
for n in nt.nodes:
    extra = ""
    if n.type == "TEX_IMAGE" and n.image:
        extra = (f"  image='{n.image.name}' "
                 f"colorspace='{n.image.colorspace_settings.name}'")
    elif n.type == "MIX":
        extra = f"  data_type={n.data_type} factor={n.inputs['Factor'].default_value}"
    elif n.type == "NORMAL_MAP":
        extra = f"  space={n.space} uv={n.uv_map}"
    print(f"  {n.type:20s} '{n.name}'{extra}")

# Find the BSDF and walk its Normal input back.
print("\nBSDF Normal chain:")
for n in nt.nodes:
    if n.type != "BSDF_PRINCIPLED":
        continue
    nin = n.inputs.get("Normal")
    if not nin or not nin.is_linked:
        print(f"  {n.name}: Normal not linked")
        continue
    print(f"  {n.name} <- {nin.links[0].from_node.type} '{nin.links[0].from_node.name}' "
          f"(socket: {nin.links[0].from_socket.name})")
    # Walk one hop back.
    src = nin.links[0].from_node
    for input_name, sock in [(s.name, s) for s in src.inputs]:
        if sock.is_linked:
            ln = sock.links[0]
            print(f"    {src.name}.{input_name} <- {ln.from_node.type} "
                  f"'{ln.from_node.name}' (socket: {ln.from_socket.name})")

# Also check if the new image got its colorspace set right.
print("\nAnatomical Normal image colorspace:")
img = bpy.data.images.get("Std_Skin_Body_Normal_anatomical")
if img:
    print(f"  image: {img.name}")
    print(f"  filepath: {img.filepath}")
    print(f"  colorspace: {img.colorspace_settings.name}")
else:
    print("  not found")
