/**
 * Orrery Live - Core Application Logic
 * Implements high-fidelity Canvas rendering, Keplerian-like orbits, 
 * parallax starfield, camera smoothing, and sidebar UI state binding.
 */

// Canvas & Context Setup
const canvas = document.getElementById("space-canvas");
const ctx = canvas.getContext("2d");

// Application Configuration and State
let isPlaying = true;
let simulationSpeed = 1.0;
let drawOrbits = true;
let drawLabels = true;
let drawStars = true;

// Camera System (World Space offsets)
const camera = {
  x: 0,
  y: 0,
  zoom: 0.85,
  targetX: 0,
  targetY: 0,
  targetZoom: 0.85
};

// Selection State
let selectedBodyId = null;
let focusedBodyId = null;

// Simulation Models
let sun = null;
let planets = [];
let allSimulationBodies = {};
let stars = [];

// Initialize Starfield (300 stars placed in a large coordinate plane)
function initStars() {
  stars = [];
  const starColors = ["#ffffff", "#eef5ff", "#fffdf0", "#ffdce2"];
  
  for (let i = 0; i < 300; i++) {
    stars.push({
      x: Math.random() * 3000,
      y: Math.random() * 3000,
      radius: Math.random() * 1.2 + 0.4,
      baseOpacity: Math.random() * 0.75 + 0.15,
      twinkleSpeed: Math.random() * 1.5 + 0.5,
      twinklePhase: Math.random() * Math.PI * 2,
      color: starColors[Math.floor(Math.random() * starColors.length)]
    });
  }
}

// Initialize Simulation Models from SOLAR_SYSTEM_DATA
function initSimulation() {
  allSimulationBodies = {};
  
  // 1. Initialize Sun
  const sunSpec = SOLAR_SYSTEM_DATA.sun;
  sun = {
    id: sunSpec.id,
    name: sunSpec.name,
    radius: 36,
    color: sunSpec.color,
    x: 0,
    y: 0,
    moons: []
  };
  allSimulationBodies[sun.id] = sun;

  // 2. Initialize Planets
  // Orbital radii and speeds are compressed/scaled for visuals
  const planetSpecs = [
    { id: "mercury", orbitRadius: 85, radius: 6.5, speed: 0.024 },
    { id: "venus", orbitRadius: 130, radius: 10.5, speed: 0.016 },
    { id: "earth", orbitRadius: 180, radius: 11.5, speed: 0.012 },
    { id: "mars", orbitRadius: 235, radius: 8.5, speed: 0.009 },
    { id: "jupiter", orbitRadius: 320, radius: 23.0, speed: 0.005 },
    { id: "saturn", orbitRadius: 430, radius: 18.0, speed: 0.003, hasRings: true },
    { id: "uranus", orbitRadius: 535, radius: 14.5, speed: 0.0018, hasRings: true },
    { id: "neptune", orbitRadius: 645, radius: 14.0, speed: 0.0011, hasRings: true }
  ];

  planets = planetSpecs.map(spec => {
    const data = SOLAR_SYSTEM_DATA[spec.id];
    const planetObj = {
      id: spec.id,
      name: data.name,
      orbitRadius: spec.orbitRadius,
      radius: spec.radius,
      speed: spec.speed,
      angle: Math.random() * Math.PI * 2, // Distributed angles on load
      color: data.color,
      hasRings: spec.hasRings || false,
      moons: [],
      x: 0,
      y: 0
    };

    // 3. Initialize Moons
    if (data.moons && data.moons.length > 0) {
      data.moons.forEach((moonData, idx) => {
        // Position orbits safely outside the planetary bodies (and Saturn rings)
        const ringPadding = planetObj.hasRings ? 20 : 10;
        const moonOrbitRadius = planetObj.radius + ringPadding + idx * 11;
        // Inner moons orbit faster
        const moonSpeed = 0.045 / Math.sqrt(idx + 1);

        const moonObj = {
          id: moonData.id,
          name: moonData.name,
          orbitRadius: moonOrbitRadius,
          radius: 2.8,
          speed: moonSpeed,
          angle: Math.random() * Math.PI * 2,
          color: moonData.color,
          parentPlanet: planetObj,
          x: 0,
          y: 0
        };
        planetObj.moons.push(moonObj);
        allSimulationBodies[moonObj.id] = moonObj;
      });
    }

    allSimulationBodies[planetObj.id] = planetObj;
    return planetObj;
  });
}

