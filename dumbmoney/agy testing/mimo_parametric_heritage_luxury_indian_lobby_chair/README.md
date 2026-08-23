# Heritage Luxury Indian Lobby Chair - 3D Parametric Configurator

A browser-based 3D parametric product configurator for a heritage luxury Indian lobby chair, inspired by royal Rajasthani and Mughal furniture design found in five-star Indian heritage hotels.

## Description

This interactive 3D configurator renders a detailed procedural chair model with:

- Scalloped arch back silhouette inspired by Indian palace architecture
- Jali-inspired lattice side panels
- Quilted cushion surfaces with piping
- Dark carved wood frame with brass/gold metal trim
- Decorative stud accents
- Multiple environment modes (hotel lobby, marble studio, dark showroom)
- Full parametric control over dimensions, materials, and details

**Note:** This is a browser 3D prototype for visualization and design exploration. It is not manufacturing-ready CAD output.

## Files

| File | Description |
|------|-------------|
| `index.html` | Main HTML page with UI structure and Three.js imports |
| `styles.css` | Dark luxury-themed CSS styling |
| `app.js` | Three.js scene, procedural geometry, materials, lighting, and controls |
| `README.md` | This file |
| `reference_heritage_luxury_indian_lobby_chair.png` | Reference design image |

## How to Run

**Important:** This project uses ES module imports and must be served via HTTP. Opening `index.html` directly with `file://` will break the 3D loading.

Open a terminal and run:

```powershell
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\mimo_parametric_heritage_luxury_indian_lobby_chair"
python -m http.server 8000
```

Then open your browser to:

http://localhost:8000

## Controls

### Materials & Colors
- **Upholstery Color** - Pick any color for the fabric
- **Upholstery Preset** - Emerald Velvet, Royal Blue Velvet, Ruby Velvet, Ivory Silk, Charcoal Leather
- **Wood Finish** - Dark Teak, Rosewood, Ebony, Walnut
- **Metal Finish** - Antique Brass, Polished Gold, Aged Bronze, Brushed Champagne

### Dimensions
- Seat Width, Seat Depth, Back Height, Back Arch, Arm Height, Leg Height

### Cushion & Detail
- Cushion Softness, Jali Density
- Toggle: Studs, Quilting, Piping

### Environment
- Five-Star Hotel Lobby, Marble Studio, Dark Showroom
- Light Intensity, Color Temperature

### Actions
- **Reset Camera** - Return camera to default view
- **Auto Rotate** - Toggle continuous rotation
- **Reset Design** - Restore all parameters to defaults
- **Screenshot** - Download PNG of current view
- **Export JSON** - Download current parameters as JSON
- **Import JSON** - Paste and apply saved parameters
- **Exploded View** - Animate parts apart for inspection

## Interaction
- **Left mouse drag** - Rotate around chair
- **Scroll wheel** - Zoom in/out
- **Right mouse drag** - Pan
- **Touch** - Single finger rotate, pinch zoom

## Technical Notes

- Built with Three.js r162 via CDN (requires internet connection)
- All chair geometry is procedural (no external 3D model files)
- Materials use PBR (Physically Based Rendering) with velvet sheen, wood grain textures, and metal reflections
- Environment includes 3D geometry (floors, walls, columns, arches) - not just a flat background
- Uses ACES Filmic tone mapping for realistic lighting
