// Authoritative Service Catalogue Taxonomy for FieldOps Commander
// Generated from FieldOps Commander Service Catalogue (16 Service Types, 116 Categories, 958 Issues)

export interface TaxonomyIssue {
  name: string;
}

export interface TaxonomyCategory {
  id: string;
  name: string;
  code: string;
  issues: string[];
}

export interface TaxonomyServiceType {
  id: string;
  name: string;
  code: string;
  description: string;
  image: string;
  theme: {
    bg: string;
    color: string;
    border: string;
  };
  categories: TaxonomyCategory[];
}

export const SERVICE_CATALOGUE_TAXONOMY: TaxonomyServiceType[] = [
  {
    "id": "electrical",
    "name": "Electrical",
    "code": "ELE",
    "description": "Lights, wiring, switchboards, fans, MCB fuse box, inverter, power supply & earthing",
    "image": "/services/electrical.png",
    "theme": {
      "bg": "#FEF3C7",
      "color": "#D97706",
      "border": "#FDE68A"
    },
    "categories": [
      {
        "id": "lights_lighting",
        "name": "Lights and Lighting",
        "code": "ELE-01",
        "issues": [
          "Light not working",
          "Flickering or blinking light",
          "Tube light replacement",
          "LED bulb or panel replacement",
          "Light holder or fitting broken",
          "Dimmer not working",
          "Chandelier or decorative light installation",
          "Outdoor or garden light fault",
          "Emergency light not working",
          "Light making buzzing noise",
          "New light point installation",
          "Street or gate light not switching on",
          "Other (please describe)"
        ]
      },
      {
        "id": "wiring_cabling",
        "name": "Wiring and Cabling",
        "code": "ELE-02",
        "issues": [
          "Exposed or loose wire",
          "Burning smell from wiring",
          "Sparking in wires",
          "Short circuit",
          "Old wiring replacement",
          "New point wiring",
          "Wires damaged by rats",
          "Concealed wiring fault",
          "Extension wiring or conduit work",
          "Loose connections in wall",
          "Wire overheating",
          "Cable tray or trunking work",
          "Other (please describe)"
        ]
      },
      {
        "id": "switches_sockets",
        "name": "Switches, Sockets and Switchboards",
        "code": "ELE-03",
        "issues": [
          "Switch not working",
          "Switch sparking",
          "Socket loose",
          "Burnt switch board",
          "Replace switch or socket",
          "Add new switch or socket point",
          "USB socket installation",
          "Modular switch upgrade",
          "Switchboard hot to touch",
          "Switchboard cracked or broken",
          "Two-way or staircase switch fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "fans_ventilation",
        "name": "Fans and Ventilation",
        "code": "ELE-04",
        "issues": [
          "Fan not rotating",
          "Fan running slow",
          "Fan making noise",
          "Fan wobbling",
          "Regulator faulty",
          "New fan installation",
          "Capacitor replacement",
          "Exhaust fan not working",
          "Exhaust fan installation",
          "Fan blade bent or damaged",
          "Other (please describe)"
        ]
      },
      {
        "id": "mcb_fuse_db",
        "name": "MCB, Fuse and Distribution Board",
        "code": "ELE-05",
        "issues": [
          "MCB tripping frequently",
          "MCB not switching on",
          "Fuse blown",
          "Distribution board overheating",
          "RCCB or ELCB tripping",
          "Replace MCB",
          "Distribution board upgrade",
          "Phase imbalance",
          "Burning smell near DB",
          "New DB installation",
          "Other (please describe)"
        ]
      },
      {
        "id": "power_supply_meter",
        "name": "Power Supply and Meter",
        "code": "ELE-06",
        "issues": [
          "Power cut in house only",
          "Voltage fluctuation",
          "Low voltage",
          "High voltage damaging appliances",
          "Electricity meter fault",
          "Meter shifting",
          "One phase missing",
          "Electric shock from wall or tap",
          "New service connection",
          "Neutral or earth fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "inverter_ups",
        "name": "Inverter, UPS and Battery",
        "code": "ELE-07",
        "issues": [
          "Inverter not charging",
          "Battery not holding backup",
          "Inverter beeping",
          "Inverter installation",
          "Battery replacement",
          "Change-over wiring",
          "Inverter overload tripping",
          "UPS not turning on",
          "Battery water top-up",
          "Other (please describe)"
        ]
      },
      {
        "id": "appliance_points",
        "name": "Appliance Electrical Points",
        "code": "ELE-08",
        "issues": [
          "Geyser point wiring",
          "AC point wiring",
          "Washing machine point",
          "Induction or electric stove point",
          "Heavy load point",
          "Fridge or oven point",
          "EV charger point installation",
          "Stabilizer installation",
          "Other (please describe)"
        ]
      },
      {
        "id": "doorbell_intercom",
        "name": "Doorbell, Intercom and Low-voltage",
        "code": "ELE-09",
        "issues": [
          "Doorbell not ringing",
          "Doorbell installation",
          "Intercom not working",
          "TV or dish cable fault",
          "Telephone line fault",
          "Landscape or garden wiring",
          "Other (please describe)"
        ]
      },
      {
        "id": "safety_earthing",
        "name": "Safety, Earthing and Inspection",
        "code": "ELE-10",
        "issues": [
          "Earthing problem",
          "Earthing test",
          "Electrical safety audit",
          "Thermal scan",
          "Surge protector installation",
          "Lightning arrestor installation",
          "Pre-purchase electrical inspection",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "plumbing",
    "name": "Plumbing",
    "code": "PLU",
    "description": "Taps, pipes, drainage, toilet fixtures, wash basins, water tank, pumps & sewage",
    "image": "/services/plumbing.png",
    "theme": {
      "bg": "#E0F2FE",
      "color": "#0284C7",
      "border": "#BAE6FD"
    },
    "categories": [
      {
        "id": "taps_faucets",
        "name": "Taps and Faucets",
        "code": "PLU-01",
        "issues": [
          "Tap leaking",
          "Tap dripping",
          "Low water flow from tap",
          "Tap handle broken",
          "Replace tap",
          "Mixer tap installation",
          "Tap loose at base",
          "Bib cock or garden tap fault",
          "Sensor tap not working",
          "Tap spout cracked",
          "Other (please describe)"
        ]
      },
      {
        "id": "pipes_pipelines",
        "name": "Pipes and Pipelines",
        "code": "PLU-02",
        "issues": [
          "Pipe leakage",
          "Burst pipe",
          "Pipe joint leaking",
          "Pipe replacement (PVC, CPVC, GI)",
          "Concealed leak inside wall",
          "Pipe making noise or hammering",
          "New pipeline laying",
          "Pipe corrosion or rust",
          "Pipe supports or clamps broken",
          "Water meter leak",
          "Other (please describe)"
        ]
      },
      {
        "id": "drainage_blockage",
        "name": "Drainage and Blockage",
        "code": "PLU-03",
        "issues": [
          "Kitchen sink blocked",
          "Bathroom drain blocked",
          "Floor drain clogged",
          "Foul smell from drain",
          "Main drain overflow",
          "Slow draining",
          "Grease trap cleaning",
          "Roof drain choke",
          "Drain pipe cracked",
          "Rainwater pipe blocked",
          "Other (please describe)"
        ]
      },
      {
        "id": "toilet_sanitary",
        "name": "Toilet and Sanitary",
        "code": "PLU-04",
        "issues": [
          "Flush tank leaking",
          "Flush not working",
          "Toilet seat broken or replacement",
          "Toilet clogged",
          "Commode leaking at base",
          "Commode loose",
          "New commode installation",
          "Health faucet leaking",
          "Urinal flush fault",
          "Cistern running continuously",
          "Concealed flush tank fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "wash_basin_sink",
        "name": "Wash Basin and Kitchen Sink",
        "code": "PLU-05",
        "issues": [
          "Basin leaking",
          "Basin cracked",
          "New basin installation",
          "Sink trap leaking",
          "Waste coupling leaking",
          "Pop-up waste stuck",
          "Kitchen sink installation",
          "Sink overflow",
          "Sink water not draining",
          "Basin loose from wall",
          "Other (please describe)"
        ]
      },
      {
        "id": "tank_motor_pump",
        "name": "Water Tank, Motor and Pump",
        "code": "PLU-06",
        "issues": [
          "Overhead tank overflowing",
          "Tank leakage",
          "Float valve faulty",
          "Motor not starting",
          "Motor running but no water",
          "Pump noisy",
          "Pump overheating",
          "Auto starter or controller fault",
          "Borewell motor problem",
          "New tank installation",
          "Tank level indicator not working",
          "Pump installation",
          "Other (please describe)"
        ]
      },
      {
        "id": "geyser_hot_water",
        "name": "Geyser and Hot Water Lines",
        "code": "PLU-07",
        "issues": [
          "Geyser leaking",
          "No hot water",
          "Geyser installation",
          "Pressure release valve fault",
          "Hot water pipe leaking",
          "Solar water heater plumbing",
          "Hot and cold water mixing problem",
          "Other (please describe)"
        ]
      },
      {
        "id": "shower_fittings",
        "name": "Shower and Bathroom Fittings",
        "code": "PLU-08",
        "issues": [
          "Shower low pressure",
          "Shower head replacement",
          "Diverter faulty",
          "Concealed valve leaking",
          "Overhead shower installation",
          "Bathtub installation or repair",
          "Shower cubicle fitting",
          "Towel rod or accessory fitting",
          "Bathroom hook or shelf fitting",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_pressure",
        "name": "Water Pressure and Supply",
        "code": "PLU-09",
        "issues": [
          "Low water pressure",
          "No water supply",
          "Pressure booster pump installation",
          "Water hammer",
          "Uneven hot and cold supply",
          "Pressure reducing valve fault",
          "Dirty or coloured water",
          "Air in pipes",
          "Other (please describe)"
        ]
      },
      {
        "id": "leakage_seepage",
        "name": "Leakage and Seepage",
        "code": "PLU-10",
        "issues": [
          "Ceiling seepage from upper bathroom",
          "Wall dampness due to pipe",
          "Bathroom floor leakage",
          "Terrace tank leakage",
          "Leak detection service",
          "Kitchen sink cabinet leak",
          "Basement water seepage",
          "Other (please describe)"
        ]
      },
      {
        "id": "sewage_septic",
        "name": "Sewage and Septic",
        "code": "PLU-11",
        "issues": [
          "Septic tank full",
          "Sewer line blockage",
          "Sewage smell",
          "Drain backflow",
          "Inspection chamber overflow",
          "Soak pit problem",
          "Septic tank cleaning",
          "Sewer line inspection with camera",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "ac_refrigeration",
    "name": "Air Conditioning and Refrigeration",
    "code": "ACR",
    "description": "Split AC, window AC, cassette, ductable, domestic & commercial refrigeration",
    "image": "/services/ac_refrigeration.png",
    "theme": {
      "bg": "#ECFEFF",
      "color": "#0891B2",
      "border": "#A5F3FC"
    },
    "categories": [
      {
        "id": "split_ac",
        "name": "Split AC",
        "code": "ACR-01",
        "issues": [
          "Not cooling",
          "Water leaking from indoor unit",
          "Strange noise",
          "Bad smell",
          "Remote not working",
          "Ice formation on coil or pipe",
          "AC tripping MCB",
          "AC not turning on",
          "Display showing error code",
          "Gas leakage",
          "Compressor not starting",
          "Outdoor fan not running",
          "Remote or sensor fault",
          "Swing flap not working",
          "Other (please describe)"
        ]
      },
      {
        "id": "window_ac",
        "name": "Window AC",
        "code": "ACR-02",
        "issues": [
          "Not cooling",
          "Noisy operation",
          "Water dripping inside room",
          "Compressor tripping",
          "Thermostat fault",
          "Fan motor fault",
          "Knob or switch broken",
          "Foul smell",
          "Frame or sleeve damage",
          "Other (please describe)"
        ]
      },
      {
        "id": "cassette_ducted",
        "name": "Cassette, Ducted and VRF Systems",
        "code": "ACR-03",
        "issues": [
          "Not cooling",
          "Water leak from cassette",
          "Drain pump fault",
          "Duct leakage",
          "Controller fault",
          "Outdoor unit error",
          "Zone not cooling",
          "Filter blocked",
          "Refrigerant leak",
          "Other (please describe)"
        ]
      },
      {
        "id": "ac_installation",
        "name": "AC Installation and Relocation",
        "code": "ACR-04",
        "issues": [
          "New AC installation",
          "AC uninstallation",
          "AC relocation",
          "Copper piping work",
          "Stand or bracket fixing",
          "Drain pipe extension",
          "Stabilizer fitting",
          "Outdoor unit stand or cage",
          "Electrical point for AC",
          "Other (please describe)"
        ]
      },
      {
        "id": "ac_servicing",
        "name": "AC Servicing and Maintenance",
        "code": "ACR-05",
        "issues": [
          "General service",
          "Jet pump deep cleaning",
          "Gas top-up",
          "Annual maintenance contract",
          "Filter cleaning",
          "Coil cleaning",
          "Pre-summer check-up",
          "Performance inspection",
          "Other (please describe)"
        ]
      },
      {
        "id": "refrigerator_domestic",
        "name": "Refrigerator (Domestic)",
        "code": "ACR-06",
        "issues": [
          "Not cooling",
          "Freezer not freezing",
          "Water leaking",
          "Noisy fridge",
          "Frost build-up",
          "Door gasket damaged",
          "Light not working",
          "Compressor not starting",
          "Thermostat fault",
          "Ice maker not working",
          "Door not closing",
          "Bad smell",
          "Other (please describe)"
        ]
      },
      {
        "id": "commercial_refrigeration",
        "name": "Commercial Refrigeration",
        "code": "ACR-07",
        "issues": [
          "Cold room not cooling",
          "Deep freezer fault",
          "Display chiller fault",
          "Visi cooler fault",
          "Bottle cooler fault",
          "Ice machine fault",
          "Walk-in cooler issue",
          "Temperature controller fault",
          "Condenser cleaning",
          "Gas refilling",
          "Other (please describe)"
        ]
      },
      {
        "id": "air_coolers_purifiers",
        "name": "Air Coolers and Air Purifiers",
        "code": "ACR-08",
        "issues": [
          "Cooler pump not working",
          "Cooler motor fault",
          "Cooling pad replacement",
          "Cooler leaking",
          "Air purifier filter change",
          "Air purifier not working",
          "Humidifier fault",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "appliances",
    "name": "Home Appliance Repair",
    "code": "APP",
    "description": "Washing machine, TV, microwave, chimney & hob, mixer grinder, geyser & dishwasher",
    "image": "/services/appliances.png",
    "theme": {
      "bg": "#EFF6FF",
      "color": "#2563EB",
      "border": "#BFDBFE"
    },
    "categories": [
      {
        "id": "washing_machine",
        "name": "Washing Machine",
        "code": "APP-01",
        "issues": [
          "Not starting",
          "Not draining",
          "Not spinning",
          "Water not filling",
          "Excessive vibration",
          "Noise during wash",
          "Door lock error",
          "Water leaking",
          "Error code displayed",
          "Clothes not cleaned",
          "Drum jammed",
          "Inlet valve fault",
          "Control panel fault",
          "Installation or demo",
          "Other (please describe)"
        ]
      },
      {
        "id": "television",
        "name": "Television",
        "code": "APP-02",
        "issues": [
          "No display",
          "No sound",
          "Lines on screen",
          "Panel broken",
          "Backlight problem",
          "HDMI port not working",
          "Wi-Fi or smart features fault",
          "Remote not working",
          "Wall mounting",
          "Software or app issue",
          "Stuck on logo",
          "TV not turning on",
          "Other (please describe)"
        ]
      },
      {
        "id": "microwave_otg",
        "name": "Microwave Oven and OTG",
        "code": "APP-03",
        "issues": [
          "Not heating",
          "Turntable not rotating",
          "Sparking inside",
          "Door not closing",
          "Display not working",
          "Buttons not responding",
          "Noise while running",
          "Tripping MCB",
          "Grill element not working",
          "Other (please describe)"
        ]
      },
      {
        "id": "kitchen_chimney_hob",
        "name": "Kitchen Chimney and Hob",
        "code": "APP-04",
        "issues": [
          "Chimney suction low",
          "Chimney noisy",
          "Oil collector issue",
          "Filter cleaning",
          "Auto-clean fault",
          "Gas stove burner problem",
          "Ignition not working",
          "Hob glass broken",
          "Gas leak smell (urgent)",
          "Gas regulator or pipe replacement",
          "Chimney installation",
          "Other (please describe)"
        ]
      },
      {
        "id": "mixer_grinder",
        "name": "Mixer Grinder and Blender",
        "code": "APP-05",
        "issues": [
          "Motor not running",
          "Jar leaking",
          "Blade blunt or broken",
          "Noisy operation",
          "Burning smell",
          "Jar coupler broken",
          "Overload cut-off tripping",
          "Switch fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "electric_water_heater",
        "name": "Electric Water Heater (Appliance)",
        "code": "APP-06",
        "issues": [
          "Not heating",
          "Thermostat fault",
          "Heating element failure",
          "Water leaking",
          "Tripping power",
          "Auto cut-off fault",
          "Indicator light not working",
          "Anode rod replacement",
          "Descaling",
          "Other (please describe)"
        ]
      },
      {
        "id": "dishwasher",
        "name": "Dishwasher",
        "code": "APP-07",
        "issues": [
          "Not draining",
          "Not cleaning properly",
          "Door will not close",
          "Detergent dispenser fault",
          "Error code",
          "Water leaking",
          "Not starting",
          "Bad smell",
          "Other (please describe)"
        ]
      },
      {
        "id": "small_kitchen_appliances",
        "name": "Small Kitchen Appliances",
        "code": "APP-08",
        "issues": [
          "Iron box not heating",
          "Induction cooktop error",
          "Electric kettle not working",
          "Rice cooker fault",
          "Toaster fault",
          "Air fryer fault",
          "Coffee maker fault",
          "Food processor fault",
          "Hand blender fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "vacuum_cleaner",
        "name": "Vacuum Cleaner and Floor Care",
        "code": "APP-09",
        "issues": [
          "Low suction",
          "Motor not working",
          "Battery not charging",
          "Brush not rotating",
          "Dust bag or filter issue",
          "Robot vacuum not mapping",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_dispenser_others",
        "name": "Water Dispenser and Others",
        "code": "APP-10",
        "issues": [
          "Dispenser not cooling",
          "No hot water",
          "Dispenser leaking",
          "Tap faulty",
          "Sewing machine repair",
          "Room heater fault",
          "Hair dryer or trimmer fault",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "carpentry",
    "name": "Carpentry and Furniture",
    "code": "CAR",
    "description": "Furniture repair, modular kitchen, wooden doors, custom furniture, polish & fitting",
    "image": "/services/carpentry.png",
    "theme": {
      "bg": "#FFEDD5",
      "color": "#EA580C",
      "border": "#FED7AA"
    },
    "categories": [
      {
        "id": "furniture_repair",
        "name": "Furniture Repair",
        "code": "CAR-01",
        "issues": [
          "Loose joints",
          "Broken leg",
          "Drawer stuck",
          "Hinge broken",
          "Wobbly table",
          "Scratches on furniture",
          "Sofa frame broken",
          "Bed frame broken",
          "Chair repair",
          "Cupboard shutter misaligned",
          "Table top damaged",
          "Other (please describe)"
        ]
      },
      {
        "id": "modular_kitchen_wardrobe",
        "name": "Modular Kitchen and Wardrobe",
        "code": "CAR-02",
        "issues": [
          "Wardrobe installation",
          "Hinge or channel replacement",
          "Shutter alignment",
          "Soft-close fitting",
          "Countertop damage",
          "Handle replacement",
          "Kitchen modification",
          "Laminate peeling",
          "Basket or tandem unit installation",
          "Cabinet water damage",
          "Other (please describe)"
        ]
      },
      {
        "id": "wooden_doors",
        "name": "Wooden Doors",
        "code": "CAR-03",
        "issues": [
          "Door not closing",
          "Door jammed",
          "Door swollen",
          "Hinge replacement",
          "Termite-damaged frame",
          "New door installation",
          "Door polishing",
          "Door scraping on floor",
          "Door handle fitting",
          "Door gap or alignment fix",
          "Other (please describe)"
        ]
      },
      {
        "id": "custom_furniture",
        "name": "Custom Furniture",
        "code": "CAR-04",
        "issues": [
          "New bed",
          "New wardrobe",
          "TV unit",
          "Study table",
          "Shoe rack",
          "Pooja unit",
          "Bookshelf",
          "Dining table",
          "Dressing table",
          "Kids furniture",
          "Office furniture",
          "Other (please describe)"
        ]
      },
      {
        "id": "polishing_finishing",
        "name": "Polishing and Finishing",
        "code": "CAR-05",
        "issues": [
          "Wood polishing",
          "Melamine or PU polish",
          "Varnish touch-up",
          "Laminate or veneer fixing",
          "Scratch repair",
          "Colour change of furniture",
          "Other (please describe)"
        ]
      },
      {
        "id": "furniture_assembly",
        "name": "Furniture Assembly and Fitting",
        "code": "CAR-06",
        "issues": [
          "Flat-pack furniture assembly",
          "Furniture dismantle and reassemble",
          "Curtain rod fitting",
          "Wall shelf fitting",
          "TV bracket fitting",
          "Mirror or frame hanging",
          "Other (please describe)"
        ]
      },
      {
        "id": "partitions_ceilings",
        "name": "Partitions and Wooden Ceilings",
        "code": "CAR-07",
        "issues": [
          "Wooden partition",
          "Plywood partition",
          "Wooden false ceiling",
          "Wall panelling",
          "Loft or mezzanine",
          "Pergola or deck",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "painting",
    "name": "Painting and Waterproofing",
    "code": "PNT",
    "description": "Interior & exterior painting, metal paint, wall defects repair, terrace waterproofing",
    "image": "/services/painting.png",
    "theme": {
      "bg": "#FDF2F8",
      "color": "#DB2777",
      "border": "#FBCFE8"
    },
    "categories": [
      {
        "id": "interior_painting",
        "name": "Interior Painting",
        "code": "PNT-01",
        "issues": [
          "Full house painting",
          "Single room painting",
          "Ceiling painting",
          "Touch-up painting",
          "Texture painting",
          "Accent or design wall",
          "Stencil work",
          "Wallpaper installation",
          "Colour consultation",
          "Kids room theme",
          "Other (please describe)"
        ]
      },
      {
        "id": "exterior_painting",
        "name": "Exterior Painting",
        "code": "PNT-02",
        "issues": [
          "Full exterior painting",
          "Compound wall painting",
          "Gate painting",
          "Terrace wall painting",
          "Weather-proof coat",
          "Exterior texture",
          "Other (please describe)"
        ]
      },
      {
        "id": "wood_metal_painting",
        "name": "Wood and Metal Painting",
        "code": "PNT-03",
        "issues": [
          "Door or furniture enamel",
          "PU finish",
          "Grill painting",
          "Gate painting",
          "Rust removal and primer",
          "Shutter painting",
          "Railing painting",
          "Other (please describe)"
        ]
      },
      {
        "id": "wall_defects",
        "name": "Wall Defects",
        "code": "PNT-04",
        "issues": [
          "Peeling paint",
          "Cracks on wall",
          "Dampness on wall",
          "Seepage patches",
          "Fungus or mould",
          "Efflorescence (white powder)",
          "Paint bubbling",
          "Putty work",
          "Hairline cracks",
          "Stains on ceiling",
          "Other (please describe)"
        ]
      },
      {
        "id": "waterproofing",
        "name": "Waterproofing",
        "code": "PNT-05",
        "issues": [
          "Terrace waterproofing",
          "Bathroom waterproofing",
          "Basement waterproofing",
          "Water tank waterproofing",
          "External wall waterproofing",
          "Balcony waterproofing",
          "Kitchen waterproofing",
          "Expansion joint treatment",
          "Crack injection grouting",
          "Other (please describe)"
        ]
      },
      {
        "id": "special_finishes",
        "name": "Special Finishes",
        "code": "PNT-06",
        "issues": [
          "Stucco finish",
          "3D wall panel",
          "Anti-bacterial coating",
          "Heat-reflective coating",
          "Epoxy coating",
          "Fire-retardant coating",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "civil_masonry",
    "name": "Civil, Masonry and Flooring",
    "code": "CIV",
    "description": "Masonry, tiles & granite, roof slab, renovation, structural repair & paving",
    "image": "/services/civil_masonry.png",
    "theme": {
      "bg": "#F5F5F4",
      "color": "#57534E",
      "border": "#E7E5E4"
    },
    "categories": [
      {
        "id": "masonry_plastering",
        "name": "Masonry and Plastering",
        "code": "CIV-01",
        "issues": [
          "Brick work",
          "Plastering",
          "Wall breaking",
          "New partition wall",
          "Compound wall",
          "Crack repair",
          "Chipping and re-plastering",
          "Sunshade or chajja repair",
          "Other (please describe)"
        ]
      },
      {
        "id": "flooring_tiles",
        "name": "Flooring and Tiles",
        "code": "CIV-02",
        "issues": [
          "Broken tile",
          "Hollow tile sound",
          "Grout damaged",
          "New tile laying",
          "Vitrified tile fitting",
          "Marble polishing",
          "Granite fitting",
          "Wooden flooring",
          "Epoxy flooring",
          "Tile levelling problem",
          "Skirting fixing",
          "Other (please describe)"
        ]
      },
      {
        "id": "roof_slab",
        "name": "Roof and Slab",
        "code": "CIV-03",
        "issues": [
          "Roof leakage",
          "Cracks in slab",
          "Terrace tiling",
          "Sheet roofing",
          "Shed or canopy",
          "Parapet repair",
          "Roof drain repair",
          "Skylight fitting",
          "Other (please describe)"
        ]
      },
      {
        "id": "bathroom_kitchen_renovation",
        "name": "Bathroom and Kitchen Renovation",
        "code": "CIV-04",
        "issues": [
          "Complete bathroom renovation",
          "Kitchen renovation",
          "Wall and floor tiling",
          "Kitchen platform or slab",
          "Sink cut-out",
          "Bathroom layout change",
          "Wet area waterproofing",
          "Other (please describe)"
        ]
      },
      {
        "id": "structural_repair",
        "name": "Structural Repair",
        "code": "CIV-05",
        "issues": [
          "Cracks in beam or column",
          "Concrete spalling",
          "Rusting reinforcement",
          "Foundation issue",
          "Retrofitting",
          "Structural audit",
          "Sagging slab",
          "Termite in structure",
          "Other (please describe)"
        ]
      },
      {
        "id": "concrete_paving",
        "name": "Concrete and Paving",
        "code": "CIV-06",
        "issues": [
          "Driveway concreting",
          "Paver block laying",
          "Stamped concrete",
          "Kerb stone",
          "Steps or ramp",
          "Compound floor repair",
          "Drain cover or channel",
          "Other (please describe)"
        ]
      },
      {
        "id": "false_ceiling_partitions",
        "name": "False Ceiling and Partitions",
        "code": "CIV-07",
        "issues": [
          "Gypsum false ceiling",
          "POP work",
          "PVC ceiling",
          "Cove lighting ceiling",
          "Ceiling crack or sag",
          "Glass or gypsum partition",
          "Other (please describe)"
        ]
      },
      {
        "id": "demolition_debris",
        "name": "Demolition and Debris Removal",
        "code": "CIV-08",
        "issues": [
          "Interior demolition",
          "Wall removal",
          "Debris removal",
          "Tile or flooring removal",
          "Site clean-up",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "cleaning",
    "name": "Cleaning Services",
    "code": "CLN",
    "description": "Home deep cleaning, sofa & carpet shampoo, water tank wash, kitchen & office clean",
    "image": "/services/cleaning.png",
    "theme": {
      "bg": "#F3E8FF",
      "color": "#9333EA",
      "border": "#E9D5FF"
    },
    "categories": [
      {
        "id": "home_deep_cleaning",
        "name": "Home Deep Cleaning",
        "code": "CLN-01",
        "issues": [
          "Full home deep clean",
          "Kitchen deep clean",
          "Bathroom deep clean",
          "Balcony cleaning",
          "Window and glass cleaning",
          "Post-construction cleaning",
          "Move-in or move-out cleaning",
          "Festival cleaning",
          "Fan and light cleaning",
          "Other (please describe)"
        ]
      },
      {
        "id": "sofa_carpet_curtain",
        "name": "Sofa, Carpet, Mattress and Curtain",
        "code": "CLN-02",
        "issues": [
          "Sofa shampooing",
          "Carpet cleaning",
          "Mattress cleaning",
          "Curtain cleaning",
          "Stain removal",
          "Odour removal",
          "Dust mite treatment",
          "Leather care",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_tank_sump",
        "name": "Water Tank and Sump Cleaning",
        "code": "CLN-03",
        "issues": [
          "Overhead tank cleaning",
          "Underground sump cleaning",
          "Tank disinfection",
          "Algae or sludge removal",
          "Water quality problem",
          "Tank repair after cleaning",
          "Other (please describe)"
        ]
      },
      {
        "id": "kitchen_cleaning",
        "name": "Kitchen Cleaning",
        "code": "CLN-04",
        "issues": [
          "Chimney degreasing",
          "Cabinet cleaning",
          "Kitchen tile cleaning",
          "Appliance exterior cleaning",
          "Gas stove cleaning",
          "Exhaust fan degreasing",
          "Other (please describe)"
        ]
      },
      {
        "id": "bathroom_cleaning",
        "name": "Bathroom Cleaning",
        "code": "CLN-05",
        "issues": [
          "Hard water stains",
          "Grout cleaning",
          "Limescale removal",
          "Drain cleaning",
          "Glass partition cleaning",
          "Mould in bathroom",
          "Other (please describe)"
        ]
      },
      {
        "id": "office_commercial_clean",
        "name": "Office and Commercial Cleaning",
        "code": "CLN-06",
        "issues": [
          "Daily housekeeping",
          "Floor scrubbing",
          "Pantry cleaning",
          "Glass facade cleaning",
          "Washroom cleaning",
          "Carpet cleaning (office)",
          "Staircase cleaning",
          "Parking area cleaning",
          "Other (please describe)"
        ]
      },
      {
        "id": "specialised_cleaning",
        "name": "Specialised Cleaning",
        "code": "CLN-07",
        "issues": [
          "Marble polishing",
          "Disinfection and sanitization",
          "Facade cleaning",
          "Solar panel cleaning",
          "Terrace cleaning",
          "Sewage tank cleaning",
          "Industrial cleaning",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "pest_control",
    "name": "Pest Control",
    "code": "PST",
    "description": "Cockroaches, termites, mosquitoes, rodents, bed bugs, birds & preventive AMC",
    "image": "/services/pest_control.png",
    "theme": {
      "bg": "#FEF2F2",
      "color": "#DC2626",
      "border": "#FECACA"
    },
    "categories": [
      {
        "id": "crawling_insects",
        "name": "Crawling Insects",
        "code": "PST-01",
        "issues": [
          "Cockroaches in kitchen",
          "Cockroaches in bathroom or drains",
          "Ants indoors",
          "Ants in garden",
          "Silverfish",
          "Centipedes or millipedes",
          "Gel or spray treatment",
          "Severe infestation",
          "Other (please describe)"
        ]
      },
      {
        "id": "termites_wood_pests",
        "name": "Termites and Wood Pests",
        "code": "PST-02",
        "issues": [
          "Termites in furniture",
          "Termites in walls or doors",
          "Pre-construction anti-termite",
          "Post-construction anti-termite",
          "Wood borer",
          "Termite inspection",
          "Termite re-treatment",
          "Other (please describe)"
        ]
      },
      {
        "id": "mosquitoes_flies",
        "name": "Mosquitoes and Flies",
        "code": "PST-03",
        "issues": [
          "Mosquito spraying",
          "Mosquito fogging",
          "Larvae in stagnant water",
          "Flies in kitchen",
          "Flies near garbage",
          "Drain fly",
          "Mosquito net installation",
          "Other (please describe)"
        ]
      },
      {
        "id": "rodents",
        "name": "Rodents",
        "code": "PST-04",
        "issues": [
          "Rats in house",
          "Mice in kitchen",
          "Rats in ceiling",
          "Rat burrows in garden",
          "Rodent proofing",
          "Cable damage by rats",
          "Dead rat removal",
          "Other (please describe)"
        ]
      },
      {
        "id": "bed_bugs",
        "name": "Bed Bugs and Parasites",
        "code": "PST-05",
        "issues": [
          "Bed bugs in mattress",
          "Bed bugs in sofa",
          "Lice or fleas",
          "Ticks in pets area",
          "Dust mites",
          "Bed bug re-treatment",
          "Other (please describe)"
        ]
      },
      {
        "id": "stinging_wildlife",
        "name": "Stinging Insects and Wildlife",
        "code": "PST-06",
        "issues": [
          "Wasp nest removal",
          "Bee hive removal",
          "Snake rescue",
          "Lizards or spiders",
          "Scorpion control",
          "Monkey or squirrel issue",
          "Bat removal",
          "Other (please describe)"
        ]
      },
      {
        "id": "birds",
        "name": "Birds",
        "code": "PST-07",
        "issues": [
          "Pigeon nets for balcony",
          "Bird spikes",
          "Bird nest removal",
          "Bird droppings clean-up",
          "Other (please describe)"
        ]
      },
      {
        "id": "preventive_contract",
        "name": "Preventive and Contract",
        "code": "PST-08",
        "issues": [
          "Annual pest control contract",
          "Quarterly service",
          "Commercial kitchen pest control",
          "Warehouse pest control",
          "Restaurant or hotel treatment",
          "Pest inspection and report",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "security_systems",
    "name": "CCTV and Security Systems",
    "code": "SEC",
    "description": "CCTV cameras, DVR/NVR, biometric access, alarm sensors, video doorbell & gates",
    "image": "/services/security.png",
    "theme": {
      "bg": "#DCFCE7",
      "color": "#16A34A",
      "border": "#BBF7D0"
    },
    "categories": [
      {
        "id": "cctv_cameras",
        "name": "CCTV Cameras",
        "code": "SEC-01",
        "issues": [
          "Camera not recording",
          "No video from camera",
          "Blurry picture",
          "Night vision not working",
          "Camera offline",
          "New camera installation",
          "Camera repositioning",
          "Cable cut or damaged",
          "Camera lens dirty or fogged",
          "Audio not working",
          "PTZ camera not rotating",
          "Other (please describe)"
        ]
      },
      {
        "id": "dvr_nvr",
        "name": "DVR and NVR",
        "code": "SEC-02",
        "issues": [
          "DVR not booting",
          "Hard disk failure",
          "No signal on monitor",
          "Storage full",
          "Password reset",
          "Playback problem",
          "Remote view setup",
          "Date and time wrong",
          "Mobile app not connecting",
          "Backup of footage",
          "Other (please describe)"
        ]
      },
      {
        "id": "biometric_access",
        "name": "Biometric and Access Control",
        "code": "SEC-03",
        "issues": [
          "Fingerprint not reading",
          "Door lock fault",
          "Card reader not working",
          "Face recognition error",
          "Attendance sync issue",
          "Magnetic lock fault",
          "New access control installation",
          "Software or user management",
          "Other (please describe)"
        ]
      },
      {
        "id": "alarms_sensors",
        "name": "Alarms and Sensors",
        "code": "SEC-04",
        "issues": [
          "False alarm",
          "Siren not working",
          "Motion sensor fault",
          "Door sensor fault",
          "Fire alarm panel fault",
          "Smoke detector chirping",
          "Gas leak detector fault",
          "Panic button not working",
          "Other (please describe)"
        ]
      },
      {
        "id": "video_door_phone",
        "name": "Video Door Phone and Intercom",
        "code": "SEC-05",
        "issues": [
          "No display",
          "No audio",
          "Call not ringing",
          "New installation",
          "Cable fault",
          "Door release not working",
          "Monitor replacement",
          "Other (please describe)"
        ]
      },
      {
        "id": "gate_automation",
        "name": "Gate and Barrier Automation",
        "code": "SEC-06",
        "issues": [
          "Sliding gate motor fault",
          "Remote not working",
          "Swing gate motor fault",
          "Boom barrier fault",
          "Limit switch problem",
          "Safety sensor fault",
          "Gate stops midway",
          "Remote duplication",
          "Other (please describe)"
        ]
      },
      {
        "id": "electric_fence",
        "name": "Electric Fence and Perimeter",
        "code": "SEC-07",
        "issues": [
          "Fence not energized",
          "False alarm on fence",
          "Energizer fault",
          "Fence wire broken",
          "New fence installation",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "it_networking",
    "name": "Computer, Laptop and Networking (IT)",
    "code": "ITN",
    "description": "Laptops, Wi-Fi router, LAN cabling, printer, OS/software, server & projectors",
    "image": "/services/it_networking.png",
    "theme": {
      "bg": "#EEF2FF",
      "color": "#4F46E5",
      "border": "#C7D2FE"
    },
    "categories": [
      {
        "id": "laptop_desktop",
        "name": "Laptop and Desktop",
        "code": "ITN-01",
        "issues": [
          "Not booting",
          "Slow performance",
          "Overheating",
          "Screen broken or flickering",
          "Keyboard not working",
          "Battery not charging or draining fast",
          "Virus or malware",
          "Operating system install",
          "Data recovery",
          "Blue screen error",
          "RAM or SSD upgrade",
          "Fan noise",
          "Touchpad or USB port fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "wifi_internet",
        "name": "Wi-Fi and Internet",
        "code": "ITN-02",
        "issues": [
          "No internet",
          "Slow internet",
          "Weak Wi-Fi signal",
          "Router configuration",
          "Mesh Wi-Fi setup",
          "Wi-Fi password change",
          "Cable laying",
          "ISP issue",
          "Dead zones",
          "Router replacement",
          "Other (please describe)"
        ]
      },
      {
        "id": "lan_cabling",
        "name": "LAN and Structured Cabling",
        "code": "ITN-03",
        "issues": [
          "Cat6 cable laying",
          "Network port dead",
          "Patch panel work",
          "Rack setup",
          "Switch configuration",
          "RJ45 crimping",
          "Fibre cable splicing",
          "Network audit",
          "Other (please describe)"
        ]
      },
      {
        "id": "printer_scanner",
        "name": "Printer and Scanner",
        "code": "ITN-04",
        "issues": [
          "Not printing",
          "Paper jam",
          "Ink or toner issue",
          "Wireless printing setup",
          "Driver problem",
          "Cartridge refill",
          "Streaks or faded print",
          "Scanner not detected",
          "Printer offline",
          "Other (please describe)"
        ]
      },
      {
        "id": "software_accounts",
        "name": "Software and Accounts",
        "code": "ITN-05",
        "issues": [
          "Windows installation",
          "MS Office installation",
          "Antivirus installation",
          "Email setup",
          "Driver installation",
          "Software licence issue",
          "Browser problems",
          "Data backup setup",
          "Other (please describe)"
        ]
      },
      {
        "id": "server_nas_backup",
        "name": "Server, NAS and Backup",
        "code": "ITN-06",
        "issues": [
          "Server down",
          "Backup failure",
          "NAS setup",
          "RAID problem",
          "User access issue",
          "Server cleaning and maintenance",
          "Cloud backup setup",
          "Firewall or VPN setup",
          "Other (please describe)"
        ]
      },
      {
        "id": "projector_display",
        "name": "Projector and Display",
        "code": "ITN-07",
        "issues": [
          "No display",
          "Colour problem",
          "Lamp failure",
          "Wireless casting issue",
          "Meeting room setup",
          "Interactive panel fault",
          "Screen or stand fitting",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "water_purifier",
    "name": "Water Purifier (RO) and Water Treatment",
    "code": "WTR",
    "description": "Domestic RO, UV purifiers, commercial RO, water softeners, dispensers & filters",
    "image": "/services/water_purifier.png",
    "theme": {
      "bg": "#F0FDF4",
      "color": "#16A34A",
      "border": "#BBF7D0"
    },
    "categories": [
      {
        "id": "ro_water_purifier",
        "name": "RO Water Purifier",
        "code": "WTR-01",
        "issues": [
          "Not purifying water",
          "Water taste bad",
          "Low water flow",
          "Leaking",
          "Noise from purifier",
          "High TDS in output",
          "Auto shut-off not working",
          "Membrane replacement",
          "Filter change",
          "Error light or alarm",
          "Pump fault",
          "SMPS or adapter fault",
          "Storage tank issue",
          "Other (please describe)"
        ]
      },
      {
        "id": "uv_uf_gravity",
        "name": "UV, UF and Gravity Purifiers",
        "code": "WTR-02",
        "issues": [
          "UV lamp not glowing",
          "UF membrane choke",
          "Gravity filter slow",
          "Candle replacement",
          "Tap or tank leaking",
          "Water smells",
          "Other (please describe)"
        ]
      },
      {
        "id": "commercial_ro_plant",
        "name": "Commercial and Industrial RO Plant",
        "code": "WTR-03",
        "issues": [
          "Plant not producing",
          "Pressure low",
          "Membrane fouling",
          "Antiscalant dosing fault",
          "Tank cleaning",
          "Pump fault",
          "Plant AMC",
          "Water quality testing",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_softener",
        "name": "Water Softener and Filtration",
        "code": "WTR-04",
        "issues": [
          "Hard water problem",
          "Softener resin recharge",
          "Iron filter problem",
          "Sediment filter replacement",
          "Whole-house filter installation",
          "Chlorine or smell removal",
          "Salt refilling",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_cooler_dispenser",
        "name": "Water Cooler and Dispenser",
        "code": "WTR-05",
        "issues": [
          "Not cooling",
          "No hot water",
          "Leaking",
          "Tap faulty",
          "Filter change",
          "Bottle sensor fault",
          "Compressor issue",
          "Other (please describe)"
        ]
      },
      {
        "id": "purifier_installation",
        "name": "Installation and Maintenance",
        "code": "WTR-06",
        "issues": [
          "New purifier installation",
          "Purifier relocation",
          "Annual maintenance contract",
          "Water quality test",
          "Uninstall purifier",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "solar_power",
    "name": "Solar and Power Backup",
    "code": "SOL",
    "description": "Rooftop solar PV, solar water heater, DG generator sets, stabilizers & outdoor solar",
    "image": "/services/solar_backup.png",
    "theme": {
      "bg": "#FFFBEB",
      "color": "#B45309",
      "border": "#FDE68A"
    },
    "categories": [
      {
        "id": "rooftop_solar",
        "name": "Rooftop Solar PV",
        "code": "SOL-01",
        "issues": [
          "Low generation",
          "Solar inverter fault",
          "Panels dirty",
          "Panel damaged",
          "Net-metering issue",
          "New installation",
          "Shading problem",
          "Wiring problem",
          "Monitoring app not working",
          "DC isolator or fuse fault",
          "Bird droppings on panels",
          "Other (please describe)"
        ]
      },
      {
        "id": "solar_water_heater",
        "name": "Solar Water Heater",
        "code": "SOL-02",
        "issues": [
          "No hot water",
          "Leakage",
          "Broken tube",
          "Tube cleaning",
          "Controller fault",
          "Tank insulation damaged",
          "Pipe leak",
          "New installation",
          "Other (please describe)"
        ]
      },
      {
        "id": "generator_dg_set",
        "name": "Generator (DG Set)",
        "code": "SOL-03",
        "issues": [
          "Generator not starting",
          "Fuel problem",
          "AMF panel fault",
          "Excessive noise or smoke",
          "Periodic service",
          "Battery weak",
          "Oil leak",
          "Change-over switch fault",
          "Load tripping",
          "Other (please describe)"
        ]
      },
      {
        "id": "voltage_stabilizers",
        "name": "Voltage Stabilizers",
        "code": "SOL-04",
        "issues": [
          "Stabilizer not working",
          "Buzzing noise",
          "Output voltage wrong",
          "Stabilizer installation",
          "Cut-off problem",
          "Display fault",
          "Other (please describe)"
        ]
      },
      {
        "id": "solar_lights",
        "name": "Solar Lights and Outdoor Power",
        "code": "SOL-05",
        "issues": [
          "Solar street light not glowing",
          "Solar garden light fault",
          "Battery replacement",
          "Sensor fault",
          "New installation",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "doors_windows",
    "name": "Doors, Windows, Locks and Glass",
    "code": "DWL",
    "description": "Locks & keys, UPVC/aluminium doors, sliding windows, glass & mirrors, shutters & gates",
    "image": "/services/doors_windows.png",
    "theme": {
      "bg": "#F8FAFC",
      "color": "#475569",
      "border": "#CBD5E1"
    },
    "categories": [
      {
        "id": "locks_keys",
        "name": "Locks and Keys",
        "code": "DWL-01",
        "issues": [
          "Lock jammed",
          "Key broken inside",
          "Lost key or duplicate key",
          "Lock replacement",
          "Digital lock installation",
          "Mortise lock fault",
          "Padlock cut",
          "Emergency lockout",
          "Cupboard lock fault",
          "Digital lock battery or error",
          "Other (please describe)"
        ]
      },
      {
        "id": "upvc_aluminium_doors",
        "name": "Doors (UPVC, Aluminium, Metal)",
        "code": "DWL-02",
        "issues": [
          "Door not closing",
          "Hinge fault",
          "Door closer fault",
          "Handle replacement",
          "Sliding door off track",
          "Main door replacement",
          "Security door installation",
          "Door frame damage",
          "Door seal or gasket worn",
          "Other (please describe)"
        ]
      },
      {
        "id": "windows_grills",
        "name": "Windows and Grills",
        "code": "DWL-03",
        "issues": [
          "Window stuck",
          "Window glass broken",
          "Mosquito mesh replacement",
          "New grill installation",
          "Sliding window track fault",
          "UPVC window seal fault",
          "Grill rust",
          "Invisible grill installation",
          "Window latch broken",
          "Other (please describe)"
        ]
      },
      {
        "id": "glass_mirror",
        "name": "Glass and Mirror",
        "code": "DWL-04",
        "issues": [
          "Glass cracked",
          "Glass replacement",
          "Shower glass fitting",
          "Glass partition",
          "Mirror fitting",
          "Toughened glass work",
          "Glass table top",
          "Safety film application",
          "Other (please describe)"
        ]
      },
      {
        "id": "rolling_shutters_gates",
        "name": "Rolling Shutters and Gates",
        "code": "DWL-05",
        "issues": [
          "Rolling shutter jammed",
          "Shutter motor fault",
          "Shutter spring broken",
          "Gate hinge broken",
          "Gate welding",
          "New gate",
          "Shutter lock fault",
          "Remote shutter issue",
          "Other (please describe)"
        ]
      },
      {
        "id": "welding_fabrication",
        "name": "Welding and Fabrication",
        "code": "DWL-06",
        "issues": [
          "Grill fabrication",
          "Staircase railing",
          "Shed or canopy",
          "MS gate repair",
          "Balcony railing",
          "Frame or stand fabrication",
          "Metal door repair",
          "Rust treatment",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "gardening",
    "name": "Gardening and Landscaping",
    "code": "GAR",
    "description": "Lawn mowing, trees & pruning, drip irrigation, landscape design & garden lights",
    "image": "/services/gardening.png",
    "theme": {
      "bg": "#F0FDF4",
      "color": "#15803D",
      "border": "#BBF7D0"
    },
    "categories": [
      {
        "id": "lawn_plants",
        "name": "Lawn and Plants",
        "code": "GAR-01",
        "issues": [
          "Lawn mowing",
          "Lawn patchy or dry",
          "New lawn laying",
          "Plant disease",
          "Plant replacement",
          "Fertilizer application",
          "Weeding",
          "Potted plant care",
          "Soil refresh",
          "Other (please describe)"
        ]
      },
      {
        "id": "trees_pruning",
        "name": "Trees and Pruning",
        "code": "GAR-02",
        "issues": [
          "Tree trimming",
          "Tree cutting",
          "Branches near wires",
          "Palm cleaning",
          "Stump removal",
          "Fallen tree removal",
          "Other (please describe)"
        ]
      },
      {
        "id": "irrigation_systems",
        "name": "Irrigation Systems",
        "code": "GAR-03",
        "issues": [
          "Drip irrigation fault",
          "Sprinkler not working",
          "Pipe leaking",
          "Timer or controller fault",
          "New irrigation setup",
          "Low pressure",
          "Other (please describe)"
        ]
      },
      {
        "id": "landscaping_design",
        "name": "Landscaping and Design",
        "code": "GAR-04",
        "issues": [
          "Garden design",
          "Terrace garden",
          "Vertical garden",
          "Water feature",
          "Rock garden",
          "Pathway or paving",
          "Balcony garden",
          "Other (please describe)"
        ]
      },
      {
        "id": "garden_lighting",
        "name": "Garden Lighting and Fixtures",
        "code": "GAR-05",
        "issues": [
          "Garden light fault",
          "Pergola or gazebo",
          "Outdoor furniture assembly",
          "Garden fence repair",
          "Compost setup",
          "Other (please describe)"
        ]
      }
    ]
  },
  {
    "id": "handyman",
    "name": "Handyman and General Services",
    "code": "GEN",
    "description": "Mounting & fitting, minor repairs, furniture shifting, maintenance inspection & emergency",
    "image": "/services/handyman.png",
    "theme": {
      "bg": "#F8FAFC",
      "color": "#334155",
      "border": "#CBD5E1"
    },
    "categories": [
      {
        "id": "mounting_fitting",
        "name": "Mounting and Fitting",
        "code": "GEN-01",
        "issues": [
          "TV wall mounting",
          "Shelf fitting",
          "Curtain rod fitting",
          "Picture or frame hanging",
          "Mirror hanging",
          "Hook or hanger fitting",
          "Blinds installation",
          "Drilling work",
          "Other (please describe)"
        ]
      },
      {
        "id": "minor_repairs",
        "name": "Minor Repairs",
        "code": "GEN-02",
        "issues": [
          "Door or window minor fix",
          "Furniture tightening",
          "Caulking and sealing",
          "Sticking tile or skirting",
          "Small plumbing fix",
          "Small electrical fix",
          "Child-proofing fixtures",
          "Other (please describe)"
        ]
      },
      {
        "id": "shifting_lifting",
        "name": "Shifting and Lifting",
        "code": "GEN-03",
        "issues": [
          "Furniture moving inside home",
          "Appliance moving",
          "Heavy lifting",
          "Packing help",
          "Unpacking and arranging",
          "Other (please describe)"
        ]
      },
      {
        "id": "maintenance_inspection",
        "name": "Maintenance Contracts and Inspection",
        "code": "GEN-04",
        "issues": [
          "Annual maintenance contract",
          "Home inspection",
          "Pre-rental inspection",
          "Quotation or site visit",
          "Preventive maintenance visit",
          "Apartment or society maintenance",
          "Other (please describe)"
        ]
      },
      {
        "id": "emergency_other",
        "name": "Emergency and Other",
        "code": "GEN-05",
        "issues": [
          "Emergency call-out (any service)",
          "Not sure which service I need",
          "Multiple services at one visit",
          "Other issue (describe)",
          "Other (please describe)"
        ]
      }
    ]
  }
];

export default SERVICE_CATALOGUE_TAXONOMY;
