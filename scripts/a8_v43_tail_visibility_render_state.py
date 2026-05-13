import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workspace" / "project" / "vtuber-a8"
SRC = PROJECT / "a6_v42_relinked_texture_paths.blend"
DST = PROJECT / "a6_v43_tail_visible_render_state.blend"
REPORT = PROJECT / "a6_v43_tail_visible_render_state_report.json"


def collection_chain(obj):
    chains = []

    def walk(collection, path):
        if obj.name in collection.objects:
            chains.append(path + [collection])
        for child in collection.children:
            walk(child, path + [collection])

    walk(bpy.context.scene.collection, [])
    return chains


bpy.ops.wm.open_mainfile(filepath=str(SRC))
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode="OBJECT")

tail = bpy.data.objects.get("Tail")
if not tail:
    raise RuntimeError("Missing Tail object")

before = {
    "hide_viewport": tail.hide_viewport,
    "hide_render": tail.hide_render,
    "hide_get": tail.hide_get(),
    "visible_get": tail.visible_get(),
    "materials": [slot.material.name if slot.material else None for slot in tail.material_slots],
}

tail.hide_viewport = False
tail.hide_render = False
tail.hide_set(False)

collections_touched = []
for chain in collection_chain(tail):
    for collection in chain:
        if collection.hide_viewport or collection.hide_render:
            collections_touched.append(
                {
                    "collection": collection.name,
                    "hide_viewport_before": collection.hide_viewport,
                    "hide_render_before": collection.hide_render,
                }
            )
        collection.hide_viewport = False
        collection.hide_render = False

after = {
    "hide_viewport": tail.hide_viewport,
    "hide_render": tail.hide_render,
    "hide_get": tail.hide_get(),
    "visible_get": tail.visible_get(),
    "materials": [slot.material.name if slot.material else None for slot in tail.material_slots],
}

report = {
    "source": str(SRC),
    "saved": str(DST),
    "tail_before": before,
    "tail_after": after,
    "collections_touched": collections_touched,
    "note": "Forces Tail and its containing collection path visible/renderable for pod material review renders.",
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(DST))
print(json.dumps(report, indent=2))
