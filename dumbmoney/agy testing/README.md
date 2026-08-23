# Orrery Live - Interactive Solar System Explorer

Welcome to **Orrery Live**, a polished, interactive, and self-contained space-science application that lets you explore the Sun, all eight planets, and representative natural satellites (moons) in a single visual space. 

This project runs entirely locally from your browser with zero bundlers, build tools, or network server configurations required. It uses a custom physics-like coordinate model rendered directly onto a high-performance HTML5 Canvas with fluid orbital overlays and glassmorphic telemetry panels.

---

## 🚀 How to Run the App

Since the application is built as a self-contained static web app, there are no packages to install or compile. You can open and experience the application in two simple ways:

### Method 1: Direct File Open (Recommended & Easiest)
1. Navigate to the project directory:
   `C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing`
2. Double-click the `index.html` file to open it directly in any modern web browser (Google Chrome, Microsoft Edge, Firefox, or Safari).
3. Alternatively, right-click `index.html`, select **Open With**, and choose your browser of choice.

### Method 2: Local HTTP Server (Optional)
If you prefer running the application through a local development server:
- **Python 3:** Run the following command in your terminal from this directory:
  ```bash
  python -m http.server 8000
  ```
  Then open your browser and navigate to `http://localhost:8000`.
- **NodeJS (npx):** Run:
  ```bash
  npx http-server . -p 8000
  ```
  Then navigate to `http://localhost:8000` in your browser.

---

## 🛠️ Codebase Structure

The project is structured with clean, separated files within the directory:
*   [index.html](file:///C:/Users/Admin/Desktop/stock%20test/open%20code%20v5%20claude%20prompt/dumbmoney/agy%20testing/index.html) - Structural framework containing the Canvas viewport, sci-fi glassmorphism details sidebar, floating controls panel, search box, and the About/Disclaimer modal overlay.
*   [styles.css](file:///C:/Users/Admin/Desktop/stock%20test/open%20code%20v5%20claude%20prompt/dumbmoney/agy%20testing/styles.css) - High-fidelity visual styling. Provides layout rules, animations, custom sliders/toggles, active state highlights, and responsive layouts that adjust for tablet and mobile devices.
*   [data.js](file:///C:/Users/Admin/Desktop/stock%20test/open%20code%20v5%20claude%20prompt/dumbmoney/agy%20testing/data.js) - Complete educational database cataloging astronomical properties (diameter, distances, atmospheric features, and trivia) for the Sun, 8 planets, and 25 representative moons.
*   [app.js](file:///C:/Users/Admin/Desktop/stock%20test/open%20code%20v5%20claude%20prompt/dumbmoney/agy%20testing/app.js) - Orchestrator of the simulation. Sets up the canvas, draws planet shading phases relative to the Sun, manages camera LERP pan/zoom tracking, monitors mouse/touch gestures, handles search autocomplete, and updates UI nodes.

---

## 🪐 Key Features

1.  **High-Fidelity Canvas Physics:**
    *   Dynamic orbital trajectories with speed and distance scales.
    *   3D spherical shader effect based on the angle to the Sun (illuminated hemisphere faces the center).
    *   Dual-arc tilted ring rendering: rings of Saturn, Uranus, Neptune, and Jupiter sit layered with their front and back segments properly surrounding the planet spheres.
2.  **Telemetry Sidebar (Glassmorphism):**
    *   Deep-space telemetry display listing type/category, actual diameter, actual orbital period, notable features, and custom memorable facts.
    *   Dynamic moon lists with custom back-navigation and zero-moon details for Mercury and Venus.
    *   Theme-matched glow lines that tint to the selected body's color profiles.
3.  **Advanced Camera Tracking:**
    *   Pan by clicking and dragging on the canvas.
    *   Zoom in/out with your scroll wheel.
    *   Click **"Zoom & Show Moons"** (or **"Focus"** in the sidebar) to smoothly center on a planet or a moon. The camera will automatically track the body in real-time as it moves.
    *   Dragging the screen while focused naturally releases camera tracking without jarring snaps.
4.  **Simulation Controls:**
    *   Pause/Resume orbit animations.
    *   Adjust orbit speeds continuously with a slider.
    *   Toggle orbital paths, text labels, and twinkling stars on or off.
    *   Reset camera offsets and zoom instantly.
5.  **Reactive Search System:**
    *   A live search input offering autocompletion for all Sun, planet, and moon names.
    *   Selecting a search match immediately centers the camera, selects the body, and pulls up its educational specs.

---

## 📐 Scientific Compromise & Scale Disclaimer

To make this simulation usable on standard monitors and mobile screens, sizes and distances are **intentionally compressed**:
*   In the actual universe, the distances between planets are tens of thousands of times greater than the size of the planets themselves. A physically exact scale would render the planets as invisible, sub-pixel dots.
*   The orbit rates and diameters have been scaled relative to one another (terrestrial planets are smaller, gas giants are larger, orbits are nested) to maintain educational integrity while offering an immersive, interactive user experience.
