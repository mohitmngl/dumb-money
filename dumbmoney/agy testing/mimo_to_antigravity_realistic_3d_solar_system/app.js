import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { solarSystemData } from './data.js';

// Global state
let scene, camera, renderer, controls;
let celestialBodies = []; // { mesh, data, isMoon, parentPlanet, orbitGroup }
let labels = []; // { element, object3D, isMoon }
let time = 0;
let timeScale = 20;
let isPaused = false;
let showOrbits = true;
let showLabels = true;
let targetedBody = null; // mesh
let raycaster = new THREE.Raycaster();
let mouse = new THREE.Vector2();

// DOM Elements
const container = document.getElementById('canvas-container');
const labelContainer = document.getElementById('label-container');
const infoPanel = document.getElementById('info-panel');
const infoContent = document.getElementById('info-content');
const speedSlider = document.getElementById('speed-slider');
const speedLabel = document.getElementById('speed-label');
const pauseBtn = document.getElementById('pause-btn');
const toggleOrbitsBtn = document.getElementById('toggle-orbits-btn');
const toggleLabelsBtn = document.getElementById('toggle-labels-btn');
const resetCamBtn = document.getElementById('reset-cam-btn');
const envSelect = document.getElementById('env-select');
const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');
const closePanelBtn = document.getElementById('close-panel');
const aboutBtn = document.getElementById('about-btn');
const aboutModal = document.getElementById('about-modal');
const closeAboutBtn = document.getElementById('close-about-btn');

init();
animate();

function init() {
    // Scene setup
    scene = new THREE.Scene();
    
    // Camera setup
    camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 3000);
    camera.position.set(0, 150, 250);

    // Renderer setup
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxDistance = 1500;
    controls.minDistance = 3;

    // Lights
    const ambientLight = new THREE.AmbientLight(0x404040, 0.6); // Soft white light
    scene.add(ambientLight);

    const sunLight = new THREE.PointLight(0xffffff, 2.5, 2000, 0.5);
    scene.add(sunLight);

    // Environment
    updateEnvironment('stars');

    // Build Solar System
    buildSolarSystem();

    // Event Listeners
    window.addEventListener('resize', onWindowResize);
    container.addEventListener('click', onMouseClick);
    // Support touch devices
    container.addEventListener('touchstart', (e) => {
        if(e.touches.length > 0) {
            e.clientX = e.touches[0].clientX;
            e.clientY = e.touches[0].clientY;
            onMouseClick(e);
        }
    }, {passive: false});
    
    speedSlider.addEventListener('input', (e) => {
        timeScale = e.target.value;
        speedLabel.textContent = (timeScale / 20).toFixed(1) + 'x';
    });
    
    pauseBtn.addEventListener('click', () => {
        isPaused = !isPaused;
        pauseBtn.textContent = isPaused ? 'Resume' : 'Pause';
        pauseBtn.classList.toggle('active', !isPaused);
    });

    toggleOrbitsBtn.addEventListener('click', () => {
        showOrbits = !showOrbits;
        toggleOrbitsBtn.textContent = showOrbits ? 'Orbits: On' : 'Orbits: Off';
        toggleOrbitsBtn.classList.toggle('active', showOrbits);
        celestialBodies.forEach(b => {
            if(b.orbitLine) b.orbitLine.visible = showOrbits;
        });
    });

    toggleLabelsBtn.addEventListener('click', () => {
        showLabels = !showLabels;
        toggleLabelsBtn.textContent = showLabels ? 'Labels: On' : 'Labels: Off';
        toggleLabelsBtn.classList.toggle('active', showLabels);
        labelContainer.style.display = showLabels ? 'block' : 'none';
    });

    resetCamBtn.addEventListener('click', () => {
        targetedBody = null;
        controls.target.set(0, 0, 0);
        camera.position.set(0, 150, 250);
        closeInfoPanel();
    });

    envSelect.addEventListener('change', (e) => updateEnvironment(e.target.value));

    closePanelBtn.addEventListener('click', closeInfoPanel);
    aboutBtn.addEventListener('click', () => aboutModal.classList.remove('hidden'));
    closeAboutBtn.addEventListener('click', () => aboutModal.classList.add('hidden'));

    searchInput.addEventListener('input', handleSearch);
    
    // Hide search on click outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
            searchResults.classList.add('hidden');
        }
    });
}

