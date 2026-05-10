"""Convert the LO_086 magenta-bleed pair into a chromatic-aberration screentone
(magenta + cyan offset), soften the shadow gate, and add a Sobel edge-only
chromatic aberration pass in the Compositor.

Run with:
    blender --background LO_086_local_shader_test_stage.blend --python apply_chromatic_aberration.py

The script does NOT save in place. It writes LO_087_chromatic_aberration.blend
next to the source file. Run again any time -- it's idempotent.
"""

import bpy, os, sys

# --------- knobs (edit if you want different intensities) ---------
OFFSET = 0.008          # mapping offset, +/- in X for magenta/cyan
MAGENTA = (0.92, 0.10, 0.55, 1.0)
CYAN    = (0.05, 0.65, 0.92, 1.0)
SOFT_GATE_STOPS = (0.0, 0.9)  # widen shadow gate so it's biased not strict
COMP_OFFSET_PX = 3.0     # compositor edge aberration in pixels
# ------------------------------------------------------------------

OUT_NAME = "LO_087_chromatic_aberration.blend"


def find_node(nt, partial):
    """Find a node whose name contains the substring (case-insensitive)."""
    partial = partial.lower()
    for n in nt.nodes:
        if partial in n.name.lower():
            return n
    return None


def edit_ch03_body():
    mat = bpy.data.materials.get("Ch03_Body")
    if not mat or not mat.use_nodes:
        print("[!] Ch03_Body not found or doesn't use nodes -- skipping shader edits")
        return
    nt = mat.node_tree

    # --- 1. Convert "magenta bleed 2" branch to cyan ---
    cyan_ink = find_node(nt, "magenta comic bleed ink 2")
    if cyan_ink and cyan_ink.bl_idname == "ShaderNodeRGB":
        cyan_ink.outputs[0].default_value = CYAN
        cyan_ink.label = "cyan comic bleed ink 2"
        print(f"[ok] {cyan_ink.name}: set color to cyan")
    else:
        print("[!] couldn't find 'magenta comic bleed ink 2' RGB node")

    # --- 2. Offset the two dot-mapping nodes in opposite directions ---
    map1 = find_node(nt, "magenta bleed 1 dot mapping")
    map2 = find_node(nt, "magenta bleed 2 dot mapping")
    for m, sign, tag in ((map1, +1, "+M"), (map2, -1, "-C")):
        if m and m.bl_idname == "ShaderNodeMapping":
            loc = m.inputs["Location"]
            loc.default_value[0] = sign * OFFSET
            loc.default_value[1] = 0.0
            loc.default_value[2] = 0.0
            print(f"[ok] {m.name}: Location.X = {loc.default_value[0]:+.4f}  ({tag})")
        else:
            print(f"[!] couldn't find mapping node for tag {tag}")

    # --- 3. Switch screentone blend modes from MIX to SCREEN so inks coexist ---
    for nm in ("magenta comic bleed screentone 1", "magenta comic bleed screentone 2"):
        n = find_node(nt, nm)
        if n and hasattr(n, "blend_type"):
            n.blend_type = "SCREEN"
            print(f"[ok] {n.name}: blend_type SCREEN")
        else:
            print(f"[!] couldn't find Mix node '{nm}'")

    # --- 4. Soften the shadow gate: widen the ramp on the gating multiplier(s) ---
    # We added "magenta bleed 1/2 only in shadow" gates earlier; if they exist,
    # widen the upstream shadow/midtone print mask ramp instead so both gates soften.
    print_mask = find_node(nt, "shadow/midtone print mask")
    if print_mask and print_mask.bl_idname == "ShaderNodeValToRGB":
        ramp = print_mask.color_ramp
        # Reset to two stops at the soft positions, white at low (= bias toward shadow)
        # but never fully zero -- keeps magenta/cyan present in lit regions too.
        # Existing ramp likely has 2 stops; just move them.
        if len(ramp.elements) >= 2:
            ramp.elements[0].position = SOFT_GATE_STOPS[0]
            ramp.elements[-1].position = SOFT_GATE_STOPS[1]
            print(f"[ok] shadow/midtone print mask ramp stops -> {SOFT_GATE_STOPS}")

    # --- 5. Cosmetics: rename the cyan branch labels for findability ---
    for nm in ("magenta bleed 2 dot window coordinates",
               "magenta bleed 2 dot mapping from downloaded screentone",
               "magenta bleed 2 Euclidean dot screen",
               "magenta bleed 2 dot size ramp",
               "magenta comic bleed screentone 2",
               "magenta bleed 2 only in shadow"):
        n = find_node(nt, nm)
        if n:
            n.label = n.name.replace("magenta", "cyan", 1)


# ===================== Compositor: Sobel-edge chromatic aberration ===========

