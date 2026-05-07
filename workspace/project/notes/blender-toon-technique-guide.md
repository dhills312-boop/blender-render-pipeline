# Blender Toon Technique Guide

Generic reference for applying the project's two cel-shader recipes to any imported model. Use this when bringing in a new asset (e.g., a fresh Mixamo character or a downloaded GLB) and decide which shader to apply.

## When to use which shader

- **TipTut 4-node cel shader** — simple subjects, large flat surfaces, when you want a soft cel look with 3–4 broad tone bands. Good for clouds, props, simple props, foliage.
- **LSM-style layer mask shader** — the "hero" shader. Use it on the main character or focal subject. Costs more nodes and more iteration but produces comic-book quality with halftone dots, rim light, and texture-driven highlights.

Both shaders work in Eevee and Cycles but were tuned for Eevee.

## TipTut 4-node cel shader

The four-node setup from the TipTut video:

`Principled BSDF -> Shader to RGB -> Constant ColorRamp -> Material Output`

- Use a `Constant ColorRamp` (NOT linear) to get hard cel transitions.
- Move the ColorRamp stops closer together for sharper/smaller bands.
- Move them farther apart for broader flat-color regions.
- Keep three or four tones max — adding more makes the model read painterly instead of cel.
- Change the key light position before over-editing the ramp. `Shader to RGB` is reading light direction, so bad light placement makes the ramp feel inaccurate.

## LSM-style layer mask shader

An extrapolated LSM-style node stack from the Mike Daviss video. Build the material with these named control nodes so it's easy for a non-technical editor to tune:

Color controls (Diffuse Color or Emission inputs into a Mix node):

- `Base [subject] color` — the local/object color underneath everything.
- `Main light color` — the large cel-lit region driven by the toon mask.
- `Alpha highlight color` — scratch/mark highlights driven by the alpha texture mask.
- `Specular halftone color` — dotted specular layer.
- `Final rim light / outline color` — the last layer; rim light belongs at the END of the stack per the source video.

Mask controls:

- `Main Light mask range / soft shadow` — adjust the two ramp stops to widen or tighten the main light.
- `Alpha texture: highlight scratches/marks` — increase Scale for smaller/busier marks; decrease for broader patches.
- `Alpha mask clamps highlight marks` — raise the white stop to show fewer marks; lower to show more.
- `Specular 1 range` — controls where the soft specular glow appears.
- `Halftone texture for specular opacity` — increase Scale for smaller dots; decrease for bigger comic dots.
- `Halftone opacity mask` — tighten the ramp stops for harder dots.
- `Rim/outline layer follows camera-facing X range` — push inner stops inward for a thicker rim/outline band, outward for a thinner band.

Layer order is significant. Stack from bottom up:

1. Base color
2. Main light (toon-mask-driven)
3. Alpha highlight (alpha-texture-driven)
4. Specular halftone (halftone-texture-driven)
5. Rim/outline (camera-facing-driven)

## Procedure for a brand new model

1. **Import** the model. If it's a Mixamo FBX, expect scale 0.01 and a 90° X rotation on the armature — apply transforms before anything else (`Object > Apply > All Transforms`).
2. **Inspect mesh layout.** If the asset arrives as multiple mesh objects, decide whether to keep them split (per-part shading) or join into one. The LSM shader can handle multi-slot materials but it's cleaner with a single mesh.
3. **Strip baked materials.** Mixamo and most asset packs ship with diffuse-only Principled BSDF materials. Remove or replace these — the cel shader expects an empty starting point.
4. **Pick TipTut or LSM** based on the subject's role in the shot (see "When to use which" above).
5. **Light first, shade second.** Place at least a key light and a fill light before tuning the ramp. The ramp's perceived correctness depends on where the light is.
6. **Set the palette per the tone direction in the scene's notes.** Each scene should have its own palette block — see the project's scene notes (e.g. `notes/lift-off-animatic-tone.md`) for the active palette.
7. **Add Grease Pencil overlays last** (see next section). GP strokes go on top of the shaded surface, not into it.

## Grease Pencil and stroke editing

- Create separate layers per pass: `outline`, `face`, `accent`, `hatch`. Tune opacity/thickness independently per layer.
- Set Stroke Placement to `Surface`, Offset to `0`. Draw while facing the surface as directly as possible.
- In the stroke material, uncheck `Use Lights` — the line color should stay graphic and flat.
- Pen pressure should affect Radius, not Opacity/Strength, unless you intentionally want faded sketch marks.
- Keep strokes slightly toward the camera if they flicker or disappear from z-fighting (`SURFACE_OFFSET_TOWARD_CAMERA = -0.004` is a known good value).
- Parent the stroke object to the model after drawing, then use object transforms for broad repositioning.
- Use fewer, heavier strokes for a cel-shaded look. Too many fine strokes read as sketch rendering instead of cartoon shading.

## Palette guidance (generic)

Each scene should declare its own palette in scene-specific notes. General principles:

- Pick **3–4 tones** for the LSM stack: shadow, midtone/base, light, highlight/accent.
- Avoid making every tone a different shade of the same color — at least one tone (often the highlight or rim) should be in a different hue family to give the cartoon read.
- Rim/outline color should be a very dark version of the subject's hue, NOT pure black, so it harmonizes with the base.
- Strokes should be near-black in the same hue family as the subject's shadow tone.

## Reference videos

- TipTut, "Basic Blender Toon - Cel Shader Tutorial 2D Grease Pencil + 3D Modelling" — the 4-node recipe.
- Mike Daviss, "LSM-style layer mask shader" — the multi-layer comic recipe.
