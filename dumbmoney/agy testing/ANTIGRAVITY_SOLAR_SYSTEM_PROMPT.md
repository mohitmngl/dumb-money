You are working in this exact project directory:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing

Build a polished, self-contained interactive solar system demo in this directory only. Do not create, edit, delete, move, or read project files outside this directory unless absolutely required by a system dependency. All deliverables, source files, assets, package files, notes, and generated outputs must live inside this directory.

Project goal:

Create a beautiful, educational, interactive solar system experience that lets a user explore the Sun, all eight planets, and detailed moon information. The demo should feel like a finished mini-app, not a throwaway sample. It should run locally from the files you create in this folder.

Core requirements:

1. Build an actual usable app as the first screen.
2. Include the Sun and all eight planets: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune.
3. Include moon information:
   - Mercury: note that it has no confirmed natural moons.
   - Venus: note that it has no confirmed natural moons.
   - Earth: include the Moon.
   - Mars: include Phobos and Deimos.
   - Jupiter: include at least the Galilean moons Io, Europa, Ganymede, and Callisto, plus indicate Jupiter has many additional known moons.
   - Saturn: include at least Titan, Enceladus, Mimas, Rhea, Iapetus, Dione, and Tethys, plus indicate Saturn has many additional known moons.
   - Uranus: include at least Titania, Oberon, Umbriel, Ariel, and Miranda, plus indicate Uranus has additional known moons.
   - Neptune: include at least Triton, Nereid, Proteus, Larissa, Galatea, Despina, Thalassa, and Naiad, plus indicate Neptune has additional known moons.
4. Include rich information panels for the Sun, each planet, and each listed moon.
5. Every information panel should include concise educational facts, such as type/category, approximate size or diameter, orbital relationship, notable features, and one memorable fact.
6. Include clear interactive controls:
   - Click or tap celestial bodies to select them.
   - Search or filter by body name.
   - Toggle labels on/off.
   - Toggle orbit paths on/off.
   - Pause/resume animation.
   - Speed control for orbital motion.
   - Reset camera/view button.
   - Option to focus on a selected planet and show its moons.
7. The solar system visualization should be dynamic and attractive:
   - Animated orbits.
   - Visually distinct Sun, planets, and moons.
   - Relative order from the Sun must be correct.
   - Scale can be educational rather than physically exact, but explain that scale is compressed for usability.
   - Avoid overlapping UI and make it responsive for desktop and mobile.
8. Provide a smooth user experience:
   - Works with mouse and keyboard where practical.
   - Has hover/focus states.
   - Has readable text and accessible contrast.
   - Has a graceful empty state if search has no matches.
   - Has a responsive layout that works on narrow screens.
9. Include an About or Notes section inside the app explaining:
   - Distances and sizes are intentionally compressed.
   - Moon counts change as discoveries are confirmed.
   - The demo focuses on major and representative moons for readability.
10. Make the project easy to run:
   - If you use a bundler or package manager, create the needed package files and scripts.
   - If a simple static app is enough, prefer a self-contained HTML/CSS/JS setup.
   - Include a README.md with exact run/open instructions.
   - Do not rely on remote network assets at runtime unless unavoidable.

Preferred implementation:

Use a self-contained static web app unless you strongly determine that a local build tool is better. Good options are HTML, CSS, and JavaScript with Canvas or CSS transforms. If you use Three.js, install or vendor dependencies locally in this folder and document how to run it. The app should not be just text cards; it must include a real visual solar system scene and meaningful interactivity.

Design direction:

Create a sophisticated space-science interface, with a dark starfield scene, clear planetary colors, subtle orbital rings, compact controls, and readable information panels. Avoid a generic marketing landing page. The first screen should be the interactive solar system itself.

Suggested files:

- README.md
- index.html
- styles.css
- app.js
- optional data file such as solar-system-data.js or data.json

Verification:

After implementation, verify that the app opens/runs locally, the main controls work, and clicking planets/moons updates the information panel. If you cannot run a browser preview, at minimum inspect the files for syntax/runtime mistakes and explain how to run the demo.

Important boundary:

Do all implementation work yourself using Antigravity CLI. Keep all created and modified files inside:

C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing

Do not ask another agent or the user to implement the app. Build the full demo now.
