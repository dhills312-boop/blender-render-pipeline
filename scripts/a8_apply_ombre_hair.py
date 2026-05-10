"""Apply the generated white/black ombre hair texture to a copy of a8.

This is intentionally non-destructive: run it against the current blend and
save to a new output blend.

Run:
    blender -b a6_v13_anatomy_p1.blend -P a8_apply_ombre_hair.py -- \
        --src <source hair png> \
        --ombre <output ombre png> \
        --out-blend <new blend path>
"""

import argparse
from array import array
import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--ombre", required=True)
    p.add_argument("--out-blend", required=True)
    p.add_argument("--hair-object", default="Hair_30629")
    return p.parse_args(argv)


def generate_ombre(src_path, out_path):
    src = bpy.data.images.load(src_path, check_existing=True)
    w, h = src.size
    n_pixels = w * h
    pixels = array("f", [0.0]) * (n_pixels * 4)
    src.pixels.foreach_get(pixels)
    new_pixels = array("f", [0.0]) * (n_pixels * 4)

    # Blender can return black RGB for very transparent source texels. If that
    # happens, keep the ombre visible by generating strand-like value variation
    # from pixel position instead of trusting the sampled RGB.
    probe_step = max(1, n_pixels // 20000)
    probe = []
    for p in range(0, n_pixels, probe_step):
        idx = p * 4
        probe.append(0.2126 * pixels[idx] + 0.7152 * pixels[idx + 1] + 0.0722 * pixels[idx + 2])
    source_has_detail = (max(probe) - min(probe)) > 0.02 if probe else False

    for y in range(h):
        v_norm = y / max(1, h - 1)
        for x in range(w):
            idx = (y * w + x) * 4
            r = pixels[idx]
            g = pixels[idx + 1]
            b = pixels[idx + 2]
            a = pixels[idx + 3]
            if source_has_detail:
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            else:
                strand = ((x * 37 + y * 11) % 97) / 96.0
                lum = 0.35 + (strand * 0.3)
            value = max(0.0, min(1.0, v_norm + ((lum - 0.5) * 0.6)))
            new_pixels[idx] = value
            new_pixels[idx + 1] = value
            new_pixels[idx + 2] = value
            new_pixels[idx + 3] = max(a, 1.0)

    ombre = bpy.data.images.new(
        os.path.splitext(os.path.basename(out_path))[0], w, h, alpha=True
    )
    ombre.pixels.foreach_set(new_pixels)
    ombre.update()
    ombre.colorspace_settings.name = "sRGB"
    ombre.filepath_raw = out_path
    ombre.file_format = "PNG"
    ombre.save()
    return ombre


def image_node_score(node):
    img = getattr(node, "image", None)
    if not img:
        return -1
    haystack = f"{img.name} {img.filepath}".lower()
    score = 0
    for token in ("darksea", "purple", "haircards", "diffuse", "base"):
        if token in haystack:
            score += 1
    return score


def apply_to_hair(hair_obj, ombre_img):
    changed = []
    for slot in hair_obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        nodes = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage"]
        nodes.sort(key=image_node_score, reverse=True)
        for node in nodes:
            if image_node_score(node) > 0:
                old = node.image.name if node.image else None
                node.image = ombre_img
                changed.append({"material": mat.name, "node": node.name, "old": old})
                break
    return changed


def main():
    args = parse_args()
    print(f"SRC: {args.src}")
    print(f"OMBRE: {args.ombre}")
    print(f"OUT BLEND: {args.out_blend}")

    hair = bpy.data.objects.get(args.hair_object)
    if not hair:
        raise RuntimeError(f"Hair object not found: {args.hair_object}")

    os.makedirs(os.path.dirname(args.ombre), exist_ok=True)
    ombre = generate_ombre(args.src, args.ombre)
    changed = apply_to_hair(hair, ombre)
    if not changed:
        raise RuntimeError(f"No plausible hair image node found on {hair.name}")

    out_dir = os.path.dirname(args.out_blend)
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)

    print("CHANGED:")
    for item in changed:
        print(f"  {item['material']} :: {item['node']} ({item['old']} -> {ombre.name})")
    print(f"SAVED: {args.out_blend}")


if __name__ == "__main__":
    main()
