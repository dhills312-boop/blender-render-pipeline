import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
TEXTURES = PROJECT / "textures"
SRC = PROJECT / "a6_v41_decals_fur_prep.blend"
DST = PROJECT / "a6_v42_relinked_texture_paths.blend"
REPORT = PROJECT / "a6_v42_relinked_texture_paths_report.json"


def norm(name):
    return name.lower().replace("\\", "/")


def build_texture_index():
    by_name = {}
    for path in TEXTURES.rglob("*"):
        if path.is_file():
            by_name.setdefault(path.name.lower(), path)
    return by_name


def candidates_for_image(image):
    names = []
    if image.filepath:
        names.append(Path(image.filepath.replace("\\", "/")).name)
    if image.name:
        names.append(image.name)
        if "." in image.name:
            # Blender often appends .001 to duplicate image datablocks.
            stem, suffix = image.name.rsplit(".", 1)
            if suffix.isdigit():
                names.append(stem)
    seen = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def relpath_for_blender(path):
    return bpy.path.relpath(str(path))


bpy.ops.wm.open_mainfile(filepath=str(SRC))

texture_index = build_texture_index()
rows = []
fixed = 0
still_missing = 0
already_ok = 0

for image in bpy.data.images:
    if image.type != "IMAGE" or image.source != "FILE":
        continue
    before = image.filepath
    resolved = Path(bpy.path.abspath(before)) if before else None
    exists_before = bool(resolved and resolved.exists())

    matched = None
    for candidate in candidates_for_image(image):
        key = candidate.lower()
        if key in texture_index:
            matched = texture_index[key]
            break

    if matched:
        relative = relpath_for_blender(matched)
        if image.filepath != relative:
            image.filepath = relative
            fixed += 1
        else:
            already_ok += 1
        status = "relinked" if image.filepath == relative else "matched"
    elif exists_before and before.startswith("//"):
        already_ok += 1
        status = "already_relative_exists"
    elif exists_before:
        # Convert local absolute paths to blend-relative when they live inside the project.
        try:
            resolved.relative_to(PROJECT)
            image.filepath = relpath_for_blender(resolved)
            fixed += 1
            status = "absolute_to_relative"
        except ValueError:
            status = "absolute_external_exists"
            already_ok += 1
    else:
        still_missing += 1
        status = "missing_no_local_match"

    rows.append(
        {
            "image": image.name,
            "before": before,
            "after": image.filepath,
            "exists_before": exists_before,
            "matched": str(matched) if matched else None,
            "status": status,
        }
    )

report = {
    "source": str(SRC),
    "saved": str(DST),
    "texture_root": str(TEXTURES),
    "fixed_or_normalized": fixed,
    "already_ok": already_ok,
    "still_missing": still_missing,
    "missing_images": [row for row in rows if row["status"] == "missing_no_local_match"],
    "all_images": rows,
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(DST))
print(json.dumps({k: v for k, v in report.items() if k not in {"all_images", "missing_images"}}, indent=2))
print(f"MISSING_NO_LOCAL_MATCH: {still_missing}")
