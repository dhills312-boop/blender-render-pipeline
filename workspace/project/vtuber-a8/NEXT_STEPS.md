# vtuber-a8 Current State

## Local Blend Checkpoints

Keep these local as the active working milestones:

- `a6_v13_anatomy_p1.blend`
  - protected sculpt/source-art file
  - contains hand-authored `Body_Sculpt` anatomy work
- `a6_v16_body_conformed_cleanup2.blend`
  - accepted body proportion checkpoint
- `a6_v17_non_skin_shader_cleanup.blend`
  - material/shader cleanup checkpoint
- `a6_v18_streetwear_visual_pass.blend`
  - rollback visual pass before clothing fitting
- `a6_v23_manual_clothing_fit_rough.blend`
  - user-authored rough clothing fit checkpoint
- `a6_v25_top_cleanup_keep_skirt.blend`
  - current clothing checkpoint
  - top cleaned into `CLEAN_StreetwearTop_v25`
  - skirt and underwear preserved from the rough pass
- `a6_v29_full_clothing_contact.blend`
  - current full-preview clothing/contact checkpoint
  - uses `FINAL_StreetwearTop_Contact`, `FINAL_PleatedSkirt_Contact`, and
    `FINAL_UnderwearSupport_Contact`
  - clothing was nudged outward from `Body` with a closest-point contact audit
    so it clears/touches instead of clipping

Tiny LFS-pointer blends still exist locally but are not meaningful disk users:

- `a6_v01_cleanup.blend`
- `a6_v02_textures_1k.blend`
- `a6_v04_sculpted.blend`
- `a6_v07_chest_uv_prep.blend`
- `a6_v09_diffuse_fixed.blend`
- `a6_v12_a4_textures_ported.blend`

## Archived Intermediates

Archived to Drive on 2026-05-12:

`G:\My Drive\VS_Code_Scripts\blender-render-pipeline-archives\vtuber-a8\2026-05-12-clothing-intermediates`

- `a6_v20_clothing_fit_light_30.blend`
- `a6_v20_clothing_fit_light_30.blend1`
- `a6_v21_clothing_edit_frozen.blend`
- `a6_v22_clothing_workroom.blend`
- `a6_v22_clothing_workroom.blend1`
- `a6_v24_manual_clothing_cleanup.blend`
- `a6_v24_manual_clothing_cleanup.blend1`

These were removed from the local project folder after archiving, freeing about
948 MiB locally.

## Active Clothing State

Use `a6_v29_full_clothing_contact.blend` next for full-avatar review.
Use `a6_v25_top_cleanup_keep_skirt.blend` as the clothing source fallback.

- `CLEAN_StreetwearTop_v25` is the cleaned top.
- `FIT_StreetwearTop` is hidden as backup.
- `FIT_PleatedSkirt_Shrinkwrap` is the rough-pass skirt state.
- `FIT_Underwear_Support.001` is the rough-pass underwear state.
- Do not use `v24` as active clothing state; it baked an unwanted skirt
  shrinkwrap result.
- In `v29`, the active visible clothing is the `FINAL_*_Contact` set.

## Next Work

1. Inspect `a6_v29_full_clothing_contact.blend`.
2. If the contact pass is accepted, treat the `FINAL_*_Contact` clothing objects
   as the active outfit.
3. Keep chains manual until the outfit fit is locked.
4. Avoid more live physics/shrinkwrap passes unless the file is stripped down
   to only body + clothing.
