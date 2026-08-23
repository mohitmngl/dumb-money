import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { solarSystemData } from './solar-system-data.js';

const state = {
  scene: null, camera: null, renderer: null, controls: null,
  sun: null, sunGlow: null,
  planetGroups: {},
  bodyMeshes: [],
  orbitLines: [],
  labelSprites: [],
  starField: null, nebulaParticles: null,
  highlightRing: null, highlightParent: null,
  isPaused: false, speed: 1, showOrbits: true, showLabels: true, autoRotate: false,
  selectedBodyId: null,
  clock: new THREE.Clock(),
  raycaster: new THREE.Raycaster(),
  pointer: new THREE.Vector2(),
  orbitalAngles: {}, moonAngles: {},
  bodyDataMap: {},
  cameraDefault: new THREE.Vector3(30, 25, 50)
};

function hash(x, y) {
  const v = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return v - Math.floor(v);
}

function smoothNoise(x, y) {
  const ix = Math.floor(x); const iy = Math.floor(y);
  const fx = x - ix; const fy = y - iy;
  const sx = fx * fx * (3 - 2 * fx); const sy = fy * fy * (3 - 2 * fy);
  const v00 = hash(ix, iy); const v10 = hash(ix + 1, iy);
  const v01 = hash(ix, iy + 1); const v11 = hash(ix + 1, iy + 1);
  return v00 * (1 - sx) * (1 - sy) + v10 * sx * (1 - sy) + v01 * (1 - sx) * sy + v11 * sx * sy;
}

function fbm(x, y, oct = 4) {
  let v = 0, a = 0.5, f = 1;
  for (let i = 0; i < oct; i++) { v += a * smoothNoise(x * f, y * f); a *= 0.5; f *= 2; }
  return v;
}

function warpNoise(x, y) {
  const wx = fbm(x * 2, y * 2, 3) * 0.3;
  const wy = fbm(x * 2 + 5.2, y * 2 + 1.3, 3) * 0.3;
  return fbm(x + wx, y + wy, 6);
}

function makePixels(w, h, fn) {
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(w, h);
  const d = img.data;
  fn(d, w, h);
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function sunTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = fbm(u * 8, v * 8, 5);
      const bright = 1 - n * 0.4 + smoothNoise(u * 20, v * 20) * 0.15;
      const i = (y * w + x) * 4;
      d[i] = Math.min(255, Math.round(255 * bright));
      d[i + 1] = Math.min(255, Math.round(200 * bright));
      d[i + 2] = Math.min(255, Math.round(80 * bright));
      d[i + 3] = 255;
    }
  });
}

function sunGlowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, 'rgba(255,230,150,1)');
  g.addColorStop(0.15, 'rgba(255,200,80,0.8)');
  g.addColorStop(0.35, 'rgba(255,150,30,0.4)');
  g.addColorStop(0.6, 'rgba(255,80,10,0.15)');
  g.addColorStop(1, 'rgba(255,50,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

function mercuryTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = fbm(u * 6, v * 6, 5);
      const crater = smoothNoise(u * 12, v * 12) > 0.6 ? 0.7 : 1;
      const base = 140 + n * 50;
      const i = (y * w + x) * 4;
      d[i] = Math.round(base * crater * (0.95 + 0.1 * smoothNoise(u * 3, v * 3)));
      d[i + 1] = Math.round(base * crater * (0.95 + 0.1 * smoothNoise(u * 3 + 1, v * 3)));
      d[i + 2] = Math.round(base * crater * (0.95 + 0.1 * smoothNoise(u * 3 + 2, v * 3)));
      d[i + 3] = 255;
    }
  });
}

function venusTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = fbm(u * 4 + smoothNoise(u * 2, v * 2) * 0.5, v * 4, 5);
      const streak = smoothNoise(u * 8, v * 2 + n * 0.3);
      const r = 180 + n * 40 + streak * 30;
      const g = 140 + n * 30 + streak * 20;
      const b = 60 + n * 20 + streak * 15;
      const i = (y * w + x) * 4;
      d[i] = Math.round(Math.min(255, r)); d[i + 1] = Math.round(Math.min(255, g));
      d[i + 2] = Math.round(Math.min(255, b)); d[i + 3] = 255;
    }
  });
}

