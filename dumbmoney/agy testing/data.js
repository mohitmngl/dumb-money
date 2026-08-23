/**
 * Solar System Demo Data
 * Contains comprehensive educational facts about the Sun, planets, and moons.
 */
const SOLAR_SYSTEM_DATA = {
  sun: {
    id: "sun",
    name: "Sun",
    type: "Yellow Dwarf Star (G2V)",
    size: "1,392,700 km (Diameter)",
    orbit: "Center of the Solar System",
    features: "Solar flares, solar wind, thermonuclear core fusion",
    fact: "The Sun accounts for 99.86% of the mass in the entire Solar System and is approximately 4.6 billion years old.",
    color: { primary: "#ffcc00", secondary: "#ff3300", glow: "rgba(255, 102, 0, 0.6)" },
    hasRings: false,
    moons: []
  },
  mercury: {
    id: "mercury",
    name: "Mercury",
    type: "Terrestrial Planet",
    size: "4,879 km (Diameter)",
    orbit: "57.9 million km (0.39 AU) from Sun | Year: 88 Earth days",
    features: "Cratered surface, extreme temperature swings (-180°C to 430°C), negligible atmosphere",
    fact: "Despite being closest to the Sun, it is not the hottest planet—Venus is, due to its runaway greenhouse effect.",
    color: { primary: "#8a8d8f", secondary: "#505054", glow: "rgba(138, 141, 143, 0.3)" },
    hasRings: false,
    moons: [] // No confirmed natural moons
  },
  venus: {
    id: "venus",
    name: "Venus",
    type: "Terrestrial Planet",
    size: "12,104 km (Diameter)",
    orbit: "108.2 million km (0.72 AU) from Sun | Year: 225 Earth days",
    features: "Thick carbon dioxide atmosphere, acid clouds, runaway greenhouse effect, crushing surface pressure",
    fact: "Venus rotates backward on its axis (retrograde), meaning the Sun rises in the west and sets in the east.",
    color: { primary: "#e3bb76", secondary: "#a1743f", glow: "rgba(227, 187, 118, 0.3)" },
    hasRings: false,
    moons: [] // No confirmed natural moons
  },
  earth: {
    id: "earth",
    name: "Earth",
    type: "Terrestrial Planet",
    size: "12,742 km (Diameter)",
    orbit: "149.6 million km (1.0 AU) from Sun | Year: 365.25 days",
    features: "Liquid water oceans, active plate tectonics, life-supporting nitrogen-oxygen atmosphere",
    fact: "Earth is the only known planet in the universe to support life, and its atmosphere protects us from meteoroids and solar radiation.",
    color: { primary: "#2b82c9", secondary: "#165080", glow: "rgba(43, 130, 201, 0.4)" },
    hasRings: false,
    moons: [
      {
        id: "moon",
        name: "The Moon (Luna)",
        type: "Natural Satellite",
        size: "3,474 km (Diameter)",
        orbit: "384,400 km from Earth | Period: 27.3 Earth days",
        features: "Tidally locked (same side faces Earth), cratered highlands, dark volcanic plains (maria)",
        fact: "The Moon is drifting away from Earth at a rate of about 3.8 centimeters per year.",
        color: { primary: "#d3d3d3", secondary: "#808080", glow: "rgba(211, 211, 211, 0.25)" }
      }
    ]
  },
  mars: {
    id: "mars",
    name: "Mars",
    type: "Terrestrial Planet",
    size: "6,779 km (Diameter)",
    orbit: "227.9 million km (1.52 AU) from Sun | Year: 687 Earth days",
    features: "Iron oxide dust (red color), Olympus Mons (largest volcano), Valles Marineris canyon, polar ice caps",
    fact: "Mars is home to Olympus Mons, the tallest volcano in the solar system, which stands three times higher than Mount Everest.",
    color: { primary: "#c1440e", secondary: "#7b2605", glow: "rgba(193, 68, 14, 0.3)" },
    hasRings: false,
    moons: [
      {
        id: "phobos",
        name: "Phobos",
        type: "Natural Satellite",
        size: "22.2 km (Mean Diameter)",
        orbit: "9,377 km from Mars | Period: 7.7 hours",
        features: "Irregularly shaped, heavily cratered, decaying orbit, close proximity to Mars",
        fact: "Phobos orbits Mars faster than Mars rotates, rising in the west and setting in the east twice a day.",
        color: { primary: "#a89f91", secondary: "#6b645b", glow: "rgba(168, 159, 145, 0.2)" }
      },
      {
        id: "deimos",
        name: "Deimos",
        type: "Natural Satellite",
        size: "12.6 km (Mean Diameter)",
        orbit: "23,460 km from Mars | Period: 30.3 hours",
        features: "Smooth appearance due to thick dust fill (regolith), low escape velocity (5.6 m/s)",
        fact: "Deimos is one of the smallest known moons in the Solar System, and is likely a captured asteroid from the outer belt.",
        color: { primary: "#bcae9e", secondary: "#736b61", glow: "rgba(188, 174, 158, 0.2)" }
      }
    ]
  },
  jupiter: {
    id: "jupiter",
    name: "Jupiter",
    type: "Gas Giant",
    size: "139,820 km (Diameter)",
    orbit: "778.5 million km (5.20 AU) from Sun | Year: 12 Earth years",
    features: "Great Red Spot (a persistent storm), distinct atmospheric bands, powerful magnetic field",
    fact: "Jupiter is twice as massive as all other planets in our solar system combined, acting as a cosmic vacuum cleaner that deflects comets.",
    color: { primary: "#d8ca9d", secondary: "#a5753f", glow: "rgba(216, 202, 157, 0.3)" },
    hasRings: true,
    ringColor: "rgba(216, 202, 157, 0.15)",
    additionalMoonsText: "Jupiter has at least 95 confirmed moons in total, representing a vast satellite system.",
    moons: [
      {
        id: "io",
        name: "Io",
        type: "Galilean Moon",
        size: "3,643 km (Diameter)",
        orbit: "421,700 km from Jupiter | Period: 1.77 Earth days",
        features: "Over 400 active volcanoes, silicate rock crust, yellow-orange sulfurous surface",
        fact: "Io is the most volcanically active body in the Solar System due to gravitational tidal heating from Jupiter and sister moons.",
        color: { primary: "#e6e65c", secondary: "#cc9900", glow: "rgba(230, 230, 92, 0.3)" }
      },
      {
        id: "europa",
        name: "Europa",
        type: "Galilean Moon",
        size: "3,122 km (Diameter)",
        orbit: "670,900 km from Jupiter | Period: 3.55 Earth days",
        features: "Smooth water-ice crust, fractured lines (lineae), subsurface liquid saltwater ocean",
        fact: "Europa's subsurface ocean contains more than twice the liquid water of all of Earth's oceans combined, making it a primary target for astrobiology.",
        color: { primary: "#cce6ff", secondary: "#80b3ff", glow: "rgba(204, 230, 255, 0.3)" }
      },
      {
        id: "ganymede",
        name: "Ganymede",
        type: "Galilean Moon",
        size: "5,268 km (Diameter)",
        orbit: "1,070,400 km from Jupiter | Period: 7.15 Earth days",
        features: "Largest moon in solar system, internally generated magnetic field, silicate-ice crust",
        fact: "Ganymede is larger than the planet Mercury and is the only moon in the Solar System known to possess its own magnetic field.",
        color: { primary: "#afafb3", secondary: "#6a6a6e", glow: "rgba(175, 175, 179, 0.25)" }
      },
      {
        id: "callisto",
        name: "Callisto",
        type: "Galilean Moon",
        size: "4,821 km (Diameter)",
        orbit: "1,882,700 km from Jupiter | Period: 16.69 Earth days",
        features: "Ancient, heavily cratered ice-rock surface, rings of Valhalla crater",
        fact: "Callisto has the oldest and most heavily cratered surface in the Solar System, showing almost no signs of geological activity.",
        color: { primary: "#827f75", secondary: "#494741", glow: "rgba(130, 127, 117, 0.25)" }
      }
    ]
  },
  saturn: {
    id: "saturn",
    name: "Saturn",
    type: "Gas Giant",
    size: "116,460 km (Diameter)",
    orbit: "1.43 billion km (9.58 AU) from Sun | Year: 29 Earth years",
    features: "Spectacular rings made of water ice and rock, extremely low density (would float in water)",
    fact: "Saturn's rings are extremely wide (up to 282,000 km) but incredibly thin, averaging only about 10 meters in thickness.",
    color: { primary: "#ebd2b0", secondary: "#c4a37b", glow: "rgba(235, 210, 176, 0.3)" },
    hasRings: true,
    ringColor: "rgba(235, 210, 176, 0.35)",
    additionalMoonsText: "Saturn has 146 confirmed moons, the most of any planet in our solar system, with a diverse mix of sizes and shapes.",
    moons: [
      {
        id: "titan",
        name: "Titan",
        type: "Major Satellite",
        size: "5,149 km (Diameter)",
        orbit: "1,221,870 km from Saturn | Period: 15.95 Earth days",
        features: "Thick nitrogen atmosphere, liquid methane/ethane lakes, orange organic haze",
        fact: "Titan is the only known moon in the solar system with a dense atmosphere and the only body other than Earth with stable surface liquid bodies.",
        color: { primary: "#dfa745", secondary: "#9e6f24", glow: "rgba(223, 167, 69, 0.3)" }
      },
      {
        id: "enceladus",
        name: "Enceladus",
        type: "Major Satellite",
        size: "504 km (Diameter)",
        orbit: "238,020 km from Saturn | Period: 1.37 Earth days",
        features: "Active water geysers, tiger stripe fractures, global sub-surface ocean",
        fact: "The geysers at Enceladus's south pole spray water vapor, icy particles, and organic molecules, feeding Saturn's E-ring.",
        color: { primary: "#ffffff", secondary: "#d0d8df", glow: "rgba(255, 255, 255, 0.4)" }
      },
      {
        id: "mimas",
        name: "Mimas",
        type: "Major Satellite",
        size: "396 km (Diameter)",
        orbit: "185,520 km from Saturn | Period: 0.94 Earth days",
        features: "Herschel impact crater (130 km wide), icy composition, tidally locked",
        fact: "Mimas's Herschel crater is so large relative to the moon that it resembles the 'Death Star' from Star Wars.",
        color: { primary: "#b3b3b3", secondary: "#777777", glow: "rgba(179, 179, 179, 0.25)" }
      },
      {
        id: "rhea",
        name: "Rhea",
        type: "Major Satellite",
        size: "1,527 km (Diameter)",
        orbit: "527,040 km from Saturn | Period: 4.52 Earth days",
        features: "Heavily cratered surface, wispy fractures, extremely thin oxygen-CO2 exosphere",
        fact: "Rhea is Saturn's second-largest moon but contains only a tiny fraction of Titan's mass because it is composed mainly of ice.",
        color: { primary: "#cccccc", secondary: "#9c9c9c", glow: "rgba(204, 204, 204, 0.25)" }
      },
      {
        id: "iapetus",
        name: "Iapetus",
        type: "Major Satellite",
        size: "1,469 km (Diameter)",
        orbit: "3,561,300 km from Saturn | Period: 79.33 Earth days",
        features: "Two-toned coloration (one dark hemisphere, one bright), 20 km high equatorial ridge",
        fact: "Iapetus features an equatorial ridge that wraps halfway around the moon, giving it a walnut-like appearance.",
        color: { primary: "#d2c3b2", secondary: "#42382e", glow: "rgba(210, 195, 178, 0.3)" }
      },
      {
        id: "dione",
        name: "Dione",
        type: "Major Satellite",
        size: "1,123 km (Diameter)",
        orbit: "377,400 km from Saturn | Period: 2.74 Earth days",
        features: "Bright ice cliffs, heavily cratered hemisphere, shares orbit with trojan moons Helene and Polydeuces",
        fact: "Dione exhibits evidence of past geological activity, with huge tectonic fractures exposing sheer ice cliffs.",
        color: { primary: "#c0c0c0", secondary: "#808080", glow: "rgba(192, 192, 192, 0.25)" }
      },
      {
        id: "tethys",
        name: "Tethys",
        type: "Major Satellite",
        size: "1,062 km (Diameter)",
        orbit: "294,660 km from Saturn | Period: 1.89 Earth days",
        features: "Giant Odysseus impact crater, Ithaca Chasma (a rift valley 2,000 km long)",
        fact: "Tethys has a very low density because it consists almost entirely of pure water ice, with a tiny amount of rock.",
        color: { primary: "#dedede", secondary: "#aaaaaa", glow: "rgba(222, 222, 222, 0.25)" }
      }
    ]
  },
  uranus: {
    id: "uranus",
    name: "Uranus",
    type: "Ice Giant",
    size: "50,724 km (Diameter)",
    orbit: "2.87 billion km (19.18 AU) from Sun | Year: 84 Earth years",
    features: "Extreme axial tilt (97.8 degrees), pale cyan-blue color, 13 faint rings",
    fact: "Uranus rotates virtually on its side, meaning its poles experience 21 years of continuous sunlight followed by 21 years of darkness.",
    color: { primary: "#b3f0ff", secondary: "#52c4db", glow: "rgba(179, 240, 255, 0.3)" },
    hasRings: true,
    ringColor: "rgba(179, 240, 255, 0.25)",
    additionalMoonsText: "Uranus has 28 confirmed moons, named after characters from the works of William Shakespeare and Alexander Pope.",
    moons: [
      {
        id: "titania",
        name: "Titania",
        type: "Major Satellite",
        size: "1,578 km (Diameter)",
        orbit: "435,900 km from Uranus | Period: 8.71 Earth days",
        features: "Largest moon of Uranus, canyons, fault scarps, mixture of ice and rock",
        fact: "Titania's surface is scored by an array of massive fault valleys, some reaching depths of up to 5 kilometers.",
        color: { primary: "#bfbdb8", secondary: "#807e7a", glow: "rgba(191, 189, 184, 0.2)" }
      },
      {
        id: "oberon",
        name: "Oberon",
        type: "Major Satellite",
        size: "1,523 km (Diameter)",
        orbit: "583,500 km from Uranus | Period: 13.46 Earth days",
        features: "Outermost major moon, ancient cratered terrain, dark spots on crater floors",
        fact: "Oberon is the second-largest moon of Uranus and has a surface that shows almost no signs of internal geological activity since its formation.",
        color: { primary: "#a39f96", secondary: "#6b6963", glow: "rgba(163, 159, 150, 0.2)" }
      },
      {
        id: "umbriel",
        name: "Umbriel",
        type: "Major Satellite",
        size: "1,169 km (Diameter)",
        orbit: "266,000 km from Uranus | Period: 4.14 Earth days",
        features: "Darkest of the major Uranian moons, prominent bright crater (Wunda) at pole",
        fact: "Umbriel's dark color is likely due to the accumulation of carbon-rich organic compounds on its surface.",
        color: { primary: "#7d7b77", secondary: "#4f4e4c", glow: "rgba(125, 123, 119, 0.2)" }
      },
      {
        id: "ariel",
        name: "Ariel",
        type: "Major Satellite",
        size: "1,158 km (Diameter)",
        orbit: "191,000 km from Uranus | Period: 2.52 Earth days",
        features: "Brightest Uranian moon, intersecting grabens (rift valleys), cryovolcanic deposits",
        fact: "Ariel shows the most recent signs of cryovolcanism (volcanoes spewing water-ammonia mixtures rather than lava) among Uranus's moons.",
        color: { primary: "#dbd8d0", secondary: "#9e9a90", glow: "rgba(219, 216, 208, 0.2)" }
      },
      {
        id: "miranda",
        name: "Miranda",
        type: "Major Satellite",
        size: "472 km (Diameter)",
        orbit: "129,000 km from Uranus | Period: 1.41 Earth days",
        features: "Extreme scrambled topography, giant grooved rings (coronae), Verona Rupes cliff",
        fact: "Miranda features Verona Rupes, a cliff estimated to be 20 km tall, which is the tallest known cliff in the Solar System.",
        color: { primary: "#d2d2d6", secondary: "#8c8c94", glow: "rgba(210, 210, 214, 0.2)" }
      }
    ]
  },
  neptune: {
    id: "neptune",
    name: "Neptune",
    type: "Ice Giant",
    size: "49,244 km (Diameter)",
    orbit: "4.50 billion km (30.07 AU) from Sun | Year: 165 Earth years",
    features: "Deep blue color, supersonic winds (up to 2,100 km/h), dynamic storm structures",
    fact: "Neptune is the only planet in the Solar System whose existence was mathematically calculated and predicted before it was actually seen.",
    color: { primary: "#3366ff", secondary: "#1a3399", glow: "rgba(51, 102, 255, 0.4)" },
    hasRings: true,
    ringColor: "rgba(51, 102, 255, 0.25)",
    additionalMoonsText: "Neptune has 16 confirmed moons, named after minor water deities in Greek and Roman mythology.",
    moons: [
      {
        id: "triton",
        name: "Triton",
        type: "Major Satellite",
        size: "2,707 km (Diameter)",
        orbit: "354,760 km from Neptune | Period: -5.88 Earth days (Retrograde)",
        features: "Retrograde orbit (backward), active liquid nitrogen geysers, cantaloupe-like terrain",
        fact: "Triton is the only massive moon in the solar system that orbits in the opposite direction of its planet's rotation, indicating it was captured from the Kuiper Belt.",
        color: { primary: "#e8ecef", secondary: "#adb7bd", glow: "rgba(232, 236, 239, 0.3)" }
      },
      {
        id: "nereid",
        name: "Nereid",
        type: "Major Satellite",
        size: "340 km (Diameter)",
        orbit: "5,513,400 km from Neptune | Period: 360.1 Earth days",
        features: "Extreme eccentric orbit (highly elongated), irregular rocky surface",
        fact: "Nereid's orbital eccentricity is one of the highest in the solar system, causing its distance from Neptune to vary by over 8 million kilometers.",
        color: { primary: "#c0c6c9", secondary: "#7d8487", glow: "rgba(192, 198, 201, 0.2)" }
      },
      {
        id: "proteus",
        name: "Proteus",
        type: "Major Satellite",
        size: "420 km (Diameter)",
        orbit: "117,640 km from Neptune | Period: 1.12 Earth days",
        features: "Highly irregular boxy shape, heavily cratered surface, low-reflectivity carbonaceous material",
        fact: "Proteus is Neptune's second largest moon but was only discovered in 1989 by Voyager 2 because it is extremely dark and orbits close to the planet.",
        color: { primary: "#737578", secondary: "#434547", glow: "rgba(115, 117, 120, 0.2)" }
      },
      {
        id: "larissa",
        name: "Larissa",
        type: "Inner Moon",
        size: "194 km (Mean Diameter)",
        orbit: "73,550 km from Neptune | Period: 0.55 Earth days",
        features: "Irregular shape, cratered terrain, orbits close to Neptune's ring system",
        fact: "Larissa is slowly spiraling inward due to tidal forces and will eventually either collide with Neptune or break apart to form a new ring.",
        color: { primary: "#8c9094", secondary: "#525559", glow: "rgba(140, 144, 148, 0.2)" }
      },
      {
        id: "galatea",
        name: "Galatea",
        type: "Inner Moon",
        size: "176 km (Mean Diameter)",
        orbit: "61,950 km from Neptune | Period: 0.43 Earth days",
        features: "Irregular shape, serves as a shepherd moon stabilizing the Adams ring arcs",
        fact: "Galatea's gravity creates radial perturbations (waves) in the Adams ring, preventing the ring particles from dispersing.",
        color: { primary: "#919599", secondary: "#585a5e", glow: "rgba(145, 149, 153, 0.2)" }
      },
      {
        id: "despina",
        name: "Despina",
        type: "Inner Moon",
        size: "150 km (Mean Diameter)",
        orbit: "52,530 km from Neptune | Period: 0.33 Earth days",
        features: "Irregular shape, orbits inside the Le Verrier ring, shepherd moon",
        fact: "Despina orbits well inside Neptune's fluid Roche limit, meaning it is only held together by its internal material strength.",
        color: { primary: "#9ca0a3", secondary: "#606366", glow: "rgba(156, 160, 163, 0.2)" }
      },
      {
        id: "thalassa",
        name: "Thalassa",
        type: "Inner Moon",
        size: "82 km (Mean Diameter)",
        orbit: "50,075 km from Neptune | Period: 0.31 Earth days",
        features: "Disc-shaped or elongated body, orbits close to the rings",
        fact: "Thalassa orbits in a complex gravitational resonance with Naiad, keeping their orbits separated in a 'dance of avoidance'.",
        color: { primary: "#8f9396", secondary: "#585a5c", glow: "rgba(143, 147, 150, 0.2)" }
      },
      {
        id: "naiad",
        name: "Naiad",
        type: "Inner Moon",
        size: "66 km (Mean Diameter)",
        orbit: "48,227 km from Neptune | Period: 0.29 Earth days",
        features: "Highly elongated shape, closest moon to Neptune's cloud tops",
        fact: "Naiad completes an orbit around Neptune in just 7 hours and 6 minutes, moving exceptionally fast across the Neptunian sky.",
        color: { primary: "#86898c", secondary: "#515354", glow: "rgba(134, 137, 140, 0.2)" }
      }
    ]
  }
};
