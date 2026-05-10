# Blender Remote Render Pipeline

Scripts for rendering Blender scenes on RunPod while keeping local Blender work light enough for a low-RAM machine.

Heavy project assets for the current Lift Off scene are staged in `workspace/project/`. On RunPod they sync to `/workspace/project/`. Pipeline render scripts sync separately to `/workspace/render-scripts/`.
RunPod new pods will need the running list of shared libraries for blender you can update them with this terminal command: apt update && apt install libsm6 libice6 libegl1 libxrender1 libxi6 libxkbcommon0

## Prerequisites

- Blender locally for scene setup and Eevee/material previews
- RunPod account
- RunPod SSH key configured
- `rsync` available locally and on the pod
- A RunPod network volume mounted at `/workspace`

If RunPod gives you a custom SSH port, set it before running remote scripts:

```bash
export SSH_OPTS="-p 12345"
```

## Quick Start

1. Apply local low-RAM settings in Blender:

```bash
blender -b your_scene.blend -P local/blender_local_config.py
```

2. Sync the pipeline/project folder to a pod with the network volume mounted:

```bash
remote/sync-to-volume.sh <pod-ssh-host> ./workspace/project /workspace/project
```

3. Render one still:

```bash
ssh <pod-ssh-host> "cd /workspace/project && blender -b /workspace/project/blender-output/lift-off/LO_083_spiderverse_downloaded_recipe.blend -P /workspace/render-scripts/render_still.py -- --config /workspace/render-scripts/render_config.json --frame 73"
```

4. Pull rendered output:

```bash
remote/pull-renders.sh <pod-ssh-host> ./renders
```

## Windows No-Rsync Fallback

If local `rsync` is not installed, use the PowerShell tar-over-ssh runner. It does not use `rsync`, `scp`, or `sftp`.

```powershell
.\remote\render-remote-tar.ps1 -HostName "USER@ssh.runpod.io" -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519"
```

This uploads `workspace/project`, uploads `scripts`, renders the configured frame, and pulls `/workspace/output` into `renders/`.

## Config

Edit `scripts/render_config.json` for defaults:

- `resolution_x`, `resolution_y`, `resolution_percentage`
- `samples`
- `use_denoising`
- `denoiser`
- `output_format`
- `color_depth`
- `output_dir`
- `frame`, `frame_start`, `frame_end`

Command-line args after `--` override the config.

## Still Render

```bash
blender -b /workspace/project/blender-output/lift-off/LO_083_spiderverse_downloaded_recipe.blend -P /workspace/render-scripts/render_still.py -- \
  --config /workspace/render-scripts/render_config.json \
  --frame 73 \
  --output-name michelle_hesitation
```

## Animation Render

```bash
blender -b /workspace/project/blender-output/lift-off/LO_083_spiderverse_downloaded_recipe.blend -P /workspace/render-scripts/render_animation.py -- \
  --start 1 \
  --end 60
```

Split frame ranges across pods by running different `--start` and `--end` values.

## Texture Swapping

Work locally with `*_1k.*` textures, then swap to `*_4k.*` on the render pod:

```bash
blender -b scene.blend -P scripts/swap_textures.py -- --direction up --save
```

Swap back:

```bash
blender -b scene.blend -P scripts/swap_textures.py -- --direction down --save
```

## Scene Prep

```bash
blender -b scene.blend -P scripts/scene_prep.py -- --save
```

This syncs subsurf viewport levels to render levels, raises particle viewport percentage to 100, and enables collections tagged with custom property `render_only = true`.

## RunPod Notes

- Use a network volume, standard tier is fine for most projects.
- Keep the volume and pod in the same datacenter region.
- Use a cheap CPU pod for large `rsync` transfers if needed.
- Use an RTX 4090 GPU pod for Cycles final renders.
- Terminate GPU pods after rendering to stop billing.

To send RunPod renders back through GitHub use this command:

git config --global user.email "dhills@gmail.com" && git config --global user.name "Daniel"

cp /workspace/output/<render_file> render-output/<render_file> 

git add render-output/<render_file> 
git commit -m "Add remote test render <render_file>"
git push

## Current Defaults

- Blender target: `4.5.0`
- Output: PNG, 16-bit
- Render mount: `/workspace`
- Project directory on pod: `/workspace/project`
- Output directory on pod: `/workspace/output`
- Current test blend: `/workspace/project/blender-output/lift-off/LO_083_spiderverse_downloaded_recipe.blend`
- First remote test samples: `128`