function earthTexture() {
  return makePixels(512, 256, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const latFactor = Math.abs(v - 0.5) * 2;
      const polarIce = Math.max(0, 1 - latFactor * 3.5);
      const n = warpNoise(u * 3, v * 3);
      const i = (y * w + x) * 4;
      if (n > 0.42) {
        const green = Math.round(100 + 80 * (1 - latFactor));
        const red = Math.round(50 + 80 * (1 - latFactor));
        const blue = Math.round(30 + 30 * (1 - latFactor));
        d[i] = red; d[i + 1] = green; d[i + 2] = blue;
      } else {
        const depth = 1 - n / 0.42;
        d[i] = Math.round(15 + 30 * (1 - depth));
        d[i + 1] = Math.round(55 + 60 * (1 - depth));
        d[i + 2] = Math.round(150 + 50 * (1 - depth));
      }
      if (polarIce > 0.3) {
        const ice = Math.min(1, (polarIce - 0.3) * 4);
        d[i] = Math.round(d[i] * (1 - ice) + 245 * ice);
        d[i + 1] = Math.round(d[i + 1] * (1 - ice) + 248 * ice);
        d[i + 2] = Math.round(d[i + 2] * (1 - ice) + 252 * ice);
      }
      d[i + 3] = 255;
    }
  });
}

function earthCloudTexture() {
  return makePixels(512, 256, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = fbm(u * 5 + 3.7, v * 5 + 9.2, 5);
      const i = (y * w + x) * 4;
      const alpha = n > 0.5 ? Math.round((n - 0.5) * 2 * 200) : 0;
      d[i] = 255; d[i + 1] = 255; d[i + 2] = 255; d[i + 3] = alpha;
    }
  });
}

function marsTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = fbm(u * 5, v * 5, 5);
      const dark = smoothNoise(u * 3, v * 3) > 0.55 ? 0.75 : 1;
      const r = 170 + n * 40 * dark;
      const g = 90 + n * 30 * dark;
      const b = 40 + n * 20 * dark;
      const i = (y * w + x) * 4;
      d[i] = Math.round(r); d[i + 1] = Math.round(g);
      d[i + 2] = Math.round(b); d[i + 3] = 255;
    }
  });
}

function jupiterTexture() {
  return makePixels(512, 256, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const perturb = smoothNoise(u * 2, v * 8) * 0.04;
      const band = (v + perturb) * 20;
      const bv = Math.abs((band % 2) - 1);
      const n = fbm(u * 3, v * 6, 3) * 0.15;
      let r, g, bB;
      const bandIdx = Math.floor(band) % 6;
      switch (bandIdx) {
        case 0: r = 200; g = 160; bB = 100; break;
        case 1: r = 230; g = 200; bB = 150; break;
        case 2: r = 180; g = 130; bB = 80; break;
        case 3: r = 240; g = 220; bB = 190; break;
        case 4: r = 160; g = 110; bB = 60; break;
        default: r = 210; g = 180; bB = 140; break;
      }
      const greatRedX = 0.65, greatRedY = 0.52;
      const dx = u - greatRedX, dy = v - greatRedY;
      const distSpot = Math.sqrt(dx * dx * 3 + dy * dy * 12);
      if (distSpot < 0.07) {
        const spot = 1 - distSpot / 0.07;
        r += 40 * spot; g -= 20 * spot; bB -= 30 * spot;
      }
      const i = (y * w + x) * 4;
      d[i] = Math.round(Math.min(255, r + r * n));
      d[i + 1] = Math.round(Math.min(255, g + g * n));
      d[i + 2] = Math.round(Math.min(255, bB + bB * n));
      d[i + 3] = 255;
    }
  });
}

function saturnTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const perturb = smoothNoise(u * 2, v * 6) * 0.03;
      const band = (v + perturb) * 12;
      const n = fbm(u * 4, v * 5, 3) * 0.1;
      let r, g, bB;
      const bi = Math.floor(band) % 4;
      switch (bi) {
        case 0: r = 220; g = 200; bB = 150; break;
        case 1: r = 200; g = 180; bB = 130; break;
        case 2: r = 240; g = 220; bB = 180; break;
        default: r = 180; g = 160; bB = 110; break;
      }
      const i = (y * w + x) * 4;
      d[i] = Math.round(r + r * n); d[i + 1] = Math.round(g + g * n);
      d[i + 2] = Math.round(bB + bB * n); d[i + 3] = 255;
    }
  });
}

function uranusTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = smoothNoise(u * 4, v * 8) * 0.08;
      const r = 100 + n * 30; const g = 190 + n * 20; const bB = 210 + n * 10;
      const i = (y * w + x) * 4;
      d[i] = Math.round(r); d[i + 1] = Math.round(g);
      d[i + 2] = Math.round(bB); d[i + 3] = 255;
    }
  });
}

function neptuneTexture() {
  return makePixels(256, 128, (d, w, h) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const u = x / w, v = y / h;
      const n = fbm(u * 3, v * 5, 4) * 0.12;
      const storm = smoothNoise(u * 6, v * 6) > 0.55 ? 0.85 : 1;
      const r = 30 + n * 30; const g = 50 + n * 40; const bB = 180 + n * 40;
      const i = (y * w + x) * 4;
      d[i] = Math.round(r * storm); d[i + 1] = Math.round(g * storm);
      d[i + 2] = Math.round(bB * storm); d[i + 3] = 255;
    }
  });
}

function saturnRingTexture() {
  const c = document.createElement('canvas');
  c.width = 512; c.height = 64;
  const ctx = c.getContext('2d');
  for (let x = 0; x < 512; x++) {
    const t = x / 512;
    const n = fbm(t * 30, 0.5, 3);
    const bright = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * 100 + n * 2));
    const gap = Math.abs(t - 0.35) < 0.02 || Math.abs(t - 0.6) < 0.015 ? 0.1 : 1;
    const alpha = t > 0.1 && t < 0.92 ? bright * gap * 200 : 0;
    ctx.fillStyle = `rgba(210,190,150,${alpha / 255})`;
    ctx.fillRect(x, 0, 1, 64);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.ClampToEdgeWrapping;
  return tex;
}

function labelSprite(text, color = '#ffdd88') {
  const canvas = document.createElement('canvas');
  canvas.width = 512; canvas.height = 128;
  const ctx = canvas.getContext('2d');
  ctx.font = 'bold 48px Arial, sans-serif';
  const m = ctx.measureText(text);
  const tw = m.width;
  canvas.width = Math.max(512, tw + 40);
  canvas.height = 128;
  const ctx2 = canvas.getContext('2d');
  ctx2.font = 'bold 48px Arial, sans-serif';
  const pad = 16;
  ctx2.shadowColor = 'rgba(0,0,0,0.8)';
  ctx2.shadowBlur = 8;
  ctx2.fillStyle = 'rgba(0,0,0,0.5)';
  const rx = 12;
  ctx2.beginPath();
  ctx2.moveTo(rx, 0);
  ctx2.lineTo(canvas.width - rx, 0);
  ctx2.quadraticCurveTo(canvas.width, 0, canvas.width, rx);
  ctx2.lineTo(canvas.width, canvas.height - rx);
  ctx2.quadraticCurveTo(canvas.width, canvas.height, canvas.width - rx, canvas.height);
  ctx2.lineTo(rx, canvas.height);
  ctx2.quadraticCurveTo(0, canvas.height, 0, canvas.height - rx);
  ctx2.lineTo(0, rx);
  ctx2.quadraticCurveTo(0, 0, rx, 0);
  ctx2.closePath();
  ctx2.fill();
  ctx2.shadowColor = 'transparent';
  ctx2.fillStyle = color;
  ctx2.textAlign = 'center';
  ctx2.textBaseline = 'middle';
  ctx2.fillText(text, canvas.width / 2, 64);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(mat);
  const scale = Math.max(4, tw / 60);
  sprite.scale.set(scale, scale * 0.25, 1);
  return sprite;
}

function buildBodyMap() {
  const map = {};
  map[solarSystemData.sun.id] = { data: solarSystemData.sun, category: 'Star' };
  for (const p of solarSystemData.planets) {
    map[p.id] = { data: p, category: 'Planet' };
    for (const m of (p.moons || [])) {
      map[m.id] = { data: m, category: 'Moon', parentPlanet: p.name, parentId: p.id };
    }
  }
  return map;
}

