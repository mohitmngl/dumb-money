You are OpenCode running with the DeepSeek V4 Flash model. Build the requested project directly. Do not delegate this task to another agent or CLI.

This prompt is intentionally extremely explicit. Follow it literally.

WORKING DIRECTORY

You must work only inside this exact directory:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\opencode_deepseek_v4_flash_realistic_3d_solar_system

Hard boundary:

- Create every source file in this directory.
- Save every generated asset in this directory.
- Save every note or README in this directory.
- Do not create project files outside this directory.
- Do not modify sibling folders.
- Do not rely on the user to copy files.

PROJECT NAME

Realistic 3D Solar System Explorer

FINAL RESULT

Create a browser-based interactive 3D solar system demo. The first screen must be the app itself, not a landing page. The user should immediately see a realistic 3D scene with the Sun, planets, starfield or space background, and controls.

The app must not be a blank black screen with controls. It must render visible celestial bodies.

TECHNICAL APPROACH

Use a static web app.

Required files:

1. index.html
2. styles.css
3. app.js
4. solar-system-data.js
5. README.md

Optional files are allowed only if useful and saved in this same directory.

Use Three.js with OrbitControls. A CDN import is acceptable. If using CDN imports, README.md must clearly say that the app should be opened through a local HTTP server, not by double-clicking index.html, because ES modules and browser CORS rules can fail under file:// URLs.

RUNNING REQUIREMENT

README.md must include these exact instructions:

```powershell
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\opencode_deepseek_v4_flash_realistic_3d_solar_system"
python -m http.server 8000
```

Then tell the user to open:

http://localhost:8000

Also explain that opening index.html directly with file:// may show controls but fail to show the 3D scene because of browser module/CORS rules.

VISUAL QUALITY TARGET

The scene should feel like a premium, realistic 3D space visualization.

Required visible scene features:

- Full viewport WebGL canvas.
- Black/deep-space background.
- Dense starfield with depth.
- Optional nebula-like procedural particles or gradient mode.
- Central glowing Sun with emissive material and corona/glow effect.
- The Sun must cast/represent light using a point light or strong light source.
- All eight planets in correct order from the Sun.
- Planet surfaces must be visually distinct and texture-like.
- Prefer procedural canvas textures so the app does not depend on image downloads.
- Mercury should look rocky/cratered.
- Venus should look warm/cloudy.
- Earth should show blue oceans, green/brown land-like patches, and white cloud-like marks.
- Mars should look red/rusty with darker patches.
- Jupiter should show bands and a Great Red Spot-like feature.
- Saturn should show bands and rings.
- Uranus should appear cyan/ice-blue and visibly tilted.
- Neptune should appear deep blue with subtle bands/storm-like marks.
- Orbit paths must be visible and toggleable.
- Labels must be visible and toggleable.
- Moons must be represented around selected/focused planets or visible as small bodies when practical.
- Information panel must be readable.
- Controls must be polished and not cover the entire scene.

REALISTIC RENDERING REQUIREMENTS

Use these rendering ideas where practical:

- WebGLRenderer with antialias true.
- renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)).
- renderer.setSize(window.innerWidth, window.innerHeight).
- Use tone mapping, such as ACESFilmicToneMapping, if available.
- Set toneMappingExposure to a sane value, such as 1.0 or 1.2.
- Use outputColorSpace or sRGB output if available in the Three.js version.
- Use a PointLight at the Sun.
- Use a faint AmbientLight so dark sides are not totally invisible.
- Use MeshStandardMaterial for planets when possible.
- Use MeshBasicMaterial or emissive material for the Sun.
- Use transparent sprite or larger back-facing sphere for Sun glow if easy.
- Use BufferGeometry/Points for starfield.
- Use procedural canvas textures with CanvasTexture.
- Make sure the camera starts far enough back and looks at the origin.
- Make sure renderer.render(scene, camera) runs every frame.

INTERACTION REQUIREMENTS

Implement these interactions:

- Drag to rotate camera/view around the solar system through OrbitControls.
- Scroll to zoom.
- Pan if practical.
- Click or tap Sun, planets, or moon markers to select them.
- Search by body name.
- Pause/resume animation.
- Speed slider for orbital animation.
- Toggle orbit paths on/off.
- Toggle labels on/off.
- Reset camera/view button.
- Focus selected body button or automatic focus behavior.
- Environment selector with at least three modes:
  - Starfield
  - Deep Space
  - Nebula
