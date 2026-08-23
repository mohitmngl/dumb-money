// Solar System Interactive Demo
(function() {
  'use strict';

  // State
  const state = {
    selectedBody: null,
    selectedType: null, // 'sun', 'planet', 'moon'
    selectedPlanetIndex: -1,
    showLabels: true,
    showOrbits: true,
    isPaused: false,
    speed: 1,
    time: 0,
    focusedPlanet: -1, // -1 = none focused
    camera: { x: 0, y: 0, zoom: 1 },
    isDragging: false,
    dragStart: { x: 0, y: 0 },
    cameraStart: { x: 0, y: 0 },
    hoveredBody: null,
    searchQuery: '',
    starField: []
  };

  // DOM
  const canvas = document.getElementById('solar-canvas');
  const ctx = canvas.getContext('2d');
  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');
  const panelTitle = document.getElementById('panel-title');
  const panelSubtitle = document.getElementById('panel-subtitle');
  const bodySelector = document.getElementById('body-selector');
  const infoContent = document.getElementById('info-content');

  // Initialize
  function init() {
    resizeCanvas();
    generateStars();
    generateBodySelector();
    showSunInfo();
    setupEventListeners();
    requestAnimationFrame(loop);
  }

  function resizeCanvas() {
    const container = canvas.parentElement;
    canvas.width = container.clientWidth * window.devicePixelRatio;
    canvas.height = container.clientHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }

  function generateStars() {
    state.starField = [];
    for (let i = 0; i < 300; i++) {
      state.starField.push({
        x: Math.random() * 2000 - 1000,
        y: Math.random() * 2000 - 1000,
        size: Math.random() * 1.5 + 0.3,
        brightness: Math.random() * 0.7 + 0.3,
        twinkleSpeed: Math.random() * 0.02 + 0.005
      });
    }
  }

  function generateBodySelector() {
    bodySelector.innerHTML = '';

    // Sun
    const sunPill = document.createElement('div');
    sunPill.className = 'body-pill' + (state.selectedType === 'sun' ? ' active' : '');
    sunPill.textContent = 'Sun';
    sunPill.onclick = () => selectSun();
    bodySelector.appendChild(sunPill);

    // Planets
    SOLAR_SYSTEM_DATA.planets.forEach((planet, i) => {
      const pill = document.createElement('div');
      pill.className = 'body-pill' + (state.selectedType === 'planet' && state.selectedPlanetIndex === i ? ' active' : '');
      pill.textContent = planet.name;
      pill.onclick = () => selectPlanet(i);
      bodySelector.appendChild(pill);
    });
  }

  // Selection functions
  function selectSun() {
    state.selectedType = 'sun';
    state.selectedBody = SOLAR_SYSTEM_DATA.sun;
    state.selectedPlanetIndex = -1;
    state.focusedPlanet = -1;
    generateBodySelector();
    showSunInfo();
    resetCamera();
  }

  function selectPlanet(index) {
    state.selectedType = 'planet';
    state.selectedPlanetIndex = index;
    state.selectedBody = SOLAR_SYSTEM_DATA.planets[index];
    state.focusedPlanet = index;
    generateBodySelector();
    showPlanetInfo(index);
    focusOnPlanet(index);
  }

  function selectMoon(planetIndex, moonIndex) {
    state.selectedType = 'moon';
    state.selectedPlanetIndex = planetIndex;
    state.selectedBody = SOLAR_SYSTEM_DATA.planets[planetIndex].moons[moonIndex];
    generateMoonCards(planetIndex, moonIndex);
    showMoonInfo(planetIndex, moonIndex);
  }

  // Info display
  function showSunInfo() {
    const sun = SOLAR_SYSTEM_DATA.sun;
    panelTitle.textContent = sun.name;
    panelSubtitle.textContent = 'Center of the Solar System';
    infoContent.innerHTML = `
      <div class="info-section">
        <div class="info-label">Type</div>
        <div class="info-value">${sun.type}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Diameter</div>
        <div class="info-value info-highlight">${sun.diameter}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Notable Features</div>
        <div class="info-value">${sun.notableFeatures}</div>
      </div>
      <div class="info-section">
        <div class="info-fact">
          <strong>Memorable Fact</strong>
          ${sun.memorableFact}
        </div>
      </div>
      <div class="info-section">
        <div class="info-label">About</div>
        <div class="info-description">${sun.info}</div>
      </div>
      <div class="about-section">
        <div class="about-title">Notes</div>
        <div class="about-text">
          <p>Distances and sizes are intentionally compressed for visualization purposes.</p>
          <p>Moon counts change as new discoveries are confirmed by astronomers.</p>
          <p>This demo focuses on major and representative moons for readability.</p>
        </div>
      </div>
    `;
  }

  function showPlanetInfo(index) {
    const planet = SOLAR_SYSTEM_DATA.planets[index];
    panelTitle.textContent = planet.name;
    panelSubtitle.textContent = planet.type;

    let moonsHtml = '';
    if (planet.moons.length > 0) {
      moonsHtml = `
        <div class="moons-section">
          <div class="moons-title">Moons (${planet.moons.length} major)</div>
          <div id="moon-cards"></div>
        </div>
      `;
    } else if (planet.moonNote) {
      moonsHtml = `
        <div class="moons-section">
          <div class="moons-title">Moons</div>
          <div class="moon-note">${planet.moonNote}</div>
        </div>
      `;
    }

    infoContent.innerHTML = `
      <div class="info-section">
        <div class="info-label">Type</div>
        <div class="info-value">${planet.type}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Diameter</div>
        <div class="info-value info-highlight">${planet.diameter}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Position</div>
        <div class="info-value">${planet.orbitalRelationship}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Orbital Period</div>
        <div class="info-value">${planet.orbitalPeriod.toLocaleString()} Earth days</div>
      </div>
      <div class="info-section">
        <div class="info-label">Notable Features</div>
        <div class="info-value">${planet.notableFeatures}</div>
      </div>
      <div class="info-section">
        <div class="info-fact">
          <strong>Memorable Fact</strong>
          ${planet.memorableFact}
        </div>
      </div>
      <div class="info-section">
        <div class="info-label">About</div>
        <div class="info-description">${planet.info}</div>
      </div>
      ${moonsHtml}
      <div class="about-section">
        <div class="about-title">Notes</div>
        <div class="about-text">
          <p>Distances and sizes are intentionally compressed for visualization purposes.</p>
          <p>Moon counts change as new discoveries are confirmed by astronomers.</p>
          <p>This demo focuses on major and representative moons for readability.</p>
        </div>
      </div>
    `;

    if (planet.moons.length > 0) {
      generateMoonCards(index, -1);
    }
  }

  function generateMoonCards(planetIndex, activeMoonIndex) {
    const container = document.getElementById('moon-cards');
    if (!container) return;
    const planet = SOLAR_SYSTEM_DATA.planets[planetIndex];

    container.innerHTML = planet.moons.map((moon, i) => `
      <div class="moon-card${activeMoonIndex === i ? ' active' : ''}" onclick="window.selectMoon(${planetIndex}, ${i})">
        <div class="moon-card-header">
          <div class="moon-dot" style="background: ${moon.color}"></div>
          <div class="moon-name">${moon.name}</div>
          <div class="moon-type">${moon.type}</div>
        </div>
        <div class="moon-fact">${moon.memorableFact}</div>
      </div>
    `).join('');
  }

  function showMoonInfo(planetIndex, moonIndex) {
    const planet = SOLAR_SYSTEM_DATA.planets[planetIndex];
    const moon = planet.moons[moonIndex];
    panelTitle.textContent = moon.name;
    panelSubtitle.textContent = `${moon.type} — Moon of ${planet.name}`;

    generateMoonCards(planetIndex, moonIndex);

    infoContent.innerHTML = `
      <div class="info-section">
        <div class="info-label">Type</div>
        <div class="info-value">${moon.type}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Diameter</div>
        <div class="info-value info-highlight">${moon.diameter}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Position</div>
        <div class="info-value">${moon.orbitalRelationship}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Orbital Period</div>
        <div class="info-value">${Math.abs(moon.orbitalPeriod).toFixed(2)} Earth days${moon.orbitalPeriod < 0 ? ' (retrograde)' : ''}</div>
      </div>
      <div class="info-section">
        <div class="info-label">Notable Features</div>
        <div class="info-value">${moon.notableFeatures}</div>
      </div>
      <div class="info-section">
        <div class="info-fact">
          <strong>Memorable Fact</strong>
          ${moon.memorableFact}
        </div>
      </div>
      <div class="info-section">
        <div class="info-label">About</div>
        <div class="info-description">${moon.info}</div>
      </div>
      <div class="about-section">
        <div class="about-title">Notes</div>
        <div class="about-text">
          <p>Distances and sizes are intentionally compressed for visualization purposes.</p>
          <p>Moon counts change as new discoveries are confirmed by astronomers.</p>
          <p>This demo focuses on major and representative moons for readability.</p>
        </div>
      </div>
    `;
  }

  function focusOnPlanet(index) {
    const planet = SOLAR_SYSTEM_DATA.planets[index];
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    state.camera.x = -planet.orbitalDistance * state.camera.zoom;
    state.camera.y = 0;
    state.camera.zoom = Math.min(w, h) / (planet.orbitalDistance * 2.8);
    state.camera.zoom = Math.max(0.15, Math.min(state.camera.zoom, 3));
  }

  function resetCamera() {
    state.camera = { x: 0, y: 0, zoom: 1 };
    state.focusedPlanet = -1;
    state.time = 0;
    generateBodySelector();
  }

  // Rendering
  function loop(timestamp) {
    if (!state.isPaused) {
      state.time += 0.016 * state.speed;
    }
    render();
    requestAnimationFrame(loop);
  }

  function render() {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;

    // Clear
    ctx.fillStyle = '#0a0a1a';
    ctx.fillRect(0, 0, w, h);

    // Draw stars
    drawStars(w, h);

    // Camera transform
    ctx.save();
    ctx.translate(w / 2 + state.camera.x, h / 2 + state.camera.y);
    ctx.scale(state.camera.zoom, state.camera.zoom);

    // Draw orbits
    if (state.showOrbits) {
      drawOrbits();
    }

    // Draw sun
    drawSun();

    // Draw planets and moons
    SOLAR_SYSTEM_DATA.planets.forEach((planet, i) => {
      drawPlanet(planet, i);
    });

    ctx.restore();

    // Draw labels (in screen space)
    if (state.showLabels) {
      ctx.save();
      ctx.translate(w / 2 + state.camera.x, h / 2 + state.camera.y);
      ctx.scale(state.camera.zoom, state.camera.zoom);
      drawLabels();
      ctx.restore();
    }
  }

  function drawStars(w, h) {
    state.starField.forEach(star => {
      const flicker = Math.sin(state.time * star.twinkleSpeed * 60) * 0.3 + 0.7;
      ctx.fillStyle = `rgba(255, 255, 255, ${star.brightness * flicker})`;
      ctx.beginPath();
      ctx.arc(
        (star.x + w / 2) % w,
        (star.y + h / 2) % h,
        star.size,
        0,
        Math.PI * 2
      );
      ctx.fill();
    });
  }

  function drawOrbits() {
    SOLAR_SYSTEM_DATA.planets.forEach(planet => {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(0, 0, planet.orbitalDistance, 0, Math.PI * 2);
      ctx.stroke();
    });
  }

  function drawSun() {
    const sun = SOLAR_SYSTEM_DATA.sun;
    const pulse = Math.sin(state.time * 2) * 2;

    // Outer glow
    const gradient3 = ctx.createRadialGradient(0, 0, sun.radius, 0, 0, sun.radius * 3);
    gradient3.addColorStop(0, 'rgba(253, 184, 19, 0.3)');
    gradient3.addColorStop(1, 'rgba(253, 184, 19, 0)');
    ctx.fillStyle = gradient3;
    ctx.beginPath();
    ctx.arc(0, 0, sun.radius * 3 + pulse, 0, Math.PI * 2);
    ctx.fill();

    // Middle glow
    const gradient2 = ctx.createRadialGradient(0, 0, sun.radius * 0.5, 0, 0, sun.radius * 2);
    gradient2.addColorStop(0, 'rgba(255, 200, 50, 0.6)');
    gradient2.addColorStop(1, 'rgba(255, 140, 0, 0)');
    ctx.fillStyle = gradient2;
    ctx.beginPath();
    ctx.arc(0, 0, sun.radius * 2, 0, Math.PI * 2);
    ctx.fill();

    // Sun body
    const gradient = ctx.createRadialGradient(
      -sun.radius * 0.2, -sun.radius * 0.2, 0,
      0, 0, sun.radius
    );
    gradient.addColorStop(0, '#FFF5D0');
    gradient.addColorStop(0.3, '#FDB813');
    gradient.addColorStop(0.7, '#FF8C00');
    gradient.addColorStop(1, '#FF6600');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(0, 0, sun.radius + pulse * 0.3, 0, Math.PI * 2);
    ctx.fill();

    // Highlight
    ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.beginPath();
    ctx.arc(-sun.radius * 0.3, -sun.radius * 0.3, sun.radius * 0.4, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawPlanet(planet, index) {
    const angle = (state.time * (1 / planet.orbitalPeriod) * Math.PI * 2) % (Math.PI * 2);
    const x = Math.cos(angle) * planet.orbitalDistance;
    const y = Math.sin(angle) * planet.orbitalDistance * 0.35; // Elliptical for perspective

    planet._screenX = x;
    planet._screenY = y;

    // Saturn's rings
    if (planet.name === 'Saturn') {
      drawSaturnRings(x, y, planet.displayRadius);
    }

    // Planet body
    const isSelected = state.selectedType === 'planet' && state.selectedPlanetIndex === index;
    const isFocused = state.focusedPlanet === index;

    // Glow for selected/focused
    if (isSelected || isFocused) {
      ctx.shadowColor = planet.color;
      ctx.shadowBlur = 15;
    }

    const gradient = ctx.createRadialGradient(
      x - planet.displayRadius * 0.2, y - planet.displayRadius * 0.2, 0,
      x, y, planet.displayRadius
    );
    gradient.addColorStop(0, lightenColor(planet.color, 30));
    gradient.addColorStop(0.7, planet.color);
    gradient.addColorStop(1, darkenColor(planet.color, 30));
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(x, y, planet.displayRadius, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    // Planet highlight
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.beginPath();
    ctx.arc(x - planet.displayRadius * 0.25, y - planet.displayRadius * 0.25, planet.displayRadius * 0.35, 0, Math.PI * 2);
    ctx.fill();

    // Draw moons if this planet is focused
    if (state.focusedPlanet === index && planet.moons.length > 0) {
      drawMoons(planet, index, x, y);
    }
  }

  function drawSaturnRings(x, y, radius) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(1, 0.3);

    // Ring 1 (outer)
    ctx.strokeStyle = 'rgba(200, 180, 140, 0.5)';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(0, 0, radius * 2.2, 0, Math.PI * 2);
    ctx.stroke();

    // Ring 2 (inner)
    ctx.strokeStyle = 'rgba(180, 160, 120, 0.6)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(0, 0, radius * 1.8, 0, Math.PI * 2);
    ctx.stroke();

    // Ring 3 (gap)
    ctx.strokeStyle = 'rgba(160, 140, 100, 0.3)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(0, 0, radius * 1.5, 0, Math.PI * 2);
    ctx.stroke();

    ctx.restore();
  }

  function drawMoons(planet, planetIndex, planetX, planetY) {
    planet.moons.forEach((moon, moonIndex) => {
      const moonAngle = (state.time * (1 / moon.orbitalPeriod) * Math.PI * 2) % (Math.PI * 2);
      const moonX = planetX + Math.cos(moonAngle) * moon.orbitalDistance;
      const moonY = planetY + Math.sin(moonAngle) * moon.orbitalDistance * 0.4;

      moon._screenX = moonX;
      moon._screenY = moonY;

      // Moon orbit
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.ellipse(planetX, planetY, moon.orbitalDistance, moon.orbitalDistance * 0.4, 0, 0, Math.PI * 2);
      ctx.stroke();

      // Moon body
      const isMoonSelected = state.selectedType === 'moon' && state.selectedPlanetIndex === planetIndex;
      if (isMoonSelected) {
        ctx.shadowColor = moon.color;
        ctx.shadowBlur = 8;
      }

      const moonGrad = ctx.createRadialGradient(
        moonX - moon.displayRadius * 0.2, moonY - moon.displayRadius * 0.2, 0,
        moonX, moonY, moon.displayRadius
      );
      moonGrad.addColorStop(0, lightenColor(moon.color, 20));
      moonGrad.addColorStop(1, moon.color);
      ctx.fillStyle = moonGrad;
      ctx.beginPath();
      ctx.arc(moonX, moonY, moon.displayRadius, 0, Math.PI * 2);
      ctx.fill();

      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
    });
  }

  function drawLabels() {
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';

    // Sun label
    ctx.font = '12px "Segoe UI", system-ui, sans-serif';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.fillText('Sun', 0, -SOLAR_SYSTEM_DATA.sun.radius - 10);

    // Planet labels
    SOLAR_SYSTEM_DATA.planets.forEach((planet, i) => {
      if (planet._screenX !== undefined) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        ctx.font = '11px "Segoe UI", system-ui, sans-serif';
        ctx.fillText(planet.name, planet._screenX, planet._screenY - planet.displayRadius - 8);
      }

      // Moon labels
      if (state.focusedPlanet === i) {
        planet.moons.forEach(moon => {
          if (moon._screenX !== undefined) {
            ctx.fillStyle = 'rgba(200, 200, 200, 0.6)';
            ctx.font = '9px "Segoe UI", system-ui, sans-serif';
            ctx.fillText(moon.name, moon._screenX, moon._screenY - moon.displayRadius - 5);
          }
        });
      }
    });
  }

  // Color utilities
  function lightenColor(hex, percent) {
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.min(255, (num >> 16) + percent);
    const g = Math.min(255, ((num >> 8) & 0x00FF) + percent);
    const b = Math.min(255, (num & 0x0000FF) + percent);
    return `rgb(${r}, ${g}, ${b})`;
  }

  function darkenColor(hex, percent) {
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.max(0, (num >> 16) - percent);
    const g = Math.max(0, ((num >> 8) & 0x00FF) - percent);
    const b = Math.max(0, (num & 0x0000FF) - percent);
    return `rgb(${r}, ${g}, ${b})`;
  }

  // Hit testing
  function getClickTarget(mx, my) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const worldX = (mx - w / 2 - state.camera.x) / state.camera.zoom;
    const worldY = (my - h / 2 - state.camera.y) / state.camera.zoom;

    // Check sun
    const sunDist = Math.sqrt(worldX * worldX + worldY * worldY);
    if (sunDist < SOLAR_SYSTEM_DATA.sun.radius) {
      return { type: 'sun' };
    }

    // Check planets
    for (let i = SOLAR_SYSTEM_DATA.planets.length - 1; i >= 0; i--) {
      const planet = SOLAR_SYSTEM_DATA.planets[i];
      if (planet._screenX !== undefined) {
        const dx = worldX - planet._screenX;
        const dy = worldY - planet._screenY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < planet.displayRadius + 5) {
          return { type: 'planet', index: i };
        }

        // Check moons
        if (state.focusedPlanet === i) {
          for (let j = 0; j < planet.moons.length; j++) {
            const moon = planet.moons[j];
            if (moon._screenX !== undefined) {
              const mdx = worldX - moon._screenX;
              const mdy = worldY - moon._screenY;
              const mdist = Math.sqrt(mdx * mdx + mdy * mdy);
              if (mdist < moon.displayRadius + 4) {
                return { type: 'moon', planetIndex: i, moonIndex: j };
              }
            }
          }
        }
      }
    }

    return null;
  }

  // Search
  function performSearch(query) {
    state.searchQuery = query.toLowerCase().trim();
    if (!state.searchQuery) {
      searchResults.classList.remove('active');
      return;
    }

    const results = [];

    // Search sun
    if ('sun'.includes(state.searchQuery)) {
      results.push({ type: 'sun', name: 'Sun', color: SOLAR_SYSTEM_DATA.sun.color });
    }

    // Search planets
    SOLAR_SYSTEM_DATA.planets.forEach((planet, i) => {
      if (planet.name.toLowerCase().includes(state.searchQuery)) {
        results.push({ type: 'planet', index: i, name: planet.name, color: planet.color });
      }
      // Search moons
      planet.moons.forEach((moon, j) => {
        if (moon.name.toLowerCase().includes(state.searchQuery)) {
          results.push({ type: 'moon', planetIndex: i, moonIndex: j, name: moon.name, color: moon.color });
        }
      });
    });

    if (results.length === 0) {
      searchResults.innerHTML = `
        <div class="search-no-results">
          No celestial bodies found for "${query}"
        </div>
      `;
    } else {
      searchResults.innerHTML = results.map(r => `
        <div class="search-result-item" data-type="${r.type}" data-index="${r.index || ''}" data-planet="${r.planetIndex || ''}" data-moon="${r.moonIndex || ''}">
          <span class="dot" style="background: ${r.color}"></span>
          ${r.name}
        </div>
      `).join('');
    }
    searchResults.classList.add('active');
  }

  // Event handlers
  function setupEventListeners() {
    // Canvas click
    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const target = getClickTarget(mx, my);

      if (target) {
        if (target.type === 'sun') selectSun();
        else if (target.type === 'planet') selectPlanet(target.index);
        else if (target.type === 'moon') selectMoon(target.planetIndex, target.moonIndex);
      }
    });

    // Canvas hover
    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const target = getClickTarget(mx, my);

      canvas.style.cursor = target ? 'pointer' : 'grab';
    });

    // Canvas drag
    canvas.addEventListener('mousedown', (e) => {
      if (e.button === 0) {
        state.isDragging = true;
        state.dragStart = { x: e.clientX, y: e.clientY };
        state.cameraStart = { x: state.camera.x, y: state.camera.y };
        canvas.style.cursor = 'grabbing';
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (state.isDragging) {
        state.camera.x = state.cameraStart.x + (e.clientX - state.dragStart.x);
        state.camera.y = state.cameraStart.y + (e.clientY - state.dragStart.y);
      }
    });

    window.addEventListener('mouseup', () => {
      state.isDragging = false;
      canvas.style.cursor = 'grab';
    });

    // Mouse wheel zoom
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
      state.camera.zoom = Math.max(0.1, Math.min(5, state.camera.zoom * zoomFactor));
    }, { passive: false });

    // Touch support
    let lastTouchDist = 0;
    canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        state.isDragging = true;
        state.dragStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        state.cameraStart = { x: state.camera.x, y: state.camera.y };
      } else if (e.touches.length === 2) {
        lastTouchDist = Math.sqrt(
          Math.pow(e.touches[0].clientX - e.touches[1].clientX, 2) +
          Math.pow(e.touches[0].clientY - e.touches[1].clientY, 2)
        );
      }
    });

    canvas.addEventListener('touchmove', (e) => {
      e.preventDefault();
      if (e.touches.length === 1 && state.isDragging) {
        state.camera.x = state.cameraStart.x + (e.touches[0].clientX - state.dragStart.x);
        state.camera.y = state.cameraStart.y + (e.touches[0].clientY - state.dragStart.y);
      } else if (e.touches.length === 2) {
        const dist = Math.sqrt(
          Math.pow(e.touches[0].clientX - e.touches[1].clientX, 2) +
          Math.pow(e.touches[0].clientY - e.touches[1].clientY, 2)
        );
        if (lastTouchDist > 0) {
          const zoomFactor = dist / lastTouchDist;
          state.camera.zoom = Math.max(0.1, Math.min(5, state.camera.zoom * zoomFactor));
        }
        lastTouchDist = dist;
      }
    }, { passive: false });

    canvas.addEventListener('touchend', () => {
      state.isDragging = false;
      lastTouchDist = 0;
    });

    // Search
    searchInput.addEventListener('input', (e) => {
      performSearch(e.target.value);
    });

    searchInput.addEventListener('focus', () => {
      if (searchInput.value) {
        performSearch(searchInput.value);
      }
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-box')) {
        searchResults.classList.remove('active');
      }
    });

    searchResults.addEventListener('click', (e) => {
      const item = e.target.closest('.search-result-item');
      if (item) {
        const type = item.dataset.type;
        if (type === 'sun') selectSun();
        else if (type === 'planet') selectPlanet(parseInt(item.dataset.index));
        else if (type === 'moon') selectMoon(parseInt(item.dataset.planet), parseInt(item.dataset.moon));
        searchResults.classList.remove('active');
        searchInput.value = '';
      }
    });

    // Controls
    document.getElementById('btn-labels').addEventListener('click', (e) => {
      state.showLabels = !state.showLabels;
      e.currentTarget.classList.toggle('active', state.showLabels);
    });

    document.getElementById('btn-orbits').addEventListener('click', (e) => {
      state.showOrbits = !state.showOrbits;
      e.currentTarget.classList.toggle('active', state.showOrbits);
    });

    document.getElementById('btn-pause').addEventListener('click', (e) => {
      state.isPaused = !state.isPaused;
      e.currentTarget.classList.toggle('active', state.isPaused);
      e.currentTarget.innerHTML = state.isPaused ? '&#9654; Play' : '&#9646;&#9646; Pause';
    });

    document.getElementById('btn-reset').addEventListener('click', resetCamera);

    document.getElementById('btn-focus-sun').addEventListener('click', selectSun);

    // Speed slider
    const speedSlider = document.getElementById('speed-slider');
    const speedValue = document.getElementById('speed-value');
    speedSlider.addEventListener('input', (e) => {
      state.speed = parseFloat(e.target.value);
      speedValue.textContent = state.speed.toFixed(1) + 'x';
    });

    // Keyboard
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        selectSun();
        searchInput.value = '';
        searchResults.classList.remove('active');
      } else if (e.key === ' ') {
        e.preventDefault();
        document.getElementById('btn-pause').click();
      } else if (e.key === 'r' || e.key === 'R') {
        resetCamera();
      } else if (e.key === 'l' || e.key === 'L') {
        document.getElementById('btn-labels').click();
      } else if (e.key === 'o' || e.key === 'O') {
        document.getElementById('btn-orbits').click();
      }
    });

    // Window resize
    window.addEventListener('resize', () => {
      resizeCanvas();
      generateStars();
    });
  }

  // Expose for onclick handlers
  window.selectMoon = selectMoon;

  // Start
  init();
})();
