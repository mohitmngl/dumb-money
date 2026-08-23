import SOLAR_SYSTEM_DATA from './solar-system-data.js';

class SolarSystemApp {
  constructor() {
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.celestialBodies = [];
    this.labels = [];
    this.orbits = [];
    this.selectedBody = null;
    this.isAnimating = true;
    this.animationSpeed = 1;
    this.clock = new THREE.Clock();
    this.showLabels = true;
    this.showOrbits = true;
    this.bodyAngles = {};
    this.backgroundMode = 'starfield';
    this.focusedBody = null;
    this.cameraTarget = new THREE.Vector3(0, 0, 0);

    this.init();
  }

  init() {
    this.createScene();
    this.createLighting();
    this.createStarfield();
    this.createSolarSystem();
    this.createControls();
    this.setupEventListeners();
    this.animate();
  }

  createScene() {
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x000011, 0.0008);

    this.camera = new THREE.PerspectiveCamera(
      60,
      window.innerWidth / window.innerHeight,
      0.1,
      10000
    );
    this.camera.position.set(50, 30, 80);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.2;

    document.getElementById('canvas-container').appendChild(this.renderer.domElement);
  }

  createLighting() {
    const ambientLight = new THREE.AmbientLight(0x111122, 0.3);
    this.scene.add(ambientLight);

    const sunLight = new THREE.PointLight(0xfff5e6, 2.5, 500, 1.5);
    sunLight.position.set(0, 0, 0);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 2048;
    sunLight.shadow.mapSize.height = 2048;
    this.scene.add(sunLight);

    const sunGlow = new THREE.PointLight(0xffaa33, 1.5, 200, 2);
    sunGlow.position.set(0, 0, 0);
    this.scene.add(sunGlow);
  }

  createStarfield() {
    const starsGeometry = new THREE.BufferGeometry();
    const starsCount = 15000;
    const positions = new Float32Array(starsCount * 3);
    const colors = new Float32Array(starsCount * 3);
    const sizes = new Float32Array(starsCount);

    for (let i = 0; i < starsCount; i++) {
      const i3 = i * 3;
      const radius = 2000 + Math.random() * 2000;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      positions[i3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i3 + 2] = radius * Math.cos(phi);

      const colorChoice = Math.random();
      if (colorChoice < 0.1) {
        colors[i3] = 0.7; colors[i3 + 1] = 0.8; colors[i3 + 2] = 1.0;
      } else if (colorChoice < 0.15) {
        colors[i3] = 1.0; colors[i3 + 1] = 0.9; colors[i3 + 2] = 0.7;
      } else {
        colors[i3] = 0.95; colors[i3 + 1] = 0.95; colors[i3 + 2] = 1.0;
      }

      sizes[i] = 0.5 + Math.random() * 1.5;
    }

    starsGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    starsGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    starsGeometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    const starsMaterial = new THREE.PointsMaterial({
      size: 1.5,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      sizeAttenuation: true
    });

    this.starField = new THREE.Points(starsGeometry, starsMaterial);
    this.scene.add(this.starField);
  }

  createNebulaBackground() {
    if (this.nebulaGroup) {
      this.scene.remove(this.nebulaGroup);
    }

    this.nebulaGroup = new THREE.Group();
    const nebulaCount = 30;

    for (let i = 0; i < nebulaCount; i++) {
      const geometry = new THREE.SphereGeometry(100 + Math.random() * 200, 16, 16);
      const material = new THREE.MeshBasicMaterial({
        color: new THREE.Color().setHSL(
          0.6 + Math.random() * 0.2,
          0.4 + Math.random() * 0.3,
          0.1 + Math.random() * 0.1
        ),
        transparent: true,
        opacity: 0.03 + Math.random() * 0.04,
        side: THREE.BackSide
      });
      const nebula = new THREE.Mesh(geometry, material);
      nebula.position.set(
        (Math.random() - 0.5) * 3000,
        (Math.random() - 0.5) * 3000,
        (Math.random() - 0.5) * 3000
      );
      nebula.scale.setScalar(1 + Math.random() * 2);
      this.nebulaGroup.add(nebula);
    }

    this.scene.add(this.nebulaGroup);
  }

  setBackground(mode) {
    this.backgroundMode = mode;
    if (this.nebulaGroup) {
      this.scene.remove(this.nebulaGroup);
      this.nebulaGroup = null;
    }

    if (mode === 'nebula') {
      this.createNebulaBackground();
      this.renderer.setClearColor(0x050510, 1);
    } else if (mode === 'minimal') {
      this.renderer.setClearColor(0x000005, 1);
      if (this.starField) this.starField.visible = false;
      return;
    } else {
      this.renderer.setClearColor(0x000008, 1);
    }

    if (this.starField) this.starField.visible = true;
  }

  createPlanetMaterial(data) {
    const color = new THREE.Color(data.color);
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');

    const gradient = ctx.createLinearGradient(0, 0, 256, 128);
    const hsl = {};
    color.getHSL(hsl);

    gradient.addColorStop(0, color.getStyle());
    gradient.addColorStop(0.3, new THREE.Color().setHSL(hsl.h, hsl.s * 0.8, hsl.l * 0.7).getStyle());
    gradient.addColorStop(0.5, color.getStyle());
    gradient.addColorStop(0.7, new THREE.Color().setHSL(hsl.h, hsl.s * 0.9, hsl.l * 0.6).getStyle());
    gradient.addColorStop(1, new THREE.Color().setHSL(hsl.h, hsl.s * 0.7, hsl.l * 0.5).getStyle());

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 256, 128);

    for (let i = 0; i < 50; i++) {
      const x = Math.random() * 256;
      const y = Math.random() * 128;
      const r = 1 + Math.random() * 4;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0,0,0,${0.05 + Math.random() * 0.1})`;
      ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;

    return new THREE.MeshStandardMaterial({
      map: texture,
      roughness: 0.7,
      metalness: 0.1
    });
  }

  createSun() {
    const sunData = SOLAR_SYSTEM_DATA.sun;
    const geometry = new THREE.SphereGeometry(sunData.size, 64, 64);

    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    const gradient = ctx.createRadialGradient(256, 128, 0, 256, 128, 256);
    gradient.addColorStop(0, '#ffffff');
    gradient.addColorStop(0.2, '#ffee88');
    gradient.addColorStop(0.5, '#ffaa33');
    gradient.addColorStop(0.8, '#ff6600');
    gradient.addColorStop(1, '#cc3300');

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 512, 256);

    for (let i = 0; i < 100; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 256;
      const r = 2 + Math.random() * 8;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,200,50,${0.1 + Math.random() * 0.2})`;
      ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);

    const material = new THREE.MeshBasicMaterial({
      map: texture,
      emissive: 0xffaa33,
      emissiveIntensity: 1.5
    });

    const sun = new THREE.Mesh(geometry, material);
    sun.position.set(0, 0, 0);
    sun.userData = { type: 'sun', data: sunData, name: sunData.name };

    this.scene.add(sun);
    this.celestialBodies.push(sun);
    this.bodyAngles[sunData.name] = 0;

    const glowGeometry = new THREE.SphereGeometry(sunData.size * 1.15, 32, 32);
    const glowMaterial = new THREE.MeshBasicMaterial({
      color: 0xffaa33,
      transparent: true,
      opacity: 0.15,
      side: THREE.BackSide
    });
    const sunGlow = new THREE.Mesh(glowGeometry, glowMaterial);
    sun.add(sunGlow);
  }

  createPlanet(key, data) {
    const geometry = new THREE.SphereGeometry(data.size, 48, 48);
    const material = this.createPlanetMaterial(data);
    const planet = new THREE.Mesh(geometry, material);
    planet.position.set(data.position[0], data.position[1], data.position[2]);
    planet.castShadow = true;
    planet.receiveShadow = true;
    planet.userData = { type: 'planet', data: data, name: data.name, key: key };

    this.scene.add(planet);
    this.celestialBodies.push(planet);
    this.bodyAngles[data.name] = 0;

    this.createOrbitPath(data.position[0], data.name);

    if (key === 'saturn') {
      this.createSaturnRings(planet, data);
    }

    if (key === 'uranus') {
      planet.rotation.z = THREE.MathUtils.degToRad(98);
    }

    if (data.moons && data.moons.length > 0) {
      data.moons.forEach((moon, index) => {
        this.createMoon(moon, planet, data, index, data.moons.length);
      });
    }
  }

  createSaturnRings(planet, data) {
    const innerRadius = data.size * 1.4;
    const outerRadius = data.size * 2.2;

    const ringGeometry = new THREE.RingGeometry(innerRadius, outerRadius, 128);
    const pos = ringGeometry.attributes.position;
    const uv = ringGeometry.attributes.uv;

    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const dist = Math.sqrt(x * x + y * y);
      const t = (dist - innerRadius) / (outerRadius - innerRadius);

      if (t > 0.2 && t < 0.3) {
        pos.setZ(i, 0.02);
      } else if (t > 0.5 && t < 0.55) {
        pos.setZ(i, 0.01);
      }
    }

    ringGeometry.computeVertexNormals();

    const ringCanvas = document.createElement('canvas');
    ringCanvas.width = 512;
    ringCanvas.height = 64;
    const ringCtx = ringCanvas.getContext('2d');

    const ringGradient = ringCtx.createLinearGradient(0, 0, 512, 0);
    ringGradient.addColorStop(0, 'rgba(180,160,120,0.1)');
    ringGradient.addColorStop(0.15, 'rgba(200,180,140,0.8)');
    ringGradient.addColorStop(0.2, 'rgba(180,160,120,0.2)');
    ringGradient.addColorStop(0.3, 'rgba(210,190,150,0.9)');
    ringGradient.addColorStop(0.5, 'rgba(190,170,130,0.7)');
    ringGradient.addColorStop(0.55, 'rgba(170,150,110,0.1)');
    ringGradient.addColorStop(0.65, 'rgba(200,180,140,0.85)');
    ringGradient.addColorStop(0.8, 'rgba(180,160,120,0.6)');
    ringGradient.addColorStop(1, 'rgba(160,140,100,0.1)');

    ringCtx.fillStyle = ringGradient;
    ringCtx.fillRect(0, 0, 512, 64);

    for (let i = 0; i < 200; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 64;
      ringCtx.fillStyle = `rgba(0,0,0,${0.05 + Math.random() * 0.1})`;
      ringCtx.fillRect(x, y, 2, 2);
    }

    const ringTexture = new THREE.CanvasTexture(ringCanvas);

    const ringMaterial = new THREE.MeshBasicMaterial({
      map: ringTexture,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
      depthWrite: false
    });

    const ring = new THREE.Mesh(ringGeometry, ringMaterial);
    ring.rotation.x = Math.PI / 2;
    planet.add(ring);
  }

  createMoon(moonData, parentPlanet, planetData, index, totalMoons) {
    const geometry = new THREE.SphereGeometry(moonData.size, 24, 24);
    const material = new THREE.MeshStandardMaterial({
      color: moonData.color,
      roughness: 0.8,
      metalness: 0.1
    });

    const moon = new THREE.Mesh(geometry, material);
    const orbitRadius = planetData.size * 1.5 + (index + 1) * 0.6;
    moon.position.set(orbitRadius, 0, 0);
    moon.castShadow = true;

    moon.userData = {
      type: 'moon',
      data: moonData,
      name: moonData.name,
      parentName: planetData.name,
      orbitRadius: orbitRadius,
      orbitSpeed: 0.5 + (totalMoons - index) * 0.15,
      orbitOffset: index * (Math.PI * 2 / totalMoons)
    };

    parentPlanet.add(moon);
    this.celestialBodies.push(moon);
    this.bodyAngles[moonData.name] = 0;
  }

  createOrbitPath(radius, name) {
    const curve = new THREE.EllipseCurve(
      0, 0,
      radius, radius,
      0, 2 * Math.PI,
      false,
      0
    );

    const points = curve.getPoints(128);
    const geometry = new THREE.BufferGeometry().setFromPoints(
      points.map(p => new THREE.Vector3(p.x, 0, p.y))
    );

    const material = new THREE.LineBasicMaterial({
      color: 0x4466aa,
      transparent: true,
      opacity: 0.25,
      linewidth: 1
    });

    const orbit = new THREE.Line(geometry, material);
    orbit.userData = { bodyName: name };
    this.scene.add(orbit);
    this.orbits.push(orbit);
  }

  createSolarSystem() {
    this.createSun();

    const planetKeys = ['mercury', 'venus', 'earth', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune'];
    planetKeys.forEach(key => {
      this.createPlanet(key, SOLAR_SYSTEM_DATA[key]);
    });
  }

  createControls() {
    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.rotateSpeed = 0.5;
    this.controls.zoomSpeed = 1.2;
    this.controls.panSpeed = 0.8;
    this.controls.minDistance = 5;
    this.controls.maxDistance = 500;
    this.controls.enablePan = true;
  }

  setupEventListeners() {
    window.addEventListener('resize', () => this.onResize());
    this.renderer.domElement.addEventListener('click', (e) => this.onClick(e));
    this.renderer.domElement.addEventListener('mousemove', (e) => this.onMouseMove(e));

    document.getElementById('search-input').addEventListener('input', (e) => this.onSearch(e.target.value));
    document.getElementById('search-input').addEventListener('focus', () => {
      const val = document.getElementById('search-input').value;
      if (val) this.onSearch(val);
    });
    document.getElementById('search-input').addEventListener('blur', () => {
      setTimeout(() => {
        document.getElementById('search-results').classList.remove('visible');
      }, 200);
    });

    document.getElementById('btn-labels').addEventListener('click', () => this.toggleLabels());
    document.getElementById('btn-orbits').addEventListener('click', () => this.toggleOrbits());
    document.getElementById('btn-animate').addEventListener('click', () => this.toggleAnimation());
    document.getElementById('btn-reset').addEventListener('click', () => this.resetCamera());
    document.getElementById('btn-about').addEventListener('click', () => this.showAbout());
    document.getElementById('about-close').addEventListener('click', () => this.hideAbout());
    document.getElementById('about-modal').addEventListener('click', (e) => {
      if (e.target.id === 'about-modal') this.hideAbout();
    });

    document.getElementById('speed-slider').addEventListener('input', (e) => {
      this.animationSpeed = parseFloat(e.target.value);
      document.getElementById('speed-value').textContent = this.animationSpeed.toFixed(1) + 'x';
    });

    document.querySelectorAll('.bg-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.bg-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.setBackground(btn.dataset.bg);
      });
    });
  }

  onResize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  onClick(event) {
    this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);

    const intersects = this.raycaster.intersectObjects(this.celestialBodies, true);
    if (intersects.length > 0) {
      let clicked = intersects[0].object;
      while (clicked.parent && !clicked.userData.type) {
        clicked = clicked.parent;
      }
      if (clicked.userData.type) {
        this.selectBody(clicked);
      }
    }
  }

  onMouseMove(event) {
    this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.celestialBodies, true);

    const tooltip = document.getElementById('tooltip');

    if (intersects.length > 0) {
      let hovered = intersects[0].object;
      while (hovered.parent && !hovered.userData.type) {
        hovered = hovered.parent;
      }
      if (hovered.userData.name) {
        tooltip.textContent = hovered.userData.name;
        tooltip.style.left = event.clientX + 15 + 'px';
        tooltip.style.top = event.clientY - 10 + 'px';
        tooltip.classList.add('visible');
        document.body.style.cursor = 'pointer';
        return;
      }
    }

    tooltip.classList.remove('visible');
    document.body.style.cursor = 'default';
  }

  selectBody(body) {
    this.selectedBody = body;
    this.focusedBody = body;
    this.showInfoPanel(body.userData.data, body.userData.type, body.userData.parentName);
    this.focusOnBody(body);
  }

  showInfoPanel(data, type, parentName) {
    const panel = document.getElementById('info-panel');
    const colorHex = '#' + new THREE.Color(data.color).getHexString();

    let html = `
      <button class="close-btn" onclick="document.getElementById('info-panel').classList.add('hidden')">×</button>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
        <div class="planet-icon" style="background:${colorHex};box-shadow:0 0 15px ${colorHex}88;"></div>
        <div>
          <h2>${data.name}</h2>
          <div class="planet-type">${data.type}</div>
        </div>
      </div>
      <div class="info-section">
        <div class="info-label">Diameter</div>
        <div class="info-value">${data.diameter}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Orbit</div>
        <div class="info-value">${data.orbit}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Notable Features</div>
        <div class="info-value">${data.features}</div>
      </div>
      <div class="info-section fun-fact">
        <div class="info-label">Memorable Fact</div>
        <div class="info-value">${data.funFact}</div>
      </div>
    `;

    if (type === 'planet' && data.moons && data.moons.length > 0) {
      html += `
        <div class="moon-list">
          <h3>Known Moons (${data.moons.length} shown)</h3>
          ${data.moons.map(moon => `
            <div class="moon-item" onclick="window.app.selectMoon('${moon.name}', '${data.name}')">
              <div class="moon-icon" style="background:#${new THREE.Color(moon.color).getHexString()};"></div>
              <div>
                <div class="moon-name">${moon.name}</div>
              </div>
              <div class="moon-extra">${moon.diameter}</div>
            </div>
          `).join('')}
          ${this.getAdditionalMoonNote(data.name)}
        </div>
      `;
    }

    panel.innerHTML = html;
    panel.classList.remove('hidden');
  }

  getAdditionalMoonNote(planetName) {
    const notes = {
      'Jupiter': 'Jupiter has 79+ confirmed moons in total',
      'Saturn': 'Saturn has 82+ confirmed moons in total',
      'Uranus': 'Uranus has 27+ confirmed moons in total',
      'Neptune': 'Neptune has 16+ confirmed moons in total'
    };
    if (notes[planetName]) {
      return `<div style="font-size:10px;color:#667788;padding:8px;font-style:italic;">${notes[planetName]}</div>`;
    }
    return '';
  }

  selectMoon(moonName, parentName) {
    const moonBody = this.celestialBodies.find(b => b.userData.name === moonName && b.userData.parentName === parentName);
    if (moonBody) {
      this.selectBody(moonBody);
    }
  }

  focusOnBody(body) {
    const worldPos = new THREE.Vector3();
    body.getWorldPosition(worldPos);

    const offset = body.userData.data.size ? body.userData.data.size * 4 : 5;
    const targetCameraPos = new THREE.Vector3(
      worldPos.x + offset,
      worldPos.y + offset * 0.5,
      worldPos.z + offset
    );

    this.animateCamera(targetCameraPos, worldPos);
  }

  animateCamera(targetPos, lookAt) {
    const startPos = this.camera.position.clone();
    const startTarget = this.controls.target.clone();
    const duration = 1500;
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const t = Math.min(elapsed / duration, 1);
      const easeT = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

      this.camera.position.lerpVectors(startPos, targetPos, easeT);
      this.controls.target.lerpVectors(startTarget, lookAt, easeT);
      this.controls.update();

      if (t < 1) {
        requestAnimationFrame(animate);
      }
    };
    animate();
  }

  onSearch(query) {
    const resultsContainer = document.getElementById('search-results');
    if (!query.trim()) {
      resultsContainer.classList.remove('visible');
      return;
    }

    const q = query.toLowerCase();
    const results = [];

    Object.values(SOLAR_SYSTEM_DATA).forEach(body => {
      if (body.name.toLowerCase().includes(q)) {
        results.push({ name: body.name, type: body.type, key: body.name });
      }
      if (body.moons) {
        body.moons.forEach(moon => {
          if (moon.name.toLowerCase().includes(q)) {
            results.push({ name: moon.name, type: `Moon of ${body.name}`, key: moon.name, parent: body.name });
          }
        });
      }
    });

    if (results.length === 0) {
      resultsContainer.innerHTML = '<div class="no-results">No matching celestial bodies found</div>';
    } else {
      resultsContainer.innerHTML = results.map(r => `
        <div class="search-item" onclick="window.app.searchSelect('${r.name}', '${r.parent || ''}')">
          <div class="search-item-name">${r.name}</div>
          <div class="search-item-type">${r.type}</div>
        </div>
      `).join('');
    }
    resultsContainer.classList.add('visible');
  }

  searchSelect(name, parent) {
    document.getElementById('search-input').value = '';
    document.getElementById('search-results').classList.remove('visible');

    const body = this.celestialBodies.find(b => {
      if (parent) {
        return b.userData.name === name && b.userData.parentName === parent;
      }
      return b.userData.name === name;
    });

    if (body) {
      this.selectBody(body);
    }
  }

  toggleLabels() {
    this.showLabels = !this.showLabels;
    document.getElementById('btn-labels').classList.toggle('active', this.showLabels);
  }

  toggleOrbits() {
    this.showOrbits = !this.showOrbits;
    document.getElementById('btn-orbits').classList.toggle('active', this.showOrbits);
    this.orbits.forEach(orbit => {
      orbit.visible = this.showOrbits;
    });
  }

  toggleAnimation() {
    this.isAnimating = !this.isAnimating;
    const btn = document.getElementById('btn-animate');
    btn.classList.toggle('active', this.isAnimating);
    btn.textContent = this.isAnimating ? '⏸ Pause' : '▶ Play';
  }

  resetCamera() {
    this.focusedBody = null;
    this.selectedBody = null;
    document.getElementById('info-panel').classList.add('hidden');
    this.animateCamera(
      new THREE.Vector3(50, 30, 80),
      new THREE.Vector3(0, 0, 0)
    );
  }

  showAbout() {
    document.getElementById('about-modal').classList.add('visible');
  }

  hideAbout() {
    document.getElementById('about-modal').classList.remove('visible');
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    const delta = this.clock.getDelta();
    const elapsed = this.clock.getElapsedTime();

    if (this.isAnimating) {
      this.celestialBodies.forEach(body => {
        if (body.userData.type === 'sun') {
          body.rotation.y += 0.001 * this.animationSpeed;
        } else if (body.userData.type === 'planet') {
          const orbitSpeed = 0.2 / (body.position.length() * 0.1);
          body.rotation.y += 0.01 * this.animationSpeed;
          const angle = elapsed * orbitSpeed * this.animationSpeed;
          const radius = body.position.length();
          body.position.x = Math.cos(angle) * radius;
          body.position.z = Math.sin(angle) * radius;
        } else if (body.userData.type === 'moon') {
          const moonAngle = elapsed * body.userData.orbitSpeed * this.animationSpeed + body.userData.orbitOffset;
          body.position.x = Math.cos(moonAngle) * body.userData.orbitRadius;
          body.position.z = Math.sin(moonAngle) * body.userData.orbitRadius;
          body.position.y = Math.sin(moonAngle * 0.5) * 0.1;
        }
      });
    }

    if (this.focusedBody) {
      const worldPos = new THREE.Vector3();
      this.focusedBody.getWorldPosition(worldPos);
      this.controls.target.copy(worldPos);
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.app = new SolarSystemApp();
});
