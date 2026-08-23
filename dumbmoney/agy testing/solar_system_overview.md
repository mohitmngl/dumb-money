# Orrery Live - Solar System Technical Overview

Welcome to the technical overview of **Orrery Live**, a self-contained, interactive space-science telemetry application simulating our solar system (the Sun, 8 planets, and 25 representative moons).

This document serves as the design registry and system architecture overview, centralizing all design choices, data scales, and interface layouts.

---

## 📂 Project Deliverables & Structure

All project files are saved and run exclusively from:
`C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing`

*   **index.html**: The HTML5 structure providing the workspace. It contains the fullscreen Canvas element, floating control panels, telemetry sidebar, and About/Educational disclaimer overlays.
*   **styles.css**: The user interface design sheet. Implements space-themed glassmorphism elements, transitions, layout rules, and responsive styling adjustments.
*   **data.js**: The astronomical telemetry database. Houses details (size, orbit, key features, and memorable facts) for the Sun, 8 planets, and 25 moons.
*   **app.js**: The engine of the application. Manages canvas resizing, rendering frames (60 FPS), Keplerian orbital loops, planet phase shading, Saturn-style ring drawing layers, and smooth camera LERP targeting.
*   **README.md**: User guide with instructions on how to load and run the app locally.
*   **ANTIGRAVITY_SOLAR_SYSTEM_PROMPT.md**: The original project prompt saved for compliance and configuration reference.

---

## ⚙️ Application Architecture

```
+------------------------------------------+
|                index.html                |
|  (Canvas Viewport, Telemetry, Controls)  |
+---------+------------+------------+------+
          |            |            |
     Loads|       Loads|       Loads|
          v            v            v
    styles.css      data.js       app.js
 (Design System)  (Database)  (Engine & Loops)
```

### 1. Data Layer (`data.js`)
*   Provides the static `SOLAR_SYSTEM_DATA` object mapping each planet by its lowercase ID.
*   Each entry houses specifications such as name, category, diameter, orbital period/distance, features, and trivia.
*   Nested lists represent major moons for each planet, providing a hierarchical astronomical map.

### 2. Simulation & Rendering Loop (`app.js`)
*   **Keplerian Approximation**: Planets follow perfect circular orbits around the central Sun (0, 0), incrementing their orbital angles $\theta$ dynamically by defined angular velocities based on `simulationSpeed`.
*   **Planetary Shading**: Renders a dynamic radial gradient on each planet sphere to simulate sunlight. The brightest side of the hemisphere always faces the Sun (0, 0), while the opposite side fades to a deep shadow.
*   **Layered Rings**: Renders tilted planetary rings (Saturn, Uranus, Neptune, and Jupiter) in two separate passes: a back half (drawn before the planet sphere) and a front half (drawn after the planet sphere). This prevents the planet from looking like it sits behind or in front of the rings.
*   **Twinkling Starfield**: Spawns 300 stars at randomized coordinates with individual twinkle phases and speeds. Incorporates subtle camera parallax scrolling (wrapping boundary) so the starfield moves slowly when panning.

### 3. Interactive Camera System
*   **LERP Camera Tracking**: The camera uses Linear Interpolation (`LERP`) to smoothly track the currently focused celestial body. 
*   **Gestures**: Users can pan by dragging the mouse across the canvas, and zoom using the scroll wheel. Panning while tracking will naturally release the focus.

---

## 📏 Scientific Compression & Scaling

In the real universe, distance scales are orders of magnitude larger than planet sizes. If rendered to scale, the planets would be sub-pixel dots. The app employs a visual balance approach:

| Celestial Body | Base Radius (px) | Orbit Radius (px) | Relative Base Speed |
| :--- | :---: | :---: | :---: |
| **Sun** | 36.0 | — | — |
| **Mercury** | 6.5 | 85 | 0.024 |
| **Venus** | 10.5 | 130 | 0.016 |
| **Earth** | 11.5 | 180 | 0.012 |
| **Mars** | 8.5 | 235 | 0.009 |
| **Jupiter** | 23.0 | 320 | 0.005 |
| **Saturn** | 18.0 | 430 | 0.003 |
| **Uranus** | 14.5 | 535 | 0.0018 |
| **Neptune** | 14.0 | 645 | 0.0011 |

*Note: Sizes and distances are compressed to ensure readability and usability on a single browser window. Moons orbit outside their planet's radius + padding, scaling their speeds dynamically relative to their orbital distance index.*

---

## 🎨 Design System & Aesthetics

*   **Dark Space Motif**: Radial background gradient (`#0a0a16` to `#030307`) with custom-colored twinkling stars.
*   **Glassmorphism Layout**: Translucent panel overlays with `backdrop-filter: blur(10px)`, subtle borders (`rgba(255, 255, 255, 0.08)`), and colored glow accents tailored to the selected planet's theme.
*   **Modern Typography**: Utilizes *Outfit* for data values and body text, and *Space Grotesk* for technical sci-fi headers and capsules.
