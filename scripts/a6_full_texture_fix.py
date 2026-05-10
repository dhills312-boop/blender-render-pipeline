"""Comprehensive texture fix:
1. Overwrite Torso_Decals_1k.png + _4k.png with actual white pixels (raw PNG bytes,
   bypasses Blender's image API which produced black last time).
2. Reload Torso_Decals data block in Blender.
3. Retarget every CC4 mis-wired Image Texture node across ALL materials so
   each role's image matches the material's expected texture prefix.

Run:
    blender -b a6_v10_skin_shader_rebuilt.blend -P a6_full_texture_fix.py -- \
        --out-blend <path> --report <path>
"""

import argparse
import json
import os
import re
import struct
import sys
import zlib

import bpy

ROLE_RE = re.compile(r"cc3iid_\(([A-Z_]+)\)_v")

# Material name -> expected texture-name prefix on disk.
MAT_PREFIX = {
    "Skin_Head": "Std_Skin_Head",
    "Skin_Body": "Std_Skin_Body",
    "Skin_Arm":  "Std_Skin_Arm",
    "Skin_Leg":  "Std_Skin_Leg",
    "Nails":     "Std_Nails",
    "Scalp1_Transparency": "Std_Skin_Head",  # scalp uses Skin_Head atlas
    "Eyelash":   "Std_Eyelash",
    "Eye_L":     "Std_Eye_L",
    "Eye_R":     "Std_Eye_R",
    "Cornea_L":  "Std_Cornea_L",
    "Cornea_R":  "Std_Cornea_R",
    "Eye_Occlusion_L": "Std_Eye_Occlusion_L",
    "Eye_Occlusion_R": "Std_Eye_Occlusion_R",
    "Tearline_L": "Std_Tearline_L",
    "Tearline_R": "Std_Tearline_R",
    "Tongue":    "Std_Tongue",
    "Upper_Teeth": "Std_Upper_Teeth",
    "Lower_Teeth": "Std_Lower_Teeth",
}

# Role tag -> keyword(s) that should appear in the matching image name.
ROLE_KEYWORDS = {
    "DIFFUSE": ["Diffuse"],
    "NORMAL": ["Normal"],
    "ROUGHNESS": ["roughness", "Roughness"],
    "METALLIC": ["metallic", "Metallic"],
    "AO": ["ao"],
    "OPACITY": ["Opacity"],
    "ALPHA": ["Opacity", "Alpha"],
    "SSS": ["SSSMap"],
    "TRANSMISSION": ["TransMap"],
    "MICRONORMAL": ["MicroN"],
    "MICRONMASK": ["MicroNMask"],
    "RGBAMASK": ["RGBAMask"],
    "BCBMAP": ["BCBMap"],
    "SCLERA": ["Sclera"],
    "SCLERANORMAL": ["ScleraN", "Sclera_N"],
    "EYEBLEND": ["BCBMap"],
    "GUMSMASK": ["GumsMask"],
    "GRADAO": ["GradAO"],
    "NBMAP": ["NBMap"],
    "ENMASK": ["ENMask"],
    "CFULCMASK": ["CFULCMask"],
    "MNAOMASK": ["MNAOMask"],
    "NMUILMASK": ["NMUILMask"],
    "WRINKLEDIFFUSE1": ["Wrinkle_Diffuse1"],
    "WRINKLEDIFFUSE2": ["Wrinkle_Diffuse2"],
    "WRINKLEDIFFUSE3": ["Wrinkle_Diffuse3"],
    "WRINKLEROUGHNESS1": ["Wrinkle_Roughness1"],
    "WRINKLEROUGHNESS2": ["Wrinkle_Roughness2"],
    "WRINKLEROUGHNESS3": ["Wrinkle_Roughness3"],
    "WRINKLENORMAL1": ["Wrinkle_Normal1"],
    "WRINKLENORMAL2": ["Wrinkle_Normal2"],
    "WRINKLENORMAL3": ["Wrinkle_Normal3"],
    "WRINKLEFLOW1": ["Wrinkle_Flow1"],
    "WRINKLEFLOW2": ["Wrinkle_Flow2"],
    "WRINKLEFLOW3": ["Wrinkle_Flow3"],
    "ROUGHNESS_PACK": ["Roughness Pack"],
    "FLOW_PACK": ["Flow Pack"],
    "SSTM_PACK": ["SSTM Pack"],
    "MSMNAO_PACK": ["MSMNAO Pack"],
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def write_white_png(path, size):
    """Write a fully-white RGB PNG via stdlib (no PIL)."""
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
        )
    out = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    out += chunk(b"IHDR", ihdr)
    row = b"\x00" + b"\xff\xff\xff" * size
    raw = row * size
    out += chunk(b"IDAT", zlib.compress(raw, 9))
    out += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)


