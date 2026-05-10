"""Step C: wire the new UV_chest layer + a paintable decal texture into
the chest material so painting on the texture only shows on the
re-UV'd torso faces.

After Step B (user unwrapped chest faces in interactive Blender), this
script:
1. Verifies the UV_chest layer exists and has been unwrapped (check that
   chest UVs are now in [0,1] range, not the original Channel0 coords).
2. Creates a new white 1024x1024 'Torso_Decals' image (multiply-neutral).
3. Saves it to disk as Torso_Decals_1k.png + 4k version.
4. Wires it into Skin_Head as a Multiply overlay, sourcing UV from the
   UV_chest layer (via a UV Map node).
5. Also wires it into Skin_Body the same way (since abdomen lives there).
6. Saves a versioned blend.

Run:
    blender -b a6_v07b_chest_uv_prep.blend -P a6_chest_uv_wire.py -- \
        --out-blend <path> --tex-dir <abs> --report <path>
"""

import argparse
import json
import os
import shutil
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--resolution", type=int, default=1024)
    return p.parse_args(argv)


def verify_uv_chest_was_unwrapped(body):
    """Check that UV_chest layer has been re-unwrapped — selected (chest)
    faces should now have UVs roughly in [0,1] range, not the original
    UDIM coords."""
    me = body.data
    if "UV_chest" not in me.uv_layers:
        return False, "UV_chest layer missing"
    uv_chest = me.uv_layers["UV_chest"].data
    if "chest_faces" not in body.vertex_groups:
        return False, "chest_faces vertex group missing"

    vg = body.vertex_groups["chest_faces"]
    chest_vert_indices = set()
    for v in me.vertices:
        for g in v.groups:
            if g.group == vg.index:
                chest_vert_indices.add(v.index)
                break

    chest_uvs = []
    for poly in me.polygons:
        # Strict: face must be ENTIRELY in chest_faces (border faces have
        # non-group verts with original UDIM UVs, throwing off the range check).
        if all(vi in chest_vert_indices for vi in poly.vertices):
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                chest_uvs.append((uv_chest[li].uv.x, uv_chest[li].uv.y))

    if not chest_uvs:
        return False, "no chest UVs found"

    us = [u[0] for u in chest_uvs]
    vs = [u[1] for u in chest_uvs]
    u_max = max(us)
    u_min = min(us)
    v_max = max(vs)
    v_min = min(vs)
    print(f"UV_chest range on chest faces: U=[{u_min:.3f}, {u_max:.3f}] "
          f"V=[{v_min:.3f}, {v_max:.3f}]")
    if u_max > 1.5 or u_min < -0.5:
        return False, (f"chest UVs still in UDIM range "
                       f"({u_min:.3f}, {u_max:.3f}) — not unwrapped")
    return True, f"unwrapped to [{u_min:.3f}, {u_max:.3f}]"


def create_white_image(name, path, res):
    """Create a fresh white image, save to disk."""
    # Remove existing data block of same name if it exists.
    existing = bpy.data.images.get(name)
    if existing:
        bpy.data.images.remove(existing)
    img = bpy.data.images.new(name, res, res, alpha=False)
    px = [1.0, 1.0, 1.0, 1.0] * (res * res)
    img.pixels.foreach_set(px)
    img.colorspace_settings.name = "sRGB"
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    # Unpack any internal data — important to avoid the cache problem from
    # earlier where Blender loaded stale embedded pixels.
    try:
        img.unpack(method="USE_LOCAL")
    except Exception:
        pass
    img.source = "FILE"
    img.filepath = "//" + os.path.relpath(
        path, os.path.dirname(bpy.data.filepath or path)
    ).replace("\\", "/")
    img.reload()
    return img


