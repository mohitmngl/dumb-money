# Interactive Solar System Explorer

A beautiful, educational, interactive solar system demo built with vanilla HTML, CSS, and JavaScript using HTML5 Canvas.

## Features

- **Sun and all 8 planets** with accurate orbital order
- **Detailed moon information** for Mercury through Neptune
- **Interactive controls**:
  - Click/tap celestial bodies to select them
  - Search/filter by body name
  - Toggle labels on/off
  - Toggle orbit paths on/off
  - Pause/resume animation
  - Speed control for orbital motion
  - Reset camera/view
  - Focus on planets to see their moons
- **Rich information panels** with educational facts
- **Responsive design** for desktop and mobile

## How to Run

### Option 1: Direct File Opening (Simplest)

1. Open the `index.html` file directly in any modern web browser:
   - Double-click `index.html`
   - Or right-click and choose "Open with" your preferred browser

### Option 2: Local Server (Recommended)

Using Python:
```bash
python -m http.server 8000
```

Then open `http://localhost:8000` in your browser.

Using Node.js (if installed):
```bash
npx serve .
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Pause/Resume animation |
| `R` | Reset camera |
| `L` | Toggle labels |
| `O` | Toggle orbits |
| `Escape` | Return to Sun view |

## Files

- `index.html` - Main HTML file
- `styles.css` - Styling
- `app.js` - Main application logic
- `solar-system-data.js` - Celestial body data
- `README.md` - This file

## Notes

- Distances and sizes are intentionally compressed for visualization purposes
- Moon counts change as new discoveries are confirmed by astronomers
- This demo focuses on major and representative moons for readability
- Works offline with no external dependencies
