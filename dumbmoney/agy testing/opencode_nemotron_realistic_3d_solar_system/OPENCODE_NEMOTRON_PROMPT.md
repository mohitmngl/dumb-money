You are OpenCode running with the Nemotron model. Build the requested project directly. Do not delegate this task to another agent or CLI.

WORKING DIRECTORY

You must work only inside this exact directory:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\opencode_nemotron_realistic_3d_solar_system

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

Create a browser-based interactive 3D solar system demo. The first screen must be the app itself, not a landing page. The user should immediately see a 3D scene with a Sun, planets, starfield or space background, and controls.

TECHNICAL APPROACH

Use a static web app.

Required files:

1. index.html
2. styles.css
3. app.js
4. solar-system-data.js
5. README.md

Optional files are allowed only if useful and saved in this same directory.

Use Three.js if possible. A CDN import is acceptable, but README.md must clearly say that the app should be opened through a local HTTP server, not by double-clicking the file, because ES modules and CDN imports can fail under file:// URLs.

If you choose not to use Three.js, you must still create a true 3D or pseudo-3D interactive visual scene. Plain text cards are not acceptable.

RUNNING REQUIREMENT

The app must be easy to run:

README.md must include these exact instructions:

```powershell
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\opencode_nemotron_realistic_3d_solar_system"
python -m http.server 8000
```

Then tell the user to open:

http://localhost:8000

Also explain that opening index.html directly with file:// may show the controls but fail to show the 3D scene because of browser module/CORS rules.

VISUAL REQUIREMENTS

The demo must look like a realistic 3D space environment.

Required visible elements:

- A black or deep-space background.
- A starfield background with many stars.
- A central glowing Sun.
- All eight planets in the correct order from the Sun.
- Orbit paths that can be shown or hidden.
- Labels that can be shown or hidden.
- A visible 3D canvas or 3D-like scene occupying most of the viewport.
- Saturn rings.
- Uranus visibly tilted, or Uranus rings/orbit treatment visibly tilted.
- Moons visible when focusing/selecting planets, or at least represented around their planet in focused view.
- A readable information panel.
- A bottom or side control bar.

INTERACTION REQUIREMENTS

Implement these interactions:

- Drag to rotate camera/view around the solar system.
- Scroll or pinch to zoom.
- Pan if practical.
- Click or tap Sun, planets, or moon markers to select them.
- Search by body name.
- Pause/resume animation.
- Speed slider for orbital animation.
- Toggle orbit paths on/off.
- Toggle labels on/off.
- Reset camera/view button.
- Focus selected planet button or behavior.
- Environment selector with at least two modes:
  - Starfield
  - Nebula or Deep Space

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
- Type
- Diameter or size
- Orbit information
- Features
- Memorable fact
- Moon list when applicable
- Note for Mercury and Venus saying no confirmed moons

LAYOUT REQUIREMENTS

The UI must be professional and readable.

Required layout:

- Full-screen 3D scene.
- Header with title and search.
- Controls that do not cover the main scene too much.
- Info panel that can be opened/closed.
- Responsive behavior for smaller screens.

Avoid:

- A blank black scene.
- Text overlapping controls.
- Tiny unreadable controls.
- Cards inside cards.
- A marketing landing page.

IMPLEMENTATION DETAILS

Use simple robust code. Do not overcomplicate.

Suggested implementation:

- index.html loads styles.css.
- index.html loads app.js as type="module".
- app.js imports solarSystemData from solar-system-data.js.
- app.js initializes the 3D scene after DOM elements exist.
- app.js creates renderer, scene, camera, controls, lights, starfield, Sun, planets, moons, labels, orbits.
- Use raycasting or clickable object mapping for selection.
- Use requestAnimationFrame for animation.
- Make sure the canvas is appended to a container and visible.
- Make sure the renderer has nonzero width and height.
- Make sure camera points toward the solar system and starts far enough back to see it.
- Make sure the Sun and planets are not black on a black background.
- Make sure errors do not stop rendering.

IMPORTANT BUG AVOIDANCE

Avoid the previous blank-screen problem:

- Do not tell the user to double-click index.html as the main run method.
- Do include HTTP server instructions.
- Do not create only the controls while the 3D module fails.
- If using ES modules, ensure all import paths are correct.
- Ensure the data export name matches the import name.
- Ensure Three.js import map keys match the imports.
- Ensure OrbitControls import path is correct.
- Ensure init() actually runs.
- Ensure animate() actually runs.
- Ensure renderer.render(scene, camera) runs every frame.
- Ensure scene contains visible objects.
- Ensure the canvas is not hidden behind CSS.

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
