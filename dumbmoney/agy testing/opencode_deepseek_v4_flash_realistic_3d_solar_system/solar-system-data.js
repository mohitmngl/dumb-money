export const solarSystemData = {
  sun: {
    id: 'sun',
    name: 'Sun',
    type: 'Star (G-type main-sequence)',
    diameter: '1,391,000 km',
    orbitInfo: 'Center of the Solar System',
    features: [
      'Contains 99.86% of the Solar System\'s mass',
      'Surface temperature ~5,500°C',
      'Converts hydrogen to helium via nuclear fusion',
      'Classified as a yellow dwarf star'
    ],
    fact: 'About 1.3 million Earths could fit inside the Sun. It takes 8 minutes and 20 seconds for sunlight to reach Earth.',
    size: 5,
    color: 0xffdd44,
    emissive: 0xffaa00
  },
  planets: [
    {
      id: 'mercury',
      name: 'Mercury',
      type: 'Terrestrial Planet',
      diameter: '4,879 km',
      orbitDistance: '57.9 million km (0.39 AU)',
      orbitalPeriod: '87.97 Earth days',
      features: [
        'Smallest planet in the Solar System',
        'Heavily cratered surface resembling our Moon',
        'Extreme temperature swings: -180°C to 430°C',
        'Has a weak magnetic field'
      ],
      fact: 'A year on Mercury is just 88 Earth days, but a day (sunrise to sunrise) lasts 176 Earth days.',
      size: 0.5,
      orbitRadius: 10,
      orbitalSpeed: 1.5,
      rotationSpeed: 0.005,
      tilt: 0.03,
      color: 0xb5b5b5,
      moons: [],
      moonNote: 'Mercury has no confirmed natural moons.'
    },
    {
      id: 'venus',
      name: 'Venus',
      type: 'Terrestrial Planet',
      diameter: '12,104 km',
      orbitDistance: '108.2 million km (0.72 AU)',
      orbitalPeriod: '224.7 Earth days',
      features: [
        'Hottest planet in the Solar System (462°C average)',
        'Spins backwards (retrograde rotation)',
        'Thick toxic atmosphere of carbon dioxide',
        'Similar size and mass to Earth — sometimes called Earth\'s twin'
      ],
      fact: 'A day on Venus (243 Earth days) is longer than a year on Venus (225 Earth days).',
      size: 0.85,
      orbitRadius: 15,
      orbitalSpeed: 1.1,
      rotationSpeed: 0.003,
      tilt: 2.64,
      color: 0xe8c870,
      moons: [],
      moonNote: 'Venus has no confirmed natural moons.'
    },
    {
      id: 'earth',
      name: 'Earth',
      type: 'Terrestrial Planet',
      diameter: '12,756 km',
      orbitDistance: '149.6 million km (1.00 AU)',
      orbitalPeriod: '365.25 days',
      features: [
        'Only known planet to support life',
        '71% of surface covered by water',
        'Has a protective magnetic field',
        'Atmosphere is 78% nitrogen, 21% oxygen'
      ],
      fact: 'Earth is the only planet not named after a Greek or Roman god.',
      size: 0.9,
      orbitRadius: 20,
      orbitalSpeed: 0.9,
      rotationSpeed: 0.02,
      tilt: 0.41,
      color: 0x4488ff,
      moons: [
        {
          id: 'moon',
          name: 'The Moon',
          type: 'Natural Satellite',
          diameter: '3,474 km',
          features: [
            'Fifth largest moon in the Solar System',
            'Responsible for Earth\'s tides',
            'Always shows the same face to Earth (tidal locking)'
          ],
          fact: 'The Moon is moving away from Earth at about 3.8 cm per year.',
          orbitRadius: 2.5,
          orbitalSpeed: 5.0,
          size: 0.25,
          color: 0xcccccc
        }
      ]
    },
    {
      id: 'mars',
      name: 'Mars',
      type: 'Terrestrial Planet',
      diameter: '6,792 km',
      orbitDistance: '227.9 million km (1.52 AU)',
      orbitalPeriod: '687 Earth days',
      features: [
        'Known as the Red Planet due to iron oxide (rust)',
        'Home to the tallest mountain in the Solar System — Olympus Mons (21.9 km)',
        'Has the largest canyon — Valles Marineris (4,000 km long)',
        'Evidence suggests liquid water once flowed on the surface'
      ],
      fact: 'A day on Mars (a sol) is only 39 minutes longer than an Earth day.',
      size: 0.65,
      orbitRadius: 25,
      orbitalSpeed: 0.7,
      rotationSpeed: 0.019,
      tilt: 0.44,
      color: 0xc1440e,
      moons: [
        {
          id: 'phobos',
          name: 'Phobos',
          type: 'Natural Satellite',
          diameter: '22.4 km',
          features: [
            'Larger of Mars\' two moons',
            'Heavily cratered and irregularly shaped',
            'Orbits Mars very close — only 6,000 km above the surface'
          ],
          fact: 'Phobos is slowly spiraling inward and will either crash into Mars or break apart in about 50 million years.',
          orbitRadius: 1.8,
          orbitalSpeed: 8.0,
          size: 0.08,
          color: 0xaa8866
        },
        {
          id: 'deimos',
          name: 'Deimos',
          type: 'Natural Satellite',
          diameter: '12.4 km',
          features: [
            'Smaller of Mars\' two moons',
            'Irregularly shaped and less cratered than Phobos',
            'May be a captured asteroid'
          ],
          fact: 'Deimos is slowly moving away from Mars and will eventually escape its gravity.',
          orbitRadius: 2.6,
          orbitalSpeed: 5.0,
          size: 0.06,
          color: 0xbb9988
        }
      ]
    },
    {
      id: 'jupiter',
      name: 'Jupiter',
      type: 'Gas Giant',
      diameter: '142,984 km',
      orbitDistance: '778.5 million km (5.20 AU)',
      orbitalPeriod: '11.86 Earth years',
      features: [
        'Largest planet in the Solar System',
        'Famous for the Great Red Spot — a storm larger than Earth',
        'Has at least 95 known moons',
        'Composed mainly of hydrogen and helium'
      ],
      fact: 'Jupiter\'s Great Red Spot has been raging for at least 400 years and is larger than Earth.',
      size: 2.5,
      orbitRadius: 35,
      orbitalSpeed: 0.4,
      rotationSpeed: 0.04,
      tilt: 0.05,
      color: 0xd4a574,
      moons: [
        {
          id: 'io',
          name: 'Io',
          type: 'Natural Satellite',
          diameter: '3,643 km',
          features: [
            'Most volcanically active body in the Solar System',
            'Surface covered in sulfur compounds giving it a yellow/orange appearance',
            'Tidally heated by Jupiter\'s immense gravity'
          ],
          fact: 'Io\'s volcanoes can eject material up to 500 km above the surface.',
          orbitRadius: 2.0,
          orbitalSpeed: 12.0,
          size: 0.18,
          color: 0xeebb55
        },
        {
          id: 'europa',
          name: 'Europa',
          type: 'Natural Satellite',
          diameter: '3,122 km',
          features: [
            'Smooth, icy surface crisscrossed with cracks',
            'Believed to harbor a subsurface liquid water ocean',
            'Considered one of the best places to search for extraterrestrial life'
          ],
          fact: 'Europa\'s subsurface ocean may contain twice as much water as all of Earth\'s oceans combined.',
          orbitRadius: 3.2,
          orbitalSpeed: 8.0,
          size: 0.16,
          color: 0xccddff
        },
        {
          id: 'ganymede',
          name: 'Ganymede',
          type: 'Natural Satellite',
          diameter: '5,268 km',
          features: [
            'Largest moon in the Solar System (larger than Mercury)',
            'Has its own magnetic field',
            'Composed of silicate rock and water ice'
          ],
          fact: 'Ganymede is the only moon known to have its own internally generated magnetic field.',
          orbitRadius: 4.5,
          orbitalSpeed: 5.0,
          size: 0.22,
          color: 0xbbaa99
        },
        {
          id: 'callisto',
          name: 'Callisto',
          type: 'Natural Satellite',
          diameter: '4,821 km',
          features: [
            'Third largest moon in the Solar System',
            'Heavily cratered ancient surface',
            'May have a subsurface ocean'
          ],
          fact: 'Callisto is the most heavily cratered object in the Solar System.',
          orbitRadius: 6.0,
          orbitalSpeed: 3.5,
          size: 0.2,
          color: 0x887766
        }
      ],
      moonNote: 'Jupiter has many additional known moons — at least 95 discovered so far.'
    },
    {
      id: 'saturn',
      name: 'Saturn',
      type: 'Gas Giant',
      diameter: '120,536 km',
      orbitDistance: '1.43 billion km (9.54 AU)',
      orbitalPeriod: '29.46 Earth years',
      features: [
        'Famous for its spectacular ring system',
        'Least dense planet — would float in water if a bathtub were big enough',
        'Has at least 146 known moons',
        'Composed mainly of hydrogen and helium'
      ],
      fact: 'Saturn\'s rings are made of billions of ice and rock particles, some as small as dust and others as large as mountains.',
      size: 2.0,
      orbitRadius: 45,
      orbitalSpeed: 0.3,
      rotationSpeed: 0.038,
      tilt: 0.47,
      color: 0xead6a6,
      hasRings: true,
      moons: [
        {
          id: 'titan',
          name: 'Titan',
          type: 'Natural Satellite',
          diameter: '5,150 km',
          features: [
            'Second largest moon in the Solar System',
            'Has a thick atmosphere (mostly nitrogen)',
            'Has liquid methane lakes and rivers on its surface'
          ],
          fact: 'Titan is the only moon in the Solar System with a substantial atmosphere.',
          orbitRadius: 3.5,
          orbitalSpeed: 3.5,
          size: 0.22,
          color: 0xddbb77
        },
        {
          id: 'enceladus',
          name: 'Enceladus',
          type: 'Natural Satellite',
          diameter: '504 km',
          features: [
            'Icy surface with massive water vapor plumes at the south pole',
            'Has a subsurface global ocean',
            'One of the brightest objects in the Solar System'
          ],
          fact: 'Enceladus\'s icy plumes shoot water hundreds of kilometers into space.',
          orbitRadius: 2.0,
          orbitalSpeed: 6.0,
          size: 0.08,
          color: 0xeeeeff
        },
        {
          id: 'mimas',
          name: 'Mimas',
          type: 'Natural Satellite',
          diameter: '396 km',
          features: [
            'Heavily cratered with a huge impact crater called Herschel',
            'Resembles the Death Star from Star Wars due to its large crater'
          ],
          fact: 'The Herschel crater on Mimas is 130 km wide — one third of the moon\'s diameter.',
          orbitRadius: 1.5,
          orbitalSpeed: 8.0,
          size: 0.07,
          color: 0xcccccc
        },
        {
          id: 'rhea',
          name: 'Rhea',
          type: 'Natural Satellite',
          diameter: '1,527 km',
          features: [
            'Second largest moon of Saturn',
            'Composed mostly of water ice',
            'Has a tenuous atmosphere of oxygen and carbon dioxide'
          ],
          fact: 'Rhea may have its own faint ring system — the first known rings around a moon.',
          orbitRadius: 2.8,
          orbitalSpeed: 4.5,
          size: 0.12,
          color: 0xccccaa
        },
        {
          id: 'iapetus',
          name: 'Iapetus',
          type: 'Natural Satellite',
          diameter: '1,469 km',
          features: [
            'Two-tone coloration — one side dark, the other bright',
            'Has a prominent equatorial ridge'
          ],
          fact: 'Iapetus looks like a walnut due to its equatorial ridge that rises up to 20 km high.',
          orbitRadius: 4.2,
          orbitalSpeed: 2.5,
          size: 0.11,
          color: 0xaa9966
        },
        {
          id: 'dione',
          name: 'Dione',
          type: 'Natural Satellite',
          diameter: '1,123 km',
          features: [
            'Composed mostly of water ice',
            'Has bright ice cliffs and dark terrain',
            'May have a subsurface ocean'
          ],
          fact: 'Dione\'s bright wispy terrain is actually a system of ice canyons.',
          orbitRadius: 2.4,
          orbitalSpeed: 5.5,
          size: 0.1,
          color: 0xddddee
        },
        {
          id: 'tethys',
          name: 'Tethys',
          type: 'Natural Satellite',
          diameter: '1,062 km',
          features: [
            'Has a massive impact crater (Odysseus) and a huge canyon (Ithaca Chasma)',
            'Composed almost entirely of water ice'
          ],
          fact: 'The Ithaca Chasma on Tethys is 100 km wide and runs nearly three-quarters of the way around the moon.',
          orbitRadius: 2.2,
          orbitalSpeed: 6.5,
          size: 0.1,
          color: 0xddddee
        }
      ],
      moonNote: 'Saturn has many additional known moons — at least 146 discovered so far.'
    },
    {
      id: 'uranus',
      name: 'Uranus',
      type: 'Ice Giant',
      diameter: '51,118 km',
      orbitDistance: '2.87 billion km (19.19 AU)',
      orbitalPeriod: '84.01 Earth years',
      features: [
        'Rotates on its side with an axial tilt of 98°',
        'Pale cyan color due to methane in its atmosphere',
        'Has a system of faint rings',
        'First planet discovered with a telescope'
      ],
      fact: 'Uranus rotates on its side, essentially rolling around the Sun on its equator.',
      size: 1.4,
      orbitRadius: 55,
      orbitalSpeed: 0.2,
      rotationSpeed: 0.03,
      tilt: 1.71,
      color: 0x78d0e0,
      moons: [
        {
          id: 'titania',
          name: 'Titania',
          type: 'Natural Satellite',
          diameter: '1,578 km',
          features: [
            'Largest moon of Uranus',
            'Has canyons and scarps indicating past tectonic activity'
          ],
          fact: 'Titania may have a subsurface ocean of liquid water.',
          orbitRadius: 2.0,
          orbitalSpeed: 4.0,
          size: 0.1,
          color: 0xbbbbcc
        },
        {
          id: 'oberon',
          name: 'Oberon',
          type: 'Natural Satellite',
          diameter: '1,523 km',
          features: [
            'Second largest moon of Uranus',
            'Heavily cratered with a dark surface'
          ],
          fact: 'Oberon\'s name comes from the king of the fairies in Shakespeare\'s A Midsummer Night\'s Dream.',
          orbitRadius: 2.8,
          orbitalSpeed: 3.0,
          size: 0.1,
          color: 0x999999
        },
        {
          id: 'umbriel',
          name: 'Umbriel',
          type: 'Natural Satellite',
          diameter: '1,169 km',
          features: [
            'Darkest moon of Uranus',
            'Has a mysterious bright ring on its surface'
          ],
          fact: 'Umbriel is the darkest major moon of Uranus, reflecting only about half the light that Titania does.',
          orbitRadius: 1.6,
          orbitalSpeed: 5.0,
          size: 0.08,
          color: 0x888888
        },
        {
          id: 'ariel',
          name: 'Ariel',
          type: 'Natural Satellite',
          diameter: '1,158 km',
          features: [
            'Brightest moon of Uranus',
            'Has the youngest surface of Uranus\'s major moons with valleys and ridges'
          ],
          fact: 'Ariel has the brightest and possibly youngest surface of Uranus\'s moons.',
          orbitRadius: 1.2,
          orbitalSpeed: 6.0,
          size: 0.08,
          color: 0xccccdd
        },
        {
          id: 'miranda',
          name: 'Miranda',
          type: 'Natural Satellite',
          diameter: '472 km',
          features: [
            'Smallest of Uranus\'s five major moons',
            'Has extreme terrain with cliffs up to 20 km high',
            'Looks like a patchwork of different geological regions'
          ],
          fact: 'Miranda\'s Verona Rupes is a cliff about 20 km high — one of the tallest in the Solar System.',
          orbitRadius: 0.8,
          orbitalSpeed: 8.0,
          size: 0.06,
          color: 0xaaaaaa
        }
      ],
      moonNote: 'Uranus has 27 known moons in total.'
    },
    {
      id: 'neptune',
      name: 'Neptune',
      type: 'Ice Giant',
      diameter: '49,528 km',
      orbitDistance: '4.50 billion km (30.07 AU)',
      orbitalPeriod: '164.8 Earth years',
      features: [
        'Windiest planet with speeds up to 2,100 km/h',
        'Deep blue color due to methane absorption',
        'Has faint rings and a Great Dark Spot (a large storm)',
        'First planet located through mathematical prediction'
      ],
      fact: 'Neptune has the strongest winds of any planet in the Solar System, reaching 2,100 km/h.',
      size: 1.3,
      orbitRadius: 65,
      orbitalSpeed: 0.15,
      rotationSpeed: 0.032,
      tilt: 0.49,
      color: 0x3355ff,
      moons: [
        {
          id: 'triton',
          name: 'Triton',
          type: 'Natural Satellite',
          diameter: '2,707 km',
          features: [
            'Largest moon of Neptune',
            'Orbits Neptune in the opposite direction (retrograde orbit)',
            'Has nitrogen geysers on its surface',
            'Likely a captured Kuiper Belt object'
          ],
          fact: 'Triton orbits Neptune backwards — it is the only large moon with a retrograde orbit.',
          orbitRadius: 2.5,
          orbitalSpeed: 3.5,
          size: 0.15,
          color: 0xddbbcc
        },
        {
          id: 'nereid',
          name: 'Nereid',
          type: 'Natural Satellite',
          diameter: '340 km',
          features: [
            'Third largest moon of Neptune',
            'Has the most eccentric orbit of any moon in the Solar System'
          ],
          fact: 'Nereid\'s orbit is so elongated that its distance from Neptune varies from 1.3 to 9.6 million km.',
          orbitRadius: 4.0,
          orbitalSpeed: 1.5,
          size: 0.06,
          color: 0xbbbbbb
        },
        {
          id: 'proteus',
          name: 'Proteus',
          type: 'Natural Satellite',
          diameter: '420 km',
          features: [
            'Second largest moon of Neptune',
            'Dark and irregularly shaped',
            'Larger than Nereid but discovered later because it orbits very close to Neptune'
          ],
          fact: 'Proteus is one of the darkest objects in the Solar System, reflecting only about 6% of sunlight.',
          orbitRadius: 1.8,
          orbitalSpeed: 5.0,
          size: 0.07,
          color: 0x888888
        },
        {
          id: 'larissa',
          name: 'Larissa',
          type: 'Natural Satellite',
          diameter: '194 km',
          features: [
            'Irregularly shaped and heavily cratered',
            'May be a captured asteroid or Kuiper Belt object'
          ],
          fact: 'Larissa was discovered when it occulted (passed in front of) a star in 1981.',
          orbitRadius: 1.4,
          orbitalSpeed: 6.0,
          size: 0.05,
          color: 0x999999
        },
        {
          id: 'galatea',
          name: 'Galatea',
          type: 'Natural Satellite',
          diameter: '158 km',
          features: [
            'Shepherd moon that helps maintain Neptune\'s ring system',
            'Discovered in 1989 by Voyager 2'
          ],
          fact: 'Galatea orbits just inside Neptune\'s Adams ring and gravitationally shapes it.',
          orbitRadius: 1.0,
          orbitalSpeed: 7.0,
          size: 0.04,
          color: 0xaaaaaa
        },
        {
          id: 'despina',
          name: 'Despina',
          type: 'Natural Satellite',
          diameter: '148 km',
          features: [
            'Small, irregularly shaped moon',
            'Orbits within Neptune\'s ring system'
          ],
          fact: 'Despina acts as a shepherd moon for Neptune\'s Le Verrier ring.',
          orbitRadius: 0.8,
          orbitalSpeed: 8.0,
          size: 0.04,
          color: 0xbbbbbb
        },
        {
          id: 'thalassa',
          name: 'Thalassa',
          type: 'Natural Satellite',
          diameter: '82 km',
          features: [
            'Small irregularly shaped moon',
            'Orbits between Galatea and Despina'
          ],
          fact: 'Thalassa was discovered from images taken by Voyager 2 in 1989.',
          orbitRadius: 0.6,
          orbitalSpeed: 9.0,
          size: 0.03,
          color: 0xcccccc
        },
        {
          id: 'naiad',
          name: 'Naiad',
          type: 'Natural Satellite',
          diameter: '66 km',
          features: [
            'Innermost moon of Neptune',
            'Discovered in 1989 by Voyager 2'
          ],
          fact: 'Naiad orbits Neptune once every 7 hours — the fastest orbit of any of Neptune\'s moons.',
          orbitRadius: 0.4,
          orbitalSpeed: 12.0,
          size: 0.03,
          color: 0xcccccc
        }
      ],
      moonNote: 'Neptune has 16 known moons in total.'
    }
  ]
};