def find_candidate_image(prefix, keywords, all_image_names):
    """Find an image starting with `prefix` and containing any keyword."""
    for img_name in all_image_names:
        if img_name.startswith(prefix) and any(k in img_name for k in keywords):
            img = bpy.data.images.get(img_name)
            if img and img.size[0] >= 32 and img.size[1] >= 32:
                return img
    return None


def main():
    args = parse_args()
    print("=" * 60)
    print(f"INPUT: {bpy.data.filepath}")
    print(f"OUTPUT: {args.out_blend}")
    print("=" * 60)

    blend_dir = os.path.dirname(bpy.data.filepath)
    tex_dir = os.path.join(blend_dir, "textures")

    # === Step 1: rewrite Torso_Decals as white PNGs on disk ===
    path_1k = os.path.join(tex_dir, "Torso_Decals_1k.png")
    path_4k = os.path.join(tex_dir, "Torso_Decals_4k.png")
    print(f"\n[1] Writing white PNGs:")
    write_white_png(path_1k, 1024)
    write_white_png(path_4k, 1024)
    print(f"    {path_1k} ({os.path.getsize(path_1k)} bytes)")
    print(f"    {path_4k} ({os.path.getsize(path_4k)} bytes)")

    # Step 2: reload Torso_Decals in Blender.
    img = bpy.data.images.get("Torso_Decals")
    if img:
        if img.packed_file:
            try:
                img.unpack(method="REMOVE")
            except Exception:
                pass
        img.source = "FILE"
        img.filepath = "//textures/Torso_Decals_1k.png"
        img.colorspace_settings.name = "sRGB"
        img.reload()
        print(f"[2] Reloaded Torso_Decals: {list(img.size)}")
    else:
        print(f"[2] WARN: Torso_Decals data block not found")

    # === Step 3: retarget mis-wired image references ===
    all_image_names = sorted(bpy.data.images.keys())
    fixes = []
    skipped = []

    for mat_name, prefix in MAT_PREFIX.items():
        mat = bpy.data.materials.get(mat_name)
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE":
                continue
            role = None
            m = ROLE_RE.search(node.name)
            if m:
                role = m.group(1)
            if not role or role not in ROLE_KEYWORDS:
                continue
            keywords = ROLE_KEYWORDS[role]
            img = node.image
            if not img:
                continue
            current = img.name
            # Is the current image already correct?
            if current.startswith(prefix) and any(k in current for k in keywords):
                continue
            # Find a better candidate.
            candidate = find_candidate_image(prefix, keywords, all_image_names)
            if not candidate:
                skipped.append({
                    "material": mat_name,
                    "role": role,
                    "current": current,
                    "reason": "no_candidate",
                })
                continue
            node.image = candidate
            fixes.append({
                "material": mat_name,
                "role": role,
                "node_name": node.name,
                "old": current,
                "new": candidate.name,
            })
            print(f"    [{mat_name}] {role}: {current} -> {candidate.name}")

    print(f"\n[3] Applied {len(fixes)} fix(es), skipped {len(skipped)}")

    # Save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "torso_decals_size": (os.path.getsize(path_1k)
                              if os.path.exists(path_1k) else 0),
        "fixes_applied": len(fixes),
        "fixes": fixes,
        "skipped": skipped,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