function init() {
  state.bodyDataMap = buildBodyMap();
  state.scene = new THREE.Scene();
  state.camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 2000);
  state.camera.position.copy(state.cameraDefault);
  state.renderer = new THREE.WebGLRenderer({ antialias: true });
  state.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  state.renderer.setSize(window.innerWidth, window.innerHeight);
  if (typeof THREE.ACESFilmicToneMapping !== 'undefined') {
    state.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    state.renderer.toneMappingExposure = 1.0;
  }
  if (state.renderer.outputColorSpace !== undefined) {
    state.renderer.outputColorSpace = THREE.SRGBColorSpace;
  }
  document.getElementById('canvas-container').appendChild(state.renderer.domElement);
  state.controls = new OrbitControls(state.camera, state.renderer.domElement);
  state.controls.enableDamping = true;
  state.controls.dampingFactor = 0.08;
  state.controls.minDistance = 5;
  state.controls.maxDistance = 300;
  state.controls.target.set(0, 0, 0);
  const ambient = new THREE.AmbientLight(0x222244, 0.25);
  state.scene.add(ambient);
  const sunLight = new THREE.PointLight(0xffffff, 2.5, 300);
  sunLight.position.set(0, 0, 0);
  state.scene.add(sunLight);
  createSun();
  createPlanets();
  createOrbitLines();
  createEnvironment('starfield');
  createLabels();
  createHighlightRing();
  setupInteraction();
  setupSearch();
  setupControls();
  window.addEventListener('resize', onResize);
  document.getElementById('error-banner').classList.add('hidden');
  animate();
}

