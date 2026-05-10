"""Procedurally paint subtle nipple/areola onto the existing 'Nipples'
diffuse decal image, then wire it into the Skin_Head material as a
Multiply overlay over the existing diffuse pipeline.

The chest geometry is on Skin_Head material (CC4 quirk — verified by UV
overlap diagnostic). So our decal needs to live in Skin_Head's graph,
not Skin_Body's.

Algorithm:
1. Locate the 'Nipples' image (or create it if missing).
2. Find the Body mesh and the world-space positions of left/right
   nipple centers (most forward chest verts on each side).
3. For each nipple, find the closest mesh vertex and read its UV coord.
4. Paint a radial gradient on the Nipples image at each UV:
   - Outer areola: ~30 px radius, color #8C4650 (mauve burgundy) at ~30% opacity
   - Inner nipple: ~10 px radius, color #6E3640 (slightly darker) at ~50% opacity
5. Save the image to textures/Nipples_1k.png (and 4k version).
6. Wire it as a Multiply layer over Skin_Head's main diffuse output going
   into the BSDF Base Color, with chest-area UV-masked influence.

Run:
    blender -b a6_v05_Test.blend -P a6_paint_nipples_diffuse.py -- \
        --out-blend <path> --tex-dir <abs> --report <path>
"""

import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def find_nipple_world_positions(body):
    """Find left and right nipple center positions in world space.
    Excludes sternum verts by requiring |x| > 0.04m (40mm off centerline)."""
    me = body.data
    left_candidates = []   # x > 0.04
    right_candidates = []  # x < -0.04
    for v in me.vertices:
        wc = body.matrix_world @ v.co
        # Chest region: z 1.30-1.45m, |x| in [0.04, 0.20]m, y < 0
        if 1.30 <= wc.z <= 1.45 and 0.04 < abs(wc.x) < 0.20 and wc.y < 0:
            if wc.x > 0:
                left_candidates.append((v.index, wc, v.co.copy()))
            else:
                right_candidates.append((v.index, wc, v.co.copy()))
    if not left_candidates or not right_candidates:
        return None, None
    # Most forward = smallest Y (Y points away from face).
    left = min(left_candidates, key=lambda c: c[1].y)
    right = min(right_candidates, key=lambda c: c[1].y)
    return left, right


def get_uv_for_vertex(obj, vert_index):
    """Find the UV coordinate associated with a vertex by scanning loops."""
    me = obj.data
    if not me.uv_layers:
        return None
    uv_layer = me.uv_layers.active.data
    # Find a loop that uses this vert.
    for poly in me.polygons:
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            if me.loops[li].vertex_index == vert_index:
                uv = uv_layer[li].uv
                return (uv.x, uv.y)
    return None


def hex_to_rgb01(h):
    """#RRGGBB -> (r, g, b) 0-1 floats."""
    h = h.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def paint_radial_gradient(pixels, width, height, cx, cy, radius, color, opacity):
    """Paint a soft radial gradient (Gaussian-like falloff) onto pixels.
    pixels: flat RGBA list, modified in-place.
    cx, cy: center in pixel space
    radius: outer radius in pixels
    color: (r, g, b) 0-1
    opacity: peak opacity 0-1 at center, fades to 0 at radius
    """
    r2 = radius * radius
    for py in range(max(0, int(cy - radius)), min(height, int(cy + radius + 1))):
        for px in range(max(0, int(cx - radius)), min(width, int(cx + radius + 1))):
            dx = px - cx
            dy = py - cy
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            # Smooth falloff: 1 at center, 0 at radius
            d = math.sqrt(d2)
            t = 1.0 - (d / radius)
            t = t * t  # squared for softer center spike
            alpha = opacity * t
            idx = (py * width + px) * 4
            # Composite over existing pixel.
            old_r = pixels[idx + 0]
            old_g = pixels[idx + 1]
            old_b = pixels[idx + 2]
            pixels[idx + 0] = old_r * (1 - alpha) + color[0] * alpha
            pixels[idx + 1] = old_g * (1 - alpha) + color[1] * alpha
            pixels[idx + 2] = old_b * (1 - alpha) + color[2] * alpha
            pixels[idx + 3] = 1.0


def get_or_create_nipples_image(width=1024, height=1024):
    """Always start with a fresh white image (existing 'Nipples' data
    might be polluted from earlier bakes). Multiply-blending with white
    leaves base diffuse unchanged everywhere except the painted nipples."""
    existing = bpy.data.images.get("Nipples")
    if existing is not None:
        # Resize / clear instead of removing (preserves users in materials).
        existing.scale(width, height)
        white_px = [1.0, 1.0, 1.0, 1.0] * (width * height)
        existing.pixels.foreach_set(white_px)
        existing.colorspace_settings.name = "sRGB"
        return existing
    img = bpy.data.images.new("Nipples", width, height, alpha=False)
    px = [1.0, 1.0, 1.0, 1.0] * (width * height)
    img.pixels.foreach_set(px)
    img.colorspace_settings.name = "sRGB"
    return img


def find_skin_head_material():
    return bpy.data.materials.get("Skin_Head")


def find_skin_head_bsdf(mat):
    if not mat or not mat.use_nodes:
        return None, None
    nt = mat.node_tree
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return nt, n
    return nt, None


