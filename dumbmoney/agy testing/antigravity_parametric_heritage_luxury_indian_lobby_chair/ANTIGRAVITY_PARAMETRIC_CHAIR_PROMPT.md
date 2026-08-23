You are Antigravity CLI. Build the project directly. Do not delegate this task to another agent or CLI.

This prompt is intentionally extremely detailed and literal. Follow it carefully.

PROJECT DIRECTORY

Work only inside this exact directory:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_parametric_heritage_luxury_indian_lobby_chair

Hard boundary:

- Create every source file in this directory.
- Save every generated asset in this directory.
- Do not create project files outside this directory.
- Do not modify sibling folders.
- Do not require the user to copy anything.

REFERENCE IMAGE

There is a reference image in the project directory:

reference_heritage_luxury_indian_lobby_chair.png

Use it as the visual design target. The browser 3D chair must clearly resemble this concept:

- Heritage luxury Indian lobby chair.
- Suitable for a five-star hotel lobby.
- Royal Rajasthani and Mughal influence.
- Modern parametric furniture design language.
- Dark carved teak/rosewood frame.
- Emerald or jewel-tone velvet upholstery by default.
- Brass/gold metal trim and inlay accents.
- Scalloped arch back silhouette.
- Jali-inspired lattice side panels or back details.
- Quilted cushion surface.
- Plush rounded seat cushion.
- Curved ergonomic back and seat.
- Decorative studs or gemstone-like trim.
- Polished luxury finish.

PROJECT GOAL

Create a browser-based 3D parametric product configurator for the chair.

The first screen must be the actual 3D configurator, not a landing page. The user should immediately see a detailed 3D chair in a luxury hotel lobby or studio environment, with controls to rotate, zoom, change colors/materials, adjust parameters, and inspect parts.

The result must look like a serious 3D product prototype for later CAD/parametric modeling.

REQUIRED FILES

Create these files:

1. index.html
2. styles.css
3. app.js
4. README.md

Optional extra files are allowed if useful and saved in the same directory.

TECHNICAL STACK

Use a static browser app.

Use Three.js with ES modules and OrbitControls.

Acceptable CDN imports:

- Three.js
- OrbitControls
- Optional lil-gui if you choose to use it
- Optional GLTFExporter if you implement export

If using CDN imports, README.md must clearly say to run a local HTTP server and not open index.html through file://.

RUNNING INSTRUCTIONS

README.md must include these exact commands:

```powershell
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_parametric_heritage_luxury_indian_lobby_chair"
python -m http.server 8000
```

Then tell the user to open:

http://localhost:8000

Also explain that opening index.html directly with file:// can break ES module imports or 3D loading.

CORE 3D REQUIREMENT

The chair must be real 3D geometry, not just an image on a plane.

Build the chair from editable procedural Three.js geometry:

- Seat cushion.
- Back cushion.
- Arched/scalloped chair back frame.
- Left and right arms.
- Left and right jali lattice side panels.
- Four legs.
- Cross braces or base rails.
- Brass trim/inlay strips.
- Decorative studs.
- Quilting lines or tufted cushion pattern.
- Piping along upholstery edges.
- Optional carved floral/leaf motifs as raised/debossed simplified geometry or pattern lines.

The model must be centered in the scene and visible at startup.

CAMERA AND INTERACTION REQUIREMENTS

Implement:

- OrbitControls for mouse/touch rotate.
- Scroll wheel zoom.
- Pan if possible.
- Reset camera button.
- Auto-rotate toggle.
- Screenshot/export image button if practical.
- Part selection by clicking chair parts if practical.
- Hover highlight or selected-part outline/color if practical.

PARAMETRIC CONTROLS

Create a visible browser control panel. It can be custom HTML or lil-gui, but it must be polished and usable.

Required editable parameters:

- Upholstery color.
- Upholstery material preset:
  - Emerald velvet
  - Royal blue velvet
  - Ruby velvet
  - Ivory silk
  - Charcoal leather
- Wood finish:
  - Dark teak
  - Rosewood
  - Ebony
  - Walnut
- Metal finish:
  - Antique brass
  - Polished gold
  - Aged bronze
  - Brushed champagne
- Cushion softness or cushion roundness.
- Seat width.
- Seat depth.
- Back height.
- Back arch height or scallop amount.
- Arm height.
- Leg height.
- Jali density or lattice spacing.
- Stud visibility on/off.
- Quilting visibility on/off.
- Piping visibility on/off.
- Environment mode:
  - Five-star hotel lobby
  - Marble studio
  - Dark showroom
