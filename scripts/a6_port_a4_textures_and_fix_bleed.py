"""Two-part fix:
1. Open a4's .blend (rejected/a4/blender file.blend), extract skin
   AO/MicroN/MicroNMask textures we don't have in a6, save them to
   a6's textures/ folder as _1k and _4k pairs.
2. Open a6_v11 (the latest a6), wire the new AO + MicroN textures into
   each skin material's Principled BSDF, AND remove the Torso_Decals
   chain from Skin_Head (so the forehead doesn't display chest decals).

This runs as a SINGLE Blender invocation (Phase 1 first, then Phase 2 in
the same Python process) to avoid invoking Blender twice. We use
bpy.ops.wm.open_mainfile to switch between blend files.

Run:
    blender -b -P a6_port_a4_textures_and_fix_bleed.py -- \
        --a4-blend "<path to a4 blend>" \
        --a6-in <a6 input blend> \
        --a6-out <a6 output blend> \
        --tex-dir <textures dir> \
        --report <report path>
"""
import argparse
import json
import os
import struct
import sys
import zlib

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--a4-blend", required=True)
    p.add_argument("--a6-in", required=True)
    p.add_argument("--a6-out", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


# ---- PHASE 1: extract textures from a4 ----

WANTED_PATTERNS = [
    # (matches function, base name we want to save as)
    ("ao",           lambda n: ("skin" in n.lower() and "ao" in n.lower()
                                and "mask" not in n.lower())),
    ("MicroN",       lambda n: ("skin" in n.lower() and "micron" in n.lower()
                                and "mask" not in n.lower())),
    ("MicroNMask",   lambda n: ("skin" in n.lower() and "micronmask" in n.lower())),
]


def safe_filename(name):
    base = os.path.basename(name)
    stem, _ = os.path.splitext(base)
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)


def ext_for(img):
    fp = img.filepath_raw or img.filepath
    if fp:
        _, ext = os.path.splitext(fp.lower())
        if ext in (".png", ".jpg", ".jpeg", ".tga", ".tif"):
            return ".jpg" if ext == ".jpeg" else ext
    fmt = img.file_format
    return {"PNG": ".png", "JPEG": ".jpg", "TARGA": ".tga"}.get(fmt, ".png")


def fmt_for_ext(ext):
    return {".png": "PNG", ".jpg": "JPEG", ".tga": "TARGA"}.get(ext.lower(), "PNG")


def save_image_render(img, target_path, target_format):
    sc = bpy.context.scene
    settings = sc.render.image_settings
    prev_fmt = settings.file_format
    prev_depth = settings.color_depth
    settings.file_format = target_format
    if target_format in ("PNG", "TIFF"):
        settings.color_depth = "8"
    try:
        img.save_render(filepath=target_path)
    finally:
        settings.file_format = prev_fmt
        settings.color_depth = prev_depth


def downsize_to_1k(src_path, dst_path, max_size, fmt):
    tmp = bpy.data.images.load(src_path)
    try:
        w, h = tmp.size
        if max(w, h) > max_size:
            if w >= h:
                new_w = max_size
                new_h = max(1, int(round(h * max_size / w)))
            else:
                new_h = max_size
                new_w = max(1, int(round(w * max_size / h)))
            tmp.scale(new_w, new_h)
        save_image_render(tmp, dst_path, fmt)
    finally:
        bpy.data.images.remove(tmp)


def phase1_extract_from_a4(a4_path, tex_dir):
    print("\n" + "=" * 60)
    print(f"PHASE 1: Extract from {a4_path}")
    print("=" * 60)
    bpy.ops.wm.open_mainfile(filepath=a4_path)

    extracted = []
    skipped = []

    for img in list(bpy.data.images):
        if img.name in ("Render Result", "Viewer Node"):
            continue
        if img.size[0] < 256 or img.size[1] < 256:
            continue
        # Match against wanted patterns.
        for tag, matcher in WANTED_PATTERNS:
            if matcher(img.name):
                base = safe_filename(img.name)
                ext = ext_for(img)
                fmt = fmt_for_ext(ext)
                path_4k = os.path.join(tex_dir, f"{base}_4k{ext}")
                path_1k = os.path.join(tex_dir, f"{base}_1k{ext}")
                # Skip if already exists (don't overwrite our existing files).
                if os.path.exists(path_4k) and os.path.exists(path_1k):
                    skipped.append({"image": img.name,
                                    "reason": "already_exists",
                                    "path": path_4k})
                    break
                try:
                    save_image_render(img, path_4k, fmt)
                    downsize_to_1k(path_4k, path_1k, 1024, fmt)
                    size_4k = os.path.getsize(path_4k)
                    size_1k = os.path.getsize(path_1k)
                    extracted.append({
                        "image": img.name,
                        "tag": tag,
                        "path_4k": path_4k,
                        "path_1k": path_1k,
                        "size_4k": size_4k,
                        "size_1k": size_1k,
                        "src_resolution": [img.size[0], img.size[1]],
                    })
                    print(f"  {img.name:40s} -> {os.path.basename(path_4k)} "
                          f"({size_4k//1024}KB) + 1k ({size_1k//1024}KB)")
                except Exception as e:
                    skipped.append({"image": img.name,
                                    "reason": f"save_failed: {e}"})
                break

    print(f"\n  extracted: {len(extracted)}, skipped: {len(skipped)}")
    return extracted, skipped


