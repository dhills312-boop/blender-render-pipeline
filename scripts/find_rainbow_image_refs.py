"""Find every material/node that references the rainbow normal map images
(Std_Skin_Body_Normal_anatomical, Nipples) so we can clean them up."""
import bpy

# Track suspects: any image whose name matches our failed-bake artifacts.
SUSPECT_IMAGE_NAMES = [
    "Std_Skin_Body_Normal_anatomical",
    "Nipples",
]

print(f"Looking for references to: {SUSPECT_IMAGE_NAMES}\n")

for mat in bpy.data.materials:
    if not mat.use_nodes or not mat.node_tree:
        continue
    hits = []
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image:
            if node.image.name in SUSPECT_IMAGE_NAMES:
                # Where does this node's output go?
                downstream = []
                for sock in node.outputs:
                    for link in sock.links:
                        downstream.append(
                            f"{link.to_node.type}('{link.to_node.name}').{link.to_socket.name}"
                        )
                hits.append({
                    "node_name": node.name,
                    "node_label": node.label,
                    "image": node.image.name,
                    "downstream_connections": downstream,
                })
    if hits:
        print(f"=== Material '{mat.name}' ===")
        for h in hits:
            print(f"  TEX_IMAGE '{h['node_name']}' (label: '{h['node_label']}')")
            print(f"    image: {h['image']}")
            for d in h["downstream_connections"]:
                print(f"    -> {d}")
        print()

# Also dump all images so we can see what data blocks exist.
print("\n=== ALL IMAGES IN .BLEND ===")
for img in bpy.data.images:
    if img.name in ("Render Result", "Viewer Node"):
        continue
    print(f"  {img.name:50s} {list(img.size)} packed={bool(img.packed_file)}")