function buildSolarSystem() {
    // The Sun
    const sunGeo = new THREE.SphereGeometry(solarSystemData.sun.radius, 64, 64);
    const sunMat = new THREE.MeshBasicMaterial({ 
        color: solarSystemData.sun.color,
        map: generateTexture(solarSystemData.sun.color, 'Sun')
    });
    const sunMesh = new THREE.Mesh(sunGeo, sunMat);
    scene.add(sunMesh);
    sunMesh.userData = { type: 'body', data: solarSystemData.sun };
    celestialBodies.push({ mesh: sunMesh, data: solarSystemData.sun, isMoon: false });
    createLabel(sunMesh, solarSystemData.sun.name);

    // Planets
    solarSystemData.planets.forEach(planet => {
        // Orbit Group (handles rotation around sun)
        const orbitGroup = new THREE.Group();
        scene.add(orbitGroup);

        // Planet Group (handles position along orbit, and local rotation)
        const planetGroup = new THREE.Group();
        planetGroup.position.x = planet.distance;
        orbitGroup.add(planetGroup);

        // Planet Mesh
        const planetGeo = new THREE.SphereGeometry(planet.radius, 32, 32);
        const planetMat = new THREE.MeshStandardMaterial({ 
            color: planet.color,
            map: generateTexture(planet.color, planet.type),
            roughness: 0.7,
            metalness: 0.1
        });
        const planetMesh = new THREE.Mesh(planetGeo, planetMat);
        
        // Tilt for Uranus and others
        if(planet.tilt) {
            planetMesh.rotation.x = THREE.MathUtils.degToRad(planet.tilt);
        }
        
        planetGroup.add(planetMesh);
        planetMesh.userData = { type: 'body', data: planet };
        celestialBodies.push({ 
            mesh: planetMesh, 
            data: planet, 
            isMoon: false, 
            orbitGroup: orbitGroup,
            distance: planet.distance,
            speed: planet.speed
        });
        createLabel(planetMesh, planet.name);

        // Rings (Saturn)
        if(planet.hasRings) {
            const ringGeo = new THREE.RingGeometry(planet.radius * 1.4, planet.radius * 2.4, 64);
            const ringMat = new THREE.MeshStandardMaterial({ 
                color: planet.color, 
                side: THREE.DoubleSide, 
                transparent: true, 
                opacity: 0.9,
                map: generateRingTexture(),
                roughness: 0.8
            });
            const ringMesh = new THREE.Mesh(ringGeo, ringMat);
            ringMesh.rotation.x = Math.PI / 2 + 0.4; // Tilted relative to planet
            planetGroup.add(ringMesh);
        }

        // Orbit Line
        const pathGeo = new THREE.RingGeometry(planet.distance - 0.15, planet.distance + 0.15, 128);
        const pathMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.15, side: THREE.DoubleSide });
        const pathMesh = new THREE.Mesh(pathGeo, pathMat);
        pathMesh.rotation.x = Math.PI / 2;
        scene.add(pathMesh);
        celestialBodies[celestialBodies.length - 1].orbitLine = pathMesh;

        // Moons
        if(planet.moons && planet.moons.length > 0) {
            planet.moons.forEach((moon, index) => {
                const mOrbitGroup = new THREE.Group();
                planetGroup.add(mOrbitGroup);
                
                // Spread out moons artificially based on index to avoid overlapping
                const mDistance = planet.radius + 1.2 + (index * 1.5);
                const mSpeed = 0.08 - (index * 0.005);
                
                // Scale moons relative to planet, but keep them visible
                const mRadius = 0.4 + (Math.random() * 0.2); 
                
                const mGeo = new THREE.SphereGeometry(mRadius, 16, 16);
                const mMat = new THREE.MeshStandardMaterial({ color: 0xcccccc, roughness: 0.9 });
                const mMesh = new THREE.Mesh(mGeo, mMat);
                mMesh.position.x = mDistance;
                
                mOrbitGroup.add(mMesh);
                mMesh.userData = { type: 'body', data: moon, parentData: planet };
                
                celestialBodies.push({
                    mesh: mMesh,
                    data: moon,
                    isMoon: true,
                    parentPlanet: planetMesh,
                    orbitGroup: mOrbitGroup,
                    distance: mDistance,
                    speed: mSpeed
                });
                
                // Moon orbit line
                const mPathGeo = new THREE.RingGeometry(mDistance - 0.02, mDistance + 0.02, 64);
                const mPathMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.1, side: THREE.DoubleSide });
                const mPathMesh = new THREE.Mesh(mPathGeo, mPathMat);
                mPathMesh.rotation.x = Math.PI / 2;
                planetGroup.add(mPathMesh);
                celestialBodies[celestialBodies.length - 1].orbitLine = mPathMesh;
                
                createLabel(mMesh, moon.name, true);
            });
        }
    });
}

