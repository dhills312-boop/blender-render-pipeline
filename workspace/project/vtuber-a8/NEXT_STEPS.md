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

1. Use the remote config for a first GPU render of the current visual state.
2. In interactive Blender, decide whether the visible anatomy detail lives only on `Body_Sculpt` or has been transferred onto `Body`.
3. For VRChat export prep, hide or exclude `Body_Sculpt` from export once the desired detail is baked/transferred.
4. Reduce materials/texture memory after the visual design is locked: atlas body-related materials, trim unused SuperSkin brush images, and keep only export-needed 1k/2k maps.

## Hair Ombre Test

The current hair is likely temporary. To make a non-destructive white-roots to
black-tips ombre test on the remote pod, run:

```powershell
.\remote\run-blender-script-tar.ps1 `
  -HostName "USER@ssh.runpod.io" `
  -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519" `
  -BlendFile "vtuber-a8/a6_v13_anatomy_p1.blend" `
  -BlenderScript "a8_apply_ombre_hair.py" `
  -IncludeAssetLibrary `
  -ScriptArgs @(
    "--src", "/workspace/Asset_Addon_Library/HairCards/DarkSea.png",
    "--ombre", "/workspace/project/vtuber-a8/textures/WhiteBlackOmbre.png",
    "--out-blend", "/workspace/project/vtuber-a8/a6_v14_hair_ombre_test.blend"
  )
```

Then render the generated blend:

```powershell
.\remote\render-remote-tar.ps1 `
  -HostName "USER@ssh.runpod.io" `
  -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519" `
  -BlendFile "vtuber-a8/a6_v14_hair_ombre_test.blend" `
  -RenderScript "render_still.py" `
  -ConfigFile "render_config.vtuber-a8.json" `
  -LocalRendersDir ".\render-output\vtuber-previews"
```