def setup_compositor_edge_aberration():
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    # Wipe and rebuild our additions while preserving Render Layers + Composite
    # Instead of nuking everything we just look for our marker nodes and rebuild.
    MARKER = "LO_087_aberration"
    # Remove any prior aberration cluster (idempotent)
    to_remove = [n for n in tree.nodes if n.label.startswith(MARKER)]
    for n in to_remove:
        tree.nodes.remove(n)

    # Locate Render Layers and Composite output
    rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
    comp = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeComposite"), None)
    if not rl:
        rl = tree.nodes.new("CompositorNodeRLayers")
        rl.location = (-800, 0)
    if not comp:
        comp = tree.nodes.new("CompositorNodeComposite")
        comp.location = (1000, 0)

    # Sobel edge detector on the image
    filt = tree.nodes.new("CompositorNodeFilter")
    filt.filter_type = "SOBEL"
    filt.label = MARKER + " sobel"
    filt.location = (-500, -200)
    tree.links.new(rl.outputs["Image"], filt.inputs["Image"])

    # Grayscale-ize the sobel into a mask via RGB-to-BW + ColorRamp for crispness
    rgb2bw = tree.nodes.new("CompositorNodeRGBToBW")
    rgb2bw.label = MARKER + " edge2bw"
    rgb2bw.location = (-300, -200)
    tree.links.new(filt.outputs["Image"], rgb2bw.inputs["Image"])

    edge_ramp = tree.nodes.new("CompositorNodeValToRGB")
    edge_ramp.label = MARKER + " edge ramp"
    edge_ramp.location = (-100, -200)
    edge_ramp.color_ramp.elements[0].position = 0.05
    edge_ramp.color_ramp.elements[1].position = 0.4
    tree.links.new(rgb2bw.outputs[0], edge_ramp.inputs["Fac"])

    # Split RGB
    sep = tree.nodes.new("CompositorNodeSeparateColor")
    sep.label = MARKER + " split"
    sep.location = (-500, 200)
    tree.links.new(rl.outputs["Image"], sep.inputs["Image"])

    # Translate Red and Blue channels in opposite directions (+/- offset px)
    tr_r = tree.nodes.new("CompositorNodeTranslate")
    tr_r.label = MARKER + " R shift"
    tr_r.location = (-250, 350)
    tr_r.inputs["X"].default_value = +COMP_OFFSET_PX

    tr_b = tree.nodes.new("CompositorNodeTranslate")
    tr_b.label = MARKER + " B shift"
    tr_b.location = (-250, 50)
    tr_b.inputs["X"].default_value = -COMP_OFFSET_PX

    # Separate outputs by index: 0=Red, 1=Green, 2=Blue, 3=Alpha
    tree.links.new(sep.outputs[0], tr_r.inputs["Image"])
    tree.links.new(sep.outputs[2], tr_b.inputs["Image"])

    comb = tree.nodes.new("CompositorNodeCombineColor")
    comb.label = MARKER + " recombine"
    comb.location = (0, 200)
    # Combine inputs by index: 0=Red, 1=Green, 2=Blue, 3=Alpha
    tree.links.new(tr_r.outputs[0], comb.inputs[0])
    tree.links.new(sep.outputs[1], comb.inputs[1])
    tree.links.new(tr_b.outputs[0], comb.inputs[2])

    # Mix the aberrated version on top of the original, gated by the edge ramp.
    # Use the legacy MixRGB node which has stable socket indices (1=Color1, 2=Color2)
    # across all Blender versions; the new Mix node renames these.
    mix = tree.nodes.new("CompositorNodeMixRGB")
    mix.label = MARKER + " edge mix"
    mix.blend_type = "MIX"
    mix.location = (300, 100)
    # Inputs by index: 0=Fac, 1=Image (base), 2=Image (overlay)
    tree.links.new(edge_ramp.outputs[0], mix.inputs[0])  # Fac
    tree.links.new(rl.outputs["Image"], mix.inputs[1])    # base
    tree.links.new(comb.outputs[0], mix.inputs[2])        # aberrated overlay

    # Wire to Composite (output 0 of MixRGB is "Image")
    tree.links.new(mix.outputs[0], comp.inputs["Image"])

    # Optional: Viewer node so the workspace preview shows the result live
    viewer = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeViewer"), None)
    if not viewer:
        viewer = tree.nodes.new("CompositorNodeViewer")
        viewer.location = (1000, 200)
    tree.links.new(mix.outputs[0], viewer.inputs["Image"])

    print(f"[ok] compositor edge aberration: +/-{COMP_OFFSET_PX}px on R/B channels")


# ===================== Main =================================================

def main():
    src = bpy.data.filepath
    if not src:
        print("[!] No filepath -- run with: blender --background <file> --python ...")
        sys.exit(1)
    edit_ch03_body()
    setup_compositor_edge_aberration()
    out = os.path.join(os.path.dirname(src), OUT_NAME)
    bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
    print(f"[done] saved -> {out}")


if __name__ == "__main__":
    main()