- Light intensity.
- Warm/cool lighting temperature if practical.

Changing controls must update the 3D model or materials live without reloading the page.

MATERIAL REQUIREMENTS

Use realistic material settings.

Velvet/fabric:

- Use MeshPhysicalMaterial or MeshStandardMaterial.
- Low metalness.
- High roughness.
- Sheen-like effect if supported.
- Procedural fine noise/bump texture for nap/fabric grain.
- Subtle anisotropic-looking highlight or directional fabric lines if practical.

Wood:

- Dark brown base.
- Procedural wood grain texture using CanvasTexture.
- Semi-gloss roughness.
- Slight normal/bump impression if practical.

Brass/gold:

- Metalness high.
- Roughness medium-low.
- Warm gold/brass color.
- Environment reflections if practical.

Cushions:

- Rounded box or softened geometry.
- Visible thick padding.
- Tufting/quilting using raised lines, grooves, small buttons, or texture pattern.
- Piping cylinders/curves around edges.

Jali lattice:

- Must be visible as geometry, not only texture.
- Use repeated thin bars, diamond grid, arch motifs, or Mughal-style geometric pattern.
- Place it on side panels or back inset.

Studs:

- Small gold/brass spheres or domes along trim/edges.
- Toggleable.

LIGHTING REQUIREMENTS

Create a luxury product-render lighting setup:

- Ambient fill light.
- Key area light or directional light.
- Warm side light.
- Rim/back light.
- Optional spotlight from above.
- Use physically plausible colors: warm hotel lighting, gold highlights.
- Chair should not be too dark.
- Materials should show highlights and shadows.

ENVIRONMENT REQUIREMENTS

Create a visible environment/background, not plain black.

Environment mode 1: Five-star hotel lobby

- Marble floor.
- Warm wall/backdrop.
- Soft architectural arches or columns in the background using simple geometry.
- Subtle reflection or shadow under chair.
- Luxury atmosphere, not cluttered.

Environment mode 2: Marble studio

- Clean marble floor.
- Neutral curved backdrop.
- Product photography lighting.

Environment mode 3: Dark showroom

- Dark floor.
- Spotlight cones or soft pools of light.
- High contrast luxury mood.

The environment can be simplified geometry, but it must be 3D and visible.

DESIGN ACCURACY REQUIREMENTS

The 3D chair must look like the reference concept, not a generic chair.

Must include:

- High arched back.
- Scalloped or pointed arch top inspired by Indian palace architecture.
- Jewel-tone cushion by default.
- Gold/brass trim lines.
- Carved dark wood frame.
- Decorative lattice/jali panels.
- Plush cushion form.
- Premium hotel lobby styling.

Avoid:

- Generic office chair.
- Plain dining chair.
- Flat 2D image.
- Blank model.
- Low-effort cubes only.

UI REQUIREMENTS

The browser UI should include:

- Title: Heritage Luxury Indian Lobby Chair Configurator.
- Small reference/design notes panel.
- Controls panel with grouped controls.
- Material swatches/buttons or dropdowns.
- Sliders for parametric dimensions.
- Environment selector.
- Reset design button.
- Reset camera button.
- Auto rotate toggle.
- Render quality toggle if practical.
- Short note saying the model is procedural and inspired by the reference image.

QUALITY AND ROBUSTNESS

Important:

- The chair must be visible immediately on page load.
- The renderer canvas must fill the viewport.
- The camera must point at the chair.
- The model must be scaled correctly.
- UI must not block the entire chair.
- Text must be readable.
- Controls must fit on desktop and mobile.
- No console-blocking JavaScript syntax errors.
- Use requestAnimationFrame.
- Handle browser resize.

OPTIONAL ADVANCED FEATURES

Add if practical:

- Export current parameters as JSON.
- Import parameters from JSON text.
- Download screenshot.
- Toggle exploded view showing labeled parts.
- Small measurement labels for width/depth/height.
- GLTF export using GLTFExporter if easy.

README REQUIREMENTS

README.md must include:

- Project title.
- Description.
- File list.
- Run commands.
- Explanation of controls.
- Note that it uses procedural geometry.
- Note that the reference image is included.
- Note that this is a browser 3D prototype, not manufacturing-ready CAD.
- Mention if CDN/internet is required.

VERIFICATION REQUIREMENTS

After implementation:

1. List the files in the directory.
2. Verify index.html, styles.css, app.js, and README.md exist.
3. Run a basic JavaScript syntax check if possible.
4. Report how to run the demo.

Build it now.