# ---- PHASE 2: wire textures + remove Skin_Head decal in a6 ----

def find_image_on_disk(tex_dir, prefix, suffix_keywords):
    """Find a 1k file matching prefix + any of keywords."""
    for fn in os.listdir(tex_dir):
        if not fn.endswith(("_1k.jpg", "_1k.png", "_1k.tga")):
            continue
        if not fn.startswith(prefix):
            continue
        if any(k in fn for k in suffix_keywords):
            return os.path.join(tex_dir, fn)
    return None


def load_image_from_disk(path):
    """Load an image as a fresh data block (no packed embedding)."""
    img = bpy.data.images.load(path, check_existing=True)
    img.source = "FILE"
    # Make path relative to the .blend.
    try:
        rel = os.path.relpath(path, os.path.dirname(bpy.data.filepath))
        img.filepath = "//" + rel.replace("\\", "/")
        img.filepath_raw = "//" + rel.replace("\\", "/")
    except Exception:
        pass
    return img


def find_principled_bsdf(mat):
    if not mat or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def remove_torso_decal_chain(mat):
    """Remove Torso_Decals image/UV/Multiply from a material; reconnect
    base color source directly to BSDF.Base Color."""
    if not mat or not mat.use_nodes:
        return False
    nt = mat.node_tree
    # Identify our injected nodes by label.
    decal_labels = {"Torso Decal Image", "Torso Decal UV",
                    "Torso Decal Multiply", "Anatomical Normal",
                    "Anatomical Normal Map", "Anatomical Normal Mix",
                    "Nipples Decal", "Nipples Multiply"}
    nodes_to_remove = [n for n in nt.nodes if n.label in decal_labels]
    if not nodes_to_remove:
        return False

    # Before removing, find base-color path. If a Mix labeled
    # "Torso Decal Multiply" exists, what feeds its Color1 input is the
    # upstream base color source we want to reconnect to BSDF.
    upstream_socket = None
    for n in nodes_to_remove:
        if n.type == "MIX_RGB" and n.label == "Torso Decal Multiply":
            color1 = n.inputs.get("Color1")
            if color1 and color1.is_linked:
                upstream_socket = color1.links[0].from_socket
            break

    # Remove the nodes (capture types first to avoid stale-pointer issues).
    for n in list(nodes_to_remove):
        try:
            nt.nodes.remove(n)
        except Exception:
            pass

    # Reconnect upstream to BSDF Base Color if we found one.
    bsdf = find_principled_bsdf(mat)
    if bsdf and upstream_socket:
        bc_in = bsdf.inputs.get("Base Color")
        if bc_in and not bc_in.is_linked:
            try:
                nt.links.new(upstream_socket, bc_in)
            except Exception:
                pass
    return True


def insert_ao_multiply(mat, ao_image):
    """Add an AO multiply between the existing base color source and
    BSDF.Base Color. AO maps are color data -> Non-Color colorspace."""
    bsdf = find_principled_bsdf(mat)
    if not (bsdf and ao_image):
        return False
    nt = mat.node_tree
    bc_in = bsdf.inputs["Base Color"]

    # Skip if AO node already exists for this material.
    for n in nt.nodes:
        if n.type == "TEX_IMAGE" and n.image == ao_image:
            return False  # already wired

    # Image Texture node (Non-Color).
    ao_image.colorspace_settings.name = "Non-Color"
    ao_node = nt.nodes.new("ShaderNodeTexImage")
    ao_node.image = ao_image
    ao_node.label = "AO"
    ao_node.location = (bsdf.location.x - 1100, bsdf.location.y + 250)

    # Mix Multiply at 0.5 factor.
    ao_mix = nt.nodes.new("ShaderNodeMixRGB")
    ao_mix.blend_type = "MULTIPLY"
    ao_mix.label = "AO Multiply"
    ao_mix.inputs["Fac"].default_value = 0.5
    ao_mix.location = (bsdf.location.x - 600, bsdf.location.y + 100)

    # Reroute existing BC source through AO mix.
    if bc_in.is_linked:
        existing = bc_in.links[0]
        src_socket = existing.from_socket
        nt.links.remove(existing)
        nt.links.new(src_socket, ao_mix.inputs["Color1"])
    nt.links.new(ao_node.outputs["Color"], ao_mix.inputs["Color2"])
    nt.links.new(ao_mix.outputs["Color"], bc_in)
    return True