// Draw Tilted Planetary Rings (Saturn, Uranus, Neptune, Jupiter)
// Uses double-arc drawing (back half then front half) so planet sits in between
function drawRings(ctx, planet, isFront) {
  ctx.save();
  
  let tilt, rMultW, rMultH, colorStr;
  
  if (planet.id === "saturn") {
    tilt = -0.22;
    rMultW = 2.15;
    rMultH = 0.52;
    colorStr = "rgba(235, 210, 176, ";
  } else if (planet.id === "uranus") {
    tilt = -1.22; // Heavily inclined
    rMultW = 1.8;
    rMultH = 0.45;
    colorStr = "rgba(179, 240, 255, ";
  } else if (planet.id === "neptune") {
    tilt = 0.15;
    rMultW = 1.7;
    rMultH = 0.38;
    colorStr = "rgba(51, 102, 255, ";
  } else if (planet.id === "jupiter") {
    tilt = -0.05;
    rMultW = 1.85;
    rMultH = 0.35;
    colorStr = "rgba(216, 202, 157, ";
  } else {
    ctx.restore();
    return;
  }

  const startAngle = isFront ? 0 : Math.PI;
  const endAngle = isFront ? Math.PI : Math.PI * 2;
  
  ctx.beginPath();
  ctx.ellipse(
    planet.x, planet.y,
    planet.radius * rMultW,
    planet.radius * rMultH,
    tilt,
    startAngle,
    endAngle
  );

  if (planet.id === "saturn") {
    // Saturn A & B Rings (Split / Details)
    ctx.strokeStyle = colorStr + "0.35)";
    ctx.lineWidth = planet.radius * 0.25;
    ctx.stroke();

    ctx.beginPath();
    ctx.ellipse(
      planet.x, planet.y,
      planet.radius * 2.3,
      planet.radius * 0.56,
      tilt,
      startAngle,
      endAngle
    );
    ctx.strokeStyle = colorStr + "0.15)";
    ctx.lineWidth = planet.radius * 0.08;
    ctx.stroke();
    
    ctx.beginPath();
    ctx.ellipse(
      planet.x, planet.y,
      planet.radius * 1.55,
      planet.radius * 0.38,
      tilt,
      startAngle,
      endAngle
    );
    ctx.strokeStyle = colorStr + "0.2)";
    ctx.lineWidth = planet.radius * 0.06;
    ctx.stroke();
  } else {
    // Subtle ring systems
    ctx.strokeStyle = colorStr + "0.18)";
    ctx.lineWidth = planet.radius * 0.08;
    ctx.stroke();
  }

  ctx.restore();
}

// Draw Glassmorphism Text Label capsules
function drawTextLabel(ctx, text, x, y, isSelected, isMoon = false) {
  ctx.save();
  ctx.font = isMoon ? "10px 'Space Grotesk', sans-serif" : "11px 'Space Grotesk', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  
  const paddingX = 6;
  const paddingY = 3.5;
  const textWidth = ctx.measureText(text).width;
  const rectW = textWidth + paddingX * 2;
  const rectH = (isMoon ? 10 : 12) + paddingY * 2;
  
  // Capsule Backdrop
  ctx.fillStyle = isSelected ? "rgba(0, 240, 255, 0.18)" : "rgba(10, 12, 22, 0.7)";
  ctx.strokeStyle = isSelected ? "rgba(0, 240, 255, 0.6)" : "rgba(255, 255, 255, 0.12)";
  ctx.lineWidth = 1;
  
  ctx.beginPath();
  const rx = x - rectW / 2;
  const ry = y - rectH / 2;
  if (ctx.roundRect) {
    ctx.roundRect(rx, ry, rectW, rectH, 5);
  } else {
    ctx.rect(rx, ry, rectW, rectH);
  }
  ctx.fill();
  ctx.stroke();
  
  // Typography color
  ctx.fillStyle = isSelected ? "#00f0ff" : isMoon ? "#b0b6c6" : "#ffffff";
  ctx.fillText(text, x, y + (isMoon ? 0.5 : 0));
  ctx.restore();
}

