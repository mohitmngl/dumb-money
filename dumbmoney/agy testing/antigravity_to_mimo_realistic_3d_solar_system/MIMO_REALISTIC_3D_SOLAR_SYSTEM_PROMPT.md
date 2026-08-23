Build a polished, self-contained, realistic 3D interactive solar system demo in this exact directory only:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_to_mimo_realistic_3d_solar_system

Do not create, edit, delete, move, or read project files outside this directory unless absolutely required by a system dependency. All deliverables, source files, assets, package files, notes, and generated outputs must live inside this directory.

Project goal:

Create a beautiful, educational, realistic 3D solar system experience that lets a user explore the Sun, all eight planets, and detailed moon information. This should feel like a finished mini-app with a spatial 3D scene, not a flat sample or landing page. It should run locally from the files created in this folder.

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
   - Use a real 3D environment, preferably Three.js.
   - Include a starfield background/environment.
   - Include a surrounding space background or skybox-style environment.
   - Add realistic lighting with the Sun as a primary light source.
   - Give planets visually distinct surfaces using procedural materials, gradients, or generated/local textures.
   - Saturn must have visible rings.
   - Uranus should have a tilted appearance or tilted ring/orbit treatment.
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
   - Prefer a toggle between background moods such as deep space, nebula-like, or minimal stars if this can be done locally without remote runtime assets.
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
   - If using Three.js from a CDN, document that an internet connection may be needed. Prefer vendored/local dependencies if practical.
   - If using a bundler or package manager, create the needed package files and scripts.
   - If a simple static app is enough, create a self-contained HTML/CSS/JS setup.
   - Include a README.md with exact run/open instructions.

Preferred implementation:

Use Three.js or another appropriate 3D browser technology. If local dependencies are practical, install or vendor them inside this folder. If a CDN is used, make the app still graceful and document that dependency clearly. The app must not be just text cards; it must include a real 3D solar system scene with camera rotation.

Design direction:

Create a sophisticated space-science interface with a full-viewport 3D scene, starfield or space environment background, compact controls, clear labels, and a readable information panel. Avoid a generic marketing landing page. The first screen should be the interactive 3D solar system itself.

Suggested files:

- README.md
- index.html
- styles.css
- app.js
- solar-system-data.js or data.json
- optional package.json if needed
- optional local vendor/dependency files if needed

Verification:

After implementation, verify that the app opens/runs locally, the main controls work, and clicking planets/moons updates the information panel. If you cannot run a browser preview, at minimum inspect the files for syntax/runtime mistakes and explain how to run the demo.
