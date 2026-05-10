# vtuber-a8 Current State

Latest checkpoint inspected:

- `a6_v13_anatomy_p1.blend`
- Local audit: `audit_reports/a6_v13_audit.json`
- Remote render config: `../../scripts/render_config.vtuber-a8.json`
- `Body_Sculpt` contains hand-authored anatomy work and should be treated as protected source art.

## What The Audit Says

- Total mesh tris: 517,986
- `Body_Sculpt` alone: 449,472 tris, visible, render-enabled
- Without `Body_Sculpt`, visible avatar geometry is roughly 68.5k tris before any other cleanup
- Materials: 21 unique
- Skinned meshes: 10
- Primary armature bones: 725
- Shape keys: 635, with common VRChat visemes detected
- Texture estimate: 356 MB

## Render Pipeline Command

PowerShell tar uploader:

```powershell
.\remote\render-remote-tar.ps1 `
  -HostName "USER@ssh.runpod.io" `
  -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519" `
  -BlendFile "vtuber-a8/a6_v13_anatomy_p1.blend" `
  -RenderScript "render_still.py" `
  -ConfigFile "render_config.vtuber-a8.json" `
  -LocalRendersDir ".\render-output\vtuber-previews"
```

Bash wrapper:

```bash
remote/render-remote.sh "$POD_HOST" \
  "vtuber-a8/a6_v13_anatomy_p1.blend" \
  "render_still.py" \
  "render_config.vtuber-a8.json"
```

## Suggested Next Pass

1. Preview the Body-to-Body_Sculpt conform pass as an A/B comparison. This
   creates a `Body_Sculpt_Conform` shape key in memory and renders the conformed
   rigged `Body` next to the original `Body_Sculpt` reference without saving an
   experiment blend.
2. If the proportions look right, save an accepted checkpoint from the same
   conform script with `--out-blend`.
3. Reduce/separate inner thighs in interactive Blender before finalizing the
   conform, because the current Body_Sculpt thigh clearance audit reports
   effectively touching geometry.
4. Do the normal/detail bake as an interactive Blender step after the silhouette
   transfer is accepted.
5. Reduce materials/texture memory after the visual design is locked: atlas
   body-related materials, trim unused SuperSkin brush images, and keep only
   export-needed 1k/2k maps.

## Body Conform Preview

Run a comparison preview without saving a new blend:

```powershell
.\remote\run-blender-script-tar.ps1 `
  -HostName "USER@ssh.runpod.io" `
  -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519" `
  -BlendFile "vtuber-a8/a6_v13_anatomy_p1.blend" `
  -BlenderScript "a8_render_conform_preview.py" `
  -ScriptArgs @(
    "--config", "/workspace/render-scripts/render_config.vtuber-a8.json",
    "--blend-file", "/workspace/project/vtuber-a8/a6_v13_anatomy_p1.blend",
    "--output-dir", "/workspace/output",
    "--output-name", "a8_body_conform_preview",
    "--report", "/workspace/project/vtuber-a8/audit_reports/body_conform_preview_report.json",
    "--compare-sculpt"
  )
```

After the pod render, copy `/workspace/output/a8_body_conform_preview.png` into
`render-output/vtuber-previews/` only if it is useful to keep.
