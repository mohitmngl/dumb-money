import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import GUI from 'lil-gui';

// State and Params
const params = {
    woodColor: 0x2b1d14,
    upholsteryColor: 0x005b3e,
    metalColor: 0xd4af37,
    seatWidth: 2.2,
    backrestHeight: 2.5,
    cushionThickness: 0.4,
    toggleJali: true
};

const woodTypes = {
    'Dark Teak': 0x2b1d14,
    'Rosewood': 0x3d1c04,
    'Ebony': 0x111111,
    'Walnut': 0x4a3728
};

const fabricColors = {
    'Emerald Velvet': 0x005b3e,
    'Ruby Red': 0x5c001a,
    'Sapphire Blue': 0x001a5c,
    'Royal Ivory': 0xe0d6c8
};

const metalFinishes = {
    'Polished Gold': 0xd4af37,
    'Antique Brass': 0xb5a642,
    'Silver': 0xc0c0c0
};

// Scene Setup
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0c10);
scene.fog = new THREE.Fog(0x0b0c10, 10, 30);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(4, 3, 5);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 3;
controls.maxDistance = 15;
controls.target.set(0, 1, 0);
controls.maxPolarAngle = Math.PI / 2 + 0.1; // Don't go too far below ground

// Lighting (Studio Setup)
const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
scene.add(ambientLight);

const mainLight = new THREE.DirectionalLight(0xfff0dd, 2);
mainLight.position.set(5, 8, 5);
mainLight.castShadow = true;
mainLight.shadow.mapSize.width = 2048;
mainLight.shadow.mapSize.height = 2048;
mainLight.shadow.bias = -0.0001;
scene.add(mainLight);

const fillLight = new THREE.DirectionalLight(0xddddff, 1);
fillLight.position.set(-5, 3, -5);
scene.add(fillLight);

const rimLight = new THREE.PointLight(0xffffff, 2, 20);
rimLight.position.set(0, 5, -5);
scene.add(rimLight);

// Floor
const floorGeometry = new THREE.PlaneGeometry(50, 50);
const floorMaterial = new THREE.MeshStandardMaterial({ 
    color: 0x111111,
    roughness: 0.1,
    metalness: 0.5
});
const floor = new THREE.Mesh(floorGeometry, floorMaterial);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

// Materials
const materials = {
    wood: new THREE.MeshPhysicalMaterial({
        color: params.woodColor,
        roughness: 0.7,
        clearcoat: 0.3,
        clearcoatRoughness: 0.2
    }),
    fabric: new THREE.MeshPhysicalMaterial({
        color: params.upholsteryColor,
        roughness: 0.8,
        metalness: 0.1,
        sheen: 1.0,
        sheenColor: new THREE.Color(params.upholsteryColor).lerp(new THREE.Color(0xffffff), 0.5)
    }),
    metal: new THREE.MeshStandardMaterial({
        color: params.metalColor,
        roughness: 0.2,
        metalness: 1.0
    })
};

// Chair Group
let chairGroup = new THREE.Group();
scene.add(chairGroup);

