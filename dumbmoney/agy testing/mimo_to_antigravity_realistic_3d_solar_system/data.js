export const solarSystemData = {
  sun: {
    id: 'sun',
    name: 'Sun',
    type: 'Yellow Dwarf Star',
    diameter: '1,392,700 km',
    orbit: 'Center of Solar System',
    features: 'Plasma, Sunspots, Solar Flares',
    fact: 'The Sun accounts for 99.86% of the mass in the solar system.',
    color: '#ffcc00',
    radius: 12,
    moons: []
  },
  planets: [
    {
      id: 'mercury',
      name: 'Mercury',
      type: 'Terrestrial Planet',
      diameter: '4,880 km',
      orbit: '57.9 million km from Sun',
      features: 'Cratered surface, no atmosphere',
      fact: 'A year on Mercury is just 88 Earth days long.',
      color: '#a8a8a8',
      radius: 1.5,
      distance: 25,
      speed: 0.04,
      moons: [],
      note: 'Note: Mercury has no confirmed natural moons.'
    },
    {
      id: 'venus',
      name: 'Venus',
      type: 'Terrestrial Planet',
      diameter: '12,104 km',
      orbit: '108.2 million km from Sun',
      features: 'Thick toxic atmosphere, extremely hot',
      fact: 'Venus rotates in the opposite direction to most planets.',
      color: '#e0c19e',
      radius: 2.5,
      distance: 35,
      speed: 0.015,
      moons: [],
      note: 'Note: Venus has no confirmed natural moons.'
    },
    {
      id: 'earth',
      name: 'Earth',
      type: 'Terrestrial Planet',
      diameter: '12,742 km',
      orbit: '149.6 million km from Sun',
      features: 'Liquid water, life',
      fact: 'Earth is the only known planet to harbor life.',
      color: '#4b95f2',
      radius: 2.6,
      distance: 48,
      speed: 0.01,
      moons: [
        {
          id: 'moon',
          name: 'The Moon',
          type: 'Natural Satellite',
          diameter: '3,474 km',
          orbit: '384,400 km from Earth',
          features: 'Craters, maria (dark basaltic plains)',
          fact: 'The Moon always shows the same face to Earth due to synchronous rotation.'
        }
      ]
    },
    {
      id: 'mars',
      name: 'Mars',
      type: 'Terrestrial Planet',
      diameter: '6,779 km',
      orbit: '227.9 million km from Sun',
      features: 'Olympus Mons, Valles Marineris, polar ice caps',
      fact: 'Mars is home to the highest mountain in the solar system, Olympus Mons.',
      color: '#c1440e',
      radius: 1.8,
      distance: 62,
      speed: 0.008,
      moons: [
        {
          id: 'phobos',
          name: 'Phobos',
          type: 'Irregular Moon',
          diameter: '22.4 km',
          orbit: '6,000 km from Mars',
          features: 'Heavily cratered, Stickney crater',
          fact: 'Phobos is slowly spiraling inward and will eventually crash into Mars.'
        },
        {
          id: 'deimos',
          name: 'Deimos',
          type: 'Irregular Moon',
          diameter: '12.4 km',
          orbit: '23,460 km from Mars',
          features: 'Smooth surface due to regolith',
          fact: 'Deimos is one of the smallest known moons in the solar system.'
        }
      ]
    },
    {
      id: 'jupiter',
      name: 'Jupiter',
      type: 'Gas Giant',
      diameter: '139,820 km',
      orbit: '778.5 million km from Sun',
      features: 'Great Red Spot, banded atmosphere',
      fact: 'Jupiter has 2.5 times the mass of all other planets in the solar system combined.',
      color: '#d39c7e',
      radius: 6,
      distance: 85,
      speed: 0.002,
      moons: [
        { id: 'io', name: 'Io', type: 'Galilean Moon', diameter: '3,643 km', orbit: '421,700 km', features: 'Volcanically active', fact: 'Most geologically active body in the solar system.' },
        { id: 'europa', name: 'Europa', type: 'Galilean Moon', diameter: '3,121 km', orbit: '671,034 km', features: 'Icy surface, subsurface ocean', fact: 'Considered one of the most promising places to look for alien life.' },
        { id: 'ganymede', name: 'Ganymede', type: 'Galilean Moon', diameter: '5,268 km', orbit: '1,070,400 km', features: 'Magnetic field', fact: 'The largest moon in the solar system, bigger than Mercury.' },
        { id: 'callisto', name: 'Callisto', type: 'Galilean Moon', diameter: '4,820 km', orbit: '1,882,700 km', features: 'Heavily cratered, old surface', fact: 'Callisto is the most heavily cratered object in the solar system.' }
      ],
      note: 'Note: Jupiter has over 90 additional known moons not shown here.'
    },
    {
      id: 'saturn',
      name: 'Saturn',
      type: 'Gas Giant',
      diameter: '116,460 km',
      orbit: '1.4 billion km from Sun',
      features: 'Prominent ring system',
      fact: 'Saturn is the only planet in our solar system less dense than water.',
      color: '#ead6b8',
      radius: 5,
      distance: 115,
      speed: 0.0009,
      hasRings: true,
      moons: [
        { id: 'titan', name: 'Titan', type: 'Major Moon', diameter: '5,149 km', orbit: '1.2 million km', features: 'Dense atmosphere, liquid methane lakes', fact: 'The only moon known to have a dense atmosphere.' },
        { id: 'enceladus', name: 'Enceladus', type: 'Major Moon', diameter: '504 km', orbit: '237,948 km', features: 'Geysers of water ice', fact: 'Reflects almost 100% of the sunlight that strikes it.' },
        { id: 'mimas', name: 'Mimas', type: 'Major Moon', diameter: '396 km', orbit: '185,539 km', features: 'Herschel crater', fact: 'Looks remarkably like the Death Star from Star Wars.' },
        { id: 'rhea', name: 'Rhea', type: 'Major Moon', diameter: '1,527 km', orbit: '527,108 km', features: 'Wispy terrain', fact: 'The second-largest moon of Saturn.' },
        { id: 'iapetus', name: 'Iapetus', type: 'Major Moon', diameter: '1,469 km', orbit: '3.5 million km', features: 'Two-tone coloration, equatorial ridge', fact: 'Has a striking "yin-yang" appearance.' },
        { id: 'dione', name: 'Dione', type: 'Major Moon', diameter: '1,122 km', orbit: '377,396 km', features: 'Ice cliffs', fact: 'Shares its orbit with two tiny co-orbital moons.' },
        { id: 'tethys', name: 'Tethys', type: 'Major Moon', diameter: '1,062 km', orbit: '294,619 km', features: 'Odysseus crater, Ithaca Chasma', fact: 'Composed almost entirely of water ice.' }
      ],
      note: 'Note: Saturn has over 140 additional known moons not shown here.'
    },
    {
      id: 'uranus',
      name: 'Uranus',
      type: 'Ice Giant',
      diameter: '50,724 km',
      orbit: '2.9 billion km from Sun',
      features: 'Extreme axial tilt (rotates on its side)',
      fact: 'Uranus has the coldest planetary atmosphere in the solar system.',
      color: '#ace5ee',
      radius: 3.5,
      distance: 145,
      speed: 0.0004,
      tilt: 98,
      moons: [
        { id: 'titania', name: 'Titania', type: 'Major Moon', diameter: '1,578 km', orbit: '435,910 km', features: 'Faults and valleys', fact: 'The largest moon of Uranus.' },
        { id: 'oberon', name: 'Oberon', type: 'Major Moon', diameter: '1,522 km', orbit: '583,520 km', features: 'Unidentified dark material on crater floors', fact: 'The outermost of the major moons of Uranus.' },
        { id: 'umbriel', name: 'Umbriel', type: 'Major Moon', diameter: '1,169 km', orbit: '266,000 km', features: 'Wunda crater (bright ring)', fact: 'The darkest of Uranus\'s major moons.' },
        { id: 'ariel', name: 'Ariel', type: 'Major Moon', diameter: '1,157 km', orbit: '190,900 km', features: 'Complex network of canyons', fact: 'The brightest of Uranus\'s moons.' },
        { id: 'miranda', name: 'Miranda', type: 'Major Moon', diameter: '471 km', orbit: '129,390 km', features: 'Verona Rupes (tallest cliff)', fact: 'Has one of the most rugged and bizarre landscapes in the solar system.' }
      ],
      note: 'Note: Uranus has over 20 additional known moons not shown here.'
    },
    {
      id: 'neptune',
      name: 'Neptune',
      type: 'Ice Giant',
      diameter: '49,244 km',
      orbit: '4.5 billion km from Sun',
      features: 'Supersonic winds, Great Dark Spot',
      fact: 'Neptune was the first planet located through mathematical calculations rather than observation.',
      color: '#274687',
      radius: 3.4,
      distance: 170,
      speed: 0.0001,
      moons: [
        { id: 'triton', name: 'Triton', type: 'Major Moon', diameter: '2,706 km', orbit: '354,759 km', features: 'Cryovolcanism, retrograde orbit', fact: 'The only large moon in the solar system with a retrograde orbit.' },
        { id: 'nereid', name: 'Nereid', type: 'Irregular Moon', diameter: '340 km', orbit: '5.5 million km', features: 'Highly eccentric orbit', fact: 'Takes 360 Earth days to orbit Neptune.' },
        { id: 'proteus', name: 'Proteus', type: 'Regular Moon', diameter: '420 km', orbit: '117,647 km', features: 'Irregular shape', fact: 'The largest non-spherical moon in the solar system.' },
        { id: 'larissa', name: 'Larissa', type: 'Regular Moon', diameter: '194 km', orbit: '73,548 km', features: 'Cratered, non-spherical', fact: 'Slowly spiraling inward toward Neptune.' },
        { id: 'galatea', name: 'Galatea', type: 'Regular Moon', diameter: '176 km', orbit: '61,953 km', features: 'Shepherd moon', fact: 'Helps maintain Neptune\'s Adams ring.' },
        { id: 'despina', name: 'Despina', type: 'Regular Moon', diameter: '150 km', orbit: '52,526 km', features: 'Amorphous shape', fact: 'Orbits within Neptune\'s ring system.' },
        { id: 'thalassa', name: 'Thalassa', type: 'Regular Moon', diameter: '81 km', orbit: '50,074 km', features: 'Disc-like shape', fact: 'Discovered by the Voyager 2 spacecraft.' },
        { id: 'naiad', name: 'Naiad', type: 'Regular Moon', diameter: '60 km', orbit: '48,227 km', features: 'Potato-shaped', fact: 'The innermost moon of Neptune.' }
      ],
      note: 'Note: Neptune has over 5 additional known moons not shown here.'
    }
  ]
};
