# LBS Arcane / Cloud / Crosshatch Production Notes

Actionable notes distilled from the user-provided transcripts for the Lift Off Blender pass.

## Arcane Style: What Matters

Arcane-style lighting is not just a colored light rig. The main lesson is that almost everything is artfully assembled per shot:

- Backgrounds are often painted or camera-projected from the shot camera.
- Character lighting may be real light, texture color correction, painted shadow, projected detail, or composited layers depending on the shot.
- Specular highlights are frequently painted and may stay locked to the surface or be animated by hand.
- Shadows can be projected or painted onto the character so they move with the body as if part of the texture.
- The shot camera is the source of truth. Details that look correct from the render camera matter more than details that work from every angle.

For Lift Off, do not try to solve the Arcane look with a universal shader or generic warm/cool lights. Use a shot-specific stack:

1. Lock animation and camera.
2. Use real lights only as a base reference.
3. Add shot-specific color correction / shadow / highlight layers.
4. Use camera projection or painted overlay layers for hero frames.
5. Add print/screentone treatment at the very end.

## Arcane Camera Projection Workflow

Core camera projection loop:

1. Set render camera and resolution.
2. Viewport render from the camera.
3. Paint over in Photoshop / Clip Studio / Blender texture paint.
4. In Blender, select objects and `U > Project From View`.
5. Use an emission/image texture material for projected paint.
6. For secondary angles, add a second UV map and second projection camera.
7. Mix the second projection over the first using PNG alpha.
8. If needed, bake the projection into an unwrapped texture using Blender texture paint external edit / apply.

Important details:

- Use Standard color management when checking projection/image consistency.
- Set image texture extension to clip/extend when projection edges repeat in bad ways.
- Add enough subdivisions to projected planes/geometry or projection will stretch weirdly.
- For moving characters, create transparent overlay images as layers and animate opacity if needed.
- Turn off bloom before projection/paint capture, then re-enable later if desired.

## Arcane Character Shading / Texturing

The LBS tutorial uses the shader as a base-texture generator, not only as the final shader:

- Start with flat local colors.
- Add soft key shadow, specular, and ambient occlusion layers.
- Bake/project that result into a texture.
- Refine with painted details and scratches.
- For shot-specific lighting, use RGB curves/gradients/projections over the base texture.

For Michelle:

- Preserve her original texture identity.
- Avoid replacing the whole material with a procedural shader.
- If adding Arcane lighting, prefer texture/projected overlays: shadow shapes, warm edge paint, local color correction.
- Painted eye/specular glints can be a separate PNG/card/layer, not physically correct specular.

## Arcane Lighting Tricks

Lighting pass should be shot-dependent:

- Sometimes use real key/rim lights.
- Sometimes use base texture plus RGB curves.
- Sometimes paint a shadow texture using a darker local color and blend with Darken-like logic.
- Bright light regions can be projected or painted if real lights do not land artistically.
- Rim/spec accents should be intentional and graphic, not purely physical.

For Lift Off:

- Camera A roof intro: likely more painterly background/camera projection than dynamic light.
- Camera B load/hold/jump: face/torso shadow and warm edge accents can be projected/painted from front camera.
- Camera C hang time: sky/backdrop can be camera-painted; Michelle can receive a separate fall-in rim/spec pass.

## LBS Hair Notes

The Arcane hair tutorial is useful if Michelle’s hair needs improvement later:

- Large painted-looking strands made from particle hair around one parent hair.
- Use Hair Info intercept for root-to-tip gradient.
- Use noise to break up color.
- Use transparency at root/tip for painted stroke feel.
- Use tangent normal into Diffuse/Specular/Translucent BSDF normals for broad painterly gradients.
- Add soft specular with Specular BSDF > Shader to RGB > ColorRamp.
- Break specular with noise-driven normal offset.
- Add rim using Translucent BSDF lit from behind, often with a point light.

Current Michelle hair is textured mesh, not particle hair. Treat this as optional later polish, not current priority.

## LBS Painterly Cloud Notes

Cloud technique is not true volumetrics. It fakes volume with stacked transparent textured planes:

- Diffuse BSDF + Transparent BSDF mixed by painted cloud alpha.
- Project cloud texture from front.
- Use arrayed planes for depth.
- Use custom normal map from metaballs rendered with normal-map matcap.
- Feed normal map into Diffuse normal.
- Diffuse > Shader to RGB > ColorRamp creates toon cloud tones.
- Use ambient occlusion for darker internal watercolor edges.
- Shape transparency with spherical gradient + noise.
- Add 3D soft color gradients using empties, not only lights.
- Use collection instances for multiple cloud pieces.
- Object viewport color can drive per-instance variation via Object Info.

For Lift Off:

- Current clouds are temporary stand-ins.
- Later, replace with stacked-plane painterly cloud pieces.
- Keep cloud friend out until explicitly reintroduced.

## Crosshatch / Screentone Notes

The downloaded crosshatch shaders are procedural and light-dependent. Their useful mechanics:

- Hatching uses Wave Texture through ColorRamp.
- Cluster rotation uses Voronoi > grayscale ramp > Vector Math into Mapping rotation.
- Patch hatching layers multiple hatch systems with offset Voronoi locations.
- Crosshatch combines two or more wave patterns with Multiply.
- Dotted line shader uses wave lines broken up by noise.
- Manga screentone uses Voronoi with randomness 0, often Chebychev for diamonds.
- Screentone uses Window coordinates, so it must be tuned to camera/render aspect ratio.
- Underpaint is Diffuse > Shader to RGB > ColorRamp with soft gray tones.
- Hatch/screentone can be combined with underpaint using Multiply.

For Lift Off:

- Do not use full-scene live procedural hatching during animation/camera work.
- Add print treatment at final render stage.
- Dots should be local-color-aware, not universally magenta.
- Magenta can be an accent ink, but dot color should often relate to the underlying character color.
- Crosshatching should be sparse/random and shadow-biased.