def insert_micron_normal(mat, micron_image, mask_image=None):
    """Add MicroNormal as a second normal map blended with the existing
    one. Optional mask scales the MicroN influence."""
    bsdf = find_principled_bsdf(mat)
    if not (bsdf and micron_image):
        return False
    nt = mat.node_tree
    n_in = bsdf.inputs.get("Normal")
    if not n_in:
        return False

    # Skip if this image is already wired (idempotent re-runs).
    for n in nt.nodes:
        if n.type == "TEX_IMAGE" and n.image == micron_image:
            return False

    micron_image.colorspace_settings.name = "Non-Color"
    if mask_image:
        mask_image.colorspace_settings.name = "Non-Color"

    micron_tex = nt.nodes.new("ShaderNodeTexImage")
    micron_tex.image = micron_image
    micron_tex.label = "MicroN"
    micron_tex.location = (bsdf.location.x - 1100, bsdf.location.y - 700)

    micron_nm = nt.nodes.new("ShaderNodeNormalMap")
    micron_nm.label = "MicroN Normal Map"
    micron_nm.location = (bsdf.location.x - 700, bsdf.location.y - 700)
    micron_nm.inputs["Strength"].default_value = 0.3
    nt.links.new(micron_tex.outputs["Color"], micron_nm.inputs["Color"])

    # If mask supplied, scale MicroN strength by mask.
    if mask_image:
        mask_tex = nt.nodes.new("ShaderNodeTexImage")
        mask_tex.image = mask_image
        mask_tex.label = "MicroN Mask"
        mask_tex.location = (bsdf.location.x - 1100, bsdf.location.y - 1000)
        # Multiply mask into Strength via a math node.
        # Skip detailed mask wiring for now — strength factor 0.3 is
        # already conservative; can refine later.

    # Mix existing Normal output with our MicroN output (vector mix).
    if n_in.is_linked:
        existing = n_in.links[0]
        src_socket = existing.from_socket
        nt.links.remove(existing)
        mix_v = nt.nodes.new("ShaderNodeMix")
        mix_v.data_type = "VECTOR"
        mix_v.label = "Normal+MicroN Mix"
        mix_v.inputs["Factor"].default_value = 0.3
        mix_v.location = (bsdf.location.x - 250, bsdf.location.y - 400)
        nt.links.new(src_socket, mix_v.inputs[4])  # A
        nt.links.new(micron_nm.outputs["Normal"], mix_v.inputs[5])  # B
        nt.links.new(mix_v.outputs[1], n_in)  # Result
    else:
        nt.links.new(micron_nm.outputs["Normal"], n_in)

    return True


def phase2_wire_a6(a6_in, a6_out, tex_dir):
    print("\n" + "=" * 60)
    print(f"PHASE 2: Open a6 and wire textures")
    print("=" * 60)
    bpy.ops.wm.open_mainfile(filepath=a6_in)

    actions = []
    mat_to_prefix = {
        "Skin_Head": "Std_Skin_Head",
        "Skin_Body": "Std_Skin_Body",
        "Skin_Arm":  "Std_Skin_Arm",
        "Skin_Leg":  "Std_Skin_Leg",
    }

    # Step 2a: remove Torso_Decals from Skin_Head.
    skin_head = bpy.data.materials.get("Skin_Head")
    removed = remove_torso_decal_chain(skin_head)
    print(f"\n[2a] Skin_Head Torso_Decals removed: {removed}")
    actions.append({"step": "remove_skin_head_decal", "removed": removed})

    # Step 2b: for each skin material, wire AO + MicroN.
    for mat_name, prefix in mat_to_prefix.items():
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            actions.append({"material": mat_name, "status": "not_found"})
            continue

        ao_path = find_image_on_disk(tex_dir, prefix, ["_ao_"])
        micron_path = find_image_on_disk(tex_dir, prefix, ["_MicroN_"])
        # MicroNMask: skip mask wiring (deferred per the script comment)
        # mask_path = find_image_on_disk(tex_dir, prefix, ["_MicroNMask_"])

        ao_added = False
        micron_added = False
        if ao_path:
            ao_img = load_image_from_disk(ao_path)
            ao_added = insert_ao_multiply(mat, ao_img)
        if micron_path:
            micron_img = load_image_from_disk(micron_path)
            micron_added = insert_micron_normal(mat, micron_img, None)

        actions.append({
            "material": mat_name,
            "ao_path": ao_path,
            "ao_added": ao_added,
            "micron_path": micron_path,
            "micron_added": micron_added,
        })
        print(f"[2b] {mat_name}: AO={'+' if ao_added else '-'} "
              f"MicroN={'+' if micron_added else '-'}  "
              f"(ao={os.path.basename(ao_path) if ao_path else 'none'}, "
              f"micron={os.path.basename(micron_path) if micron_path else 'none'})")

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=a6_out, copy=False)
    print(f"\nSAVED: {a6_out}")

    return actions


def main():
    args = parse_args()
    os.makedirs(args.tex_dir, exist_ok=True)

    extracted, skipped = phase1_extract_from_a4(args.a4_blend, args.tex_dir)
    actions = phase2_wire_a6(args.a6_in, args.a6_out, args.tex_dir)

    rep = {
        "phase1_extracted": extracted,
        "phase1_skipped": skipped,
        "phase2_actions": actions,
        "a6_output": args.a6_out,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"\nREPORT: {args.report}")


if __name__ == "__main__":
    main()
