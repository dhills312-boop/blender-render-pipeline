"""Identify all CC4 texture nodes whose image references don't match
their expected material+role.

The CC4 export sometimes ships with crossed references where, e.g., a
DIFFUSE node in Skin_Body material is pointing at Std_Upper_Teeth_Diffuse.

This script:
1. Walks every material on Body.
2. For each Image Texture node whose name has a CC4 role tag (DIFFUSE,
   NORMAL, ROUGHNESS, etc.), figures out the expected texture name based
   on the material name + the role.
3. Reports mismatches.
4. For each mismatch, suggests the correct texture from the available
   images on disk.
"""

import os
import re
import sys
import bpy

# Map CC4 material names to the texture name prefix on disk.
MATERIAL_TO_TEX_PREFIX = {
    "Skin_Head": "Std_Skin_Head",
    "Skin_Body": "Std_Skin_Body",
    "Skin_Arm": "Std_Skin_Arm",
    "Skin_Leg": "Std_Skin_Leg",
    "Eye_L": "Std_Eye_L",
    "Eye_R": "Std_Eye_R",
    "Cornea_L": "Std_Cornea_L",
    "Cornea_R": "Std_Cornea_R",
    "Eye_Occlusion_L": "Std_Eye_Occlusion_L",
    "Eye_Occlusion_R": "Std_Eye_Occlusion_R",
    "Tearline_L": "Std_Tearline_L",
    "Tearline_R": "Std_Tearline_R",
    "Eyelash": "Std_Eyelash",
    "Tongue": "Std_Tongue",
    "Upper_Teeth": "Std_Upper_Teeth",
    "Lower_Teeth": "Std_Lower_Teeth",
    "Nails": "Std_Nails",
}

# CC4 role-tag regex: extract role from node name like
# 'cc3iid_(DIFFUSE)_v2.2.3_1013'
ROLE_RE = re.compile(r"cc3iid_\(([A-Z_]+)\)_v")


def role_from_node_name(name):
    m = ROLE_RE.search(name)
    return m.group(1) if m else None


def main():
    body = bpy.data.objects.get("Body")
    if not body:
        print("No Body")
        sys.exit(1)

    # Index all images by name (so we can match candidates).
    all_image_names = sorted(bpy.data.images.keys())

    print(f"Materials on Body: {[s.material.name for s in body.material_slots if s.material]}")
    print()

    mismatches = []
    for slot in body.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        prefix = MATERIAL_TO_TEX_PREFIX.get(mat.name)
        if not prefix:
            continue  # not in our known list

        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE":
                continue
            role = role_from_node_name(node.name)
            if not role:
                continue
            img = node.image
            if not img:
                continue
            img_name = img.name

            # Expected: image name should start with the material's prefix
            # AND contain the role keyword (case-insensitive).
            expected_prefix = prefix
            role_lower = role.lower()
            # Some roles map to slightly different texture name patterns:
            # NORMAL -> Normal, ROUGHNESS -> roughness, MICRONORMAL -> MicroN, etc.
            role_aliases = {
                "DIFFUSE": ["Diffuse"],
                "NORMAL": ["Normal"],
                "ROUGHNESS": ["roughness", "Roughness"],
                "METALLIC": ["metallic", "Metallic"],
                "AO": ["ao"],
                "OPACITY": ["Opacity"],
                "SSS": ["SSSMap"],
                "TRANSMISSION": ["TransMap"],
                "MICRONORMAL": ["MicroN"],
                "MICRONMASK": ["MicroNMask"],
                "RGBAMASK": ["RGBAMask"],
                "BCBMAP": ["BCBMap"],
            }
            keywords = role_aliases.get(role, [role.title()])

            ok = img_name.startswith(expected_prefix) and any(
                k in img_name for k in keywords
            )

            if not ok:
                # Try to find a candidate replacement.
                candidates = []
                for cand in all_image_names:
                    if cand.startswith(expected_prefix) and any(
                        k in cand for k in keywords
                    ):
                        candidates.append(cand)
                mismatches.append({
                    "material": mat.name,
                    "node_name": node.name,
                    "role": role,
                    "current_image": img_name,
                    "expected_prefix": expected_prefix,
                    "expected_keywords": keywords,
                    "candidates": candidates,
                })

    print(f"Found {len(mismatches)} mismatched image references:\n")
    for m in mismatches:
        print(f"  [{m['material']}] {m['node_name']}")
        print(f"    role: {m['role']}")
        print(f"    current image: {m['current_image']}")
        print(f"    expected to start with: {m['expected_prefix']}")
        print(f"    expected to contain one of: {m['expected_keywords']}")
        if m["candidates"]:
            print(f"    available candidate(s): {m['candidates']}")
        else:
            print(f"    NO CANDIDATE FOUND (texture may be missing entirely)")
        print()


if __name__ == "__main__":
    main()
