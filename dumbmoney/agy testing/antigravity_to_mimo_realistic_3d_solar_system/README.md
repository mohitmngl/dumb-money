# Realistic 3D Solar System Explorer

An interactive 3D solar system demo built with Three.js that lets you explore the Sun, all eight planets, and detailed moon information.

## Features

- **Realistic 3D Scene**: Full Three.js implementation with starfield background, dynamic lighting from the Sun, and procedural planet textures
- **All 8 Planets**: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune - in correct orbital order
- **Detailed Moon Information**: 
  - Earth: Moon
  - Mars: Phobos, Deimos
  - Jupiter: Io, Europa, Ganymede, Callisto (+ note about 79+ total moons)
  - Saturn: Titan, Enceladus, Mimas, Rhea, Iapetus, Dione, Tethys (+ note about 82+ total moons)
  - Uranus: Titania, Oberon, Umbriel, Ariel, Miranda (+ note about 27+ total moons)
  - Neptune: Triton, Nereid, Proteus, Larissa, Galatea, Despina, Thalassa, Naiad (+ note about 16+ total moons)
- **Saturn's Rings**: Visually distinct ring system with banding
- **Uranus Tilt**: Axial tilt of 98° shown correctly
- **Interactive Controls**: Drag/rotate, zoom, pan, click to select
- **Search Functionality**: Filter planets and moons by name
- **Toggle Features**: Labels, orbit paths, animation pause/resume
- **Speed Control**: Adjustable orbital animation speed
- **Background Options**: Starfield, Nebula, or Minimal styles
- **Focus Camera**: Click any body to focus camera and view details

## How to Run

### Option 1: Local HTTP Server (Recommended)

The app uses ES modules, so you need a local HTTP server:

**Using Python:**
```bash
# Navigate to the project directory
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_to_mimo_realistic_3d_solar_system"

# Python 3
python -m http.server 8000

# Python 2
python -m SimpleHTTPServer 8000
```

**Using Node.js (if installed):**
```bash
npx http-server -p 8000
```

**Using PHP (if installed):**
```bash
php -S localhost:8000
```

Then open your browser to: `http://localhost:8000`

### Option 2: Direct File Opening

Simply double-click `index.html` to open it in your browser. Note: Some browsers may restrict ES module loading from `file://` protocol. If you encounter issues, use Option 1.

## Controls

| Control | Action |
|---------|--------|
| Left click + drag | Rotate camera around solar system |
| Scroll wheel | Zoom in/out |
| Right click + drag | Pan camera |
| Click on planet/moon | Select and view information panel |
| Search input | Filter and find celestial bodies |
| Labels button | Toggle planet/moon name labels |
| Orbits button | Toggle orbital path lines |
| Pause button | Pause/resume orbital animation |
| Speed slider | Adjust animation speed (0-5x) |
| Background buttons | Switch between Starfield, Nebula, Minimal |
| Reset button | Return camera to default position |
| About button | View scale notes and information |

## Technical Details

- **3D Engine**: Three.js r128
- **Rendering**: WebGL with ACES filmic tone mapping
- **Lighting**: Point light from Sun with shadows
- **Materials**: Procedural canvas textures for planets
- **Controls**: OrbitControls with damping
- **Dependencies**: CDN-loaded Three.js (requires internet connection on first load)

## Scale Notice

Distances and sizes in this demo are intentionally compressed for educational usability. In reality:
- The Sun would be much larger relative to planets
- Distances between planets are vastly larger
- This representation focuses on relative ordering and visual clarity

## Browser Compatibility

Works best in modern browsers:
- Chrome/Edge 80+
- Firefox 75+
- Safari 13+

## Files

- `index.html` - Main HTML structure
- `styles.css` - All styling and responsive layout
- `app.js` - Three.js application and interactions
- `solar-system-data.js` - All celestial body data
- `README.md` - This documentation