function buildChair() {
    // Clear existing
    while(chairGroup.children.length > 0){ 
        chairGroup.remove(chairGroup.children[0]); 
    }
    
    const w = params.seatWidth;
    const d = 2.0;
    const t = params.cushionThickness;
    const h = params.backrestHeight;
    const legH = 1.2;

    // 1. Seat Base (Wood)
    const baseGeom = new THREE.BoxGeometry(w + 0.1, 0.2, d + 0.1);
    const base = new THREE.Mesh(baseGeom, materials.wood);
    base.position.y = legH;
    base.castShadow = true;
    base.receiveShadow = true;
    chairGroup.add(base);

    // Metal Trim around base
    const trimGeom = new THREE.BoxGeometry(w + 0.15, 0.05, d + 0.15);
    const trim = new THREE.Mesh(trimGeom, materials.metal);
    trim.position.y = legH;
    trim.castShadow = true;
    chairGroup.add(trim);

    // 2. Seat Cushion (Velvet)
    const cushionGeom = new THREE.BoxGeometry(w, t, d);
    const cushion = new THREE.Mesh(cushionGeom, materials.fabric);
    cushion.position.y = legH + 0.1 + t/2;
    cushion.castShadow = true;
    cushion.receiveShadow = true;
    chairGroup.add(cushion);

    // 3. Legs (Wood with metal caps)
    const legRadius = 0.1;
    const legPositions = [
        [w/2 - 0.1, d/2 - 0.1],
        [-w/2 + 0.1, d/2 - 0.1],
        [w/2 - 0.1, -d/2 + 0.1],
        [-w/2 + 0.1, -d/2 + 0.1]
    ];

    legPositions.forEach(pos => {
        // Wood leg
        const legGeom = new THREE.CylinderGeometry(legRadius, legRadius * 0.6, legH, 16);
        const leg = new THREE.Mesh(legGeom, materials.wood);
        leg.position.set(pos[0], legH/2, pos[1]);
        leg.castShadow = true;
        chairGroup.add(leg);

        // Metal cap (foot)
        const capGeom = new THREE.CylinderGeometry(legRadius * 0.65, legRadius * 0.5, 0.2, 16);
        const cap = new THREE.Mesh(capGeom, materials.metal);
        cap.position.set(pos[0], 0.1, pos[1]);
        cap.castShadow = true;
        chairGroup.add(cap);
    });

    // 4. Backrest (Scalloped Arch - Parametric)
    const backShape = new THREE.Shape();
    const bw = w / 2;
    backShape.moveTo(-bw, 0);
    backShape.lineTo(bw, 0);
    backShape.lineTo(bw, h * 0.6);
    // Scalloped curves
    backShape.quadraticCurveTo(bw * 0.8, h * 0.8, bw * 0.5, h * 0.9);
    backShape.quadraticCurveTo(0, h * 1.1, -bw * 0.5, h * 0.9);
    backShape.quadraticCurveTo(-bw * 0.8, h * 0.8, -bw, h * 0.6);
    backShape.lineTo(-bw, 0);

    const extrudeSettings = { depth: 0.2, bevelEnabled: true, bevelSegments: 3, steps: 2, bevelSize: 0.05, bevelThickness: 0.05 };
    const backGeom = new THREE.ExtrudeGeometry(backShape, extrudeSettings);
    backGeom.center(); // Center the geometry

    // Backrest Cushion (Fabric)
    const backCushion = new THREE.Mesh(backGeom, materials.fabric);
    backCushion.position.set(0, legH + 0.1 + h/2, -d/2 + 0.2);
    backCushion.castShadow = true;
    chairGroup.add(backCushion);

    // Backrest Frame (Wood)
    const frameExtrude = { depth: 0.1, bevelEnabled: true, bevelSegments: 2, steps: 1, bevelSize: 0.08, bevelThickness: 0.05 };
    const backFrameGeom = new THREE.ExtrudeGeometry(backShape, frameExtrude);
    backFrameGeom.center();
    const backFrame = new THREE.Mesh(backFrameGeom, materials.wood);
    backFrame.position.set(0, legH + 0.1 + h/2, -d/2 + 0.05);
    backFrame.castShadow = true;
    chairGroup.add(backFrame);

    // 5. Armrests with Jali pattern
    const armW = 0.15;
    const armH = 1.0;
    const armD = d * 0.8;
    
    [-w/2 - armW/2 + 0.05, w/2 + armW/2 - 0.05].forEach(x => {
        // Armrest top (Wood)
        const armTopGeom = new THREE.BoxGeometry(armW, 0.1, armD);
        const armTop = new THREE.Mesh(armTopGeom, materials.wood);
        armTop.position.set(x, legH + armH, 0);
        armTop.castShadow = true;
        chairGroup.add(armTop);

        // Armrest support front
        const armSuppGeom = new THREE.CylinderGeometry(0.04, 0.04, armH, 16);
        const armSupp = new THREE.Mesh(armSuppGeom, materials.wood);
        armSupp.position.set(x, legH + armH/2, armD/2 - 0.1);
        armSupp.castShadow = true;
        chairGroup.add(armSupp);

        // Jali Panel (Lattice)
        if (params.toggleJali) {
            const jaliGroup = new THREE.Group();
            const rows = 4;
            const cols = 6;
            const spacingY = armH * 0.8 / rows;
            const spacingZ = armD * 0.8 / cols;
            
            for(let i=0; i<=rows; i++) {
                const barGeom = new THREE.CylinderGeometry(0.015, 0.015, armD * 0.9);
                barGeom.rotateX(Math.PI/2);
                const bar = new THREE.Mesh(barGeom, materials.wood);
                bar.position.set(x, legH + 0.2 + i*spacingY, 0);
                bar.castShadow = true;
                jaliGroup.add(bar);
            }
            
            for(let j=0; j<=cols; j++) {
                const barGeom = new THREE.CylinderGeometry(0.015, 0.015, armH * 0.8);
                const bar = new THREE.Mesh(barGeom, materials.wood);
                bar.position.set(x, legH + 0.1 + armH/2, -armD/2 + 0.1 + j*spacingZ);
                bar.castShadow = true;
                jaliGroup.add(bar);
            }
            chairGroup.add(jaliGroup);
        }
    });

    // 6. Decorative Studs (Metal)
    const studGeom = new THREE.SphereGeometry(0.03, 16, 16);
    // Add studs around the seat
    for (let i = -w/2 + 0.1; i <= w/2 - 0.1; i += 0.2) {
        const stud = new THREE.Mesh(studGeom, materials.metal);
        stud.position.set(i, legH + 0.1 + t/2, d/2 + 0.01);
        chairGroup.add(stud);
    }
}

