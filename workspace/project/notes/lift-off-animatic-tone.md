# "Lift Off" Animatic — Tone & Palette

Scene-specific palette decisions for the cel-shaded animatic referencing the "Lift Off" sample. See `notes/blender-toon-technique-guide.md` for the generic LSM/TipTut technique reference.

## Cast

- **The Cloud** — secondary character, already established. Existing TipTut 4-node cel shader. Mario mouth + green glowing eyes.
- **Michelle** — primary character, new to scene. Mixamo humanoid base with the `Ch03` mesh and a 4K diffuse texture (`Ch03_1001_Diffuse.png`) that already has skin / clothes / sneakers painted in.

## Cloud palette (existing, reference)

Soft 4-band cel ramp, blue-grey shadow → blue midtone → pale cyan light → warm off-white top:
- Cloud shadow: `~#3A4A5E`
- Cloud midtone: `~#5B8AAA`
- Cloud light: `~#A8D8EC`
- Cloud top light: `~#FFF8EB`

Mouth/eyes: green glowing iris with C-bite cutouts; Mario mouth GP overlay.

## Michelle approach: diffuse-driven single-material LSM

Michelle's texture is already a fully-designed streetwear character — dark brown skin, yellow tracksuit/leggings, black-and-white hoodie with red and cyan accents, white sneakers with red trim. She already reads as on-brand for a sneaker-discovery app.

**Decision:** do NOT override her colors with a brand-purple monochrome. Instead, **drive the LSM cel shader from her diffuse texture** so we get a cel-shaded version of her actual character design.

### Single-material LSM stack

One material across her single mesh slot. Five layers:

| Layer | Source | Notes |
|---|---|---|
| **Base body** | `Ch03_1001_Diffuse.png` (4K) | Sampled directly. Yellow tracksuit reads as yellow, skin reads as skin, etc. |
| **Main light** | Diffuse × 1.18 brightness | Cel-lit version of the diffuse |
| **Shadow** | Diffuse × 0.55 brightness, slightly cooler hue | Cel-shadowed version |
| **Specular halftone** | Warm yellow tint `#FFE56D` over diffuse-driven mask | Ties scene together; only on the lit side |
| **Rim accent** | Warm yellow `#FFE56D` | Unified across the whole figure |

The cel ramp (Constant ColorRamp on Shader-to-RGB output) splits into three bands at:
- 0.0 → 0.35 → shadow
- 0.35 → 0.65 → main
- 0.65 → 1.0 → light + halftone

### Eyes — cyan callback to the cloud

Michelle's diffuse already has cyan accents on her hoodie. Reinforce by giving her **cyan irises** as a separate eye material if/when we identify the eye geometry — but only after the main shader works. Skip on first pass.

### Color grade (subtle)

Apply a final-stage warm tint at 5–10% strength to push the whole figure toward the "Lift Off sunset" key light:
- Multiply by `#FFE0C8` at 0.10 mix factor

This is implemented inside the single-material LSM at the very end of the node chain (post-rim, pre-output) so the whole figure shares the grade.

## Why this works

- **Michelle's character integrity is preserved.** Yellow tracksuit + AJ-style sneakers + cyan hoodie accents are perfect HypeFeed mascot energy — overriding them with purple would be a downgrade.
- **The cel shading + warm rim is what marries her to the cloud's world.** Same rim color across both characters' shaders unifies them.
- **Single material slot** matches Michelle's actual mesh structure (one slot in the FBX). Avoids fragile mesh-splitting.
- **Diffuse texture as base input** is the production-standard approach for cel-shading textured characters (vs. flat-color cel which only works on simple props).

## Lighting plan

- **Key light**: warm tungsten-ish (`~#FFD28A`) at strength 3-5. Camera-right and slightly above. Drives the cel ramp's split.
- **Fill light**: cool blue (`~#5B8AAA`) at strength 0.5-1. Camera-left, low. Pulls the cloud's tonal influence into the shadow side.
- **Rim light**: NOT a real light — the LSM rim layer simulates this in shader.

## Risks

- **Diffuse texture could clash with cel shading.** If the texture is too detailed (lots of fine paint marks), the cel ramp will quantize them weirdly. Mitigation: bias the ramp toward fewer, broader bands (3 zones instead of 5).
- **Black areas in the diffuse render to pure-black cel shadow** which can crush. Mitigation: clamp the shadow band's minimum to a dark navy (`~#1A1820`) so blacks still have some hue.
- **Yellow tracksuit may bloom too hot in light pass.** Mitigation: the main-light multiplier is conservative at 1.18 (not 1.5+).
