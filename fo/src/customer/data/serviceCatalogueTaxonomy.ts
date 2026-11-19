// Authoritative Service Catalogue Taxonomy for FieldOps Commander
// Generated from FieldOps Commander Service Catalogue (16 Service Types, 115 Categories, 1070 Issues)

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
        "name": "Lights, Bulbs & Tube Lights",
        "code": "ELE-01",
        "issues": [
          "Bulb & holder replacement",
          "Tube light repair or installation",
          "Ceiling light installation or replacement",
          "Wall light installation or replacement",
          "Outdoor light installation or replacement",
          "Decorative light or chandelier installation"
        ]
      },
      {
        "id": "wiring_cabling",
        "name": "House Wiring & Cables",
        "code": "ELE-02",
        "issues": [
          "New House Wiring Installation",
          "Old Wiring Replacement",
          "Damaged or Exposed Wire Repair",
          "Short Circuit & Wiring Repair",
          "Burning Smell & Overheating Check",
          "Loose Wire Connection Repair",
          "Hidden Wiring Fault Detection",
          "Rat-Damaged Wire Repair",
          "Electrical Conduit & Casing Installation",
          "Additional Wiring & New Connection"
        ]
      },
      {
        "id": "switches_sockets",
        "name": "Switches, Sockets & Plug Points",
        "code": "ELE-03",
        "issues": [
          "Switch Repair & Replacement",
          "Socket Repair & Replacement",
          "Switchboard Repair & Replacement",
          "New Switchboard Installation",
          "New Plug Point Installation",
          "Plug Top Replacement",
          "Modular Switch Upgrade",
          "USB Charging Socket Installation",
          "Sparking Switch or Socket Repair",
          "Burnt or Overheated Switchboard Repair",
          "Two-Way & Staircase Switch Repair"
        ]
      },
      {
        "id": "fans_ventilation",
        "name": "Fans & Exhaust Fans",
        "code": "ELE-04",
        "issues": [
          "Ceiling Fan Repair",
          "Fan Speed & Noise Repair",
          "Fan Wobbling & Balancing",
          "Fan Regulator Repair & Replacement",
          "Ceiling Fan Installation",
          "Fan Replacement & Uninstallation",
          "Fan Capacitor Replacement",
          "Fan Blade Repair & Replacement",
          "Exhaust Fan Repair",
          "Exhaust Fan Installation",
          "Decorative & BLDC Fan Installation"
        ]
      },
      {
        "id": "mcb_fuse_db",
        "name": "MCB, Fuse & Distribution Box",
        "code": "ELE-05",
        "issues": [
          "MCB Tripping Problem",
          "MCB Not Turning On",
          "Fuse Replacement",
          "RCCB / ELCB Tripping Repair",
          "MCB Replacement",
          "Distribution Box Repair",
          "New Distribution Box Installation",
          "Distribution Box Upgrade",
          "Burning Smell & Overheating Repair",
          "Phase Problem & Load Balancing",
          "Other Electrical Issue"
        ]
      },
      {
        "id": "inverter_ups",
        "name": "Inverter, UPS & Battery",
        "code": "ELE-07",
        "issues": [
          "Inverter Not Charging Repair",
          "Inverter Backup Problem",
          "Inverter Beeping & Warning Repair",
          "Inverter Installation",
          "Inverter Replacement",
          "Battery Replacement",
          "Battery Water Level Check & Top-Up",
          "Inverter Overload & Tripping Repair",
          "UPS Repair & Installation",
          "Inverter Changeover Switch Repair",
          "Other Electrical Issue"
        ]
      },
      {
        "id": "appliance_points",
        "name": "Appliance Connections & New Points",
        "code": "ELE-08",
        "issues": [
          "Geyser Power Point Installation",
          "AC Power Point Installation",
          "Washing Machine Power Point",
          "Induction & Electric Stove Connection",
          "Heavy-Duty Power Point Installation",
          "Fridge & Oven Power Point",
          "EV Charger Point Installation",
          "Voltage Stabilizer Installation",
          "Appliance Wiring & Connection Repair",
          "New Appliance Power Point Installation",
          "Other Electrical Issue"
        ]
      },
      {
        "id": "doorbell_intercom",
        "name": "Doorbell & Intercom",
        "code": "ELE-09",
        "issues": [
          "Doorbell Not Working Repair",
          "New Doorbell Installation",
          "Video Doorbell Installation",
          "Video Doorbell Repair",
          "Intercom Not Working Repair",
          "New Intercom Installation",
          "Doorbell Chime & Transformer Repair",
          "Gate Intercom Installation & Repair",
          "Other Electrical Issue"
        ]
      },
      {
        "id": "safety_earthing",
        "name": "Earthing & Electrical Safety",
        "code": "ELE-10",
        "issues": [
          "Earthing Problem Repair",
          "New Earthing Installation",
          "Earthing Resistance Testing",
          "Electrical Safety Inspection",
          "Electrical Thermal Scanning",
          "Surge Protector Installation",
          "Lightning Arrester Installation",
          "Home Electrical Safety Check",
          "Pre-Purchase Electrical Inspection",
          "Other Electrical Issue"
        ]
      },
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
        "name": "Taps & Faucets",
        "code": "PLU-01",
        "issues": [
          "Tap Leakage Repair",
          "Low Water Flow Repair",
          "Tap Handle Repair & Replacement",
          "Tap Replacement",
          "Mixer Tap Installation",
          "Loose Tap Repair",
          "Bib Cock & Garden Tap Repair",
          "Sensor Tap Repair",
          "Tap Spout Repair & Replacement",
          "Other Tap & Faucet Issue"
        ]
      },
      {
        "id": "pipes_pipelines",
        "name": "Pipes & Plumbing Lines",
        "code": "PLU-02",
        "issues": [
          "Pipe Leakage Repair",
          "Burst Pipe Repair",
          "Pipe Joint Leakage Repair",
          "Pipe Replacement (PVC, CPVC & GI)",
          "Noisy Pipe & Water Hammer Repair",
          "New Pipe Line Installation",
          "Rusted Pipe Replacement",
          "Pipe Clamp & Support Repair",
          "Water Meter Leakage Repair",
          "Other Pipe & Pipeline Issue"
        ]
      },
      {
        "id": "drainage_blockage",
        "name": "Drainage & Blockage",
        "code": "PLU-03",
        "issues": [
          "Kitchen Sink Blockage Removal",
          "Bathroom Drain Cleaning",
          "Floor Drain Blockage Removal",
          "Drain Bad Smell Removal",
          "Main Drain Overflow Repair",
          "Slow Drainage Problem",
          "Grease Trap Cleaning",
          "Roof & Rainwater Drain Cleaning",
          "Damaged Drain Pipe Repair",
          "Other Drainage Issue"
        ]
      },
      {
        "id": "toilet_sanitary",
        "name": "Toilet & Sanitary Fittings",
        "code": "PLU-04",
        "issues": [
          "Flush Tank Leakage Repair",
          "Flush System Repair",
          "Toilet Seat Replacement",
          "Toilet Blockage Removal",
          "Toilet Base Leakage Repair",
          "Loose Toilet Repair",
          "New Toilet Installation",
          "Health Faucet Repair & Replacement",
          "Urinal Flush Repair",
          "Continuous Flush Water Leakage Repair",
          "Concealed Flush Tank Repair",
          "Other Toilet & Sanitary Issue"
        ]
      },
      {
        "id": "wash_basin_sink",
        "name": "Washbasin & Kitchen Sink",
        "code": "PLU-05",
        "issues": [
          "Washbasin Leakage Repair",
          "Cracked Washbasin Replacement",
          "New Washbasin Installation",
          "Sink Trap Leakage Repair",
          "Basin Waste Coupling Repair",
          "Washbasin Pop-up Waste Repair",
          "New Kitchen Sink Installation",
          "Kitchen Sink Overflow Repair",
          "Kitchen Sink Drainage Repair",
          "Loose Washbasin Fixing",
          "Other Washbasin & Sink Issue"
        ]
      },
      {
        "id": "tank_motor_pump",
        "name": "Water Tanks, Pumps & Motors",
        "code": "PLU-06",
        "issues": [
          "Overhead Tank Overflow Repair",
          "Water Tank Leakage Repair",
          "Float Valve Repair & Replacement",
          "Water Motor Not Starting Repair",
          "Motor Running Without Water Supply",
          "Water Pump Noise Repair",
          "Water Pump Overheating Repair",
          "Pump Auto Starter & Controller Repair",
          "Borewell Motor Repair",
          "New Water Tank Installation",
          "Water Tank Level Indicator Repair",
          "Water Pump Installation",
          "Water Tank Cleaning",
          "Other Water Tank & Pump Issue"
        ]
      },
      {
        "id": "geyser_hot_water",
        "name": "Geyser & Water Heater",
        "code": "PLU-07",
        "issues": [
          "Geyser Water Leakage Repair",
          "Geyser Not Heating Water",
          "New Geyser Installation",
          "Geyser Pressure Relief Valve Repair",
          "Hot Water Pipe Leakage Repair",
          "Solar Water Heater Plumbing",
          "Hot & Cold Water Mixing Problem",
          "Other Geyser & Water Heater Issue"
        ]
      },
      {
        "id": "shower_fittings",
        "name": "Shower & Bathroom Fittings",
        "code": "PLU-08",
        "issues": [
          "Low Shower Water Pressure Repair",
          "Shower Head Replacement",
          "Shower Diverter Repair & Replacement",
          "Concealed Shower Valve Leakage Repair",
          "Overhead Shower Installation",
          "Bathtub Installation & Repair",
          "Shower Cubicle Installation",
          "Bathroom Accessories Installation",
          "Other Shower & Bathroom Fittings Issue"
        ]
      },
      {
        "id": "water_pressure",
        "name": "Water Supply & Pressure Problems",
        "code": "PLU-09",
        "issues": [
          "Low Water Pressure Problem",
          "No Water Supply Problem",
          "Water Pressure Booster Pump Installation",
          "Water Hammer Problem",
          "Hot & Cold Water Supply Problem",
          "Pressure Reducing Valve Repair",
          "Dirty Water Supply Problem",
          "Air Lock in Water Pipes",
          "Other Water Supply Issue"
        ]
      },
      {
        "id": "leakage_seepage",
        "name": "Water Leakage & Seepage",
        "code": "PLU-10",
        "issues": [
          "Ceiling Water Leakage Repair",
          "Wall Dampness & Leakage Repair",
          "Bathroom Floor Leakage Repair",
          "Terrace Water Tank Leakage Repair",
          "Hidden Water Leakage Detection",
          "Kitchen Cabinet Water Leakage Repair",
          "Basement Water Seepage Repair",
          "Other Water Leakage & Seepage Issue"
        ]
      },
      {
        "id": "sewage_septic",
        "name": "Sewerage & Septic Tank",
        "code": "PLU-11",
        "issues": [
          "Septic Tank Emptying Service",
          "Sewer Line Blockage Removal",
          "Sewage Bad Smell Problem",
          "Sewer & Drain Backflow Repair",
          "Inspection Chamber Overflow Repair",
          "Soak Pit Repair & Cleaning",
          "Septic Tank Cleaning",
          "CCTV Sewer Line Inspection",
          "Other Sewerage & Septic Tank Issue"
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
          "AC Not Cooling",
          "Indoor Unit Water Leakage",
          "AC Making Noise",
          "Bad Smell from AC",
          "AC Remote Not Working",
          "Ice Formation on AC Coil",
          "AC Tripping Power Supply",
          "AC Not Switching On",
          "AC Error Code Problem",
          "Refrigerant Gas Leakage",
          "AC Compressor Not Starting",
          "Outdoor Fan Not Working",
          "AC Temperature Sensor Fault",
          "AC Swing Flap Not Working",
          "Other Split AC Issue"
        ]
      },
      {
        "id": "window_ac",
        "name": "Window AC",
        "code": "ACR-02",
        "issues": [
          "Window AC Not Cooling",
          "Window AC Making Noise",
          "Window AC Water Leakage",
          "Compressor Tripping Problem",
          "Thermostat Not Working",
          "Window AC Fan Motor Repair",
          "AC Knob & Switch Repair",
          "Bad Smell from Window AC",
          "Window AC Frame Repair",
          "Other Window AC Issue"
        ]
      },
      {
        "id": "cassette_ducted",
        "name": "Cassette, Ductable & VRF AC Systems",
        "code": "ACR-03",
        "issues": [
          "Cassette / Ducted AC Not Cooling",
          "Cassette AC Water Leakage",
          "AC Drain Pump Repair",
          "AC Duct Leakage Repair",
          "AC Controller Not Working",
          "Outdoor Unit Error Repair",
          "Zone Cooling Problem",
          "AC Filter Cleaning",
          "Refrigerant Gas Leakage Repair",
          "Other Cassette / Ducted / VRF Issue"
        ]
      },
      {
        "id": "ac_installation",
        "name": "AC Installation, Uninstallation & Relocation",
        "code": "ACR-04",
        "issues": [
          "New AC Installation",
          "AC Uninstallation",
          "AC Shifting & Relocation",
          "AC Copper Pipe Installation",
          "AC Outdoor Unit Stand Installation",
          "AC Drain Pipe Extension",
          "AC Stabilizer Installation",
          "AC Outdoor Unit Cage Installation",
          "New Electrical Point for AC",
          "Other AC Installation Work"
        ]
      },
      {
        "id": "ac_servicing",
        "name": "AC Service & Maintenance",
        "code": "ACR-05",
        "issues": [
          "AC General Service",
          "AC Jet Wash Deep Cleaning",
          "AC Gas Refill",
          "AC Annual Maintenance Contract (AMC)",
          "AC Filter Cleaning",
          "AC Evaporator & Condenser Coil Cleaning",
          "AC Pre-Summer Service",
          "AC Performance Check-up",
          "Other AC Maintenance Service"
        ]
      },
      {
        "id": "refrigerator_domestic",
        "name": "Home Refrigerator Repair",
        "code": "ACR-06",
        "issues": [
          "Refrigerator Not Cooling",
          "Freezer Not Freezing",
          "Refrigerator Water Leakage",
          "Refrigerator Making Noise",
          "Excessive Ice Build-up",
          "Refrigerator Door Gasket Replacement",
          "Refrigerator Light Not Working",
          "Refrigerator Compressor Not Starting",
          "Refrigerator Thermostat Repair",
          "Ice Maker Not Working",
          "Refrigerator Door Not Closing",
          "Bad Smell from Refrigerator",
          "Other Refrigerator Issue",
          "Refrigerator PCB / Control Board Repair",
          "Refrigerator Defrost Problem"
        ]
      },
      {
        "id": "commercial_refrigeration",
        "name": "Commercial Refrigeration",
        "code": "ACR-07",
        "issues": [
          "Cold Room Not Cooling",
          "Deep Freezer Repair",
          "Display Chiller Repair",
          "Visi Cooler Repair",
          "Bottle Cooler Repair",
          "Commercial Ice Machine Repair",
          "Walk-in Cooler Repair",
          "Temperature Controller Repair",
          "Condenser Coil Cleaning",
          "Commercial Refrigerant Gas Refill",
          "Other Commercial Refrigeration Issue"
        ]
      },
      {
        "id": "air_coolers_purifiers",
        "name": "Air Coolers, Air Purifiers & Humidifiers",
        "code": "ACR-08",
        "issues": [
          "Air Cooler Pump Not Working",
          "Air Cooler Motor Repair",
          "Air Cooler Cooling Pad Replacement",
          "Air Cooler Water Leakage",
          "Air Purifier Filter Replacement",
          "Air Purifier Not Working",
          "Humidifier Repair",
          "Air Cooler General Service",
          "Other Air Cooler & Purifier Issue"
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
          "Washing Machine Not Starting",
          "Water Not Draining",
          "Drum Not Spinning",
          "Water Not Filling",
          "Excessive Vibration",
          "Unusual Noise During Washing",
          "Door Lock Problem",
          "Water Leakage",
          "Error Code on Display",
          "Clothes Not Washing Properly",
          "Drum Jammed",
          "Water Inlet Valve Problem",
          "Control Panel Not Working",
          "Washing Machine Installation & Demo",
          "Other Washing Machine Problem"
        ]
      },
      {
        "id": "television",
        "name": "TV (LED, LCD & Smart TV)",
        "code": "APP-02",
        "issues": [
          "TV Screen Not Displaying",
          "No Sound",
          "Lines on TV Screen",
          "Broken TV Screen",
          "Screen Backlight Not Working",
          "HDMI Port Not Working",
          "Wi-Fi / Smart TV Not Working",
          "TV Remote Not Working",
          "TV Wall Mounting & Installation",
          "TV Software / App Problem",
          "TV Stuck on Logo",
          "TV Not Switching On",
          "Other TV Problem"
        ]
      },
      {
        "id": "microwave_otg",
        "name": "Microwave Oven & OTG",
        "code": "APP-03",
        "issues": [
          "Microwave Not Heating",
          "Turntable Not Rotating",
          "Sparks Inside Microwave",
          "Door Not Closing Properly",
          "Display Not Working",
          "Buttons Not Responding",
          "Unusual Noise During Operation",
          "Circuit Breaker Tripping",
          "Grill Heater Not Working",
          "Other Microwave / OTG Problem"
        ]
      },
      {
        "id": "kitchen_chimney_hob",
        "name": "Kitchen Chimney & Hob",
        "code": "APP-04",
        "issues": [
          "Chimney Suction Is Low",
          "Chimney Making Noise",
          "Oil Collector Problem",
          "Chimney Filter Cleaning",
          "Auto-Clean Not Working",
          "Gas Burner Not Working Properly",
          "Gas Stove Ignition Not Working",
          "Broken Hob Glass",
          "Gas Leakage (Emergency)",
          "Gas Regulator / Pipe Replacement",
          "Chimney Installation",
          "Other Chimney / Hob Problem"
        ]
      },
      {
        "id": "mixer_grinder",
        "name": "Mixer Grinder & Blender",
        "code": "APP-05",
        "issues": [
          "Motor Not Working",
          "Mixer Jar Leakage",
          "Blade Damaged / Not Cutting",
          "Unusual Noise",
          "Burning Smell from Motor",
          "Jar Coupler Damaged",
          "Overload Protector Keeps Tripping",
          "Power Switch Not Working",
          "Other Mixer Grinder Problem"
        ]
      },
      {
        "id": "electric_water_heater",
        "name": "Electric Geyser & Water Heater",
        "code": "APP-06",
        "issues": [
          "Geyser Not Heating Water",
          "Thermostat Not Working",
          "Heating Element Damaged",
          "Geyser Water Leakage",
          "Geyser Tripping Circuit Breaker",
          "Automatic Cut-Off Not Working",
          "Indicator Light Not Working",
          "Anode Rod Replacement",
          "Geyser Descaling / Cleaning",
          "Other Geyser Problem"
        ]
      },
      {
        "id": "dishwasher",
        "name": "Dishwasher",
        "code": "APP-07",
        "issues": [
          "Dishwasher Not Draining",
          "Dishes Not Getting Clean",
          "Door Not Closing Properly",
          "Detergent Dispenser Not Working",
          "Error Code on Display",
          "Water Leakage",
          "Dishwasher Not Starting",
          "Bad Smell from Dishwasher",
          "Other Dishwasher Problem"
        ]
      },
      {
        "id": "small_kitchen_appliances",
        "name": "Small Kitchen Appliances",
        "code": "APP-08",
        "issues": [
          "Electric Iron Not Heating",
          "Induction Cooktop Not Working",
          "Electric Kettle Not Working",
          "Rice Cooker Not Working",
          "Toaster Not Working",
          "Air Fryer Not Working",
          "Coffee Maker Not Working",
          "Food Processor Not Working",
          "Hand Blender Not Working",
          "Other Kitchen Appliance Problem"
        ]
      },
      {
        "id": "vacuum_cleaner",
        "name": "Vacuum Cleaner & Floor Care",
        "code": "APP-09",
        "issues": [
          "Low Suction / Weak Cleaning",
          "Motor Not Working",
          "Battery Not Charging",
          "Brush Not Rotating",
          "Dust Bag / Filter Blocked",
          "Robot Vacuum Mapping Problem",
          "Other Vacuum Cleaner Problem",
          "Vacuum Cleaner Overheating / Burning Smell"
        ]
      },
      {
        "id": "water_dispenser_others",
        "name": "Water Dispenser & Other Appliances",
        "code": "APP-10",
        "issues": [
          "Water Dispenser Not Cooling",
          "Water Dispenser Not Heating",
          "Water Dispenser Leakage",
          "Dispenser Tap Not Working",
          "Sewing machine repair",
          "Room Heater Not Working",
          "Hair Dryer / Trimmer Not Working",
          "Other Appliance Problem"
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
        "name": "Furniture Repair & Restoration",
        "code": "CAR-01",
        "issues": [
          "Loose Furniture Joints",
          "Broken Table or Chair Leg",
          "Drawer Stuck or Jammed",
          "Broken Hinge",
          "Wobbly Table",
          "Furniture Scratch Repair",
          "Broken Sofa Frame",
          "Broken Bed Frame",
          "Chair Repair",
          "Cupboard Door Alignment",
          "Damaged Tabletop",
          "Furniture Wood Cracked or Damaged",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "modular_kitchen_wardrobe",
        "name": "Modular Kitchen and Wardrobe",
        "code": "CAR-02",
        "issues": [
          "Wardrobe Installation",
          "Hinge or Drawer Channel Replacement",
          "Cabinet Shutter Alignment",
          "Soft-Close Hinge Fitting",
          "Kitchen Countertop Repair",
          "Cabinet Handle Replacement",
          "Modular Kitchen Modification",
          "Laminate Peeling or Replacement",
          "Kitchen Basket or Pull-Out Unit Installation",
          "Water-Damaged Cabinet Repair",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "wooden_doors",
        "name": "Wooden Door Repair & Installation",
        "code": "CAR-03",
        "issues": [
          "Door Not Closing Properly",
          "Door Stuck or Jammed",
          "Door Swollen Due to Moisture",
          "Door Hinge Replacement",
          "Termite-Damaged Door Frame",
          "New Wooden Door Installation",
          "Wooden Door Polishing",
          "Door Scraping Against Floor",
          "Door Handle Installation or Replacement",
          "Door Gap and Alignment Repair",
          "Door Lock or Latch Not Working",
          "Door Frame Damaged or Cracked",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "custom_furniture",
        "name": "Custom Furniture Design & Making",
        "code": "CAR-04",
        "issues": [
          "Custom Bed Making",
          "Custom Wardrobe Making",
          "Custom TV Unit Making",
          "Custom Study Table Making",
          "Custom Shoe Rack Making",
          "Custom Pooja Unit Making",
          "Custom Bookshelf Making",
          "Custom Dining Table Making",
          "Custom Dressing Table Making",
          "Custom Kids' Furniture Making",
          "Custom Office Furniture Making",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "polishing_finishing",
        "name": "Furniture Polishing & Painting",
        "code": "CAR-05",
        "issues": [
          "Wooden Furniture Polishing",
          "Melamine or PU Polish Finish",
          "Varnish Touch-Up",
          "Furniture Scratch Removal",
          "Furniture Repainting or Colour Change",
          "Old Furniture Polishing and Restoration",
          "Furniture Paint Peeling",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "furniture_assembly",
        "name": "Furniture Assembly & Installation",
        "code": "CAR-06",
        "issues": [
          "Ready-to-Assemble Furniture Assembly",
          "Furniture Dismantling and Reassembly",
          "Bed Assembly",
          "Wardrobe Assembly",
          "Table and Chair Assembly",
          "Furniture Installation",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "partitions_ceilings",
        "name": "Woodwork, Partitions & False Ceilings",
        "code": "CAR-07",
        "issues": [
          "Wooden Partition Installation",
          "Plywood Partition Installation",
          "Wooden False Ceiling Installation",
          "Wooden Wall Panelling",
          "Loft Storage or Mezzanine Work",
          "Wooden Partition Repair",
          "False Ceiling Panel Repair",
          "Wooden Pergola or Deck Installation",
          "Other (Please Describe)"
        ]
      }
    ]
  },
  {
    "id": "painting",
    "name": "Painting, Wall Repair & Waterproofing",
    "code": "PNT",
    "description": "Interior and exterior painting, wood and metal painting, wall crack repair, texture painting and terrace waterproofing.",
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
          "Full House Interior Painting",
          "Single Room Painting",
          "Ceiling painting",
          "Paint Touch-Up",
          "Texture Wall Painting",
          "Feature Wall Painting",
          "Stencil Wall Painting",
          "Wallpaper installation",
          "Paint Colour Selection",
          "Kids' Room Wall Design",
          "Other Interior Painting Work"
        ]
      },
      {
        "id": "exterior_painting",
        "name": "Exterior Painting",
        "code": "PNT-02",
        "issues": [
          "Full exterior painting",
          "Compound wall painting",
          "Main Gate Painting",
          "Terrace & Parapet Wall Painting",
          "Weatherproof Exterior Painting",
          "Exterior Texture Painting",
          "Other Exterior Painting Work"
        ]
      },
      {
        "id": "wood_metal_painting",
        "name": "Wood & Metal Painting",
        "code": "PNT-03",
        "issues": [
          "Door & Furniture Enamel Painting",
          "PU Polish & Finish",
          "Window & Metal Grill Painting",
          "Metal Gate Painting",
          "Rust Removal & Anti-Rust Primer",
          "Rolling Shutter Painting",
          "Metal Railing Painting",
          "Other Wood & Metal Painting"
        ]
      },
      {
        "id": "wall_defects",
        "name": "Wall Repair & Crack Filling",
        "code": "PNT-04",
        "issues": [
          "Paint Peeling",
          "Wall Crack Repair",
          "Damp Wall Treatment",
          "Water Seepage Repair",
          "Fungus & Mould Removal",
          "White Salt Deposits on Walls",
          "Paint Bubbling & Blistering",
          "Wall Putty & Surface Repair",
          "Hairline Crack Filling",
          "Ceiling Water Stain Repair",
          "Other Wall Repair Issue"
        ]
      },
      {
        "id": "waterproofing",
        "name": "Waterproofing Services",
        "code": "PNT-05",
        "issues": [
          "Terrace & Roof Waterproofing",
          "Bathroom waterproofing",
          "Basement waterproofing",
          "Water tank waterproofing",
          "External wall waterproofing",
          "Balcony waterproofing",
          "Kitchen waterproofing",
          "Expansion Joint Sealing",
          "Crack Injection Treatment",
          "Other Waterproofing Work"
        ]
      },
      {
        "id": "special_finishes",
        "name": "Special Finishes",
        "code": "PNT-06",
        "issues": [
          "Stucco Texture Finish",
          "3D Wall Panel Installation",
          "Anti-Bacterial Wall Coating",
          "Heat-Reflective Roof Coating",
          "Epoxy Floor Coating",
          "Fire-Resistant Coating",
          "Other Special Finish"
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
          "Full Home Deep Cleaning",
          "Kitchen Deep Cleaning",
          "Bathroom Deep Cleaning",
          "Balcony Cleaning",
          "Window and Glass Cleaning",
          "Post-Construction Cleaning",
          "Move-In / Move-Out Cleaning",
          "Festival Deep Cleaning",
          "Fan and Light Cleaning",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "sofa_carpet_curtain",
        "name": "Sofa, Carpet, Mattress & Curtain Cleaning",
        "code": "CLN-02",
        "issues": [
          "Sofa Shampooing",
          "Carpet Deep Cleaning",
          "Mattress Deep Cleaning",
          "Curtain Cleaning",
          "Upholstery Stain Removal",
          "Bad Odour Removal",
          "Dust Mite Treatment",
          "Leather Sofa Cleaning",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "water_tank_sump",
        "name": "Water Tank & Sump Cleaning",
        "code": "CLN-03",
        "issues": [
          "Overhead Water Tank Cleaning",
          "Underground Sump Cleaning",
          "Water Tank Disinfection",
          "Algae and Sludge Removal",
          "Hard Water Scale Removal",
          "Water Tank Descaling",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "kitchen_cleaning",
        "name": "Kitchen Deep Cleaning",
        "code": "CLN-04",
        "issues": [
          "Kitchen Chimney Degreasing",
          "Kitchen Cabinet Cleaning",
          "Kitchen Tile and Backsplash Cleaning",
          "Kitchen Appliance Cleaning",
          "Gas Stove and Hob Cleaning",
          "Exhaust Fan Cleaning",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "bathroom_cleaning",
        "name": "Bathroom Deep Cleaning",
        "code": "CLN-05",
        "issues": [
          "Hard Water Stain Removal",
          "Bathroom Tile and Grout Cleaning",
          "Limescale Removal",
          "Bathroom Drain Cleaning",
          "Shower Glass Cleaning",
          "Mould and Mildew Removal",
          "Toilet and Washbasin Deep Cleaning"
        ]
      },
      {
        "id": "office_commercial_clean",
        "name": "Office & Commercial Cleaning",
        "code": "CLN-06",
        "issues": [
          "Daily Office Housekeeping",
          "Floor Scrubbing and Cleaning",
          "Office Pantry Cleaning",
          "Glass Facade Cleaning",
          "Office Washroom Cleaning",
          "Office Carpet Cleaning",
          "Staircase Cleaning",
          "Parking Area Cleaning",
          "Other (Please Describe)"
        ]
      },
      {
        "id": "specialised_cleaning",
        "name": "Specialised Cleaning Services",
        "code": "CLN-07",
        "issues": [
          "Marble Floor Polishing",
          "Disinfection and Sanitization",
          "Building Facade Cleaning",
          "Solar Panel Cleaning",
          "Terrace Cleaning",
          "Septic Tank Cleaning",
          "Industrial Deep Cleaning",
          "Other (Please Describe)"
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
    "description": "CCTV cameras, DVR/NVR, biometric access, alarms, video door phone & gates",
    "image": "/services/security.png",
    "theme": {
      "bg": "#DCFCE7",
      "color": "#16A34A",
      "border": "#BBF7D0"
    },
    "categories": [
      {
        "id": "cctv_cameras",
        "name": "CCTV Cameras & Installation",
        "code": "SEC-01",
        "issues": [
          "No Picture / Video Feed",
          "Blurry Camera Footage",
          "Night Vision Not Working",
          "Camera Offline / Disconnected",
          "New CCTV Camera Installation",
          "Camera Angle Adjustment / Relocation",
          "Camera Cable Damaged",
          "Camera Lens Cleaning / Fogging",
          "Camera Microphone / Audio Fault",
          "PTZ Camera Movement Not Working",
          "Other CCTV Camera Issue",
          "Camera Power Supply Fault"
        ]
      },
      {
        "id": "dvr_nvr",
        "name": "DVR, NVR & Recording Systems",
        "code": "SEC-02",
        "issues": [
          "Camera Not Recording",
          "DVR / NVR Not Turning On",
          "Hard Disk Not Detected",
          "No Display on Monitor",
          "Recording Storage Full",
          "DVR / NVR Password Reset",
          "Recorded Video Not Playing",
          "Mobile / Remote Viewing Setup",
          "Date & Time Incorrect",
          "CCTV Mobile App Not Connecting",
          "Video Recording Backup / Export",
          "Other DVR / NVR Issue"
        ]
      },
      {
        "id": "biometric_access",
        "name": "Biometric Attendance & Access Control",
        "code": "SEC-03",
        "issues": [
          "Fingerprint Not Recognized",
          "Access Door Lock Not Working",
          "Access Card Not Reading",
          "Face Recognition Not Working",
          "Attendance Data Not Syncing",
          "Magnetic Door Lock Not Working",
          "New Access Control Installation",
          "User Registration / Access Management",
          "Other Biometric / Access Control Issue"
        ]
      },
      {
        "id": "alarms_sensors",
        "name": "Security Alarms & Sensors",
        "code": "SEC-04",
        "issues": [
          "False Alarm Triggering",
          "Alarm Siren Not Working",
          "Motion Sensor Not Detecting",
          "Door / Window Sensor Not Working",
          "Fire Alarm Control Panel Fault",
          "Smoke Detector Beeping / Low Battery",
          "Gas Leak Detector Not Working",
          "Emergency Panic Button Not Working",
          "Other Alarm / Sensor Issue"
        ]
      },
      {
        "id": "video_door_phone",
        "name": "Video Door Phone & Intercom",
        "code": "SEC-05",
        "issues": [
          "Indoor Monitor Screen Not Working",
          "No Sound / Audio Not Working",
          "Doorbell Call Not Ringing",
          "New Video Door Phone Installation",
          "Door Phone Wiring / Cable Fault",
          "Door Unlock Button Not Working",
          "Indoor Monitor Replacement",
          "Other Video Door Phone Issue"
        ]
      },
      {
        "id": "gate_automation",
        "name": "Automatic Gates & Boom Barriers",
        "code": "SEC-06",
        "issues": [
          "Sliding Gate Motor Not Working",
          "Gate Remote Not Working",
          "Swing Gate Motor Not Working",
          "Boom Barrier Not Opening / Closing",
          "Gate Limit Switch Fault",
          "Safety Sensor Not Working",
          "Gate Stops or Reverses Midway",
          "Additional Remote Programming",
          "Other Gate Automation Issue"
        ]
      },
      {
        "id": "electric_fence",
        "name": "Electric Fencing & Perimeter Security",
        "code": "SEC-07",
        "issues": [
          "Electric Fence Has No Power",
          "Electric Fence False Alarm",
          "Fence Energizer Not Working",
          "Electric Fence Wire Damaged",
          "New Electric Fence Installation",
          "Other Electric Fence Issue",
          "Electric Fence Voltage Too Low",
          "Electric Fence Short Circuit / Ground Fault",
          "Electric Fence Maintenance & Inspection"
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
        "name": "Domestic RO Water Purifier",
        "code": "WTR-01",
        "issues": [
          "Water not getting purified",
          "Bad taste or smell in water",
          "Water flow is very slow",
          "Water leakage",
          "Unusual noise from purifier",
          "High TDS in purified water",
          "Auto shut-off not working",
          "RO membrane problem",
          "RO filter replacement",
          "Warning light or beeping",
          "RO booster pump not working",
          "Power supply or adapter problem",
          "Storage tank not filling or holding water",
          "Other (please describe)"
        ]
      },
      {
        "id": "uv_uf_gravity",
        "name": "UV, UF & Gravity Water Purifiers",
        "code": "WTR-02",
        "issues": [
          "UV lamp not working",
          "UF membrane blocked",
          "Slow water flow from gravity filter",
          "Filter candle replacement",
          "Water leakage from tap or tank",
          "Bad smell or taste in water",
          "Other (please describe)"
        ]
      },
      {
        "id": "commercial_ro_plant",
        "name": "Commercial & Industrial RO Plants",
        "code": "WTR-03",
        "issues": [
          "RO plant not producing water",
          "Low water pressure",
          "RO membrane blocked or scaled",
          "Antiscalant dosing system problem",
          "RO storage tank cleaning",
          "RO pump not working",
          "Annual Maintenance Contract (AMC)",
          "Water quality testing",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_softener",
        "name": "Water Softeners & Filter Systems",
        "code": "WTR-04",
        "issues": [
          "Hard water coming from tap",
          "Water softener resin regeneration",
          "Iron removal filter not working",
          "Sediment filter replacement",
          "Whole-house water filter installation",
          "Chlorine or bad smell in water",
          "Water softener salt refill",
          "Other (please describe)"
        ]
      },
      {
        "id": "water_cooler_dispenser",
        "name": "Water Coolers & Dispensers",
        "code": "WTR-05",
        "issues": [
          "Water cooler not cooling",
          "Hot water not dispensing",
          "Water leakage",
          "Water dispensing tap not working",
          "Water filter replacement",
          "Bottle sensor not working",
          "Compressor not working",
          "Other (please describe)"
        ]
      },
      {
        "id": "purifier_installation",
        "name": "RO Installation & Maintenance",
        "code": "WTR-06",
        "issues": [
          "New water purifier installation",
          "Water purifier shifting or relocation",
          "Annual Maintenance Contract (AMC)",
          "Water quality testing",
          "Water purifier removal",
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