// Core Simulation Loop
function tick() {
  // 1. Resize viewport if container dims mismatch
  if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
  }

  // 2. Clear view with deep-space tint
  ctx.fillStyle = "#030307";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // 3. Render Twinkling Stars with parallax scrolling
  if (drawStars) {
    stars.forEach(star => {
      let alpha = star.baseOpacity;
      if (document.getElementById("toggle-stars").checked) {
        alpha += Math.sin(Date.now() * 0.002 * star.twinkleSpeed + star.twinklePhase) * 0.15;
        alpha = Math.max(0.05, Math.min(1.0, alpha));
      }
      ctx.fillStyle = star.color;
      ctx.globalAlpha = alpha;
      
      // Infinite parallax wrap calculation
      let sx = (star.x - camera.x * 0.06) % canvas.width;
      let sy = (star.y - camera.y * 0.06) % canvas.height;
      if (sx < 0) sx += canvas.width;
      if (sy < 0) sy += canvas.height;

      ctx.beginPath();
      ctx.arc(sx, sy, star.radius, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1.0; // Reset alpha
  }

  // 4. Smooth Camera Lerp
  if (focusedBodyId) {
    const focusedBody = allSimulationBodies[focusedBodyId];
    if (focusedBody) {
      camera.targetX = focusedBody.x;
      camera.targetY = focusedBody.y;
    }
  }

  camera.zoom += (camera.targetZoom - camera.zoom) * 0.12;
  camera.x += (camera.targetX - camera.x) * 0.12;
  camera.y += (camera.targetY - camera.y) * 0.12;

  // 5. Apply Camera Matrix Transformation
  ctx.save();
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.scale(camera.zoom, camera.zoom);
  ctx.translate(-camera.x, -camera.y);

  // 6. Draw Planet Orbit Paths
  if (drawOrbits) {
    planets.forEach(planet => {
      ctx.beginPath();
      ctx.arc(0, 0, planet.orbitRadius, 0, Math.PI * 2);
      if (selectedBodyId === planet.id) {
        ctx.strokeStyle = planet.color.primary + "3A"; // 22% primary accent
        ctx.lineWidth = 1.8;
      } else {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
        ctx.lineWidth = 1;
      }
      ctx.stroke();
    });
  }

  // 7. Render Sun
  const sunPulseRad = sun.radius + Math.sin(Date.now() / 350) * 1.2;
  let sunGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, sunPulseRad * 1.5);
  sunGrad.addColorStop(0, "#ffffff");
  sunGrad.addColorStop(0.2, "#ffea55");
  sunGrad.addColorStop(0.65, "#ff5500");
  sunGrad.addColorStop(1, "rgba(255, 51, 0, 0)");
  ctx.fillStyle = sunGrad;
  ctx.beginPath();
  ctx.arc(0, 0, sunPulseRad * 1.5, 0, Math.PI * 2);
  ctx.fill();

  // Draw Sun Core
  ctx.fillStyle = "#ffe244";
  ctx.shadowColor = "#ff5500";
  ctx.shadowBlur = Math.max(10, 25 * camera.zoom);
  ctx.beginPath();
  ctx.arc(0, 0, sunPulseRad, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0; // Reset shadow

  // Solar flares corona effect
  ctx.strokeStyle = "rgba(255, 102, 0, 0.25)";
  ctx.lineWidth = 2;
  const numFlares = 8;
  const cycle = Date.now() * 0.0008;
  for (let i = 0; i < numFlares; i++) {
    const angle = (i * Math.PI * 2) / numFlares + cycle;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(angle) * (sunPulseRad * 1.3), Math.sin(angle) * (sunPulseRad * 1.3));
    ctx.stroke();
  }

  // Sun Selection Indicator
  if (selectedBodyId === sun.id) {
    ctx.strokeStyle = "rgba(0, 240, 255, 0.65)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.arc(0, 0, sun.radius + 8, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (drawLabels) {
    drawTextLabel(ctx, sun.name, 0, sun.radius + 15, selectedBodyId === sun.id);
  }

  // 8. Update and Render Planets and Moons
  planets.forEach(planet => {
    // Apply orbital movement
    if (isPlaying) {
      planet.angle += planet.speed * simulationSpeed;
    }
    planet.x = Math.cos(planet.angle) * planet.orbitRadius;
    planet.y = Math.sin(planet.angle) * planet.orbitRadius;

    // Draw Back half of rings (e.g. behind sphere)
    if (planet.hasRings) {
      drawRings(ctx, planet, false);
    }

    // Planetary Phase Shader (gradient centered towards the Sun at 0,0)
    const angleToSun = Math.atan2(-planet.y, -planet.x);
    let planetSphereGrad = ctx.createRadialGradient(
      planet.x + Math.cos(angleToSun) * planet.radius * 0.35,
      planet.y + Math.sin(angleToSun) * planet.radius * 0.35,
      0,
      planet.x,
      planet.y,
      planet.radius
    );
    planetSphereGrad.addColorStop(0, planet.color.primary);
    planetSphereGrad.addColorStop(0.65, planet.color.secondary);
    planetSphereGrad.addColorStop(0.95, "#06060c"); // Night side shading
    planetSphereGrad.addColorStop(1.0, "#010103");

    ctx.fillStyle = planetSphereGrad;
    ctx.beginPath();
    ctx.arc(planet.x, planet.y, planet.radius, 0, Math.PI * 2);
    ctx.fill();

    // Atmosphere halo
    let haloGrad = ctx.createRadialGradient(
      planet.x, planet.y, planet.radius * 0.9,
      planet.x, planet.y, planet.radius * 1.3
    );
    haloGrad.addColorStop(0, "rgba(0, 0, 0, 0)");
    haloGrad.addColorStop(0.2, planet.color.primary + "1E"); // ~12% opacity
    haloGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = haloGrad;
    ctx.beginPath();
    ctx.arc(planet.x, planet.y, planet.radius * 1.3, 0, Math.PI * 2);
    ctx.fill();

    // Draw Front half of rings (overlaps planet front hemisphere)
    if (planet.hasRings) {
      drawRings(ctx, planet, true);
    }

    // Selected Planet Outline
    if (selectedBodyId === planet.id) {
      ctx.strokeStyle = "rgba(0, 240, 255, 0.7)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.arc(planet.x, planet.y, planet.radius + 6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw Labels
    if (drawLabels) {
      drawTextLabel(ctx, planet.name, planet.x, planet.y + planet.radius + 15, selectedBodyId === planet.id);
    }

    // Render moons
    planet.moons.forEach((moon, mIdx) => {
      if (isPlaying) {
        moon.angle += moon.speed * simulationSpeed;
      }
      moon.x = planet.x + Math.cos(moon.angle) * moon.orbitRadius;
      moon.y = planet.y + Math.sin(moon.angle) * moon.orbitRadius;

      // Render moon paths (only when planet/moon is focused, or at close zooms)
      const isFocusedSystem = (focusedBodyId === planet.id || focusedBodyId === moon.id || camera.zoom > 1.3);
      if (drawOrbits && isFocusedSystem) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(planet.x, planet.y, moon.orbitRadius, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Moon body shadow phase gradient
      const moonAngleToSun = Math.atan2(-moon.y, -moon.x);
      let moonGrad = ctx.createRadialGradient(
        moon.x + Math.cos(moonAngleToSun) * moon.radius * 0.3,
        moon.y + Math.sin(moonAngleToSun) * moon.radius * 0.3,
        0,
        moon.x,
        moon.y,
        moon.radius
      );
      moonGrad.addColorStop(0, moon.color.primary);
      moonGrad.addColorStop(0.7, moon.color.secondary);
      moonGrad.addColorStop(1, "#020204");
      
      ctx.fillStyle = moonGrad;
      ctx.beginPath();
      ctx.arc(moon.x, moon.y, moon.radius, 0, Math.PI * 2);
      ctx.fill();

      // Selected Moon outline
      if (selectedBodyId === moon.id) {
        ctx.strokeStyle = "rgba(0, 240, 255, 0.75)";
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.arc(moon.x, moon.y, moon.radius + 3, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Moon text labeling (only shown when focused on planet/moon, or high zoom)
      const showLabelsForMoons = drawLabels && (focusedBodyId === planet.id || focusedBodyId === moon.id || camera.zoom > 1.8);
      if (showLabelsForMoons) {
        drawTextLabel(ctx, moon.name, moon.x, moon.y + moon.radius + 9, selectedBodyId === moon.id, true);
      }
    });
  });

  ctx.restore(); // Restore view transformations

  // Schedule next frame
  requestAnimationFrame(tick);
}

// Interactive Selection Binding
function selectBody(id) {
  selectedBodyId = id;
  const body = allSimulationBodies[id];
  if (!body) return;

  // Transition UI displays
  document.getElementById("sidebar-empty-state").classList.add("hidden");
  document.getElementById("sidebar-content").classList.remove("hidden");

  // Fetch educational data properties
  let eduData = SOLAR_SYSTEM_DATA[id];
  let categoryStr = "";
  let parentPlanet = null;

  if (!eduData) {
    // Search moons list
    Object.values(SOLAR_SYSTEM_DATA).forEach(p => {
      if (p.moons) {
        const found = p.moons.find(m => m.id === id);
        if (found) {
          eduData = found;
          parentPlanet = p;
          categoryStr = found.type;
        }
      }
    });
  } else {
    categoryStr = eduData.type;
  }

  if (!eduData) return;

  // Bind facts to UI
  document.getElementById("info-name").textContent = eduData.name;
  document.getElementById("info-category").textContent = categoryStr;
  document.getElementById("info-size").textContent = eduData.size;
  document.getElementById("info-orbit").textContent = eduData.orbit;
  document.getElementById("info-features").textContent = eduData.features;
  document.getElementById("info-fact").textContent = eduData.fact;

  // Bind Sidebar accent line color
  const accentLine = document.getElementById("info-accent-line");
  accentLine.style.backgroundColor = body.color.primary;
  accentLine.style.boxShadow = `0 0 10px ${body.color.glow}`;

  // Update Focus Buttons in Left panel
  const focusBtn = document.getElementById("focus-btn");
  focusBtn.classList.remove("disabled");
  focusBtn.disabled = false;

  // Populate Moon details panel dynamically
  const moonsSection = document.getElementById("moons-section");
  const moonsList = document.getElementById("moons-list");
  const moonCountBadge = document.getElementById("moon-count-badge");
  const additionalMoonsText = document.getElementById("additional-moons-text");

  // Highlight moon pills in DOM
  document.querySelectorAll(".moon-pill").forEach(pill => pill.classList.remove("active-moon"));

  if (id === "sun") {
    moonsSection.classList.remove("hidden");
    moonCountBadge.textContent = "8";
    moonsList.innerHTML = "";
    additionalMoonsText.textContent = "The Sun is orbited by all eight planets and countless minor bodies.";
    additionalMoonsText.classList.remove("hidden");
  } else if (parentPlanet) {
    // selected body is a Moon
    moonsSection.classList.remove("hidden");
    moonCountBadge.textContent = "Parent";
    moonsList.innerHTML = "";

    const parentBtn = document.createElement("button");
    parentBtn.className = "moon-pill active-moon";
    parentBtn.textContent = `← Back to ${parentPlanet.name}`;
    parentBtn.onclick = (e) => {
      e.stopPropagation();
      selectBody(parentPlanet.id);
    };
    moonsList.appendChild(parentBtn);
    
    additionalMoonsText.textContent = `${eduData.name} orbits the ${parentPlanet.type} ${parentPlanet.name}.`;
    additionalMoonsText.classList.remove("hidden");
  } else {
    // selected body is a Planet
    const moonsData = eduData.moons || [];
    if (moonsData.length > 0) {
      moonsSection.classList.remove("hidden");
      moonCountBadge.textContent = moonsData.length;
      moonsList.innerHTML = "";

      moonsData.forEach(moon => {
        const pill = document.createElement("button");
        pill.className = "moon-pill";
        pill.textContent = moon.name;
        pill.onclick = (e) => {
          e.stopPropagation();
          selectBody(moon.id);
        };
        moonsList.appendChild(pill);
      });

      if (eduData.additionalMoonsText) {
        additionalMoonsText.textContent = eduData.additionalMoonsText;
        additionalMoonsText.classList.remove("hidden");
      } else {
        additionalMoonsText.classList.add("hidden");
      }
    } else {
      // Mercury/Venus (0 moons)
      moonsSection.classList.remove("hidden");
      moonCountBadge.textContent = "0";
      moonsList.innerHTML = "";
      additionalMoonsText.textContent = `${eduData.name} has no confirmed natural moons.`;
      additionalMoonsText.classList.remove("hidden");
    }
  }

  // Synchronize sidebar button text
  const sidebarFocus = document.getElementById("sidebar-action-focus");
  if (parentPlanet) {
    sidebarFocus.querySelector(".btn-text").textContent = "Focus Moon";
  } else if (id === "sun") {
    sidebarFocus.querySelector(".btn-text").textContent = "Focus Sun";
  } else {
    sidebarFocus.querySelector(".btn-text").textContent = "Focus Planet & Moons";
  }
}

// Camera focus orchestration
function focusOnBody(id) {
  const body = allSimulationBodies[id];
  if (!body) return;

  focusedBodyId = id;

  // Set camera target positions to center the body
  camera.targetX = body.x;
  camera.targetY = body.y;

  // Determine appropriate zoom levels based on target diameter
  if (id === "sun") {
    camera.targetZoom = 0.95;
  } else if (body.parentPlanet) {
    camera.targetZoom = 4.2; // Moons need higher zoom
  } else {
    // Planet zoom scale scales relative to size
    camera.targetZoom = Math.max(1.3, Math.min(3.2, 23.0 / body.radius));
  }

  // Update left bar controls
  document.getElementById("focus-btn").classList.add("hidden");
  document.getElementById("exit-focus-btn").classList.remove("hidden");
}

function exitFocus() {
  focusedBodyId = null;
  camera.targetX = 0;
  camera.targetY = 0;
  camera.targetZoom = 0.85;

  document.getElementById("exit-focus-btn").classList.add("hidden");
  const focusBtn = document.getElementById("focus-btn");
  focusBtn.classList.remove("hidden");
  
  if (selectedBodyId) {
    focusBtn.classList.remove("disabled");
    focusBtn.disabled = false;
  } else {
    focusBtn.classList.add("disabled");
    focusBtn.disabled = true;
  }
}

// Search and Autocomplete Event handlers
const searchInput = document.getElementById("search-input");
const clearSearchBtn = document.getElementById("clear-search");
const searchResults = document.getElementById("search-results");

function handleSearch(query) {
  query = query.trim().toLowerCase();

  if (!query) {
    clearSearch();
    return;
  }

  clearSearchBtn.classList.remove("hidden");
  searchResults.classList.remove("hidden");
  searchResults.innerHTML = "";

  const matches = [];

  // Search Sun
  if (SOLAR_SYSTEM_DATA.sun.name.toLowerCase().includes(query)) {
    matches.push({ body: SOLAR_SYSTEM_DATA.sun, type: "Star", parent: null });
  }

  // Search Planets and Moons
  Object.values(SOLAR_SYSTEM_DATA).forEach(p => {
    if (p.id === "sun") return;

    if (p.name.toLowerCase().includes(query)) {
      matches.push({ body: p, type: p.type, parent: null });
    }

    p.moons.forEach(m => {
      if (m.name.toLowerCase().includes(query)) {
        matches.push({ body: m, type: "Moon", parent: p.name });
      }
    });
  });

  if (matches.length === 0) {
    const emptyItem = document.createElement("div");
    emptyItem.className = "search-empty";
    emptyItem.textContent = "No celestial bodies matched your search";
    searchResults.appendChild(emptyItem);
    return;
  }

  matches.forEach(match => {
    const item = document.createElement("div");
    item.className = "search-item";

    const labelContainer = document.createElement("div");
    const nameLabel = document.createElement("div");
    nameLabel.className = "name";
    nameLabel.textContent = match.body.name;
    labelContainer.appendChild(nameLabel);

    if (match.parent) {
      const parentLabel = document.createElement("div");
      parentLabel.className = "parent";
      parentLabel.textContent = `Orbits ${match.parent}`;
      labelContainer.appendChild(parentLabel);
    }
    item.appendChild(labelContainer);

    const categoryLabel = document.createElement("div");
    categoryLabel.className = "type";
    categoryLabel.textContent = match.type.split(" ")[0];
    item.appendChild(categoryLabel);

    item.onclick = () => {
      selectBody(match.body.id);
      focusOnBody(match.body.id);
      clearSearch();
      searchInput.value = match.body.name;
      clearSearchBtn.classList.remove("hidden");
    };

    searchResults.appendChild(item);
  });
}

function clearSearch() {
  searchInput.value = "";
  clearSearchBtn.classList.add("hidden");
  searchResults.classList.add("hidden");
  searchResults.innerHTML = "";
}

// Mouse Drag and Camera Pan Mechanics
let isDragging = false;
let dragStartX = 0;
let dragStartY = 0;
let cameraDragStartX = 0;
let cameraDragStartY = 0;

canvas.addEventListener("mousedown", (e) => {
  isDragging = true;
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  cameraDragStartX = camera.targetX;
  cameraDragStartY = camera.targetY;
});

canvas.addEventListener("mousemove", (e) => {
  if (!isDragging) return;

  const dx = e.clientX - dragStartX;
  const dy = e.clientY - dragStartY;

  // Release camera tracking if dragged more than 3 screen pixels
  if (Math.hypot(dx, dy) > 3) {
    if (focusedBodyId !== null) {
      focusedBodyId = null;
      document.getElementById("exit-focus-btn").classList.add("hidden");
      document.getElementById("focus-btn").classList.remove("hidden");
      
      // Pivot camera smoothly onto current positioning coordinates
      camera.targetX = camera.x;
      camera.targetY = camera.y;
      camera.targetZoom = camera.zoom;
      
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      cameraDragStartX = camera.x;
      cameraDragStartY = camera.y;
    } else {
      camera.targetX = cameraDragStartX - dx / camera.zoom;
      camera.targetY = cameraDragStartY - dy / camera.zoom;
    }
  }
});

canvas.addEventListener("mouseup", (e) => {
  if (!isDragging) return;
  isDragging = false;

  const dx = e.clientX - dragStartX;
  const dy = e.clientY - dragStartY;

  // Detect canvas clicks (less than 5 pixels drag distance)
  if (Math.hypot(dx, dy) < 5) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let clickedBody = null;
    let minDistance = Infinity;

    // Hit test screen projections
    Object.values(allSimulationBodies).forEach(body => {
      const screenX = canvas.width / 2 + (body.x - camera.x) * camera.zoom;
      const screenY = canvas.height / 2 + (body.y - camera.y) * camera.zoom;
      const dist = Math.hypot(mouseX - screenX, mouseY - screenY);
      
      // Accessibility hit boundaries (min 20px hit radius)
      const threshold = Math.max(body.radius * camera.zoom, 20);

      if (dist < threshold && dist < minDistance) {
        minDistance = dist;
        clickedBody = body;
      }
    });

    if (clickedBody) {
      selectBody(clickedBody.id);
    }
  }
});

// Scroll Wheel Zoom binding
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  
  const zoomFactor = 1.15;
  if (e.deltaY < 0) {
    camera.targetZoom = Math.min(15.0, camera.targetZoom * zoomFactor);
  } else {
    camera.targetZoom = Math.max(0.04, camera.targetZoom / zoomFactor);
  }
}, { passive: false });

// Mobile Touch Support
canvas.addEventListener("touchstart", (e) => {
  if (e.touches.length === 1) {
    isDragging = true;
    dragStartX = e.touches[0].clientX;
    dragStartY = e.touches[0].clientY;
    cameraDragStartX = camera.targetX;
    cameraDragStartY = camera.targetY;
  }
}, { passive: true });

canvas.addEventListener("touchmove", (e) => {
  if (!isDragging || e.touches.length !== 1) return;

  const dx = e.touches[0].clientX - dragStartX;
  const dy = e.touches[0].clientY - dragStartY;

  if (Math.hypot(dx, dy) > 3) {
    if (focusedBodyId !== null) {
      focusedBodyId = null;
      document.getElementById("exit-focus-btn").classList.add("hidden");
      document.getElementById("focus-btn").classList.remove("hidden");
      
      camera.targetX = camera.x;
      camera.targetY = camera.y;
      camera.targetZoom = camera.zoom;
      
      dragStartX = e.touches[0].clientX;
      dragStartY = e.touches[0].clientY;
      cameraDragStartX = camera.x;
      cameraDragStartY = camera.y;
    } else {
      camera.targetX = cameraDragStartX - dx / camera.zoom;
      camera.targetY = cameraDragStartY - dy / camera.zoom;
    }
  }
}, { passive: true });

canvas.addEventListener("touchend", (e) => {
  if (isDragging) {
    isDragging = false;
    
    const dx = e.changedTouches[0].clientX - dragStartX;
    const dy = e.changedTouches[0].clientY - dragStartY;

    if (Math.hypot(dx, dy) < 5) {
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.changedTouches[0].clientX - rect.left;
      const mouseY = e.changedTouches[0].clientY - rect.top;

      let clickedBody = null;
      let minDistance = Infinity;

      Object.values(allSimulationBodies).forEach(body => {
        const screenX = canvas.width / 2 + (body.x - camera.x) * camera.zoom;
        const screenY = canvas.height / 2 + (body.y - camera.y) * camera.zoom;
        const dist = Math.hypot(mouseX - screenX, mouseY - screenY);
        
        // Touch target sizing (slightly larger, min 25px)
        const threshold = Math.max(body.radius * camera.zoom, 25);

        if (dist < threshold && dist < minDistance) {
          minDistance = dist;
          clickedBody = body;
        }
      });

      if (clickedBody) {
        selectBody(clickedBody.id);
      }
    }
  }
});

// Controls & Event Handlers Wiring
document.getElementById("play-pause-btn").onclick = () => {
  isPlaying = !isPlaying;
  const btn = document.getElementById("play-pause-btn");
  if (isPlaying) {
    btn.classList.add("active-state");
    btn.querySelector(".btn-icon").textContent = "⏸";
    btn.querySelector(".btn-text").textContent = "Pause";
  } else {
    btn.classList.remove("active-state");
    btn.querySelector(".btn-icon").textContent = "▶";
    btn.querySelector(".btn-text").textContent = "Resume";
  }
};

document.getElementById("reset-cam-btn").onclick = () => {
  exitFocus();
};

document.getElementById("focus-btn").onclick = () => {
  if (selectedBodyId) {
    focusOnBody(selectedBodyId);
  }
};

document.getElementById("exit-focus-btn").onclick = () => {
  exitFocus();
};

document.getElementById("sidebar-action-focus").onclick = () => {
  if (selectedBodyId) {
    focusOnBody(selectedBodyId);
  }
};

// Wire Quick Jump links in Empty Sidebar
document.querySelectorAll(".quick-link-btn").forEach(btn => {
  btn.onclick = () => {
    const id = btn.getAttribute("data-id");
    selectBody(id);
    focusOnBody(id);
  };
});

// Checkboxes and speed slider
document.getElementById("toggle-orbits").onchange = (e) => {
  drawOrbits = e.target.checked;
};

document.getElementById("toggle-labels").onchange = (e) => {
  drawLabels = e.target.checked;
};

document.getElementById("toggle-stars").onchange = (e) => {
  drawStars = e.target.checked;
};

document.getElementById("speed-slider").oninput = (e) => {
  simulationSpeed = parseFloat(e.target.value);
  document.getElementById("speed-val").textContent = `${simulationSpeed.toFixed(1)}x`;
};

// Search wires
searchInput.oninput = (e) => handleSearch(e.target.value);
searchInput.onfocus = (e) => handleSearch(e.target.value);
clearSearchBtn.onclick = () => clearSearch();

document.addEventListener("click", (e) => {
  if (!e.target.closest(".search-wrapper")) {
    searchResults.classList.add("hidden");
  }
});

// About Modal Triggers
const aboutModal = document.getElementById("about-modal");
const aboutToggleBtn = document.getElementById("about-toggle-btn");
const closeAboutBtn = document.getElementById("close-about-btn");
const dismissModalBtn = document.getElementById("dismiss-modal-btn");

aboutToggleBtn.onclick = () => {
  aboutModal.classList.remove("hidden");
};

closeAboutBtn.onclick = () => {
  aboutModal.classList.add("hidden");
};

dismissModalBtn.onclick = () => {
  aboutModal.classList.add("hidden");
};

aboutModal.onclick = (e) => {
  if (e.target === aboutModal) {
    aboutModal.classList.add("hidden");
  }
};

// Kickoff Application
window.onload = () => {
  initStars();
  initSimulation();
  
  // Set default dimensions and start simulation loops
  canvas.width = canvas.clientWidth;
  canvas.height = canvas.clientHeight;
  tick();

  // Highlight empty state quicklinks or show About Modal on first visit
  aboutModal.classList.remove("hidden");
};
