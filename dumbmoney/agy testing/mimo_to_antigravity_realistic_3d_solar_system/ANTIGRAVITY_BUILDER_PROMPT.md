You are Antigravity CLI acting as the final implementation worker. Mimo CLI is the coordinator in this experiment, and Mimo has invoked you to build the actual app.

Work only in this exact directory:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\mimo_to_antigravity_realistic_3d_solar_system

Do not create, edit, delete, move, or read project files outside this directory unless absolutely required by a system dependency. All deliverables, source files, assets, package files, notes, and generated outputs must live inside this directory.

Project goal:

Create a beautiful, educational, realistic 3D solar system experience that lets a user explore the Sun, all eight planets, and detailed moon information. This should feel like a finished mini-app with a spatial 3D scene, realistic background environment, camera rotation, and polished interactive controls. It should run locally from the files created in this folder.

Core requirements:

1. Build an actual usable 3D app as the first screen.
2. Include the Sun and all eight planets: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune.
3. Include moon information:
   - Mercury: note that it has no confirmed natural moons.
   - Venus: note that it has no confirmed natural moons.
   - Earth: include the Moon.
   - Mars: include Phobos and Deimos.
   - Jupiter: include at least Io, Europa, Ganymede, and Callisto, plus indicate Jupiter has many additional known moons.
   - Saturn: include at least Titan, Enceladus, Mimas, Rhea, Iapetus, Dione, and Tethys, plus indicate Saturn has many additional known moons.
   - Uranus: include at least Titania, Oberon, Umbriel, Ariel, and Miranda, plus indicate Uranus has additional known moons.
   - Neptune: include at least Triton, Nereid, Proteus, Larissa, Galatea, Despina, Thalassa, and Naiad, plus indicate Neptune has additional known moons.
4. Include rich information panels for the Sun, each planet, and each listed moon.
5. Every information panel should include concise educational facts, such as type/category, approximate diameter, orbital relationship, notable features, and one memorable fact.
6. Make the visual scene realistic and immersive:
   - Use a real 3D browser environment, preferably Three.js.
   - Include a starfield background/environment.
   - Include a surrounding space background or skybox-style environment.
   - Add realistic lighting with the Sun as a primary point light and ambient fill.
   - Give planets visually distinct surfaces using procedural materials, gradients, generated canvas textures, or local texture-like assets.
   - Saturn must have visible rings with layered/banded material.
   - Uranus should have a strongly tilted appearance or tilted ring/orbit treatment.
   - Include orbit paths that can be toggled.
   - Relative order from the Sun must be correct.
   - Scale may be educational rather than physically exact, but explain that scale is compressed for usability.
7. Include interactive 3D controls:
   - Drag/rotate camera around the solar system.
   - Zoom in/out.
   - Pan where practical.
   - Click or tap celestial bodies to select them.
   - Search or filter by body name.
   - Toggle labels on/off.
   - Toggle orbit paths on/off.
   - Pause/resume animation.
   - Speed control for orbital motion.
   - Reset camera/view button.
   - Focus on a selected planet and show its moons.
   - Option to rotate selected body or auto-rotate the view.
8. Include a background/environment control:
   - At minimum a starfield environment.
   - Prefer a toggle between background moods such as deep space, nebula-like, and minimal stars if this can be done locally without remote runtime assets.
9. Provide a smooth user experience:
   - Works with mouse and keyboard where practical.
   - Has hover/focus states.
   - Has readable text and accessible contrast.
   - Has a graceful empty state if search has no matches.
   - Has a responsive layout that works on desktop and narrow screens.
10. Include an About or Notes section inside the app explaining:
   - Distances and sizes are intentionally compressed.
   - Moon counts change as discoveries are confirmed.
   - The demo focuses on major and representative moons for readability.
   - Texture/materials are educational approximations unless exact imagery is included.
11. Make the project easy to run:
   - If using Three.js from a CDN, document that an internet connection may be needed.
   - Prefer a self-contained static app where possible.
   - Include a README.md with exact run/open instructions.

Preferred implementation:

Use Three.js or another appropriate 3D browser technology. The app must not be just text cards; it must include a real 3D solar system scene with camera rotation, zooming, a starfield/background environment, and clickable celestial bodies.

Suggested files:

- README.md
- index.html
- styles.css
- app.js
- solar-system-data.js or data.json
- optional package.json if needed
- optional local vendor/dependency files if needed

Verification:

After implementation, verify that the folder contains the app files and README. If possible, run a syntax check or local server sanity check. Report how to run the demo.
