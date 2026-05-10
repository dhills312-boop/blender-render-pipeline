"""Quick dump of render-related state for debugging silhouette issue."""

import bpy

sc = bpy.context.scene
print("=" * 60)
print(f"Engine: {sc.render.engine}")
print(f"Filter: {sc.render.image_settings.color_mode}")
print(f"View Transform: {sc.view_settings.view_transform}")
print(f"Look: {sc.view_settings.look}")
print(f"Exposure: {sc.view_settings.exposure}")
print(f"Gamma: {sc.view_settings.gamma}")
print(f"Film Transparent: {sc.render.film_transparent}")
print(f"Use Compositor: {sc.render.use_compositing}")

# World
world = sc.world
print(f"\nWorld: {world.name if world else 'NONE'}")
if world and world.use_nodes:
    bg = world.node_tree.nodes.get("Background")
    if bg:
        print(f"  bg color: {list(bg.inputs['Color'].default_value)}")
        print(f"  bg strength: {bg.inputs['Strength'].default_value}")

# Compositor
print(f"\nCompositor enabled: {sc.use_nodes}")
if sc.use_nodes and sc.node_tree:
    print(f"  compositor node count: {len(sc.node_tree.nodes)}")
    for n in sc.node_tree.nodes:
        print(f"    {n.type:30s} {n.name}")

# View Layer
vl = sc.view_layers[0]
print(f"\nView Layer: {vl.name}")
print(f"  use: {vl.use}")

# Camera
print(f"\nCamera: {sc.camera.name if sc.camera else 'NONE'}")

# Lights
print("\nLights:")
for l in bpy.data.objects:
    if l.type == "LIGHT":
        print(f"  {l.name}: type={l.data.type} energy={l.data.energy}")

# A few materials
print("\nMaterial diagnostic (find principled by type, not name):")
for mat in [m for m in bpy.data.materials if m.users > 0][:8]:
    if not (mat.use_nodes and mat.node_tree):
        continue
    bsdfs = [n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"]
    emissions = [n for n in mat.node_tree.nodes if n.type == "EMISSION"]
    print(f"\n  {mat.name}:")
    for bsdf in bsdfs:
        bc = bsdf.inputs.get("Base Color")
        em = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        em_strength = bsdf.inputs.get("Emission Strength")
        alpha = bsdf.inputs.get("Alpha")
        print(f"    BSDF '{bsdf.name}':")
        if bc:
            print(f"      base_color: linked={bc.is_linked} "
                  f"value={list(bc.default_value)}")
        if em:
            print(f"      emission_color: linked={em.is_linked} "
                  f"value={list(em.default_value) if hasattr(em.default_value, '__iter__') else em.default_value}")
        if em_strength:
            print(f"      emission_strength: linked={em_strength.is_linked} "
                  f"value={em_strength.default_value}")
        if alpha:
            print(f"      alpha: linked={alpha.is_linked} value={alpha.default_value}")
    for em_node in emissions:
        col = em_node.inputs.get("Color")
        strength = em_node.inputs.get("Strength")
        print(f"    EMISSION '{em_node.name}': color={list(col.default_value) if col else None}"
              f" strength={strength.default_value if strength else None}")

print("=" * 60)
