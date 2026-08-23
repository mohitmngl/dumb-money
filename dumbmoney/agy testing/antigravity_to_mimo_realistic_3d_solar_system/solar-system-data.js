// Solar System Data
const SOLAR_SYSTEM_DATA = {
  sun: {
    name: "Sun",
    type: "Star",
    diameter: "1,391,000 km",
    orbit: "N/A (Center of Solar System)",
    features: "Composed primarily of hydrogen and helium; contains 99.86% of the solar system's mass",
    funFact: "The Sun's core temperature is about 15 million degrees Celsius - hot enough to fuse hydrogen into helium",
    color: 0xffd700,
    size: 5,
    position: [0, 0, 0],
    moons: []
  },
  mercury: {
    name: "Mercury",
    type: "Terrestrial Planet",
    diameter: "4,879 km",
    orbit: "Orbits Sun at ~57.9 million km (0.39 AU)",
    features: "Smallest planet, heavily cratered surface, extreme temperature swings (-180°C to 430°C)",
    funFact: "Mercury has no atmosphere and no confirmed natural moons",
    color: 0x8c7e6d,
    size: 0.4,
    position: [10, 0, 0],
    moons: []
  },
  venus: {
    name: "Venus",
    type: "Terrestrial Planet",
    diameter: "12,104 km",
    orbit: "Orbits Sun at ~108.2 million km (0.72 AU)",
    features: "Thick toxic atmosphere, hottest planet (465°C), rotates backwards (retrograde)",
    funFact: "Venus has no confirmed natural moons despite being similar in size to Earth",
    color: 0xe6c299,
    size: 0.9,
    position: [18, 0, 0],
    moons: []
  },
  earth: {
    name: "Earth",
    type: "Terrestrial Planet",
    diameter: "12,756 km",
    orbit: "Orbits Sun at ~149.6 million km (1.00 AU)",
    features: "Only known planet with liquid water on surface, protective magnetic field, nitrogen-oxygen atmosphere",
    funFact: "Earth is the only planet not named after a Greek or Roman god",
    color: 0x4a90d9,
    size: 1.0,
    position: [26, 0, 0],
    moons: [
      {
        name: "Moon",
        diameter: "3,474 km",
        orbit: "Orbits Earth at ~384,400 km",
        features: "Tidally locked to Earth, no atmosphere, covered in craters and maria (dark basaltic plains)",
        funFact: "The Moon is slowly drifting away from Earth at about 3.8 cm per year",
        color: 0xc8c8c8,
        size: 0.25,
        position: [26, 2, 0]
      }
    ]
  },
  mars: {
    name: "Mars",
    type: "Terrestrial Planet",
    diameter: "6,792 km",
    orbit: "Orbits Sun at ~227.9 million km (1.52 AU)",
    features: "Red appearance from iron oxide, thin CO₂ atmosphere, Olympus Mons (tallest volcano), Valles Marineris (largest canyon)",
    funFact: "Mars has two small moons named after the Greek gods of fear and dread",
    color: 0xc1440e,
    size: 0.6,
    position: [36, 0, 0],
    moons: [
      {
        name: "Phobos",
        diameter: "22.4 km",
        orbit: "Orbits Mars at ~9,376 km",
        features: "Irregular shape, heavily cratered, orbit decaying - will crash into Mars or break apart in ~50 million years",
        funFact: "Phobos orbits Mars faster than Mars rotates - it rises in the west and sets in the east",
        color: 0x8b7355,
        size: 0.1,
        position: [36, 1.2, 0]
      },
      {
        name: "Deimos",
        diameter: "12.4 km",
        orbit: "Orbits Mars at ~23,463 km",
        features: "Smaller and smoother than Phobos, irregular shape, darker surface",
        funFact: "Deimos is slowly moving away from Mars and will eventually escape its orbit",
        color: 0x7a6b5a,
        size: 0.08,
        position: [36, 1.8, 0]
      }
    ]
  },
  jupiter: {
    name: "Jupiter",
    type: "Gas Giant",
    diameter: "142,984 km",
    orbit: "Orbits Sun at ~778.5 million km (5.20 AU)",
    features: "Largest planet, Great Red Spot (persistent storm), 79+ known moons, strong magnetic field",
    funFact: "Jupiter's Great Red Spot is shrinking - it was once 3 times the size of Earth",
    color: 0xc88b3a,
    size: 2.5,
    position: [52, 0, 0],
    moons: [
      {
        name: "Io",
        diameter: "3,643 km",
        orbit: "Orbits Jupiter at ~421,700 km",
        features: "Most volcanically active body in solar system, over 400 active volcanoes, sulfur-rich surface",
        funFact: "Io's volcanoes erupt so powerfully that it has created a dust ring around Jupiter",
        color: 0xf5deb3,
        size: 0.15,
        position: [52, 3.5, 0]
      },
      {
        name: "Europa",
        diameter: "3,122 km",
        orbit: "Orbits Jupiter at ~671,034 km",
        features: "Smooth icy surface, possible subsurface ocean, may have conditions suitable for life",
        funFact: "Europa's ocean may contain twice as much water as all of Earth's oceans combined",
        color: 0xf0f0f0,
        size: 0.14,
        position: [52, 4.0, 0]
      },
      {
        name: "Ganymede",
        diameter: "5,268 km",
        orbit: "Orbits Jupiter at ~1,070,412 km",
        features: "Largest moon in solar system, has its own magnetic field, mixed ice and rock surface",
        funFact: "Ganymede is larger than the planet Mercury",
        color: 0xb8a88a,
        size: 0.2,
        position: [52, 4.5, 0]
      },
      {
        name: "Callisto",
        diameter: "4,821 km",
        orbit: "Orbits Jupiter at ~1,882,709 km",
        features: "Heavily cratered, ancient surface, thin CO₂ atmosphere, possible subsurface ocean",
        funFact: "Callisto has the most cratered surface of any body in the solar system",
        color: 0x696969,
        size: 0.18,
        position: [52, 5.0, 0]
      }
    ]
  },
  saturn: {
    name: "Saturn",
    type: "Gas Giant",
    diameter: "120,536 km",
    orbit: "Orbits Sun at ~1,432 million km (9.58 AU)",
    features: "Spectacular ring system, lowest density of any planet, 82+ known moons, fast rotation",
    funFact: "Saturn's rings are made mostly of ice particles ranging from tiny grains to house-sized chunks",
    color: 0xe8d5a3,
    size: 2.2,
    position: [72, 0, 0],
    moons: [
      {
        name: "Titan",
        diameter: "5,150 km",
        orbit: "Orbits Saturn at ~1,221,870 km",
        features: "Thick nitrogen atmosphere, methane lakes and rivers, second largest moon in solar system",
        funFact: "Titan is the only moon with a dense atmosphere and liquid on its surface",
        color: 0xe8c36e,
        size: 0.2,
        position: [72, 3.5, 0]
      },
      {
        name: "Enceladus",
        diameter: "504 km",
        orbit: "Orbits Saturn at ~237,948 km",
        features: "Ice-covered, geysers erupting water vapor from south pole, subsurface ocean",
        funFact: "Enceladus shoots geysers of water into space that feed Saturn's E ring",
        color: 0xf5f5f5,
        size: 0.08,
        position: [72, 4.0, 0]
      },
      {
        name: "Mimas",
        diameter: "396 km",
        orbit: "Orbits Saturn at ~185,404 km",
        features: "Heavily cratered, enormous Herschel Crater gives it Death Star appearance",
        funFact: "Mimas looks like the Death Star from Star Wars due to its giant impact crater",
        color: 0xb8b8b8,
        size: 0.07,
        position: [72, 4.5, 0]
      },
      {
        name: "Rhea",
        diameter: "1,528 km",
        orbit: "Orbits Saturn at ~527,108 km",
        features: "Second largest moon of Saturn, heavily cratered ice surface, possible thin atmosphere",
        funFact: "Rhea may have a ring system of its own - the first moon discovered with rings",
        color: 0xc8c8c8,
        size: 0.1,
        position: [72, 5.0, 0]
      },
      {
        name: "Iapetus",
        diameter: "1,469 km",
        orbit: "Orbits Saturn at ~3,560,820 km",
        features: "Two-toned appearance (one hemisphere dark, one bright), prominent equatorial ridge",
        funFact: "Iapetus has a mysterious ridge around its equator up to 20 km tall",
        color: 0xd4c4a8,
        size: 0.09,
        position: [72, 5.5, 0]
      },
      {
        name: "Dione",
        diameter: "1,123 km",
        orbit: "Orbits Saturn at ~377,396 km",
        features: "Ice surface with bright cliffs and canyons, possible subsurface ocean",
        funFact: "Dione's wispy terrain consists of bright ice cliffs up to hundreds of meters tall",
        color: 0xe0e0e0,
        size: 0.08,
        position: [72, 6.0, 0]
      },
      {
        name: "Tethys",
        diameter: "1,062 km",
        orbit: "Orbits Saturn at ~294,664 km",
        features: "Dominant feature is huge Odysseus crater, composed almost entirely of water ice",
        funFact: "Tethys is the most lightly cratered of Saturn's large moons",
        color: 0xd8d8d8,
        size: 0.07,
        position: [72, 6.5, 0]
      }
    ]
  },
  uranus: {
    name: "Uranus",
    type: "Ice Giant",
    diameter: "51,118 km",
    orbit: "Orbits Sun at ~2,867 million km (19.22 AU)",
    features: "Rotates on its side (98° tilt), pale blue-green color from methane, 27+ known moons, faint rings",
    funFact: "Uranus rotates on its side, likely due to a collision with an Earth-sized object long ago",
    color: 0x73c2c9,
    size: 1.5,
    position: [96, 0, 0],
    moons: [
      {
        name: "Titania",
        diameter: "1,578 km",
        orbit: "Orbits Uranus at ~435,910 km",
        features: "Largest moon of Uranus, icy surface with canyons and possible subsurface ocean",
        funFact: "Titania has canyons up to 10 times deeper than the Grand Canyon",
        color: 0xb0b0b0,
        size: 0.12,
        position: [96, 2.5, 0]
      },
      {
        name: "Oberon",
        diameter: "1,523 km",
        orbit: "Orbits Uranus at ~583,520 km",
        features: "Outermost major moon, heavily cratered, dark reddish surface material",
        funFact: "Oberon may have a subsurface ocean beneath its icy crust",
        color: 0xa0a0a0,
        size: 0.11,
        position: [96, 3.0, 0]
      },
      {
        name: "Umbriel",
        diameter: "1,169 km",
        orbit: "Orbits Uranus at ~266,000 km",
        features: "Darkest of Uranus's major moons, heavily cratered, mysterious bright rings in Wunda crater",
        funFact: "Umbriel is the darkest and least studied of Uranus's five major moons",
        color: 0x696969,
        size: 0.09,
        position: [96, 3.5, 0]
      },
      {
        name: "Ariel",
        diameter: "1,158 km",
        orbit: "Orbits Uranus at ~190,900 km",
        features: "Brightest of Uranus's moons, extensive canyon systems, evidence of past geologic activity",
        funFact: "Ariel has the youngest and brightest surface of all Uranian moons",
        color: 0xc0c0c0,
        size: 0.09,
        position: [96, 4.0, 0]
      },
      {
        name: "Miranda",
        diameter: "472 km",
        orbit: "Orbits Uranus at ~129,390 km",
        features: "Smallest of five major moons, dramatic cliff called Verona Rupes (20 km high)",
        funFact: "Verona Rupes on Miranda is the tallest known cliff in the solar system",
        color: 0xb0b0b0,
        size: 0.07,
        position: [96, 4.5, 0]
      }
    ]
  },
  neptune: {
    name: "Neptune",
    type: "Ice Giant",
    diameter: "49,528 km",
    orbit: "Orbits Sun at ~4,515 million km (30.07 AU)",
    features: "Deep blue color from methane, fastest winds in solar system (2,100 km/h), 16+ known moons",
    funFact: "Neptune was the first planet found through mathematical prediction rather than observation",
    color: 0x4169e1,
    size: 1.4,
    position: [120, 0, 0],
    moons: [
      {
        name: "Triton",
        diameter: "2,707 km",
        orbit: "Orbits Neptune at ~354,759 km",
        features: "Largest Neptune moon, retrograde orbit (captured Kuiper Belt object), nitrogen geysers",
        funFact: "Triton is slowly spiraling inward and will be torn apart by Neptune's gravity in ~3.6 billion years",
        color: 0xc8d8c0,
        size: 0.15,
        position: [120, 2.5, 0]
      },
      {
        name: "Nereid",
        diameter: "340 km",
        orbit: "Orbits Neptune at ~5,513,818 km",
        features: "Second largest moon, highly eccentric orbit, possibly captured object",
        funFact: "Nereid has the most eccentric orbit of any known moon in the solar system",
        color: 0x999999,
        size: 0.06,
        position: [120, 3.0, 0]
      },
      {
        name: "Proteus",
        diameter: "420 km",
        orbit: "Orbits Neptune at ~117,647 km",
        features: "Second largest inner moon, irregular shape, too small for gravity to make it round",
        funFact: "Proteus is so dark it reflects only 6% of the sunlight that hits it",
        color: 0x666666,
        size: 0.07,
        position: [120, 3.5, 0]
      },
      {
        name: "Larissa",
        diameter: "194 km",
        orbit: "Orbits Neptune at ~73,548 km",
        features: "Irregular shape, heavily cratered, part of Neptune's inner moon group",
        funFact: "Larissa was originally discovered during a stellar occultation in 1981",
        color: 0x888888,
        size: 0.05,
        position: [120, 4.0, 0]
      },
      {
        name: "Galatea",
        diameter: "176 km",
        orbit: "Orbits Neptune at ~61,953 km",
        features: "Dusty ring arcs maintained by Galatea's gravity, irregular shape",
        funFact: "Galatea helps maintain Neptune's inner ring arcs through gravitational resonance",
        color: 0x909090,
        size: 0.04,
        position: [120, 4.5, 0]
      },
      {
        name: "Despina",
        diameter: "150 km",
        orbit: "Orbits Neptune at ~52,526 km",
        features: "Inner moon, irregular shape, close to Neptune's ring system",
        funFact: "Despina orbits inside Neptune's Roche limit and may eventually break apart to form a ring",
        color: 0x808080,
        size: 0.04,
        position: [120, 5.0, 0]
      },
      {
        name: "Thalassa",
        diameter: "80 km",
        orbit: "Orbits Neptune at ~50,074 km",
        features: "Very small inner moon, irregular shape, likely formed from debris of an earlier moon",
        funFact: "Thalassa's name comes from the primordial Greek goddess of the sea",
        color: 0x707070,
        size: 0.03,
        position: [120, 5.5, 0]
      },
      {
        name: "Naiad",
        diameter: "58 km",
        orbit: "Orbits Neptune at ~48,227 km",
        features: "Innermost known moon of Neptune, closest to the planet",
        funFact: "Naiad is in a unique orbital resonance with Thalassa that keeps them from colliding",
        color: 0x606060,
        size: 0.02,
        position: [120, 6.0, 0]
      }
    ]
  }
};

export default SOLAR_SYSTEM_DATA;