// Procedural Textures using Canvas
function generateTexture(colorStr, type) {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');
    
    // Base color
    ctx.fillStyle = colorStr || '#ffffff';
    ctx.fillRect(0, 0, 512, 256);
    
    if (type === 'Gas Giant' || type === 'Ice Giant') {
        // Bands for gas giants
        for(let i=0; i<20; i++) {
            ctx.fillStyle = `rgba(255, 255, 255, ${Math.random() * 0.2})`;
            ctx.fillRect(0, Math.random() * 256, 512, Math.random() * 30 + 5);
            ctx.fillStyle = `rgba(0, 0, 0, ${Math.random() * 0.15})`;
            ctx.fillRect(0, Math.random() * 256, 512, Math.random() * 30 + 5);
        }
        // A simple storm spot for Jupiter
        if(colorStr === '#d39c7e') {
            ctx.fillStyle = 'rgba(180, 80, 50, 0.4)';
            ctx.beginPath();
            ctx.ellipse(256, 170, 40, 20, 0, 0, 2 * Math.PI);
            ctx.fill();
        }
    } else if (type === 'Sun') {
        // Plasma effect for Sun
        for(let i=0; i<150; i++) {
            ctx.fillStyle = `rgba(255, 180, 50, ${Math.random() * 0.4})`;
            ctx.beginPath();
            ctx.arc(Math.random() * 512, Math.random() * 256, Math.random() * 25, 0, Math.PI * 2);
            ctx.fill();
        }
    } else {
        // Craters and noise for terrestrial planets
        for(let i=0; i<500; i++) {
            ctx.fillStyle = `rgba(0, 0, 0, ${Math.random() * 0.2})`;
            ctx.beginPath();
            ctx.arc(Math.random() * 512, Math.random() * 256, Math.random() * 5, 0, Math.PI * 2);
            ctx.fill();
        }
        for(let i=0; i<200; i++) {
            ctx.fillStyle = `rgba(255, 255, 255, ${Math.random() * 0.1})`;
            ctx.beginPath();
            ctx.arc(Math.random() * 512, Math.random() * 256, Math.random() * 3, 0, Math.PI * 2);
            ctx.fill();
        }
    }
    
    const texture = new THREE.CanvasTexture(canvas);
    return texture;
}

function generateRingTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');
    
    const cx = 256, cy = 256, r = 256;
    const grad = ctx.createRadialGradient(cx, cy, r*0.3, cx, cy, r);
    // Create distinctive gaps and bands for Saturn's rings
    grad.addColorStop(0, 'rgba(255,255,255,0)');
    grad.addColorStop(0.1, 'rgba(230,220,200,0.8)');
    grad.addColorStop(0.3, 'rgba(230,220,200,0.9)');
    grad.addColorStop(0.4, 'rgba(255,255,255,0.1)'); // Cassini Division approximation
    grad.addColorStop(0.5, 'rgba(230,220,200,0.8)');
    grad.addColorStop(0.8, 'rgba(200,190,170,0.5)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    
    ctx.fillStyle = grad;
    ctx.fillRect(0,0,512,512);
    
    return new THREE.CanvasTexture(canvas);
}