function createSun() {
  const sunGeo = new THREE.SphereGeometry(solarSystemData.sun.size, 48, 48);
  const sunMat = new THREE.MeshBasicMaterial({ map: sunTexture() });
  state.sun = new THREE.Mesh(sunGeo, sunMat);
  state.sun.userData.bodyId = 'sun';
  state.sun.userData.bodyName = 'Sun';
  state.scene.add(state.sun);
  state.bodyMeshes.push(state.sun);
  const glowMat = new THREE.SpriteMaterial({
    map: sunGlowTexture(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false
  });
  state.sunGlow = new THREE.Sprite(glowMat);
  state.sunGlow.scale.set(30, 30, 1);
  state.sunGlow.position.set(0, 0, 0);
  state.scene.add(state.sunGlow);
}

function createPlanets() {
  for (const pData of solarSystemData.planets) {
    const group = new THREE.Group();
    group.position.set(pData.orbitRadius, 0, 0);
    const tex = getPlanetTexture(pData.id);
    const geo = new THREE.SphereGeometry(pData.size, 32, 32);
    const mat = new THREE.MeshStandardMaterial({
      map: tex, roughness: 0.7, metalness: 0.1
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.userData.bodyId = pData.id;
    mesh.userData.bodyName = pData.name;
    mesh.rotation.z = pData.tilt || 0;
    group.add(mesh);
    state.bodyMeshes.push(mesh);
    if (pData.hasRings) {
      const ringGeo = new THREE.RingGeometry(pData.size * 1.3, pData.size * 2.6, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        map: saturnRingTexture(), side: THREE.DoubleSide, transparent: true, opacity: 0.7, depthWrite: false
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.rotation.x = Math.PI / 2.5;
      ringMesh.userData.bodyId = pData.id;
      ringMesh.userData.isRing = true;
      group.add(ringMesh);
    }
    if (pData.moons && pData.moons.length > 0) {
      for (const moonData of pData.moons) {
        const mGeo = new THREE.SphereGeometry(moonData.size, 16, 16);
        const mMat = new THREE.MeshStandardMaterial({
          color: moonData.color || 0xcccccc, roughness: 0.8
        });
        const mMesh = new THREE.Mesh(mGeo, mMat);
        mMesh.name = `moon_${moonData.id}`;
        mMesh.userData.bodyId = moonData.id;
        mMesh.userData.bodyName = moonData.name;
        mMesh.userData.parentPlanetId = pData.id;
        const angle = (Math.PI * 2 / pData.moons.length) * pData.moons.indexOf(moonData);
        mMesh.position.set(moonData.orbitRadius * Math.cos(angle), 0, moonData.orbitRadius * Math.sin(angle));
        group.add(mMesh);
        state.bodyMeshes.push(mMesh);
        state.moonAngles[moonData.id] = angle;
      }
    }
    state.scene.add(group);
    state.planetGroups[pData.id] = { group, data: pData, mesh };
    state.orbitalAngles[pData.id] = Math.random() * Math.PI * 2;
  }
}

function getPlanetTexture(id) {
  switch (id) {
    case 'mercury': return mercuryTexture();
    case 'venus': return venusTexture();
    case 'earth': return earthTexture();
    case 'mars': return marsTexture();
    case 'jupiter': return jupiterTexture();
    case 'saturn': return saturnTexture();
    case 'uranus': return uranusTexture();
    case 'neptune': return neptuneTexture();
    default: return null;
  }
}

function createOrbitLines() {
  for (const pData of solarSystemData.planets) {
    const segments = 64;
    const pts = [];
    for (let i = 0; i <= segments; i++) {
      const a = (i / segments) * Math.PI * 2;
      pts.push(new THREE.Vector3(pData.orbitRadius * Math.cos(a), 0, pData.orbitRadius * Math.sin(a)));
    }
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const col = new THREE.Color(pData.color || 0xffffff);
    col.multiplyScalar(0.5);
    const mat = new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.3 });
    const line = new THREE.Line(geo, mat);
    state.scene.add(line);
    state.orbitLines.push(line);
  }
}

function createLabels() {
  const sunLabel = labelSprite('Sun', '#ffdd44');
  sunLabel.position.set(0, solarSystemData.sun.size + 1.5, 0);
  sunLabel.userData.bodyId = 'sun';
  state.scene.add(sunLabel);
  state.labelSprites.push(sunLabel);
  for (const pData of solarSystemData.planets) {
    const pl = labelSprite(pData.name, '#ffffff');
    pl.position.set(0, pData.size + 1, 0);
    pl.userData.bodyId = pData.id;
    pl.userData.planetId = pData.id;
    state.planetGroups[pData.id].group.add(pl);
    state.labelSprites.push(pl);
    if (pData.moons && pData.moons.length > 0) {
      for (const moonData of pData.moons) {
        const ml = labelSprite(moonData.name, '#aaaacc');
        ml.position.set(0, moonData.size + 0.5, 0);
        ml.userData.bodyId = moonData.id;
        ml.userData.isMoonLabel = true;
        const moonMesh = state.planetGroups[pData.id].group.getObjectByName(`moon_${moonData.id}`);
        if (moonMesh) {
          moonMesh.add(ml);
        }
        state.labelSprites.push(ml);
      }
    }
  }
}

function createHighlightRing() {
  const geo = new THREE.TorusGeometry(1, 0.06, 16, 32);
  const mat = new THREE.MeshBasicMaterial({ color: 0x44ddff, transparent: true, opacity: 0.9 });
  state.highlightRing = new THREE.Mesh(geo, mat);
  state.highlightRing.visible = false;
  state.scene.add(state.highlightRing);
}

function createEnvironment(mode) {
  state.envMode = mode;
  if (state.starField) { state.scene.remove(state.starField); state.starField = null; }
  if (state.nebulaParticles) { state.scene.remove(state.nebulaParticles); state.nebulaParticles = null; }
  if (mode === 'deepspace') {
    const count = 2000;
    const pos = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 200 + Math.random() * 600;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.cos(phi);
      pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
      sizes[i] = 0.3 + Math.random() * 0.8;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    const mat = new THREE.PointsMaterial({ color: 0x888899, size: 0.5, sizeAttenuation: true, transparent: true, opacity: 0.5 });
    state.starField = new THREE.Points(geo, mat);
    state.scene.add(state.starField);
  } else {
    const count = mode === 'nebula' ? 8000 : 5000;
    const pos = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 100 + Math.random() * 700;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.cos(phi);
      pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
      const temp = 0.7 + Math.random() * 0.3;
      colors[i * 3] = temp;
      colors[i * 3 + 1] = temp * (0.8 + Math.random() * 0.2);
      colors[i * 3 + 2] = temp * (0.7 + Math.random() * 0.3);
      sizes[i] = 0.5 + Math.random() * 2;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const mat = new THREE.PointsMaterial({
      size: 0.6, sizeAttenuation: true, vertexColors: true, transparent: true, opacity: 0.9
    });
    state.starField = new THREE.Points(geo, mat);
    state.scene.add(state.starField);
    if (mode === 'nebula') {
      const nCount = 3000;
      const nPos = new Float32Array(nCount * 3);
      const nCol = new Float32Array(nCount * 3);
      const nSizes = new Float32Array(nCount);
      for (let i = 0; i < nCount; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 50 + Math.random() * 250;
        nPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
        nPos[i * 3 + 1] = r * Math.cos(phi) * 0.4;
        nPos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
        const hue = 0.6 + Math.random() * 0.3;
        const sat = 0.3 + Math.random() * 0.4;
        const color = new THREE.Color().setHSL(hue, sat, 0.3 + Math.random() * 0.3);
        nCol[i * 3] = color.r; nCol[i * 3 + 1] = color.g; nCol[i * 3 + 2] = color.b;
        nSizes[i] = 3 + Math.random() * 8;
      }
      const nGeo = new THREE.BufferGeometry();
      nGeo.setAttribute('position', new THREE.BufferAttribute(nPos, 3));
      nGeo.setAttribute('color', new THREE.BufferAttribute(nCol, 3));
      const nMat = new THREE.PointsMaterial({
        size: 5, sizeAttenuation: true, vertexColors: true,
        transparent: true, opacity: 0.15, blending: THREE.AdditiveBlending, depthWrite: false
      });
      state.nebulaParticles = new THREE.Points(nGeo, nMat);
      state.scene.add(state.nebulaParticles);
    }
  }
}

function setupInteraction() {
  const canvas = state.renderer.domElement;
  canvas.addEventListener('click', (event) => {
    const rect = canvas.getBoundingClientRect();
    state.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    state.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    state.raycaster.setFromCamera(state.pointer, state.camera);
    const meshes = state.bodyMeshes.filter(m => m.visible);
    const intersects = state.raycaster.intersectObjects(meshes, false);
    if (intersects.length > 0) {
      let hit = intersects[0].object;
      if (hit.userData.isRing) {
        hit = hit.parent ? hit.parent.children.find(c => c.userData.bodyId) : hit;
      }
      const bid = hit.userData.bodyId;
      if (bid) selectBody(bid);
    }
  });
  canvas.addEventListener('dblclick', () => {
    if (state.selectedBodyId) focusBody(state.selectedBodyId);
  });
}

function selectBody(bodyId) {
  state.selectedBodyId = bodyId;
  updateHighlight();
  showInfoPanel(bodyId);
  document.getElementById('focus-btn').disabled = false;
}

function updateHighlight() {
  if (!state.selectedBodyId || !state.highlightRing) {
    state.highlightRing.visible = false;
    return;
  }
  const pos = getBodyWorldPosition(state.selectedBodyId);
  if (!pos) { state.highlightRing.visible = false; return; }
  const size = getBodySize(state.selectedBodyId);
  state.highlightRing.position.copy(pos);
  state.highlightRing.scale.set(size * 1.5, size * 1.5, size * 1.5);
  state.highlightRing.lookAt(state.camera.position);
  state.highlightRing.visible = true;
}

function getBodyWorldPosition(bodyId) {
  if (bodyId === 'sun') return new THREE.Vector3(0, 0, 0);
  for (const pData of solarSystemData.planets) {
    if (pData.id === bodyId) {
      const g = state.planetGroups[pData.id];
      if (g) return g.group.position.clone();
    }
      if (pData.moons) {
        for (const mData of pData.moons) {
          if (mData.id === bodyId) {
            const g = state.planetGroups[pData.id];
            if (g) {
              g.group.updateMatrixWorld(true);
              const mm = g.group.getObjectByName(`moon_${mData.id}`);
              if (mm) {
                const wp = new THREE.Vector3();
                mm.getWorldPosition(wp);
                return wp;
              }
            }
          }
        }
      }
  }
  return null;
}

function getBodySize(bodyId) {
  const entry = state.bodyDataMap[bodyId];
  if (!entry) return 1;
  return entry.data.size || 1;
}

function showInfoPanel(bodyId) {
  const entry = state.bodyDataMap[bodyId];
  if (!entry) return;
  const data = entry.data;
  const panel = document.getElementById('info-panel');
  document.getElementById('info-name').textContent = data.name;
  const content = document.getElementById('info-content');
  let html = '';
  html += `<div class="info-section"><h3>Type</h3><p>${entry.category}${entry.parentPlanet ? ` of ${entry.parentPlanet}` : ''}</p></div>`;
  if (data.diameter) html += `<div class="info-section"><h3>Diameter</h3><p>${data.diameter}</p></div>`;
  if (data.orbitInfo) html += `<div class="info-section"><h3>Orbit</h3><p>${data.orbitInfo}</p></div>`;
  if (data.orbitDistance) html += `<div class="info-section"><h3>Distance from Sun</h3><p>${data.orbitDistance}</p></div>`;
  if (data.orbitalPeriod) html += `<div class="info-section"><h3>Orbital Period</h3><p>${data.orbitalPeriod}</p></div>`;
  html += `<div class="info-section"><h3>Features</h3><ul>`;
  for (const f of (data.features || [])) html += `<li>${f}</li>`;
  html += `</ul></div>`;
  if (data.moons && data.moons.length > 0) {
    html += `<div class="info-section"><h3>Moons (${data.moons.length} shown)</h3><ul>`;
    for (const m of data.moons) html += `<li><strong>${m.name}</strong> — ${m.diameter}</li>`;
    html += `</ul>`;
    if (data.moonNote) html += `<p class="info-moon-note">${data.moonNote}</p>`;
    html += `</div>`;
  } else if (data.moonNote) {
    html += `<div class="info-section"><h3>Moons</h3><p class="info-moon-note">${data.moonNote}</p></div>`;
  }
  if (data.fact) {
    html += `<div class="info-section"><div class="info-fact">✨ ${data.fact}</div></div>`;
  }
  content.innerHTML = html;
  panel.classList.remove('hidden');
}

function closeInfoPanel() {
  document.getElementById('info-panel').classList.add('hidden');
  state.selectedBodyId = null;
  if (state.highlightRing) state.highlightRing.visible = false;
  document.getElementById('focus-btn').disabled = true;
}

function focusBody(bodyId) {
  const pos = getBodyWorldPosition(bodyId);
  if (!pos) return;
  const size = getBodySize(bodyId);
  state.controls.target.lerp(pos, 0.5);
  const offset = new THREE.Vector3(size * 8, size * 4, size * 8);
  state.camera.position.copy(pos).add(offset);
  state.controls.update();
}

function resetCamera() {
  state.camera.position.copy(state.cameraDefault);
  state.controls.target.set(0, 0, 0);
  state.controls.update();
}

function setupSearch() {
  const input = document.getElementById('search-input');
  const results = document.getElementById('search-results');
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    if (!q) { results.classList.add('hidden'); return; }
    const matches = [];
    for (const [id, entry] of Object.entries(state.bodyDataMap)) {
      if (entry.data.name.toLowerCase().includes(q)) {
        matches.push({ id, name: entry.data.name, category: entry.category, color: getBodyColor(id) });
      }
    }
    results.innerHTML = '';
    if (matches.length === 0) { results.classList.add('hidden'); return; }
    for (const m of matches) {
      const div = document.createElement('div');
      div.className = 'search-result-item';
      div.innerHTML = `<span class="result-color" style="background:#${m.color.toString(16).padStart(6,'0')}"></span><span>${m.name}</span><span class="result-type">${m.category}</span>`;
      div.addEventListener('click', () => { selectBody(m.id); focusBody(m.id); results.classList.add('hidden'); input.value = ''; });
      results.appendChild(div);
    }
    results.classList.remove('hidden');
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#search-container')) results.classList.add('hidden');
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = input.value.toLowerCase().trim();
      if (!q) return;
      for (const [id, entry] of Object.entries(state.bodyDataMap)) {
        if (entry.data.name.toLowerCase().includes(q)) {
          selectBody(id); focusBody(id);
          results.classList.add('hidden'); input.value = '';
          break;
        }
      }
    }
    if (e.key === 'Escape') { results.classList.add('hidden'); input.blur(); }
  });
}

