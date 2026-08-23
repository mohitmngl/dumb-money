import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ─── Globals ────────────────────────────────────────────────────────────────────
let scene, camera, renderer, controls;
let chairGroup, envGroup;
let lights = {};
let animFrame;
let autoRotate = false;
let exploded = false;
let explodedParts = [];

const params = {
  upholsteryColor: '#0d5c3f',
  upholsteryPreset: 'emerald-velvet',
  woodFinish: 'dark-teak',
  metalFinish: 'antique-brass',
  seatWidth: 48,
  seatDepth: 44,
  backHeight: 72,
  backArch: 18,
  armHeight: 24,
  legHeight: 18,
  cushionSoftness: 0.6,
  jaliDensity: 5,
  studs: true,
  quilting: true,
  piping: true,
  envMode: 'lobby',
  lightIntensity: 1.0,
  colorTemp: 0,
};

const UPHOLSTERY_PRESETS = {
  'emerald-velvet': { color: '#0d5c3f', roughness: 0.82, metalness: 0, sheen: 0.6, type: 'velvet' },
  'royal-blue-velvet': { color: '#1a2f6e', roughness: 0.82, metalness: 0, sheen: 0.6, type: 'velvet' },
  'ruby-velvet': { color: '#8b1a2b', roughness: 0.82, metalness: 0, sheen: 0.6, type: 'velvet' },
  'ivory-silk': { color: '#f0e8d8', roughness: 0.55, metalness: 0, sheen: 0.8, type: 'silk' },
  'charcoal-leather': { color: '#2a2a2a', roughness: 0.45, metalness: 0.02, sheen: 0.15, type: 'leather' },
};

const WOOD_PRESETS = {
  'dark-teak': { color: '#2e1a0e', roughness: 0.55 },
  'rosewood': { color: '#3a1520', roughness: 0.5 },
  'ebony': { color: '#111111', roughness: 0.4 },
  'walnut': { color: '#3d2b1f', roughness: 0.52 },
};

const METAL_PRESETS = {
  'antique-brass': { color: '#b8943e', roughness: 0.35, metalness: 0.9 },
  'polished-gold': { color: '#d4a830', roughness: 0.15, metalness: 0.95 },
  'aged-bronze': { color: '#8a7050', roughness: 0.45, metalness: 0.85 },
  'brushed-champagne': { color: '#c8b898', roughness: 0.3, metalness: 0.88 },
};

// Material caches
let woodTex = null, woodBumpTex = null;
let velvetBumpTex = null;

