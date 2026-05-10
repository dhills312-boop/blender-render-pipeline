"""Save embedded textures to disk in both 4K and 1K versions, retarget materials.

Adopts the lift-off pipeline convention:
    <texture_dir>/<name>_4k.<ext>
    <texture_dir>/<name>_1k.<ext>

After this script, the .blend references the *_1k.* files locally; the *_4k.*
versions live alongside them so swap_textures.py can flip between resolutions
for remote renders.

Run via:
    blender -b a6_v01_cleanup.blend -P a6_textures_to_1k.py -- \
        --tex-dir <abs_path> --out-blend <new_path> --report <report_path>
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import bpy


# Skip these — internal Blender images, not part of the model.
SKIP_NAMES = {"Render Result", "Viewer Node"}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--tex-dir", required=True,
                   help="Directory to save texture files into")
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--target-size", type=int, default=1024,
                   help="Target longest edge for the _1k version (default 1024)")
    return p.parse_args(argv)


def safe_filename(name):
    """Make an image name safe for a filename — strip path, slashes, etc."""
    base = os.path.basename(name)
    # Strip any extension already in the name (some images carry .jpg etc).
    stem, _ = os.path.splitext(base)
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)


def ext_from_image(img):
    """Best-guess extension based on source filepath or file format."""
    fp = img.filepath_raw or img.filepath
    if fp:
        _, ext = os.path.splitext(fp.lower())
        if ext in (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr",
                   ".webp", ".bmp"):
            return ".jpg" if ext == ".jpeg" else ext
    fmt = img.file_format
    return {
        "PNG": ".png", "JPEG": ".jpg", "TARGA": ".tga", "TIFF": ".tif",
        "OPEN_EXR": ".exr", "WEBP": ".webp", "BMP": ".bmp",
    }.get(fmt, ".png")


def file_format_for_ext(ext):
    return {
        ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".tga": "TARGA",
        ".tif": "TIFF", ".tiff": "TIFF", ".exr": "OPEN_EXR",
        ".webp": "WEBP", ".bmp": "BMP",
    }.get(ext.lower(), "PNG")


def save_image_as(img, target_path, target_format):
    """Save img to target_path using target_format without mutating the original."""
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


def downsize_copy(src_path, dst_path, target_size, fmt):
    """Load src as a temp Blender image, scale it, save as dst, remove temp."""
    tmp = bpy.data.images.load(src_path)
    try:
        w, h = tmp.size
        if max(w, h) > target_size:
            if w >= h:
                new_w = target_size
                new_h = max(1, int(round(h * target_size / w)))
            else:
                new_h = target_size
                new_w = max(1, int(round(w * target_size / h)))
            tmp.scale(new_w, new_h)
        save_image_as(tmp, dst_path, fmt)
    finally:
        bpy.data.images.remove(tmp)


def main():
    args = parse_args()
    tex_dir = Path(args.tex_dir)
    tex_dir.mkdir(parents=True, exist_ok=True)
    print(f"TEX DIR:  {tex_dir}")
    print(f"OUT BLEND: {args.out_blend}")
    print(f"TARGET 1K SIZE: {args.target_size}")

    report = {
        "tex_dir": str(tex_dir),
        "out_blend": args.out_blend,
        "target_1k_size": args.target_size,
        "processed": [],
        "skipped": [],
    }

    images_to_process = [
        img for img in bpy.data.images
        if img.name not in SKIP_NAMES
        and img.size[0] > 0
        and img.size[1] > 0
    ]
    print(f"\nProcessing {len(images_to_process)} image(s)...")

    for img in images_to_process:
        name = safe_filename(img.name)
        ext = ext_from_image(img)
        fmt = file_format_for_ext(ext)

        path_4k = tex_dir / f"{name}_4k{ext}"
        path_1k = tex_dir / f"{name}_1k{ext}"

        # Save the source as the _4k version (preserves the original).
        try:
            save_image_as(img, str(path_4k), fmt)
        except Exception as e:
            print(f"  SKIP {name}: failed to save 4k - {e}")
            report["skipped"].append({"name": img.name, "error": str(e)})
            continue

        # Generate the _1k version from the just-saved file (so we work from
        # bytes-on-disk, not the in-memory Blender state which we don't want
        # to mutate).
        try:
            downsize_copy(str(path_4k), str(path_1k), args.target_size, fmt)
        except Exception as e:
            print(f"  WARN {name}: 1k downsize failed, copying 4k - {e}")
            shutil.copy(path_4k, path_1k)

        # Retarget the .blend's image to point at the _1k file on disk.
        # Make path relative to the .blend dir so the project is portable.
        out_dir = os.path.dirname(args.out_blend)
        try:
            rel_path = os.path.relpath(str(path_1k), out_dir).replace("\\", "/")
            img.filepath = "//" + rel_path
            img.filepath_raw = "//" + rel_path
        except Exception:
            img.filepath = str(path_1k)
            img.filepath_raw = str(path_1k)
        # Unpack from the .blend if it was packed.
        if img.packed_file:
            try:
                img.unpack(method="REMOVE")
            except Exception:
                pass
        img.source = "FILE"
        img.reload()

        size_4k = path_4k.stat().st_size if path_4k.exists() else 0
        size_1k = path_1k.stat().st_size if path_1k.exists() else 0
        report["processed"].append({
            "name": img.name,
            "saved_4k": str(path_4k),
            "saved_1k": str(path_1k),
            "size_4k_kb": round(size_4k / 1024, 1),
            "size_1k_kb": round(size_1k / 1024, 1),
            "blend_now_points_to": img.filepath,
            "current_size": [img.size[0], img.size[1]],
        })
        print(f"  {name:40s} 4k={size_4k//1024:5d}KB  1k={size_1k//1024:5d}KB")

    # Save the .blend with images now pointing at _1k files on disk.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    total_4k_mb = sum(p["size_4k_kb"] for p in report["processed"]) / 1024
    total_1k_mb = sum(p["size_1k_kb"] for p in report["processed"]) / 1024
    report["total_4k_mb"] = round(total_4k_mb, 1)
    report["total_1k_mb"] = round(total_1k_mb, 1)
    report["count_processed"] = len(report["processed"])
    report["count_skipped"] = len(report["skipped"])
    print(f"TOTAL 4K disk: {total_4k_mb:.1f} MB")
    print(f"TOTAL 1K disk: {total_1k_mb:.1f} MB")

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