function getBodyColor(id) {
  if (id === 'sun') return 0xffdd44;
  for (const p of solarSystemData.planets) {
    if (p.id === id) return p.color;
    if (p.moons) for (const m of p.moons) if (m.id === id) return m.color || 0xcccccc;
  }
  return 0xffffff;
}

function setupControls() {
  const pauseBtn = document.getElementById('pause-btn');
  pauseBtn.addEventListener('click', () => {
    state.isPaused = !state.isPaused;
    pauseBtn.textContent = state.isPaused ? 'Resume' : 'Pause';
  });
  const speedSlider = document.getElementById('speed-slider');
  speedSlider.addEventListener('input', () => {
    state.speed = parseFloat(speedSlider.value);
    document.getElementById('speed-label').textContent = state.speed.toFixed(1) + 'x';
  });
  const orbitBtn = document.getElementById('toggle-orbits');
  orbitBtn.addEventListener('click', () => {
    state.showOrbits = !state.showOrbits;
    orbitBtn.classList.toggle('active');
    for (const line of state.orbitLines) line.visible = state.showOrbits;
  });
  const labelBtn = document.getElementById('toggle-labels');
  labelBtn.addEventListener('click', () => {
    state.showLabels = !state.showLabels;
    labelBtn.classList.toggle('active');
    for (const ls of state.labelSprites) ls.visible = state.showLabels;
  });
  document.getElementById('reset-camera').addEventListener('click', resetCamera);
  const focusBtn = document.getElementById('focus-btn');
  focusBtn.disabled = true;
  focusBtn.addEventListener('click', () => {
    if (state.selectedBodyId) focusBody(state.selectedBodyId);
  });
  document.getElementById('env-selector').addEventListener('change', (e) => {
    createEnvironment(e.target.value);
  });
  document.getElementById('auto-rotate-toggle').addEventListener('change', (e) => {
    state.autoRotate = e.target.checked;
    state.controls.autoRotate = state.autoRotate;
    state.controls.autoRotateSpeed = 2.0;
  });
  document.getElementById('info-close').addEventListener('click', closeInfoPanel);
  const aboutBtn = document.getElementById('about-btn');
  const aboutModal = document.getElementById('about-modal');
  aboutBtn.addEventListener('click', () => aboutModal.classList.remove('hidden'));
  document.querySelector('.modal-close').addEventListener('click', () => aboutModal.classList.add('hidden'));
  aboutModal.addEventListener('click', (e) => {
    if (e.target === aboutModal) aboutModal.classList.add('hidden');
  });
}