// Initial Build
buildChair();

// GUI Setup
const gui = new GUI({ title: 'Chair Parameters' });
gui.domElement.parentElement.style.zIndex = "100";

const colorsFolder = gui.addFolder('Materials & Colors');
colorsFolder.add({ w: 'Dark Teak' }, 'w', Object.keys(woodTypes)).name('Wood Finish').onChange(v => {
    materials.wood.color.setHex(woodTypes[v]);
});
colorsFolder.add({ f: 'Emerald Velvet' }, 'f', Object.keys(fabricColors)).name('Upholstery').onChange(v => {
    const col = fabricColors[v];
    materials.fabric.color.setHex(col);
    materials.fabric.sheenColor = new THREE.Color(col).lerp(new THREE.Color(0xffffff), 0.5);
});
colorsFolder.add({ m: 'Polished Gold' }, 'm', Object.keys(metalFinishes)).name('Metal Accents').onChange(v => {
    materials.metal.color.setHex(metalFinishes[v]);
});

const dimensionsFolder = gui.addFolder('Dimensions & Style');
dimensionsFolder.add(params, 'seatWidth', 1.8, 3.0, 0.1).name('Seat Width').onChange(buildChair);
dimensionsFolder.add(params, 'backrestHeight', 2.0, 3.5, 0.1).name('Backrest Height').onChange(buildChair);
dimensionsFolder.add(params, 'cushionThickness', 0.2, 0.8, 0.05).name('Cushion Plushness').onChange(buildChair);
dimensionsFolder.add(params, 'toggleJali').name('Jali Side Panels').onChange(buildChair);

// Animation Loop
const clock = new THREE.Clock();

function animate() {
    requestAnimationFrame(animate);
    
    controls.update();
    
    // Slow rotation for presentation
    if (!controls.state && chairGroup.children.length > 0) {
        // Optional: auto-rotate
        // chairGroup.rotation.y += 0.002;
    }
    
    renderer.render(scene, camera);
}

// Handle Window Resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// Remove Loading Screen
window.onload = () => {
    setTimeout(() => {
        const loading = document.getElementById('loading');
        loading.style.opacity = '0';
        setTimeout(() => loading.remove(), 1000);
    }, 500);
};

animate();
