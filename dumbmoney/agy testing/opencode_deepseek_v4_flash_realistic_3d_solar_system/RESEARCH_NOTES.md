Research notes used to shape the prompt:

- Three.js with OrbitControls is a standard browser approach for interactive 3D solar-system demos.
- ES module imports and Three.js CDN imports should be served through a local HTTP server, not opened directly through file://.
- Three.js realistic rendering benefits from renderer color management, tone mapping, output color space, antialiasing, high pixel ratio control, a point light for the Sun, ambient fill, and visible emissive materials.
- Realistic planet appearances can be made with NASA/Solar System Scope-style equirectangular texture maps, but for a self-contained app procedural canvas textures are safer and avoid runtime asset failures.
- NASA and USGS planetary mapping references highlight texture-style planetary maps and moon surfaces; the prompt asks for procedural texture-like materials if exact assets are not bundled locally.
- A convincing space environment should include many stars, depth variation, environment color modes, and optional nebula-like procedural background particles.

Source links:

- https://threejs.org/
- https://threejs.org/docs/#examples/en/controls/OrbitControls
- https://threejs.org/docs/#api/en/renderers/WebGLRenderer.toneMapping
- https://www.solarsystemscope.com/textures/
- https://science.nasa.gov/science-org-term/image-or-texture/
- https://www.usgs.gov/science/science-explorer/planetary-science/planetary-mapping
