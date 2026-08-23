# Realistic 3D Solar System Explorer

An interactive 3D visualization of our Solar System built with Three.js. Explore the Sun, all eight planets, and dozens of moons with realistic procedural textures, orbital mechanics, and detailed educational information.

## Files

- `index.html` — Main HTML page with import map for Three.js CDN
- `styles.css` — Full-screen dark UI styling with responsive layout
- `app.js` — Three.js scene, procedural textures, interactions, animation loop
- `solar-system-data.js` — Complete celestial body data (Sun, 8 planets, all required moons)
- `README.md` — This file

## How to Run

This app uses ES modules and loads Three.js from a CDN. You **must** serve it through a local HTTP server — opening `index.html` directly via `file://` will fail due to browser CORS and module security policies.

Run this command in the project directory:

```powershell
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\opencode_deepseek_v4_flash_realistic_3d_solar_system"
python -m http.server 8000
```

Then open in your browser:

```
http://localhost:8000
```

> **Warning:** Opening `index.html` directly with `file://` may show controls but will fail to load the 3D scene because browsers block ES module imports from `file://` URLs.

## Features

- Full-screen WebGL 3D scene with antialiasing and tone mapping
- Procedural canvas textures for all celestial bodies (no external image downloads)
- Sun with emissive material, point light, and corona glow effect
- All eight planets in correct order with distinct visual appearances
- Saturn's rings with procedural banded texture
- Moons rendered for every planet that has them
- Visible orbit paths (toggleable)
- Floating labels for all bodies (toggleable)
- Click/tap any body to view detailed information panel
- Search by body name with autocomplete results
- Pause/resume orbital animation
- Speed slider (0x to 5x)
- Orbit path visibility toggle
- Label visibility toggle
- Reset camera button
- Focus selected body button
- Environment selector with three modes: Starfield, Deep Space, Nebula
- Auto-rotate camera toggle
- About modal with controls reference
- Responsive layout for desktop and mobile screens

## Controls

| Control | Action |
|---------|--------|
| Drag | Rotate camera around the scene |
| Scroll | Zoom in/out |
| Right-click + drag | Pan |
| Click body | Select and show info panel |
| Double-click body | Focus camera on body |
| Search bar | Type to find and focus on any body |

## Scale Disclaimer

Planet sizes and orbital distances are **not to scale**. They are artistically adjusted for visual clarity and educational purposes. In reality, the Sun dwarfs the planets and the distances between orbits are vast.

## Moon Count Disclaimer

Moon counts reflect known confirmed natural satellites as of 2024. Rendered moons represent major/significant moons. Outer planets have many additional small moons not individually rendered.

## CDN Dependency

Three.js (including OrbitControls) is loaded via CDN from jsdelivr.net. An internet connection is required. The import map in `index.html` references:

- `https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js`
- `https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/`

No other external dependencies.