- Optional auto-rotate camera toggle.

EDUCATIONAL DATA REQUIREMENTS

Include the Sun and all eight planets:

1. Sun
2. Mercury
3. Venus
4. Earth
5. Mars
6. Jupiter
7. Saturn
8. Uranus
9. Neptune

Moon data requirements:

- Mercury: explicitly state that Mercury has no confirmed natural moons.
- Venus: explicitly state that Venus has no confirmed natural moons.
- Earth: include The Moon.
- Mars: include Phobos and Deimos.
- Jupiter: include Io, Europa, Ganymede, and Callisto. Also state that Jupiter has many additional known moons.
- Saturn: include Titan, Enceladus, Mimas, Rhea, Iapetus, Dione, and Tethys. Also state that Saturn has many additional known moons.
- Uranus: include Titania, Oberon, Umbriel, Ariel, and Miranda. Also state that Uranus has additional known moons.
- Neptune: include Triton, Nereid, Proteus, Larissa, Galatea, Despina, Thalassa, and Naiad. Also state that Neptune has additional known moons.

For every body in the data, include at least:

- name
- type/category
- approximate diameter or size note
- orbital relationship
- notable features
- one memorable fact

INFORMATION PANEL REQUIREMENTS

When a body is selected, show a panel with:

- Name
- Type/category
- Diameter or size
- Orbit information
- Features
- Memorable fact
- Moon list when applicable
- Note for Mercury and Venus saying no confirmed moons

LAYOUT REQUIREMENTS

Required layout:

- Full-screen 3D scene.
- Header with title and search.
- Compact bottom or side controls.
- Information panel that can be opened/closed.
- About modal or notes section.
- Responsive layout for smaller screens.

Avoid:

- Blank black scene.
- Controls with no rendering.
- Text overlapping controls.
- Tiny unreadable controls.
- Cards inside cards.
- Marketing landing page.

IMPLEMENTATION DETAILS

Use robust, simple code.

index.html:

- Include a div with id="canvas-container".
- Include a div with id="label-container".
- Include a header/search input.
- Include controls for speed, pause, orbit toggle, label toggle, reset, environment selector, about.
- Include an info panel.
- Include app.js as type="module".
- Include an import map for Three.js and addons if using CDN.

solar-system-data.js:

- Export a named constant called solarSystemData.
- Use this exact export name so app.js can import it.
- Include all required planets and moons.

app.js:

- Import * as THREE from 'three'.
- Import OrbitControls from 'three/addons/controls/OrbitControls.js'.
- Import { solarSystemData } from './solar-system-data.js'.
- Wait for DOM elements if necessary.
- Create scene, camera, renderer, controls.
- Append renderer.domElement to #canvas-container.
- Create stars/environment.
- Create Sun.
- Create planets.
- Create orbit rings.
- Create moons.
- Create labels.
- Implement raycasting.
- Implement search.
- Implement info panel.
- Implement controls.
- Implement animation loop.
- Implement resize handling.

IMPORTANT BUG AVOIDANCE

Avoid the previous blank-screen problem:

- Do not tell the user to double-click index.html as the main run method.
- Do include HTTP server instructions.
- Do not create only controls while the 3D module fails.
- Ensure import paths are correct.
- Ensure solar-system-data.js export name matches the app.js import.
- Ensure Three.js import map keys match the imports.
- Ensure OrbitControls import path is correct.
- Ensure init() actually runs.
- Ensure animate() actually runs.
- Ensure renderer.render(scene, camera) runs every frame.
- Ensure scene contains visible objects.
- Ensure the canvas is not hidden behind CSS.
- Ensure the camera sees the Sun and planets at startup.
- Add a visible fallback/error banner if module setup fails.

README REQUIREMENTS

README.md must include:

- Project title.
- Short description.
- File list.
- Exact run commands.
- Note that local HTTP server is recommended/required.
- Feature list.
- Scale disclaimer.
- Moon count disclaimer.
- CDN dependency note if Three.js is loaded from CDN.

VERIFICATION REQUIREMENTS

After writing files:

1. List the files in the directory.
2. Check that index.html, styles.css, app.js, solar-system-data.js, and README.md exist.
3. If possible, run a basic syntax check.
4. Report exactly how to run the app.

Do the implementation now.