def wire_decal_into_material(mat, decal_img, uv_layer_name):
    """Add the decal texture as a Multiply overlay on top of whatever
    currently feeds Base Color of the material's Principled BSDF.

    Decal samples from the supplied UV map name (UV_chest) so it only
    shows on chest/torso faces; non-torso faces have garbage UVs in that
    layer (but neutral-white pixels = identity multiply)."""
    if not mat or not mat.use_nodes:
        return False, "no node tree"
    nt = mat.node_tree

    # Find Principled BSDF.
    bsdf = None
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bsdf = n
            break
    if not bsdf:
        return False, "no Principled BSDF"

    bc_in = bsdf.inputs.get("Base Color")
    if not bc_in:
        return False, "BSDF has no Base Color input"

    # If we already injected a decal node here, remove the old wiring first.
    for n in list(nt.nodes):
        if n.label in ("Torso Decal Image", "Torso Decal UV",
                       "Torso Decal Multiply", "Nipples Decal",
                       "Nipples Multiply"):
            nt.nodes.remove(n)
    # Re-find BSDF after node removal.
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bsdf = n
            break

    bc_in = bsdf.inputs["Base Color"]

    # UV Map node — sources from UV_chest layer specifically.
    uv_node = nt.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = uv_layer_name
    uv_node.label = "Torso Decal UV"
    uv_node.location = (bsdf.location.x - 1200, bsdf.location.y + 350)

    # Image Texture node.
    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.image = decal_img
    img_node.label = "Torso Decal Image"
    img_node.location = (bsdf.location.x - 900, bsdf.location.y + 300)
    nt.links.new(uv_node.outputs["UV"], img_node.inputs["Vector"])
    # Diffuse decal -> sRGB (color, not data).
    if decal_img.colorspace_settings.name != "sRGB":
        decal_img.colorspace_settings.name = "sRGB"

    # Mix RGB Multiply.
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.label = "Torso Decal Multiply"
    mix.inputs["Fac"].default_value = 1.0
    mix.location = (bsdf.location.x - 250, bsdf.location.y + 200)

    # Capture and reroute existing BC source.
    if bc_in.is_linked:
        existing = bc_in.links[0]
        src_socket = existing.from_socket
        nt.links.remove(existing)
        nt.links.new(src_socket, mix.inputs["Color1"])
    nt.links.new(img_node.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bc_in)

    return True, "wired"


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    body = bpy.data.objects.get("Body")
    if not body:
        print("ERROR: Body not found")
        sys.exit(1)

    # Step 1: verify UV_chest was unwrapped.
    ok, msg = verify_uv_chest_was_unwrapped(body)
    print(f"\n[1] UV_chest verification: {ok} — {msg}")
    if not ok:
        print("ERROR: Step B (Smart UV Project) doesn't seem to have run.")
        print("       Open a6_v07b_chest_uv_prep.blend, do U > Smart UV "
              "Project on chest faces, save, and re-run this script.")
        sys.exit(1)

    # Step 2: create the decal image.
    os.makedirs(args.tex_dir, exist_ok=True)
    img_path_1k = os.path.join(args.tex_dir, "Torso_Decals_1k.png")
    img_path_4k = os.path.join(args.tex_dir, "Torso_Decals_4k.png")
    decal_img = create_white_image(
        "Torso_Decals", img_path_1k, args.resolution
    )
    # Mirror to 4k for swap_textures.py compatibility.
    shutil.copy(img_path_1k, img_path_4k)
    print(f"\n[2] Created decal image: {img_path_1k}")
    print(f"    + 4k mirror: {img_path_4k}")

    # Step 3: wire into Skin_Head and Skin_Body.
    wired_results = {}
    for mat_name in ("Skin_Head", "Skin_Body"):
        mat = bpy.data.materials.get(mat_name)
        if mat:
            ok, msg = wire_decal_into_material(mat, decal_img, "UV_chest")
            wired_results[mat_name] = msg
            print(f"[3] {mat_name}: {msg}")
        else:
            wired_results[mat_name] = "material not found"

    # Save .blend.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "uv_chest_status": msg,
        "decal_image_1k": img_path_1k,
        "decal_image_4k": img_path_4k,
        "decal_image_resolution": args.resolution,
        "uv_layer_used": "UV_chest",
        "wired_into": wired_results,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