// ─── Procedural Textures ────────────────────────────────────────────────────────
function makeWoodTexture(color, size = 512) {
  const c = document.createElement('canvas');
  c.width = size; c.height = size;
  const ctx = c.getContext('2d');
  const base = new THREE.Color(color);
  ctx.fillStyle = `rgb(${base.r*255|0},${base.g*255|0},${base.b*255|0})`;
  ctx.fillRect(0, 0, size, size);
  for (let i = 0; i < 200; i++) {
    const y = Math.random() * size;
    const h = 0.5 + Math.random() * 2;
    const bright = 0.7 + Math.random() * 0.5;
    ctx.fillStyle = `rgba(${base.r*bright*255|0},${base.g*bright*255|0},${base.b*bright*255|0},0.25)`;
    ctx.fillRect(0, y, size, h);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function makeBumpTexture(type, color, size = 256) {
  const c = document.createElement('canvas');
  c.width = size; c.height = size;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#808080';
  ctx.fillRect(0, 0, size, size);
  if (type === 'wood') {
    for (let i = 0; i < 120; i++) {
      const y = Math.random() * size;
      ctx.fillStyle = `rgba(0,0,0,${0.05 + Math.random() * 0.12})`;
      ctx.fillRect(0, y, size, 0.5 + Math.random() * 1.5);
    }
  } else if (type === 'velvet') {
    for (let x = 0; x < size; x += 2) {
      for (let y = 0; y < size; y += 2) {
        const v = 128 + (Math.random() - 0.5) * 30;
        ctx.fillStyle = `rgb(${v|0},${v|0},${v|0})`;
        ctx.fillRect(x, y, 2, 2);
      }
    }
  } else if (type === 'leather') {
    for (let i = 0; i < 60; i++) {
      const x = Math.random() * size;
      const y = Math.random() * size;
      const r = 2 + Math.random() * 6;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0,0,0,${0.06 + Math.random() * 0.08})`;
      ctx.fill();
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function ensureTextures() {
  if (!woodTex) {
    woodTex = makeWoodTexture(WOOD_PRESETS[params.woodFinish].color);
    woodBumpTex = makeBumpTexture('wood');
    velvetBumpTex = makeBumpTexture('velvet');
  }
}

// ─── Material Factories ─────────────────────────────────────────────────────────
function makeWoodMaterial() {
  const p = WOOD_PRESETS[params.woodFinish];
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(p.color),
    roughness: p.roughness,
    metalness: 0.05,
    map: woodTex ? woodTex.clone() : null,
    bumpMap: woodBumpTex ? woodBumpTex.clone() : null,
    bumpScale: 0.3,
  });
}

function makeMetalMaterial() {
  const p = METAL_PRESETS[params.metalFinish];
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(p.color),
    roughness: p.roughness,
    metalness: p.metalness,
  });
}

function makeUpholsteryMaterial() {
  const p = UPHOLSTERY_PRESETS[params.upholsteryPreset];
  const col = new THREE.Color(params.upholsteryColor);
  const tex = velvetBumpTex ? velvetBumpTex.clone() : null;
  if (p.type === 'velvet' || p.type === 'silk') {
    return new THREE.MeshPhysicalMaterial({
      color: col,
      roughness: p.roughness,
      metalness: p.metalness,
      sheen: p.sheen,
      sheenRoughness: 0.6,
      sheenColor: col.clone().multiplyScalar(1.3),
      bumpMap: tex,
      bumpScale: 0.15,
    });
  }
  return new THREE.MeshPhysicalMaterial({
    color: col,
    roughness: p.roughness,
    metalness: p.metalness,
    clearcoat: 0.1,
    clearcoatRoughness: 0.5,
    bumpMap: tex,
    bumpScale: 0.1,
  });
}

// ─── Chair Geometry Builders ────────────────────────────────────────────────────
function buildChair() {
  ensureTextures();
  if (chairGroup) {
    scene.remove(chairGroup);
    chairGroup.traverse(c => {
      if (c.geometry) c.geometry.dispose();
      if (c.material) {
        if (Array.isArray(c.material)) c.material.forEach(m => m.dispose());
        else c.material.dispose();
      }
    });
  }
  chairGroup = new THREE.Group();
  chairGroup.name = 'chair';
  explodedParts = [];

  const W = params.seatWidth / 100;
  const D = params.seatDepth / 100;
  const BH = params.backHeight / 100;
  const BA = params.backArch / 100;
  const AH = params.armHeight / 100;
  const LH = params.legHeight / 100;
  const soft = params.cushionSoftness;

  const wood = makeWoodMaterial();
  const metal = makeMetalMaterial();
  const upholstery = makeUpholsteryMaterial();

  // ── Legs ──
  const legGeo = new THREE.CylinderGeometry(0.015, 0.018, LH, 8);
  const legPositions = [
    [-W / 2 + 0.03, -LH / 2, -D / 2 + 0.03],
    [W / 2 - 0.03, -LH / 2, -D / 2 + 0.03],
    [-W / 2 + 0.03, -LH / 2, D / 2 - 0.03],
    [W / 2 - 0.03, -LH / 2, D / 2 - 0.03],
  ];
  legPositions.forEach(p => {
    const leg = new THREE.Mesh(legGeo, wood);
    leg.position.set(...p);
    leg.castShadow = true;
    chairGroup.add(leg);
    explodedParts.push({ mesh: leg, orig: new THREE.Vector3(...p), dir: new THREE.Vector3(0, -1, 0) });
  });

  // Leg caps (brass)
  const capGeo = new THREE.CylinderGeometry(0.019, 0.016, 0.012, 8);
  legPositions.forEach(p => {
    const cap = new THREE.Mesh(capGeo, metal);
    cap.position.set(p[0], -LH + 0.006, p[2]);
    cap.castShadow = true;
    chairGroup.add(cap);
  });

  // ── Cross braces ──
  const braceGeo = new THREE.BoxGeometry(0.018, 0.018, D - 0.06);
  [-W / 2 + 0.03, W / 2 - 0.03].forEach(x => {
    const brace = new THREE.Mesh(braceGeo, wood);
    brace.position.set(x, -LH * 0.5, 0);
    brace.castShadow = true;
    chairGroup.add(brace);
  });

  const braceGeo2 = new THREE.BoxGeometry(W - 0.06, 0.018, 0.018);
  [-D / 2 + 0.03, D / 2 - 0.03].forEach(z => {
    const brace = new THREE.Mesh(braceGeo2, wood);
    brace.position.set(0, -LH * 0.5, z);
    brace.castShadow = true;
    chairGroup.add(brace);
  });

  // ── Seat frame ──
  const seatFrameThick = 0.035;
  const seatFrameH = 0.04;
  // Front
  const sfFront = new THREE.Mesh(new THREE.BoxGeometry(W, seatFrameH, seatFrameThick), wood);
  sfFront.position.set(0, -LH + seatFrameH / 2, -D / 2 + seatFrameThick / 2);
  sfFront.castShadow = true;
  chairGroup.add(sfFront);
  // Back
  const sfBack = new THREE.Mesh(new THREE.BoxGeometry(W, seatFrameH, seatFrameThick), wood);
  sfBack.position.set(0, -LH + seatFrameH / 2, D / 2 - seatFrameThick / 2);
  sfBack.castShadow = true;
  chairGroup.add(sfBack);
  // Left
  const sfLeft = new THREE.Mesh(new THREE.BoxGeometry(seatFrameThick, seatFrameH, D - seatFrameThick * 2), wood);
  sfLeft.position.set(-W / 2 + seatFrameThick / 2, -LH + seatFrameH / 2, 0);
  sfLeft.castShadow = true;
  chairGroup.add(sfLeft);
  // Right
  const sfRight = new THREE.Mesh(new THREE.BoxGeometry(seatFrameThick, seatFrameH, D - seatFrameThick * 2), wood);
  sfRight.position.set(W / 2 - seatFrameThick / 2, -LH + seatFrameH / 2, 0);
  sfRight.castShadow = true;
  chairGroup.add(sfRight);

  const seatY = -LH + seatFrameH;

  // ── Seat cushion ──
  const cushionW = W - 0.04;
  const cushionD = D - 0.04;
  const cushionH = 0.06 * soft + 0.04;
  const seatCushion = new THREE.Mesh(
    new THREE.BoxGeometry(cushionW, cushionH, cushionD, 12, 6, 12),
    upholstery
  );
  seatCushion.name = 'seat-cushion';
  seatCushion.position.set(0, seatY + cushionH / 2, 0);
  seatCushion.castShadow = true;
  seatCushion.receiveShadow = true;
  // Round edges by displacing vertices
  roundBoxVertices(seatCushion, soft * 0.015);
  chairGroup.add(seatCushion);
  explodedParts.push({ mesh: seatCushion, orig: seatCushion.position.clone(), dir: new THREE.Vector3(0, 1, 0) });

  // Quilting on seat
  if (params.quilting) {
    addQuilting(seatCushion, cushionW, cushionD, cushionH, 0, seatY + cushionH, 0);
  }

  // ── Back frame ──
  const backFrameThick = 0.035;
  const backFrameW = W;
  const backFrameH = BH;
  const backY = seatY;

  // Create scalloped arch back
  const backShape = new THREE.Shape();
  const hw = backFrameW / 2;
  backShape.moveTo(-hw, 0);
  backShape.lineTo(-hw, backFrameH - BA);
  // Scalloped arch top
  const archSegments = 12;
  for (let i = 0; i <= archSegments; i++) {
    const t = i / archSegments;
    const angle = Math.PI * t;
    const scallopX = -hw + backFrameW * t;
    const baseY = backFrameH - BA + BA * Math.sin(angle);
    // Add scallop waviness
    const scallops = 3;
    const wave = Math.sin(t * Math.PI * scallops) * BA * 0.12;
    backShape.lineTo(scallopX, baseY + wave);
  }
  backShape.lineTo(hw, 0);
  backShape.lineTo(-hw, 0);

  const backExtrudeSettings = {
    depth: backFrameThick,
    bevelEnabled: true,
    bevelThickness: 0.005,
    bevelSize: 0.005,
    bevelSegments: 2,
  };
  const backGeo = new THREE.ExtrudeGeometry(backShape, backExtrudeSettings);
  const backFrame = new THREE.Mesh(backGeo, wood);
  backFrame.position.set(0, backY, D / 2 - backFrameThick);
  backFrame.castShadow = true;
  chairGroup.add(backFrame);

  // ── Back cushion (inset) ──
  const bcW = W - 0.1;
  const bcH = BH - 0.12;
  const bcD = 0.05 * soft + 0.03;
  const backCushion = new THREE.Mesh(
    new THREE.BoxGeometry(bcW, bcH, bcD, 10, 10, 6),
    upholstery
  );
  backCushion.name = 'back-cushion';
  backCushion.position.set(0, backY + bcH / 2 + 0.06, D / 2 - backFrameThick - bcD / 2);
  backCushion.castShadow = true;
  roundBoxVertices(backCushion, soft * 0.012);
  chairGroup.add(backCushion);
  explodedParts.push({ mesh: backCushion, orig: backCushion.position.clone(), dir: new THREE.Vector3(0, 0, 1) });

  if (params.quilting) {
    addQuilting(backCushion, bcW, bcH, bcD, 0, backY + 0.06 + bcH / 2, D / 2 - backFrameThick - bcD);
  }

  // ── Arms ──
  const armW = 0.05;
  const armD = D - 0.02;
  const armH = AH;
  [-1, 1].forEach(side => {
    const x = side * (W / 2 + armW / 2 - 0.01);
    // Arm rail (wood)
    const armRail = new THREE.Mesh(
      new THREE.BoxGeometry(armW, 0.025, armD),
      wood
    );
    armRail.position.set(x, seatY + armH - 0.0125, 0);
    armRail.castShadow = true;
    chairGroup.add(armRail);

    // Arm front post
    const armPost = new THREE.Mesh(
      new THREE.CylinderGeometry(0.015, 0.018, armH, 8),
      wood
    );
    armPost.position.set(x, seatY + armH / 2, -D / 2 + 0.02);
    armPost.castShadow = true;
    chairGroup.add(armPost);

    // Arm back post (shorter, connects to back)
    const armBackPost = new THREE.Mesh(
      new THREE.CylinderGeometry(0.013, 0.016, BH * 0.35, 8),
      wood
    );
    armBackPost.position.set(x, seatY + BH * 0.175, D / 2 - 0.02);
    armBackPost.castShadow = true;
    chairGroup.add(armBackPost);

    // Arm finial (brass knob on front)
    const finial = new THREE.Mesh(
      new THREE.SphereGeometry(0.02, 12, 8),
      metal
    );
    finial.position.set(x, seatY + armH + 0.01, -D / 2 + 0.02);
    finial.castShadow = true;
    chairGroup.add(finial);

    explodedParts.push({ mesh: armRail, orig: armRail.position.clone(), dir: new THREE.Vector3(side * 1, 0.5, 0) });

    // ── Jali lattice panel (between arm and seat, side) ──
    addJaliPanel(x, seatY + 0.01, 0, armW * 0.6, armH * 0.75, D * 0.7, side, metal);

    // Brass trim on arm top
    const trimGeo = new THREE.BoxGeometry(armW + 0.004, 0.006, armD + 0.004);
    const trim = new THREE.Mesh(trimGeo, metal);
    trim.position.set(x, seatY + armH + 0.003, 0);
    trim.castShadow = true;
    chairGroup.add(trim);
  });

  // ── Brass trim on seat frame edges ──
  const brassTrimH = 0.005;
  // Front
  const btf = new THREE.Mesh(new THREE.BoxGeometry(W + 0.004, brassTrimH, 0.006), metal);
  btf.position.set(0, seatY + 0.002, -D / 2 - 0.001);
  chairGroup.add(btf);
  // Sides
  [-1, 1].forEach(side => {
    const bts = new THREE.Mesh(new THREE.BoxGeometry(0.006, brassTrimH, D + 0.004), metal);
    bts.position.set(side * (W / 2 + 0.003), seatY + 0.002, 0);
    chairGroup.add(bts);
  });

  // ── Back trim (arch outline) ──
  const archCurve = new THREE.CurvePath();
  const archPts = [];
  for (let i = 0; i <= 40; i++) {
    const t = i / 40;
    const angle = Math.PI * t;
    const x = -hw + backFrameW * t;
    const baseY = backFrameH - BA + BA * Math.sin(angle);
    const scallops = 3;
    const wave = Math.sin(t * Math.PI * scallops) * BA * 0.12;
    archPts.push(new THREE.Vector3(x, baseY + wave, 0));
  }
  const archCurveLine = new THREE.CatmullRomCurve3(archPts);
  const tubeGeo = new THREE.TubeGeometry(archCurveLine, 40, 0.005, 6, false);
  const archTrim = new THREE.Mesh(tubeGeo, metal);
  archTrim.position.set(0, backY, D / 2 - backFrameThick + backFrameThick / 2);
  chairGroup.add(archTrim);

  // ── Decorative studs ──
  if (params.studs) {
    addStuds(metal, seatY, W, D, BH, BA);
  }

  // ── Piping ──
  if (params.piping) {
    addPiping(upholstery, seatCushion, cushionW, cushionH, cushionD, 0, seatY + cushionH / 2, 0);
    addPiping(upholstery, backCushion, bcW, bcH, bcD, 0, backY + 0.06 + bcH / 2, D / 2 - backFrameThick - bcD / 2);
  }

  scene.add(chairGroup);
}

function roundBoxVertices(mesh, amount) {
  const geo = mesh.geometry;
  const pos = geo.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    const fx = Math.abs(v.x);
    const fy = Math.abs(v.y);
    const fz = Math.abs(v.z);
    const maxDim = Math.max(fx, fy, fz);
    const edgeFactor = Math.pow(fx / 0.5 + fy / 0.5 + fz / 0.5, 3);
    const push = amount * Math.min(edgeFactor, 1);
    const len = v.length() || 1;
    v.normalize().multiplyScalar(push);
    pos.setXYZ(i, pos.getX(i) + v.x * (fy > 0.01 ? 1 : 0), pos.getY(i) + v.y, pos.getZ(i) + v.z);
  }
  geo.computeVertexNormals();
  pos.needsUpdate = true;
}

function addJaliPanel(x, y, z, w, h, d, side, metalMat) {
  const density = params.jaliDensity;
  const panelGroup = new THREE.Group();
  panelGroup.name = 'jali';

  // Vertical bars
  for (let i = 0; i < density; i++) {
    const t = (i + 0.5) / density;
    const barGeo = new THREE.CylinderGeometry(0.003, 0.003, h, 4);
    const bar = new THREE.Mesh(barGeo, metalMat);
    bar.position.set(0, h / 2, -d / 2 + t * d);
    panelGroup.add(bar);
  }
  // Horizontal bars
  for (let i = 0; i < Math.floor(density * 0.7); i++) {
    const t = (i + 0.5) / (density * 0.7);
    const barGeo = new THREE.CylinderGeometry(0.003, 0.003, d, 4);
    const bar = new THREE.Mesh(barGeo, metalMat);
    bar.rotation.x = Math.PI / 2;
    bar.position.set(0, t * h, 0);
    panelGroup.add(bar);
  }
  // Diamond pattern overlays
  for (let r = 0; r < density - 1; r++) {
    for (let c = 0; c < Math.floor(density * 0.7) - 1; c++) {
      const cx = ((c + 0.5) / (density * 0.7 - 1) - 0.5) * d;
      const cy = ((r + 0.5) / (density - 1)) * h;
      const diamondSize = Math.min(d / density, h / density) * 0.25;
      const shape = new THREE.Shape();
      shape.moveTo(0, diamondSize);
      shape.lineTo(diamondSize, 0);
      shape.lineTo(0, -diamondSize);
      shape.lineTo(-diamondSize, 0);
      shape.lineTo(0, diamondSize);
      const dGeo = new THREE.ShapeGeometry(shape);
      const diamond = new THREE.Mesh(dGeo, metalMat);
      diamond.position.set(0, cy, cx);
      diamond.rotation.y = Math.PI / 2;
      panelGroup.add(diamond);
    }
  }

  panelGroup.position.set(x, y, z);
  chairGroup.add(panelGroup);
}

function addStuds(metalMat, seatY, W, D, BH, BA) {
  const studGeo = new THREE.SphereGeometry(0.006, 6, 6);
  // Front edge studs
  const frontStuds = 8;
  for (let i = 0; i < frontStuds; i++) {
    const t = (i + 0.5) / frontStuds;
    const stud = new THREE.Mesh(studGeo, metalMat);
    stud.position.set(-W / 2 + t * W, seatY + 0.04, -D / 2 - 0.005);
    chairGroup.add(stud);
  }
  // Side edge studs
  const sideStuds = 6;
  [-1, 1].forEach(side => {
    for (let i = 0; i < sideStuds; i++) {
      const t = (i + 0.5) / sideStuds;
      const stud = new THREE.Mesh(studGeo, metalMat);
      stud.position.set(side * (W / 2 + 0.005), seatY + 0.04, -D / 2 + t * D);
      chairGroup.add(stud);
    }
  });
  // Back arch studs
  const archStuds = 16;
  const hw = W / 2;
  for (let i = 0; i <= archStuds; i++) {
    const t = i / archStuds;
    const angle = Math.PI * t;
    const sx = -hw + W * t;
    const baseY = BH - BA + BA * Math.sin(angle);
    const wave = Math.sin(t * Math.PI * 3) * BA * 0.12;
    const stud = new THREE.Mesh(studGeo, metalMat);
    stud.position.set(sx, seatY + baseY + wave, D / 2 - 0.03);
    chairGroup.add(stud);
  }
}

function addQuilting(cushion, cW, cH, cD, cx, cy, cz) {
  const lines = new THREE.Group();
  lines.name = 'quilting';
  const mat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.9 });
  const grid = 4;
  // Horizontal lines
  for (let i = 1; i < grid; i++) {
    const t = i / grid;
    const lineGeo = new THREE.BoxGeometry(cW * 0.9, 0.002, 0.002);
    const line = new THREE.Mesh(lineGeo, mat);
    line.position.set(cx, cy - cH / 2 + t * cH, cz + cD / 2 + 0.001);
    lines.add(line);
  }
  // Vertical lines
  for (let i = 1; i < grid; i++) {
    const t = i / grid;
    const lineGeo = new THREE.BoxGeometry(0.002, 0.002, cD * 0.9);
    const line = new THREE.Mesh(lineGeo, mat);
    line.position.set(cx - cW / 2 + t * cW, cy - cH / 2 + 0.001, cz + cD / 2 + 0.001);
    lines.add(line);
  }
  // Diamond lines
  for (let r = 0; r < grid - 1; r++) {
    for (let c = 0; c < grid - 1; c++) {
      const dSize = Math.min(cW, cH) / grid * 0.8;
      const shape = new THREE.Shape();
      shape.moveTo(0, dSize);
      shape.lineTo(dSize, 0);
      shape.lineTo(0, -dSize);
      shape.lineTo(-dSize, 0);
      shape.lineTo(0, dSize);
      const dGeo = new THREE.ShapeGeometry(shape);
      const diamond = new THREE.Mesh(dGeo, mat);
      const dx = cx - cW / 2 + (c + 0.5) / (grid - 1) * cW;
      const dy = cy - cH / 2 + (r + 0.5) / (grid - 1) * cH;
      diamond.position.set(dx, dy, cz + cD / 2 + 0.002);
      lines.add(diamond);
    }
  }
  chairGroup.add(lines);
}

function addPiping(mat, cushion, cW, cH, cD, cx, cy, cz) {
  const pipeR = 0.004;
  const pipeMat = mat.clone();
  pipeMat.color = mat.color.clone().multiplyScalar(0.85);

  // Top edge pipe
  const topCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-cW / 2, cy + cH / 2, cz),
    new THREE.Vector3(0, cy + cH / 2 + pipeR * 2, cz),
    new THREE.Vector3(cW / 2, cy + cH / 2, cz),
  ]);
  const topPipe = new THREE.Mesh(new THREE.TubeGeometry(topCurve, 12, pipeR, 6, false), pipeMat);
  chairGroup.add(topPipe);

  // Bottom edge pipe
  const botCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-cW / 2, cy - cH / 2, cz),
    new THREE.Vector3(0, cy - cH / 2 - pipeR * 2, cz),
    new THREE.Vector3(cW / 2, cy - cH / 2, cz),
  ]);
  const botPipe = new THREE.Mesh(new THREE.TubeGeometry(botCurve, 12, pipeR, 6, false), pipeMat);
  chairGroup.add(botPipe);
}

// ─── Environment ────────────────────────────────────────────────────────────────
function buildEnvironment() {
  if (envGroup) {
    scene.remove(envGroup);
    envGroup.traverse(c => {
      if (c.geometry) c.geometry.dispose();
      if (c.material) {
        if (Array.isArray(c.material)) c.material.forEach(m => m.dispose());
        else c.material.dispose();
      }
    });
  }
  envGroup = new THREE.Group();
  envGroup.name = 'environment';

  const mode = params.envMode;

  if (mode === 'lobby') {
    // Marble floor
    const floorTex = makeMarbleTexture('#d4c8b8', 1024);
    floorTex.repeat.set(4, 4);
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(8, 8),
      new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.3, metalness: 0.05 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -params.legHeight / 100 - 0.001;
    floor.receiveShadow = true;
    envGroup.add(floor);

    // Warm wall backdrop
    const wall = new THREE.Mesh(
      new THREE.PlaneGeometry(8, 4),
      new THREE.MeshStandardMaterial({ color: '#3a2e22', roughness: 0.8 })
    );
    wall.position.set(0, 1.5, -3);
    envGroup.add(wall);

    // Columns
    const colGeo = new THREE.CylinderGeometry(0.08, 0.09, 3.5, 12);
    const colMat = new THREE.MeshStandardMaterial({ color: '#c4b49c', roughness: 0.4 });
    [-1.8, 1.8].forEach(x => {
      const col = new THREE.Mesh(colGeo, colMat);
      col.position.set(x, 1.5, -2.5);
      col.castShadow = true;
      envGroup.add(col);
      // Column base
      const base = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.1, 0.25), colMat);
      base.position.set(x, -0.05, -2.5);
      envGroup.add(base);
    });

    // Arch silhouette behind
    const archShape = new THREE.Shape();
    archShape.moveTo(-1.2, 0);
    archShape.lineTo(-1.2, 2);
    archShape.quadraticCurveTo(-1.2, 3.2, 0, 3.2);
    archShape.quadraticCurveTo(1.2, 3.2, 1.2, 2);
    archShape.lineTo(1.2, 0);
    archShape.lineTo(1, 0);
    archShape.lineTo(1, 2);
    archShape.quadraticCurveTo(1, 2.8, 0, 2.8);
    archShape.quadraticCurveTo(-1, 2.8, -1, 2);
    archShape.lineTo(-1, 0);
    archShape.lineTo(-1.2, 0);
    const archGeo = new THREE.ExtrudeGeometry(archShape, { depth: 0.06, bevelEnabled: false });
    const archMat = new THREE.MeshStandardMaterial({ color: '#2a2018', roughness: 0.7 });
    const arch = new THREE.Mesh(archGeo, archMat);
    arch.position.set(0, -0.05, -2.9);
    envGroup.add(arch);

    scene.background = new THREE.Color('#1a1410');
  }
  else if (mode === 'studio') {
    const floorTex = makeMarbleTexture('#e8e0d4', 1024);
    floorTex.repeat.set(3, 3);
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(6, 6),
      new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.2, metalness: 0.08 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -params.legHeight / 100 - 0.001;
    floor.receiveShadow = true;
    envGroup.add(floor);

    // Curved backdrop
    const backdropGeo = new THREE.CylinderGeometry(3, 3, 4, 32, 1, true, Math.PI * 0.6, Math.PI * 0.8);
    const backdropMat = new THREE.MeshStandardMaterial({ color: '#d8d0c4', roughness: 0.9, side: THREE.DoubleSide });
    const backdrop = new THREE.Mesh(backdropGeo, backdropMat);
    backdrop.position.set(0, 1.5, -1);
    envGroup.add(backdrop);

    scene.background = new THREE.Color('#2a2420');
  }
  else if (mode === 'showroom') {
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(6, 6),
      new THREE.MeshStandardMaterial({ color: '#0a0a0a', roughness: 0.15, metalness: 0.3 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -params.legHeight / 100 - 0.001;
    floor.receiveShadow = true;
    envGroup.add(floor);

    // Subtle wall
    const wall = new THREE.Mesh(
      new THREE.PlaneGeometry(6, 3),
      new THREE.MeshStandardMaterial({ color: '#111', roughness: 0.9 })
    );
    wall.position.set(0, 1.2, -3);
    envGroup.add(wall);

    scene.background = new THREE.Color('#050505');
  }

  scene.add(envGroup);
}

function makeMarbleTexture(color, size = 512) {
  const c = document.createElement('canvas');
  c.width = size; c.height = size;
  const ctx = c.getContext('2d');
  const base = new THREE.Color(color);
  ctx.fillStyle = `rgb(${base.r*255|0},${base.g*255|0},${base.b*255|0})`;
  ctx.fillRect(0, 0, size, size);
  // Veins
  for (let i = 0; i < 30; i++) {
    ctx.beginPath();
    ctx.moveTo(Math.random() * size, Math.random() * size);
    for (let j = 0; j < 5; j++) {
      ctx.lineTo(Math.random() * size, Math.random() * size);
    }
    ctx.strokeStyle = `rgba(0,0,0,${0.03 + Math.random() * 0.06})`;
    ctx.lineWidth = 0.5 + Math.random() * 1.5;
    ctx.stroke();
  }
  return new THREE.CanvasTexture(c);
}

// ─── Lighting ───────────────────────────────────────────────────────────────────
function buildLighting() {
  Object.values(lights).forEach(l => scene.remove(l));
  lights = {};

  const intensity = params.lightIntensity;
  const temp = params.colorTemp;

  const warmBase = new THREE.Color(1, 0.92, 0.78);
  const coolBase = new THREE.Color(0.85, 0.9, 1);
  const baseColor = warmBase.clone().lerp(coolBase, (temp + 1) / 2);

  // Ambient
  lights.ambient = new THREE.AmbientLight(baseColor.clone().multiplyScalar(0.3 * intensity), 0.3 * intensity);
  scene.add(lights.ambient);

  // Key light (warm directional)
  lights.key = new THREE.DirectionalLight(baseColor.clone().multiplyScalar(0.9 * intensity), 0.9 * intensity);
  lights.key.position.set(2, 4, 1);
  lights.key.castShadow = true;
  lights.key.shadow.mapSize.set(1024, 1024);
  lights.key.shadow.camera.near = 0.1;
  lights.key.shadow.camera.far = 10;
  lights.key.shadow.camera.left = -2;
  lights.key.shadow.camera.right = 2;
  lights.key.shadow.camera.top = 2;
  lights.key.shadow.camera.bottom = -2;
  scene.add(lights.key);

  // Warm side light
  lights.side = new THREE.PointLight(new THREE.Color(1, 0.85, 0.6).multiplyScalar(intensity), 0.5 * intensity, 6);
  lights.side.position.set(-2.5, 1.5, 0.5);
  scene.add(lights.side);

  // Rim/back light
  lights.rim = new THREE.DirectionalLight(baseColor.clone().multiplyScalar(0.4 * intensity), 0.4 * intensity);
  lights.rim.position.set(-1, 3, -3);
  scene.add(lights.rim);

  // Top spotlight
  if (params.envMode === 'showroom') {
    lights.spot = new THREE.SpotLight(new THREE.Color(1, 0.95, 0.85).multiplyScalar(intensity), 1.5 * intensity, 8, Math.PI / 6, 0.5);
    lights.spot.position.set(0, 4, 0);
    lights.spot.target.position.set(0, 0, 0);
    lights.spot.castShadow = true;
    scene.add(lights.spot);
    scene.add(lights.spot.target);
  }
}

// ─── Scene Setup ────────────────────────────────────────────────────────────────
function initScene() {
  const canvas = document.getElementById('viewport');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x1a1410, 0.15);

  camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.05, 50);
  camera.position.set(1.2, 0.8, 1.8);

  controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0.3, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.5;
  controls.maxDistance = 5;
  controls.maxPolarAngle = Math.PI * 0.85;
  controls.update();

  window.addEventListener('resize', onResize);
}

function onResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
  animFrame = requestAnimationFrame(animate);
  if (autoRotate && chairGroup) {
    chairGroup.rotation.y += 0.004;
  }
  controls.update();
  renderer.render(scene, camera);
}

// ─── UI Bindings ────────────────────────────────────────────────────────────────
function bindUI() {
  // Color picker
  const colorInput = document.getElementById('upholstery-color');
  colorInput.addEventListener('input', e => {
    params.upholsteryColor = e.target.value;
    buildChair();
  });

  // Presets
  document.getElementById('upholstery-preset').addEventListener('change', e => {
    params.upholsteryPreset = e.target.value;
    const p = UPHOLSTERY_PRESETS[e.target.value];
    params.upholsteryColor = p.color;
    colorInput.value = p.color;
    buildChair();
  });

  document.getElementById('wood-finish').addEventListener('change', e => {
    params.woodFinish = e.target.value;
    woodTex = null; woodBumpTex = null;
    ensureTextures();
    buildChair();
  });

  document.getElementById('metal-finish').addEventListener('change', e => {
    params.metalFinish = e.target.value;
    buildChair();
  });

  // Sliders
  const sliderMap = {
    'seat-width': ['seatWidth', 'val-seat-width'],
    'seat-depth': ['seatDepth', 'val-seat-depth'],
    'back-height': ['backHeight', 'val-back-height'],
    'back-arch': ['backArch', 'val-back-arch'],
    'arm-height': ['armHeight', 'val-arm-height'],
    'leg-height': ['legHeight', 'val-leg-height'],
    'cushion-softness': ['cushionSoftness', 'val-cushion-softness'],
    'jali-density': ['jaliDensity', 'val-jali-density'],
  };

  Object.entries(sliderMap).forEach(([id, [param, valId]]) => {
    const el = document.getElementById(id);
    el.addEventListener('input', e => {
      const v = parseFloat(e.target.value);
      params[param] = v;
      document.getElementById(valId).textContent = v;
      buildChair();
    });
  });

  // Toggles
  document.getElementById('studs-toggle').addEventListener('change', e => { params.studs = e.target.checked; buildChair(); });
  document.getElementById('quilting-toggle').addEventListener('change', e => { params.quilting = e.target.checked; buildChair(); });
  document.getElementById('piping-toggle').addEventListener('change', e => { params.piping = e.target.checked; buildChair(); });

  // Environment
  document.getElementById('env-mode').addEventListener('change', e => {
    params.envMode = e.target.value;
    buildEnvironment();
    buildLighting();
  });

  document.getElementById('light-intensity').addEventListener('input', e => {
    params.lightIntensity = parseFloat(e.target.value);
    document.getElementById('val-light-intensity').textContent = params.lightIntensity.toFixed(1);
    buildLighting();
  });

  document.getElementById('color-temp').addEventListener('input', e => {
    params.colorTemp = parseFloat(e.target.value);
    document.getElementById('val-color-temp').textContent = params.colorTemp.toFixed(1);
    buildLighting();
  });

  // Action buttons
  document.getElementById('btn-reset-camera').addEventListener('click', () => {
    camera.position.set(1.2, 0.8, 1.8);
    controls.target.set(0, 0.3, 0);
    controls.update();
  });

  document.getElementById('btn-auto-rotate').addEventListener('click', e => {
    autoRotate = !autoRotate;
    e.target.textContent = `Auto Rotate: ${autoRotate ? 'ON' : 'OFF'}`;
  });

  document.getElementById('btn-reset-design').addEventListener('click', () => {
    params.upholsteryColor = '#0d5c3f';
    params.upholsteryPreset = 'emerald-velvet';
    params.woodFinish = 'dark-teak';
    params.metalFinish = 'antique-brass';
    params.seatWidth = 48; params.seatDepth = 44;
    params.backHeight = 72; params.backArch = 18;
    params.armHeight = 24; params.legHeight = 18;
    params.cushionSoftness = 0.6; params.jaliDensity = 5;
    params.studs = true; params.quilting = true; params.piping = true;
    refreshUI();
    woodTex = null; woodBumpTex = null;
    ensureTextures();
    buildChair();
    buildEnvironment();
    buildLighting();
  });

  document.getElementById('btn-screenshot').addEventListener('click', () => {
    renderer.render(scene, camera);
    const link = document.createElement('a');
    link.download = 'heritage-chair-screenshot.png';
    link.href = renderer.domElement.toDataURL('image/png');
    link.click();
  });

  document.getElementById('btn-export-json').addEventListener('click', () => {
    const json = JSON.stringify(params, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const link = document.createElement('a');
    link.download = 'chair-params.json';
    link.href = URL.createObjectURL(blob);
    link.click();
  });

  document.getElementById('btn-import-json').addEventListener('click', () => {
    const ta = document.getElementById('json-import-area');
    const actions = document.getElementById('json-import-actions');
    ta.classList.remove('hidden');
    actions.classList.remove('hidden');
    ta.value = '';
    ta.focus();
  });

  document.getElementById('btn-apply-json').addEventListener('click', () => {
    try {
      const data = JSON.parse(document.getElementById('json-import-area').value);
      Object.assign(params, data);
      refreshUI();
      woodTex = null; woodBumpTex = null;
      ensureTextures();
      buildChair();
      buildEnvironment();
      buildLighting();
    } catch (e) {
      alert('Invalid JSON: ' + e.message);
    }
    document.getElementById('json-import-area').classList.add('hidden');
    document.getElementById('json-import-actions').classList.add('hidden');
  });

  document.getElementById('btn-cancel-json').addEventListener('click', () => {
    document.getElementById('json-import-area').classList.add('hidden');
    document.getElementById('json-import-actions').classList.add('hidden');
  });

  document.getElementById('btn-exploded').addEventListener('click', () => {
    exploded = !exploded;
    document.getElementById('btn-exploded').textContent = exploded ? 'Normal View' : 'Exploded View';
    animateExploded(exploded);
  });

  // Info panel
  document.getElementById('info-toggle').addEventListener('click', () => {
    document.getElementById('info-panel').classList.toggle('hidden');
  });
}

function refreshUI() {
  document.getElementById('upholstery-color').value = params.upholsteryColor;
  document.getElementById('upholstery-preset').value = params.upholsteryPreset;
  document.getElementById('wood-finish').value = params.woodFinish;
  document.getElementById('metal-finish').value = params.metalFinish;
  document.getElementById('seat-width').value = params.seatWidth;
  document.getElementById('val-seat-width').textContent = params.seatWidth;
  document.getElementById('seat-depth').value = params.seatDepth;
  document.getElementById('val-seat-depth').textContent = params.seatDepth;
  document.getElementById('back-height').value = params.backHeight;
  document.getElementById('val-back-height').textContent = params.backHeight;
  document.getElementById('back-arch').value = params.backArch;
  document.getElementById('val-back-arch').textContent = params.backArch;
  document.getElementById('arm-height').value = params.armHeight;
  document.getElementById('val-arm-height').textContent = params.armHeight;
  document.getElementById('leg-height').value = params.legHeight;
  document.getElementById('val-leg-height').textContent = params.legHeight;
  document.getElementById('cushion-softness').value = params.cushionSoftness;
  document.getElementById('val-cushion-softness').textContent = params.cushionSoftness;
  document.getElementById('jali-density').value = params.jaliDensity;
  document.getElementById('val-jali-density').textContent = params.jaliDensity;
  document.getElementById('studs-toggle').checked = params.studs;
  document.getElementById('quilting-toggle').checked = params.quilting;
  document.getElementById('piping-toggle').checked = params.piping;
  document.getElementById('env-mode').value = params.envMode;
  document.getElementById('light-intensity').value = params.lightIntensity;
  document.getElementById('val-light-intensity').textContent = params.lightIntensity.toFixed(1);
  document.getElementById('color-temp').value = params.colorTemp;
  document.getElementById('val-color-temp').textContent = params.colorTemp.toFixed(1);
}

function animateExploded(show) {
  const duration = 600;
  const start = performance.now();
  const startPositions = explodedParts.map(p => p.mesh.position.clone());

  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    explodedParts.forEach((part, i) => {
      const target = show
        ? part.orig.clone().add(part.dir.clone().multiplyScalar(0.25))
        : part.orig;
      part.mesh.position.lerpVectors(startPositions[i], target, ease);
    });
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ─── Init ───────────────────────────────────────────────────────────────────────
initScene();
buildLighting();
buildEnvironment();
buildChair();
bindUI();
animate();

// Hide loading
setTimeout(() => {
  document.getElementById('loading').classList.add('hidden');
}, 800);
