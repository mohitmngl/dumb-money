# Heritage Luxury Indian Lobby Chair - Parametric Configurator

This is a browser-based 3D parametric product configurator for a heritage luxury Indian lobby chair. It uses Three.js and ES modules.

## Design Highlights
- **Royal Rajasthani & Mughal Influence**: Scalloped arches, rich materials, and jali patterns.
- **Parametric Controls**: Adjust dimensions, materials (teak, rosewood, ebony), upholstery colors (emerald velvet, etc.), and metal accents.
- **Luxury Studio Environment**: Premium dark mode presentation with studio lighting and glassmorphism UI.

## How to Run

To run this 3D configurator, you need to use a local HTTP server because it uses ES modules (`type="module"`), which cannot be loaded directly via `file://` protocol due to browser CORS policies.

Follow these exact commands:

```powershell
cd C:\Users\Admin\Desktop\stock
```

And then navigate to the full project directory:

```powershell
cd "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_parametric_heritage_luxury_indian_lobby_chair"
```

Once in the directory, run a local web server. You can use Python or Node.js:

**Using Python:**
```powershell
python -m http.server 8000
```
Then open your browser and navigate to `http://localhost:8000`

**Using Node.js (npx):**
```powershell
npx http-server -p 8000
```
Then open your browser and navigate to `http://localhost:8000`