def wire_nipples_overlay_to_skin_head(mat, nipples_img):
    """Add the Nipples image as a Multiply blend over whatever currently
    feeds Skin_Head's BSDF Base Color input."""
    nt, bsdf = find_skin_head_bsdf(mat)
    if not bsdf:
        return None

    bc_in = bsdf.inputs.get("Base Color")
    if not bc_in:
        return None

    # Image Texture node referencing the Nipples decal.
    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.image = nipples_img
    img_node.label = "Nipples Decal"
    img_node.location = (bsdf.location.x - 900, bsdf.location.y + 300)
    # Diffuse decal -> sRGB (color, not data)
    if nipples_img.colorspace_settings.name != "sRGB":
        nipples_img.colorspace_settings.name = "sRGB"

    # Mix RGB node in Multiply mode.
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.label = "Nipples Multiply"
    mix.inputs["Fac"].default_value = 1.0
    mix.location = (bsdf.location.x - 250, bsdf.location.y + 200)

    # Capture existing BC source.
    if bc_in.is_linked:
        existing_link = bc_in.links[0]
        existing_src_socket = existing_link.from_socket
        nt.links.remove(existing_link)
        nt.links.new(existing_src_socket, mix.inputs["Color1"])
    nt.links.new(img_node.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bc_in)

    return mat.name


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    body = bpy.data.objects.get("Body")
    if not body:
        print("ERROR: Body not found.")
        sys.exit(1)

    # Step 1: get or create the Nipples image.
    nipples = get_or_create_nipples_image(width=1024, height=1024)
    print(f"\n[1] Nipples image: {nipples.name} {list(nipples.size)} "
          f"colorspace={nipples.colorspace_settings.name}")

    # Step 2: find nipple positions on the body.
    left, right = find_nipple_world_positions(body)
    if not left or not right:
        print("ERROR: Could not locate nipple positions on Body.")
        sys.exit(1)
    print(f"\n[2] Left nipple vert {left[0]} world={list(left[1])}")
    print(f"    Right nipple vert {right[0]} world={list(right[1])}")

    # Step 3: get UV coordinates.
    left_uv = get_uv_for_vertex(body, left[0])
    right_uv = get_uv_for_vertex(body, right[0])
    if not left_uv or not right_uv:
        print("ERROR: Could not find UVs for nipple verts.")
        sys.exit(1)
    print(f"\n[3] Left UV: {left_uv}")
    print(f"    Right UV: {right_uv}")

    # Map UVs to pixel coords (handle UDIM by taking modulo 1).
    width, height = nipples.size
    left_uv_local = (left_uv[0] % 1.0, left_uv[1] % 1.0)
    right_uv_local = (right_uv[0] % 1.0, right_uv[1] % 1.0)
    left_px = (left_uv_local[0] * width, (1.0 - left_uv_local[1]) * height)
    right_px = (right_uv_local[0] * width, (1.0 - right_uv_local[1]) * height)
    print(f"    Left pixel: {left_px}")
    print(f"    Right pixel: {right_px}")

    # Step 4: paint.
    print(f"\n[4] Painting areola + nipple at both positions...")
    pixels = list(nipples.pixels)

    # Mauve burgundy from the question (RGB ~140, 70, 80).
    areola_color = hex_to_rgb01("#8C4650")
    nipple_color = hex_to_rgb01("#6E3640")

    # Outer areola: 30px radius, 30% opacity at center
    # Inner nipple: 10px radius, 50% opacity at center
    for px_pos in [left_px, right_px]:
        paint_radial_gradient(
            pixels, width, height,
            px_pos[0], px_pos[1],
            radius=30, color=areola_color, opacity=0.30,
        )
        paint_radial_gradient(
            pixels, width, height,
            px_pos[0], px_pos[1],
            radius=10, color=nipple_color, opacity=0.50,
        )

    nipples.pixels.foreach_set(pixels)
    nipples.update()

    # Step 5: save image to disk.
    os.makedirs(args.tex_dir, exist_ok=True)
    img_path = os.path.join(args.tex_dir, "Nipples_1k.png")
    img_path_4k = os.path.join(args.tex_dir, "Nipples_4k.png")
    nipples.filepath_raw = img_path
    nipples.file_format = "PNG"
    nipples.save()
    # Also copy to 4k.png so swap_textures.py works.
    import shutil
    shutil.copy(img_path, img_path_4k)
    print(f"\n[5] Saved: {img_path}")
    print(f"        and: {img_path_4k}")

    # Step 6: wire into Skin_Head as Multiply overlay.
    mat = find_skin_head_material()
    if not mat:
        print("WARN: Skin_Head not found, skipping wiring.")
    else:
        wired = wire_nipples_overlay_to_skin_head(mat, nipples)
        print(f"\n[6] Wired Nipples overlay into '{wired}' as Multiply blend")

    # Step 7: save .blend.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "nipples_image_path": img_path,
        "left_uv": left_uv,
        "right_uv": right_uv,
        "left_pixel": list(left_px),
        "right_pixel": list(right_px),
        "areola_color": "#8C4650",
        "nipple_color": "#6E3640",
        "areola_radius_px": 30,
        "nipple_radius_px": 10,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
