"""Swap names of Channel0 and UV_chest UV layers on Body.

User accidentally ran Smart UV Project on Channel0 (original CC4 atlas)
instead of UV_chest. Channel0 now has the new packed torso unwrap, and
UV_chest has the original CC4 atlas (because UV_chest was created as a
copy of Channel0 in the prep script).

Swap their names so:
- Channel0 = original CC4 atlas (referenced by all CC4 textures)
- UV_chest = new packed torso unwrap (for our decal texture)

Verifies the swap by re-checking the UV ranges.

Run:
    blender -b a6_v07b_chest_uv_prep.blend -P swap_uv_layers.py -- \
        --out-blend <path> --report <path>
"""
import argparse
import json
import os
import sys
import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out-blend", required=True)
    p.add_argument("--report", required=True)
    return p.parse_args(argv)


def get_chest_uv_range(body, layer_name):
    me = body.data
    if layer_name not in me.uv_layers:
        return None
    uv_data = me.uv_layers[layer_name].data
    vg = body.vertex_groups.get("chest_faces")
    if not vg:
        return None
    chest_verts = set()
    for v in me.vertices:
        for g in v.groups:
            if g.group == vg.index:
                chest_verts.add(v.index)
                break
    us, vs = [], []
    for poly in me.polygons:
        if any(vi in chest_verts for vi in poly.vertices):
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                us.append(uv_data[li].uv.x)
                vs.append(uv_data[li].uv.y)
    if not us:
        return None
    return {
        "u_range": [min(us), max(us)],
        "v_range": [min(vs), max(vs)],
        "is_packed_01": max(us) <= 1.05 and min(us) >= -0.05,
    }


def main():
    args = parse_args()
    body = bpy.data.objects.get("Body")
    if not body:
        print("ERROR: no Body")
        sys.exit(1)
    me = body.data
    print(f"UV layers before: {[u.name for u in me.uv_layers]}")

    if "Channel0" not in me.uv_layers or "UV_chest" not in me.uv_layers:
        print("ERROR: Need both Channel0 and UV_chest layers to swap.")
        sys.exit(1)

    # Read state before swap.
    before_ch0 = get_chest_uv_range(body, "Channel0")
    before_uvc = get_chest_uv_range(body, "UV_chest")
    print(f"\nBefore swap:")
    print(f"  Channel0  chest UV range: {before_ch0}")
    print(f"  UV_chest  chest UV range: {before_uvc}")

    # Swap by renaming via temp.
    me.uv_layers["Channel0"].name = "_tmp_swap_"
    me.uv_layers["UV_chest"].name = "Channel0"
    me.uv_layers["_tmp_swap_"].name = "UV_chest"

    # After swap.
    after_ch0 = get_chest_uv_range(body, "Channel0")
    after_uvc = get_chest_uv_range(body, "UV_chest")
    print(f"\nAfter swap:")
    print(f"  Channel0  chest UV range: {after_ch0}")
    print(f"  UV_chest  chest UV range: {after_uvc}")

    # Set Channel0 as active for render (CC4 textures reference it).
    me.uv_layers.active_index = me.uv_layers.find("Channel0")
    me.uv_layers["Channel0"].active_render = True

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=args.out_blend, copy=False)
    print(f"\nSAVED: {args.out_blend}")

    rep = {
        "input": bpy.data.filepath,
        "output": args.out_blend,
        "before": {"Channel0": before_ch0, "UV_chest": before_uvc},
        "after": {"Channel0": after_ch0, "UV_chest": after_uvc},
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    print(f"REPORT: {args.report}")

    # Validation: UV_chest should now be packed [0,1], Channel0 should be UDIM.
    if after_uvc and after_uvc["is_packed_01"]:
        print("\n✓ UV_chest is now packed in [0,1] — correct")
    else:
        print("\n✗ UV_chest is NOT packed [0,1] — swap may not have worked")
    if after_ch0 and not after_ch0["is_packed_01"]:
        print("✓ Channel0 has UDIM range — correct (CC4 textures will work)")
    else:
        print("✗ Channel0 is unexpectedly packed [0,1] — CC4 textures may break")


if __name__ == "__main__":
    main()
