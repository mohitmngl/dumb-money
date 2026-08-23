# 3D Solar System Explorer

A beautiful, realistic, and interactive 3D solar system experience built with HTML, CSS, and modern Three.js. This educational mini-app lets you explore the Sun, all eight planets, and their major moons in a spatial 3D environment.

## Features

- **Immersive 3D Environment:** Navigate a realistic spatial 3D scene using your mouse or touch (drag to rotate, scroll/pinch to zoom).
- **Accurate Celestial Roster:** Includes the Sun, 8 major planets, and extensive details on moons.
- **Rich Educational Information:** Click on any celestial body to view its category, diameter, orbital data, notable features, and interesting facts.
- **Dynamic Visuals:** Procedural canvas textures generate distinct planetary surfaces, rings for Saturn, and a tilted axis for Uranus, eliminating the need for external image assets.
- **Interactive Controls:** Search for bodies by name, toggle orbit paths and labels, pause/adjust time speed, and customize the background mood (Starfield, Deep Space, Nebula).

## How to Run Locally

Because this project utilizes ES6 Modules (`<script type="module">` and Three.js imports), **it must be served over a local HTTP server**. Opening the `index.html` file directly from your file system (via `file://`) will result in CORS errors and the 3D scene will not load.

### Option 1: Python (Recommended)
If you have Python installed, open your terminal/command prompt, navigate to this project folder, and run:
```bash
python -m http.server 8000
```
Then, open your web browser and navigate to: [http://localhost:8000](http://localhost:8000)

### Option 2: Node.js (npx)
If you have Node.js installed, you can use the `serve` package without installing it globally:
```bash
npx serve .
```
Navigate to the local address provided in your terminal (usually `http://localhost:3000`).

### Option 3: VS Code Live Server
If you use Visual Studio Code:
1. Install the **Live Server** extension.
2. Right-click on `index.html` in the file explorer.
3. Select **Open with Live Server**.

## Dependencies

- **Three.js:** The library is loaded dynamically via a CDN (`unpkg.com`) through an import map in `index.html`. 
- *Note: An active internet connection is required the first time you load the app so the browser can fetch the Three.js library.*

## Notes on Scale

Distances and sizes in this simulation are intentionally compressed. If true cosmic scale were used, the planets would be microscopic specks separated by vast stretches of empty space, making an interactive app impossible to navigate. This educational approximation focuses on the relationship, relative order, and details of the bodies.