function animate() {
  requestAnimationFrame(animate);
  const delta = state.clock.getDelta();
  if (!state.isPaused) {
    const d = delta * state.speed;
    for (const pData of solarSystemData.planets) {
      const angle = state.orbitalAngles[pData.id] || 0;
      const na = angle + pData.orbitalSpeed * d;
      state.orbitalAngles[pData.id] = na;
      const pg = state.planetGroups[pData.id];
      if (pg) {
        pg.group.position.x = pData.orbitRadius * Math.cos(na);
        pg.group.position.z = pData.orbitRadius * Math.sin(na);
        pg.mesh.rotation.y += pData.rotationSpeed * d * 20;
        const moons = pData.moons || [];
        for (let i = 0; i < moons.length; i++) {
          const md = moons[i];
          const ma = state.moonAngles[md.id] || 0;
          const nma = ma + md.orbitalSpeed * d;
          state.moonAngles[md.id] = nma;
          const mm = pg.group.getObjectByName(`moon_${md.id}`);
          if (mm) {
            mm.position.x = md.orbitRadius * Math.cos(nma);
            mm.position.z = md.orbitRadius * Math.sin(nma);
          }
        }
      }
    }
    if (state.sun) state.sun.rotation.y += d * 0.1;
    if (state.sunGlow) {
      state.sunGlow.material.rotation += d * 0.005;
    }
  }
  if (state.selectedBodyId && state.highlightRing) {
    state.highlightRing.lookAt(state.camera.position);
  }
  state.controls.update();
  state.renderer.render(state.scene, state.camera);
}

function onResize() {
  const w = window.innerWidth, h = window.innerHeight;
  state.camera.aspect = w / h;
  state.camera.updateProjectionMatrix();
  state.renderer.setSize(w, h);
}

document.addEventListener('DOMContentLoaded', () => {
  try { init(); } catch (e) {
    console.error('Failed to initialize:', e);
    document.getElementById('error-banner').classList.remove('hidden');
  }
});
