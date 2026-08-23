Research notes used to shape the Mimo prompt:

- Three.js is the most direct browser stack for a standalone 3D configurator.
- OrbitControls is the standard Three.js addon for mouse/touch rotation, zooming, and panning.
- MeshPhysicalMaterial supports advanced reflectivity and sheen, useful for brass, polished wood, and velvet-like upholstery.
- MeshStandardMaterial is a robust fallback for cloth-like materials if a custom shader is too much.
- lil-gui can expose runtime controls for parameters, but a custom HTML control panel can be more polished for a product configurator.
- A product configurator should use a real renderer/camera/scene loop, stable lighting, readable controls, and avoid file:// module loading problems by using a local HTTP server.
- For this project, procedural Three.js geometry is preferable to an imported GLB so the chair can be edited parametrically in the browser.
- Procedural canvas textures can represent velvet nap, carved wood grain, brass highlights, quilting, jali lattice panels, and marble/environment details without remote runtime assets.

Useful sources:

- https://threejs.org/
- https://threejs.org/docs/#examples/en/controls/OrbitControls
- https://threejs.org/docs/pages/MeshPhysicalMaterial.html
- https://lil-gui.georgealways.com/
- https://threejsresources.com/tool/lil-gui
- https://sbcode.net/threejs/meshphysicalmaterial/
- https://wawasensei.dev/tuto/how-to-use-three-js-to-create-a-3D-product-configurator
- https://dyadicsolutions.com.tw/en/blog/building-3d-product-configurators
