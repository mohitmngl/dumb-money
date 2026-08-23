Upgrade the existing browser 3D chair configurator in this folder. Do not create a new project. Modify the existing files only as needed.

Target folder:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_parametric_heritage_luxury_indian_lobby_chair

Reference image:

reference_heritage_luxury_indian_lobby_chair.png

The current result is a useful prototype but does not yet match the reference image closely enough. Upgrade it so it looks much more like a premium animated-feature-quality 3D product render of the reference chair.

Most important visual target:

- Deep emerald green velvet upholstery by default, not magenta, ivory, or flat color.
- Luxurious royal Indian hotel lobby chair, not a simple blocky chair.
- High scalloped Mughal/Rajasthani palace-arch back with multiple rounded lobes, not a plain rectangle or simple pointed arch.
- Thick rounded seat cushion with visible softness, bevels, piping, and velvet texture.
- Quilted diamond cushion/back panel with small gold buttons/studs at intersections.
- Curved dark polished wood arms that sweep upward and forward, with gold/brass trim.
- Ornate jali lattice side panels with repeated quatrefoil/arch/diamond shapes, not a plain square grid.
- Glossy dark carved teak/rosewood frame with procedural wood grain.
- Rich polished gold/brass trim around the arch, arms, front rail, side panels, and legs.
- Gemstone-like emerald accents on arm fronts and lower front legs if practical.
- Decorative gold crest/ornament at top center of back if practical.
- Tapered/cabriole-style legs with gold caps, not straight plain cylinders only.
- Marble lobby floor with reflection/shadow.
- Warm hotel lobby background with columns, arches, wall lamps, and depth.
- Cinematic warm key lighting, soft fill, rim light, contact shadows, and material highlights.

Required improvements:

1. Replace the default upholstery preset with emerald velvet.
2. Improve chair silhouette:
   - Add a multi-lobed scalloped arch back outline.
   - Add rounded cushion geometry and bevels.
   - Add curved arms using tubes/curves or segmented geometry.
3. Improve jali:
   - Replace plain square grid with more ornate repeating motif.
   - Use visible gold/brass lattice material.
4. Improve materials:
   - Velvet must have procedural fine nap/noise texture and visible fabric grain.
   - Wood must have procedural grain and glossy dark finish.
   - Brass/gold must be metallic with highlights.
5. Improve cushion details:
   - Diamond quilting on back and/or pillow.
   - Piping cylinders/curves around cushion edges.
   - Gold studs/buttons.
6. Improve environment:
   - Default environment should be five-star hotel lobby.
   - Add marble floor, warm columns/arches, side wall lamp glow, and blurred/depth-like background geometry.
7. Improve lighting:
   - Warm area/key light.
   - Fill light.
   - Rim/back light.
   - Contact shadow-like grounding.
   - Optional bloom/glow if robust.
8. Keep controls working:
   - Rotate/zoom.
   - Change upholstery/material presets.
   - Change dimensions.
   - Toggle studs, quilting, piping, exploded view if present.
   - Environment selector.
9. Add or update README with a comparison note:
   - This upgraded version aims to match the included reference image.

Robustness:

- app.js must pass `node --check`.
- The chair must be visible immediately at startup.
- Camera must start at a flattering three-quarter view.
- The UI must not hide the chair.
- Do not break the local server workflow.

After upgrading:

1. Run `node --check app.js`.
2. List files.
3. Report what changed and how to run it.