function createLabel(object3D, text, isMoon = false) {
    const div = document.createElement('div');
    div.className = 'body-label' + (isMoon ? ' moon-label hidden' : '');
    div.textContent = text;
    labelContainer.appendChild(div);
    
    // Prevent dragging from starting when clicking label
    div.addEventListener('pointerdown', (e) => e.stopPropagation());
    
    div.addEventListener('click', (e) => {
        e.stopPropagation();
        selectBody(object3D);
    });

    labels.push({ element: div, object3D, isMoon });
}

function updateEnvironment(type) {
    scene.background = null; 
    if (scene.children.find(c => c.name === 'starfield')) {
        scene.remove(scene.children.find(c => c.name === 'starfield'));
    }

    if (type === 'stars' || type === 'deep' || type === 'nebula') {
        const starGeo = new THREE.BufferGeometry();
        const starCount = 8000;
        const positions = new Float32Array(starCount * 3);
        const colors = new Float32Array(starCount * 3);
        
        for(let i=0; i<starCount*3; i+=3) {
            positions[i] = (Math.random() - 0.5) * 2000;
            positions[i+1] = (Math.random() - 0.5) * 2000;
            positions[i+2] = (Math.random() - 0.5) * 2000;
            
            const color = new THREE.Color();
            if (type === 'nebula') {
                // Purple/Pink/Blue hues
                color.setHSL(Math.random() * 0.2 + 0.6, 0.8, Math.random() * 0.5 + 0.5);
            } else {
                // White/Light Blue hues
                color.setHSL(Math.random() * 0.1 + 0.5, 0.2, Math.random() * 0.5 + 0.5);
            }
            colors[i] = color.r;
            colors[i+1] = color.g;
            colors[i+2] = color.b;
        }
        
        starGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        starGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        
        const starMat = new THREE.PointsMaterial({ 
            size: type === 'stars' ? 1.5 : 2, 
            vertexColors: true,
            transparent: true,
            opacity: type === 'deep' ? 0.3 : 0.8
        });
        
        const starField = new THREE.Points(starGeo, starMat);
        starField.name = 'starfield';
        scene.add(starField);
        
        if (type === 'nebula') {
            scene.background = new THREE.Color(0x0a0515); // Deep purple-blue
        } else if (type === 'deep') {
            scene.background = new THREE.Color(0x000000); // Pitch black
        } else {
            scene.background = new THREE.Color(0x050508); // Very dark gray
        }
    }
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function onMouseClick(event) {
    if(event.target !== renderer.domElement) return; // Don't trigger if clicking UI
    
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    // Intersect only bodies, not orbits or stars
    const intersectables = celestialBodies.map(b => b.mesh);
    const intersects = raycaster.intersectObjects(intersectables, false);

    if (intersects.length > 0) {
        selectBody(intersects[0].object);
    }
}

function selectBody(mesh) {
    targetedBody = mesh;
    const data = mesh.userData.data;
    const parentData = mesh.userData.parentData;
    
    showInfoPanel(data, parentData);
    
    // Manage moon labels visibility based on selection
    labels.forEach(l => {
        if(l.isMoon) {
            const moonData = l.object3D.userData.data;
            const isChildOfSelected = data.moons && data.moons.find(m => m.id === moonData.id);
            const isSibling = parentData && parentData.moons.find(m => m.id === moonData.id);
            const isSelf = data.id === moonData.id;
            
            if (isChildOfSelected || isSibling || isSelf) {
                l.element.classList.remove('hidden');
            } else {
                l.element.classList.add('hidden');
            }
        }
    });
}

function showInfoPanel(data, parentData) {
    const color = data.color || (parentData ? parentData.color : '#ccc');
    let moonsHtml = '';
    
    if (data.moons && data.moons.length > 0) {
        moonsHtml = `
            <div class="moons-section">
                <h3>Major Moons</h3>
                <div>
                    ${data.moons.map(m => `<span class="moon-tag" data-id="${m.id}">${m.name}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    let noteHtml = data.note ? `<p style="font-size: 0.85rem; color: #aaa; margin-top: 15px; font-style: italic;">${data.note}</p>` : '';

    infoContent.innerHTML = `
        <div class="info-header">
            <div class="info-color-swatch" style="background-color: ${color}"></div>
            <div>
                <div class="info-title">${data.name}</div>
                <div class="info-type">${data.type} ${parentData ? `(Orbits ${parentData.name})` : ''}</div>
            </div>
        </div>
        
        <div class="info-fact">
            "${data.fact}"
        </div>
        
        <div class="info-grid">
            <div class="info-item">
                <div class="info-label">Diameter</div>
                <div class="info-value">${data.diameter}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Orbit</div>
                <div class="info-value">${data.orbit}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Notable Features</div>
                <div class="info-value">${data.features}</div>
            </div>
        </div>
        
        ${moonsHtml}
        ${noteHtml}
    `;

    infoPanel.classList.remove('hidden');

    // Add click listeners to newly created moon tags
    const tags = infoContent.querySelectorAll('.moon-tag');
    tags.forEach(tag => {
        tag.addEventListener('click', () => {
            const moonId = tag.getAttribute('data-id');
            const moonObj = celestialBodies.find(b => b.data.id === moonId);
            if (moonObj) selectBody(moonObj.mesh);
        });
    });
}

function closeInfoPanel() {
    infoPanel.classList.add('hidden');
    // Hide all moon labels again
    labels.forEach(l => {
        if(l.isMoon) l.element.classList.add('hidden');
    });
}

function handleSearch(e) {
    const q = e.target.value.toLowerCase().trim();
    searchResults.innerHTML = '';
    
    if (!q) {
        searchResults.classList.add('hidden');
        return;
    }

    const matches = celestialBodies.filter(b => b.data.name.toLowerCase().includes(q));
    
    if (matches.length === 0) {
        searchResults.innerHTML = '<div class="search-result-item" style="color:#aaa; cursor:default;">No results found</div>';
    } else {
        matches.forEach(m => {
            const div = document.createElement('div');
            div.className = 'search-result-item';
            div.innerHTML = `<strong>${m.data.name}</strong> <span style="color:#aaa; font-size:0.8rem;">${m.isMoon ? '(Moon)' : '(Planet/Star)'}</span>`;
            div.addEventListener('click', () => {
                selectBody(m.mesh);
                searchInput.value = '';
                searchResults.classList.add('hidden');
            });
            searchResults.appendChild(div);
        });
    }
    searchResults.classList.remove('hidden');
}

function animate() {
    requestAnimationFrame(animate);

    if (!isPaused) {
        const delta = timeScale * 0.001;
        time += delta;

        celestialBodies.forEach(body => {
            // Orbital rotation
            if (body.orbitGroup && body.speed) {
                body.orbitGroup.rotation.y += body.speed * (timeScale / 20);
            }
            // Axial rotation
            if (body.mesh) {
                body.mesh.rotation.y += 0.01 * (timeScale / 20);
            }
        });
    }

    // Camera follow target smoothly
    if (targetedBody) {
        const targetWorldPos = new THREE.Vector3();
        targetedBody.getWorldPosition(targetWorldPos);
        
        // Lerp the controls target to the celestial body position
        controls.target.lerp(targetWorldPos, 0.05);
    }

    controls.update();

    // Update 2D labels positions
    labels.forEach(label => {
        if (!label.element.classList.contains('hidden')) {
            const pos = new THREE.Vector3();
            label.object3D.getWorldPosition(pos);
            
            // Project 3D position to 2D screen space
            pos.project(camera);
            
            // If z > 1, the object is behind the camera
            if (pos.z > 1) {
                label.element.style.display = 'none';
            } else {
                label.element.style.display = '';
                const x = (pos.x * .5 + .5) * window.innerWidth;
                const y = (pos.y * -.5 + .5) * window.innerHeight;
                label.element.style.left = `${x}px`;
                label.element.style.top = `${y}px`;
            }
        }
    });

    renderer.render(scene, camera);
}
