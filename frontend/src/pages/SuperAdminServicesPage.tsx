import { useActiveAutoRefresh } from "../hooks/useActiveAutoRefresh";
import React, { useState, useEffect, useMemo } from "react";
import {
  Wrench,
  PlusCircle,
  Search,
  CheckCircle2,
  Share2,
  Layers,
  AlertCircle,
  X,
  Zap,
  Droplet,
  Snowflake,
  Plug,
  Hammer,
  Shield,
  Check,
  ArrowRight,
  ArrowLeft,
  Trash2,
} from "lucide-react";
import {
  getAdminServices,
  createAdminServicesBatch,
  toggleServiceActive,
  deleteAdminService,
  getTaxonomySuggestions,
  type ServiceCatalogItem,
  type TaxonomySuggestionsResponse,
} from "../services/servicesCatalogService";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import ConfirmationDialog from "../components/ui/ConfirmationDialog";
import { useToast } from "../hooks/useToast";
import useAuthStore from "../store/authStore";
import { SERVICE_CATALOGUE_TAXONOMY, type TaxonomyServiceType, type TaxonomyCategory } from "../data/serviceCatalogueTaxonomy";
import { getCategoryCardImage, getIssueCardImage } from "../data/categoryImages";

// Standard 16-type, 115-category, 1070-issue taxonomy from FieldOps Service Catalogue
const KNOWN_CATEGORIES_MAP: Record<string, string[]> = {};
const KNOWN_ISSUES_MAP: Record<string, string[]> = {};

SERVICE_CATALOGUE_TAXONOMY.forEach((st) => {
  KNOWN_CATEGORIES_MAP[st.name] = st.categories.map((c) => c.name);
  st.categories.forEach((c) => {
    KNOWN_ISSUES_MAP[c.name] = c.issues;
  });
});

const ELECTRICAL_CATEGORY_LABELS: Record<string, string> = {
  "lights and lighting": "Lights, Bulbs & Tube Lights",
  "wiring and cabling": "House Wiring & Cables",
  "switches, sockets and switchboards": "Switches, Sockets & Plug Points",
  "fans and ventilation": "Fans & Exhaust Fans",
  "mcb, fuse and distribution board": "MCB, Fuse & Distribution Box",
  "inverter, ups and battery": "Inverter, UPS & Battery",
  "appliance electrical points": "Appliance Connections & New Points",
  "doorbell, intercom and low-voltage": "Doorbell & Intercom",
  "safety, earthing and inspection": "Earthing & Electrical Safety",
};

const PLUMBING_CATEGORY_LABELS: Record<string, string> = {
  "taps and faucets": "Taps & Faucets",
  "pipes and pipelines": "Pipes & Plumbing Lines",
  "drainage and blockage": "Drainage & Blockage",
  "toilet and sanitary": "Toilet & Sanitary Fittings",
  "wash basin and kitchen sink": "Washbasin & Kitchen Sink",
  "water tank, motor and pump": "Water Tanks, Pumps & Motors",
  "geyser and hot water lines": "Geyser & Water Heater",
  "shower and bathroom fittings": "Shower & Bathroom Fittings",
  "water pressure and supply": "Water Supply & Pressure Problems",
  "leakage and seepage": "Water Leakage & Seepage",
  "sewage and septic": "Sewerage & Septic Tank",
};

const HVAC_CATEGORY_LABELS: Record<string, string> = {
  "cassette, ducted and vrf systems": "Cassette, Ductable & VRF AC Systems",
  "cassette, ductable & vrf ac": "Cassette, Ductable & VRF AC Systems",
  "ac installation and relocation": "AC Installation, Uninstallation & Relocation",
  "ac installation & uninstallation": "AC Installation, Uninstallation & Relocation",
  "ac servicing and maintenance": "AC Service & Maintenance",
  "refrigerator (domestic)": "Home Refrigerator Repair",
  "home refrigerator": "Home Refrigerator Repair",
  "air coolers and air purifiers": "Air Coolers, Air Purifiers & Humidifiers",
};

const APPLIANCE_CATEGORY_LABELS: Record<string, string> = {
  "television": "TV (LED, LCD & Smart TV)",
  "microwave oven and otg": "Microwave Oven & OTG",
  "kitchen chimney and hob": "Kitchen Chimney & Hob",
  "mixer grinder and blender": "Mixer Grinder & Blender",
  "vacuum cleaner and floor care": "Vacuum Cleaner & Floor Care",
  "electric water heater (appliance)": "Electric Geyser & Water Heater",
  "water dispenser and others": "Water Dispenser & Other Appliances",
};

const CARPENTRY_CATEGORY_LABELS: Record<string, string> = {
  "furniture repair": "Furniture Repair & Restoration",
  "modular kitchen and wardrobe": "Modular Kitchen and Wardrobe",
  "wooden doors": "Wooden Door Repair & Installation",
  "custom furniture": "Custom Furniture Design & Making",
  "custom furniture making": "Custom Furniture Design & Making",
  "polishing and finishing": "Furniture Polishing & Painting",
  "furniture assembly and fitting": "Furniture Assembly & Installation",
  "partitions and wooden ceilings": "Woodwork, Partitions & False Ceilings",
  "wooden partitions & false ceilings": "Woodwork, Partitions & False Ceilings",
};

const SECURITY_CATEGORY_LABELS: Record<string, string> = {
  "cctv cameras": "CCTV Cameras & Installation",
  "dvr and nvr": "DVR, NVR & Recording Systems",
  "biometric and access control": "Biometric Attendance & Access Control",
  "alarms and sensors": "Security Alarms & Sensors",
  "video door phone and intercom": "Video Door Phone & Intercom",
  "gate and barrier automation": "Automatic Gates & Boom Barriers",
  "electric fence and perimeter": "Electric Fencing & Perimeter Security",
};

const WATER_PURIFIER_CATEGORY_LABELS: Record<string, string> = {
  "ro water purifier": "Domestic RO Water Purifier",
  "uv, uf and gravity purifiers": "UV, UF & Gravity Water Purifiers",
  "commercial and industrial ro plant": "Commercial & Industrial RO Plants",
  "water softener and filtration": "Water Softeners & Filter Systems",
  "water cooler and dispenser": "Water Coolers & Dispensers",
  "installation and maintenance": "RO Installation & Maintenance",
};

const PAINTING_CATEGORY_LABELS: Record<string, string> = {
  "wood and metal painting": "Wood & Metal Painting",
  "wall defects": "Wall Repair & Crack Filling",
  "waterproofing": "Waterproofing Services",
};

const CLEANING_CATEGORY_LABELS: Record<string, string> = {
  "sofa, carpet, mattress and curtain": "Sofa, Carpet, Mattress & Curtain Cleaning",
  "water tank and sump cleaning": "Water Tank & Sump Cleaning",
  "kitchen cleaning": "Kitchen Deep Cleaning",
  "bathroom cleaning": "Bathroom Deep Cleaning",
  "office and commercial cleaning": "Office & Commercial Cleaning",
  "specialised cleaning": "Specialised Cleaning Services",
};

const CLEANING_ISSUE_LABELS: Record<string, Record<string, string>> = {
  "home deep cleaning": {
    "full home deep clean": "Full Home Deep Cleaning",
    "kitchen deep clean": "Kitchen Deep Cleaning",
    "bathroom deep clean": "Bathroom Deep Cleaning",
    "balcony cleaning": "Balcony Cleaning",
    "window and glass cleaning": "Window and Glass Cleaning",
    "post-construction cleaning": "Post-Construction Cleaning",
    "move-in or move-out cleaning": "Move-In / Move-Out Cleaning",
    "festival cleaning": "Festival Deep Cleaning",
    "fan and light cleaning": "Fan and Light Cleaning",
    "other (please describe)": "Other (Please Describe)",
  },
  "sofa, carpet, mattress & curtain cleaning": {
    "sofa shampooing": "Sofa Shampooing",
    "carpet cleaning": "Carpet Deep Cleaning",
    "mattress cleaning": "Mattress Deep Cleaning",
    "curtain cleaning": "Curtain Cleaning",
    "stain removal": "Upholstery Stain Removal",
    "odour removal": "Bad Odour Removal",
    "dust mite treatment": "Dust Mite Treatment",
    "leather care": "Leather Sofa Cleaning",
    "other (please describe)": "Other (Please Describe)",
  },
  "water tank & sump cleaning": {
    "overhead tank cleaning": "Overhead Water Tank Cleaning",
    "underground sump cleaning": "Underground Sump Cleaning",
    "tank disinfection": "Water Tank Disinfection",
    "algae or sludge removal": "Algae and Sludge Removal",
    "water quality problem": "Hard Water Scale Removal",
    "tank repair after cleaning": "Water Tank Descaling",
    "other (please describe)": "Other (Please Describe)",
  },
  "kitchen deep cleaning": {
    "chimney degreasing": "Kitchen Chimney Degreasing",
    "cabinet cleaning": "Kitchen Cabinet Cleaning",
    "kitchen tile cleaning": "Kitchen Tile and Backsplash Cleaning",
    "appliance exterior cleaning": "Kitchen Appliance Cleaning",
    "gas stove cleaning": "Gas Stove and Hob Cleaning",
    "exhaust fan degreasing": "Exhaust Fan Cleaning",
    "other (please describe)": "Other (Please Describe)",
  },
  "bathroom deep cleaning": {
    "hard water stains": "Hard Water Stain Removal",
    "grout cleaning": "Bathroom Tile and Grout Cleaning",
    "limescale removal": "Limescale Removal",
    "drain cleaning": "Bathroom Drain Cleaning",
    "glass partition cleaning": "Shower Glass Cleaning",
    "mould in bathroom": "Mould and Mildew Removal",
    "other (please describe)": "Toilet and Washbasin Deep Cleaning",
  },
  "office & commercial cleaning": {
    "daily housekeeping": "Daily Office Housekeeping",
    "floor scrubbing": "Floor Scrubbing and Cleaning",
    "pantry cleaning": "Office Pantry Cleaning",
    "glass facade cleaning": "Glass Facade Cleaning",
    "washroom cleaning": "Office Washroom Cleaning",
    "carpet cleaning (office)": "Office Carpet Cleaning",
    "staircase cleaning": "Staircase Cleaning",
    "parking area cleaning": "Parking Area Cleaning",
    "other (please describe)": "Other (Please Describe)",
  },
  "specialised cleaning services": {
    "marble polishing": "Marble Floor Polishing",
    "disinfection and sanitization": "Disinfection and Sanitization",
    "facade cleaning": "Building Facade Cleaning",
    "solar panel cleaning": "Solar Panel Cleaning",
    "terrace cleaning": "Terrace Cleaning",
    "sewage tank cleaning": "Septic Tank Cleaning",
    "industrial cleaning": "Industrial Deep Cleaning",
    "other (please describe)": "Other (Please Describe)",
  },
};

const PAINTING_ISSUE_LABELS: Record<string, Record<string, string>> = {
  "interior painting": {
    "full house painting": "Full House Interior Painting",
    "single room painting": "Single Room Painting",
    "touch-up painting": "Paint Touch-Up",
    "texture painting": "Texture Wall Painting",
    "accent or design wall": "Feature Wall Painting",
    "stencil work": "Stencil Wall Painting",
    "colour consultation": "Paint Colour Selection",
    "kids room theme": "Kids' Room Wall Design",
    "other (please describe)": "Other Interior Painting Work",
  },
  "exterior painting": {
    "gate painting": "Main Gate Painting",
    "terrace wall painting": "Terrace & Parapet Wall Painting",
    "weather-proof coat": "Weatherproof Exterior Painting",
    "exterior texture": "Exterior Texture Painting",
    "other (please describe)": "Other Exterior Painting Work",
  },
  "wood & metal painting": {
    "door or furniture enamel": "Door & Furniture Enamel Painting",
    "pu finish": "PU Polish & Finish",
    "grill painting": "Window & Metal Grill Painting",
    "gate painting": "Metal Gate Painting",
    "rust removal and primer": "Rust Removal & Anti-Rust Primer",
    "shutter painting": "Rolling Shutter Painting",
    "railing painting": "Metal Railing Painting",
    "other (please describe)": "Other Wood & Metal Painting",
  },
  "wall repair & crack filling": {
    "peeling paint": "Paint Peeling",
    "cracks on wall": "Wall Crack Repair",
    "dampness on wall": "Damp Wall Treatment",
    "seepage patches": "Water Seepage Repair",
    "fungus or mould": "Fungus & Mould Removal",
    "efflorescence (white powder)": "White Salt Deposits on Walls",
    "paint bubbling": "Paint Bubbling & Blistering",
    "putty work": "Wall Putty & Surface Repair",
    "hairline cracks": "Hairline Crack Filling",
    "stains on ceiling": "Ceiling Water Stain Repair",
    "other (please describe)": "Other Wall Repair Issue",
  },
  "waterproofing services": {
    "terrace waterproofing": "Terrace & Roof Waterproofing",
    "expansion joint treatment": "Expansion Joint Sealing",
    "crack injection grouting": "Crack Injection Treatment",
    "other (please describe)": "Other Waterproofing Work",
  },
  "special finishes": {
    "stucco finish": "Stucco Texture Finish",
    "3d wall panel": "3D Wall Panel Installation",
    "anti-bacterial coating": "Anti-Bacterial Wall Coating",
    "heat-reflective coating": "Heat-Reflective Roof Coating",
    "epoxy coating": "Epoxy Floor Coating",
    "fire-retardant coating": "Fire-Resistant Coating",
    "other (please describe)": "Other Special Finish",
  },
};

const getServiceTypeLabel = (serviceType?: string | null) => {
  const label = serviceType?.trim() || "General";
  const normalized = label.toLowerCase();
  if (["painting", "painting & waterproofing", "painting and waterproofing", "painting, wall repair & waterproofing"].includes(normalized)) {
    return "Painting, Wall Repair & Waterproofing";
  }
  return label;
};

const getCategoryLabel = (serviceType?: string | null, category?: string | null) => {
  const label = category || "General";
  const serviceTypeName = serviceType?.trim().toLowerCase();
  if (serviceTypeName === "electrical") {
    return ELECTRICAL_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "plumbing") {
    return PLUMBING_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "air conditioning and refrigeration") {
    return HVAC_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "home appliance repair") {
    return APPLIANCE_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "carpentry and furniture") {
    return CARPENTRY_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "cctv and security systems") {
    return SECURITY_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "water purifier (ro) and water treatment") {
    return WATER_PURIFIER_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (
    serviceTypeName === "painting" ||
    serviceTypeName === "painting & waterproofing" ||
    serviceTypeName === "painting and waterproofing" ||
    serviceTypeName === "painting, wall repair & waterproofing"
  ) {
    return PAINTING_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  if (serviceTypeName === "cleaning services") {
    return CLEANING_CATEGORY_LABELS[label.trim().toLowerCase()] || label;
  }
  return label;
};

const isRemovedElectricalCategory = (category?: string | null) =>
  ["power supply and meter", "meter & main power supply", "power_supply_meter"].includes(
    (category || "").trim().toLowerCase()
  );

const getIssueLabel = (serviceType?: string | null, category?: string | null, issue?: string | null) => {
  const serviceTypeName = serviceType?.trim().toLowerCase();
  const categoryName = getCategoryLabel(serviceType, category).trim().toLowerCase();
  if (serviceTypeName === "cleaning services") {
    return CLEANING_ISSUE_LABELS[categoryName]?.[(issue || "").trim().toLowerCase()] || issue || "";
  }
  if (
    serviceTypeName !== "painting" &&
    serviceTypeName !== "painting & waterproofing" &&
    serviceTypeName !== "painting and waterproofing" &&
    serviceTypeName !== "painting, wall repair & waterproofing"
  ) return issue || "";
  return PAINTING_ISSUE_LABELS[categoryName]?.[(issue || "").trim().toLowerCase()] || issue || "";
};

const isCurrentManagedCatalogIssue = (item: ServiceCatalogItem) => {
  const category = item.category?.trim().toLowerCase();
  const serviceTypeName = item.service_type?.trim().toLowerCase();
  if (serviceTypeName === "electrical" && isRemovedElectricalCategory(category)) return false;
  const serviceType = SERVICE_CATALOGUE_TAXONOMY.find(
    (entry) => entry.id === serviceTypeName || entry.name.toLowerCase() === serviceTypeName
  );
  if (!serviceType) return true;

  const managedElectricalCategoryIds = [
    "lights_lighting",
    "wiring_cabling",
    "switches_sockets",
    "fans_ventilation",
    "mcb_fuse_db",
    "inverter_ups",
    "appliance_points",
    "doorbell_intercom",
    "safety_earthing",
  ];
  const isManagedCategory = serviceType.id === "plumbing" || serviceType.id === "ac_refrigeration" || serviceType.id === "carpentry" ||
    (serviceType.id === "electrical" && managedElectricalCategoryIds.includes(
      serviceType.categories.find((entry) =>
        getCategoryLabel(item.service_type, item.category) === entry.name || category === entry.id
      )?.id || ""
    ));
  if (!isManagedCategory) return true;

  const managedCategory = serviceType.categories.find((entry) =>
    getCategoryLabel(item.service_type, item.category) === entry.name || category === entry.id
  );
  if (!managedCategory) return true;

  return managedCategory.issues.some(
    (issue) => issue.toLowerCase() === (item.issue || "").trim().toLowerCase()
  );
};

interface ServiceCatalogueAddWizardProps {
  onClose: () => void;
  onSaved: (issueCount: number, serviceTypeName: string) => Promise<void> | void;
  configuredServices: ServiceCatalogItem[];
}

type ServiceCatalogueWizardStep = 1 | 2 | 3;

/**
 * Admin-side version of the customer catalogue journey:
 * Service Type -> Category -> Issues.
 * Images are resolved through the exact same taxonomy and helpers as the customer page.
 * No image files are copied or created by this component.
 */
function ServiceCatalogueAddWizard({ onClose, onSaved, configuredServices }: ServiceCatalogueAddWizardProps) {
  const [step, setStep] = useState<ServiceCatalogueWizardStep>(1);
  const [selectedServiceType, setSelectedServiceType] = useState<TaxonomyServiceType | null>(null);
  const [activeCategory, setActiveCategory] = useState<TaxonomyCategory | null>(null);
  const [selectedIssuesByCategory, setSelectedIssuesByCategory] = useState<Record<string, string[]>>({});

  const normalizeCatalogValue = (value?: string | null) =>
    (value || "").trim().toLowerCase().replace(/[^a-z0-9]/g, "");

  const getSavedIssuesForType = (
    serviceType: TaxonomyServiceType,
    services: ServiceCatalogItem[] = configuredServices,
  ) => {
    const result: Record<string, string[]> = {};

    const matchesType = (value: string) => {
      const normalized = normalizeCatalogValue(value);
      return (
        normalized === normalizeCatalogValue(serviceType.name) ||
        normalized === normalizeCatalogValue(serviceType.id)
      );
    };

    serviceType.categories.forEach((category) => {
      const savedIssues = services.filter((service) => {
        if (!matchesType(service.service_type)) return false;

        const savedCategory = normalizeCatalogValue(
          getCategoryLabel(service.service_type, service.category)
        );

        return (
          savedCategory === normalizeCatalogValue(category.name) ||
          normalizeCatalogValue(service.category) === normalizeCatalogValue(category.id)
        );
      });

      result[category.id] = category.issues.filter((issue) =>
        savedIssues.some(
          (service) =>
            normalizeCatalogValue(service.issue) === normalizeCatalogValue(issue)
        )
      );
    });

    return result;
  };
  const [serviceSearch, setServiceSearch] = useState("");
  const [categorySearch, setCategorySearch] = useState("");
  const [issueSearch, setIssueSearch] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const visibleServiceTypes = useMemo(() => {
    const query = serviceSearch.trim().toLowerCase();
    if (!query) return SERVICE_CATALOGUE_TAXONOMY;
    return SERVICE_CATALOGUE_TAXONOMY.filter((item) =>
      `${item.name} ${item.description}`.toLowerCase().includes(query)
    );
  }, [serviceSearch]);

  const getActiveCountForServiceType = (serviceType: TaxonomyServiceType) => {
    const activeServices = configuredServices.filter((item) => item?.is_active === true);

    // Use the same service type, category, and issue matching as the wizard's
    // selected state so the card count cannot include issues the wizard shows
    // as unconfigured. Count distinct taxonomy issues, not database rows.
    return Object.values(getSavedIssuesForType(serviceType, activeServices))
      .reduce((count, issues) => count + issues.length, 0);
  };



  const visibleCategories = useMemo(() => {
    if (!selectedServiceType) return [];
    const query = categorySearch.trim().toLowerCase();
    if (!query) return selectedServiceType.categories;
    return selectedServiceType.categories.filter((item) =>
      `${item.name} ${item.code}`.toLowerCase().includes(query)
    );
  }, [selectedServiceType, categorySearch]);

  const visibleIssues = useMemo(() => {
    if (!activeCategory) return [];
    const query = issueSearch.trim().toLowerCase();
    if (!query) return activeCategory.issues;
    return activeCategory.issues.filter((item) => item.toLowerCase().includes(query));
  }, [activeCategory, issueSearch]);

  const selectedCategoryCount = Object.values(selectedIssuesByCategory).filter((items) => items.length > 0).length;
  const selectedIssueCount = Object.values(selectedIssuesByCategory).reduce((count, items) => count + items.length, 0);

  const chooseServiceType = (serviceType: TaxonomyServiceType) => {
    const changingType = selectedServiceType?.id !== serviceType.id;

    if (changingType) {
      setSelectedIssuesByCategory(getSavedIssuesForType(serviceType));
    }

    setSelectedServiceType(serviceType);
    setActiveCategory(null);
    setCategorySearch("");
    setIssueSearch("");
    setErrorMessage("");
    setStep(2);
  };

  const openCategory = (category: TaxonomyCategory) => {
    setActiveCategory(category);
    setIssueSearch("");
    setErrorMessage("");
    setStep(3);
  };

  const handleWizardBack = (event?: React.MouseEvent<HTMLButtonElement>) => {
    // This control navigates only within the service wizard. Prevent a parent
    // click handler or browser default from triggering app-level navigation.
    event?.preventDefault();
    event?.stopPropagation();

    if (submitting) return;

    setErrorMessage("");

    if (step === 3) {
      // Step 3: Issues -> Step 2: Categories
      setActiveCategory(null);
      setIssueSearch("");
      setStep(2);
      return;
    }

    if (step === 2) {
      // Step 2: Categories -> Step 1: Service Types
      // Preserve selectedServiceType and selectedIssuesByCategory.
      setActiveCategory(null);
      setCategorySearch("");
      setIssueSearch("");
      setStep(1);
    }
  };

  const toggleIssue = (issue: string) => {
    if (!activeCategory) return;
    setSelectedIssuesByCategory((current) => {
      const existing = current[activeCategory.id] || [];
      const next = existing.includes(issue)
        ? existing.filter((item) => item !== issue)
        : [...existing, issue];
      return { ...current, [activeCategory.id]: next };
    });
  };

  const selectAllVisibleIssues = () => {
    if (!activeCategory) return;
    setSelectedIssuesByCategory((current) => ({
      ...current,
      [activeCategory.id]: [...activeCategory.issues],
    }));
  };

  const clearActiveCategory = () => {
    if (!activeCategory) return;
    setSelectedIssuesByCategory((current) => ({ ...current, [activeCategory.id]: [] }));
  };

  const removeCategorySelection = (categoryId: string) => {
    setSelectedIssuesByCategory((current) => ({ ...current, [categoryId]: [] }));
  };

  const handleAddSelected = async () => {
    if (!selectedServiceType || submitting) return;

    const normalize = normalizeCatalogValue;

    const savedSelections = getSavedIssuesForType(selectedServiceType);

    const groupsToAdd = selectedServiceType.categories
      .map((category) => {
        const selected = selectedIssuesByCategory[category.id] || [];
        const saved = savedSelections[category.id] || [];

        return {
          category: category.name,
          issues: selected.filter(
            (issue) =>
              !saved.some(
                (existing) => normalize(existing) === normalize(issue)
              )
          ),
        };
      })
      .filter((group) => group.issues.length > 0);

    const servicesToRemove = configuredServices.filter((service) => {
      const matchingType =
        normalize(service.service_type) === normalize(selectedServiceType.name) ||
        normalize(service.service_type) === normalize(selectedServiceType.id);

      if (!matchingType) return false;

      const category = selectedServiceType.categories.find(
        (item) =>
          normalize(item.name) ===
            normalize(getCategoryLabel(service.service_type, service.category)) ||
          normalize(item.id) === normalize(service.category)
      );

      if (!category) return false;

      const knownIssue = category.issues.some(
        (issue) => normalize(issue) === normalize(service.issue)
      );

      if (!knownIssue) return false;

      const selected = selectedIssuesByCategory[category.id] || [];

      return !selected.some(
        (issue) => normalize(issue) === normalize(service.issue)
      );
    });

    const additionsCount = groupsToAdd.reduce(
      (count, group) => count + group.issues.length,
      0
    );

    if (additionsCount === 0 && servicesToRemove.length === 0) {
      setErrorMessage("No changes to save.");
      return;
    }

    setSubmitting(true);
    setErrorMessage("");

    try {
      if (groupsToAdd.length > 0) {
        await createAdminServicesBatch({
          service_type: selectedServiceType.name,
          groups: groupsToAdd,
        });
      }

      for (const service of servicesToRemove) {
        await deleteAdminService(service.id);
      }

      await onSaved(selectedIssueCount, selectedServiceType.name);
    } catch (err: any) {
      setErrorMessage(
        err?.response?.data?.detail ||
        "Unable to save all service changes. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const cardBase: React.CSSProperties = {
    border: "1px solid #E2E8F0",
    borderRadius: 12,
    background: "#FFFFFF",
    overflow: "hidden",
    cursor: "pointer",
    textAlign: "left",
    padding: 0,
    minWidth: 0,
    transition: "border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease",
  };

  const isIssueSelected = (issue: string) => Boolean(
    activeCategory && (selectedIssuesByCategory[activeCategory.id] || []).includes(issue)
  );

  return (
    <div
      style={{
        // Keep the catalogue inside the existing FieldOps application shell.
        // The global header and left navigation are rendered by App.tsx and
        // must remain visible while this page fills only the main content area.
        position: "relative",
        width: "100%",
        height: "100%",
        minHeight: 0,
        minWidth: 0,
        flex: 1,
        boxSizing: "border-box",
        background: "#F8FAFC",
        display: "flex",
        alignItems: "stretch",
        justifyContent: "stretch",
        padding: 0,
        overflow: "hidden",
      }}
    >
      <section
        role="main"
        aria-label="Add service offering"
        style={{
          width: "100%",
          height: "100%",
          minHeight: 0,
          minWidth: 0,
          flex: 1,
          background: "#F8FAFC",
          border: 0,
          borderRadius: 0,
          boxShadow: "none",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Full-page admin service catalogue workspace */}
        <header style={{ background: "#FFFFFF", borderBottom: "1px solid #E2E8F0", padding: "17px 22px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
            <div>
              <h2 style={{ margin: 0, color: "#0F172A", fontSize: 20, fontWeight: 800 }}>Add Service Offering</h2>
              <p style={{ margin: "4px 0 0", color: "#64748B", fontSize: 12.5 }}>
                Select the same service types, categories and issues shown in the customer catalogue.
              </p>
            </div>

          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16, maxWidth: 690 }}>
            {(["Service Type", "Category", "Issues"] as const).map((label, index) => {
              const number = (index + 1) as ServiceCatalogueWizardStep;
              const active = step === number;
              const complete = step > number;
              return (
                <React.Fragment key={label}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: active || complete ? "#047857" : "#64748B", fontSize: 12.5, fontWeight: 800, whiteSpace: "nowrap" }}>
                    <span style={{ width: 27, height: 27, borderRadius: 99, display: "grid", placeItems: "center", background: active || complete ? "#059669" : "#FFFFFF", border: `1px solid ${active || complete ? "#059669" : "#CBD5E1"}`, color: active || complete ? "#FFFFFF" : "#64748B" }}>
                      {complete ? <Check size={14} /> : number}
                    </span>
                    {label}
                  </div>
                  {index < 2 && <div style={{ height: 1, flex: 1, minWidth: 24, background: "#CBD5E1" }} />}
                </React.Fragment>
              );
            })}
          </div>
        </header>

        {/* Main catalogue workspace */}
        <main style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          {step === 1 && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
                <div>
                  <h3 style={{ margin: 0, color: "#0F172A", fontSize: 17, fontWeight: 800 }}>Step 1: Select Service Type</h3>
                  <p style={{ margin: "4px 0 0", color: "#64748B", fontSize: 12 }}>Choose one service type to configure its categories and issues.</p>
                </div>
                <div style={{ position: "relative", width: "min(330px, 100%)" }}>
                  <Search size={15} color="#94A3B8" style={{ position: "absolute", top: 11, left: 11 }} />
                  <input value={serviceSearch} onChange={(event) => setServiceSearch(event.target.value)} placeholder="Search 16 service types..." style={{ width: "100%", boxSizing: "border-box", padding: "9px 12px 9px 34px", border: "1px solid #CBD5E1", borderRadius: 9, fontSize: 12.5, outline: "none" }} />
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(195px, 1fr))", gap: 14 }}>
                {visibleServiceTypes.map((serviceType) => {
                  const liveCount = getActiveCountForServiceType(serviceType);
                  const isSelected = selectedServiceType?.id === serviceType.id;

                  return (
                    <button
                      key={serviceType.id}
                      type="button"
                      onClick={() => chooseServiceType(serviceType)}
                      aria-label={`Choose ${serviceType.name}. ${liveCount} active services.`}
                      style={{
                        ...cardBase,
                        border: `1.5px solid ${isSelected ? "#059669" : "#E2E8F0"}`,
                        borderRadius: 14,
                        padding: "10px 10px 12px",
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        textAlign: "left",
                        minHeight: 238,
                        boxShadow: isSelected ? "0 0 0 2px rgba(5,150,105,.12)" : "0 2px 8px rgba(15,23,42,.03)",
                        position: "relative",
                      }}
                      onMouseEnter={(event) => {
                        event.currentTarget.style.transform = "translateY(-3px)";
                        event.currentTarget.style.boxShadow = "0 10px 22px -4px rgba(15,23,42,.10)";
                        event.currentTarget.style.borderColor = "#059669";
                      }}
                      onMouseLeave={(event) => {
                        event.currentTarget.style.transform = "translateY(0)";
                        event.currentTarget.style.boxShadow = isSelected ? "0 0 0 2px rgba(5,150,105,.12)" : "0 2px 8px rgba(15,23,42,.03)";
                        event.currentTarget.style.borderColor = isSelected ? "#059669" : "#E2E8F0";
                      }}
                    >
                      <div
                        style={{
                          height: 105,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          marginBottom: 8,
                          background: "#F8FAFC",
                          borderRadius: 10,
                          border: "1px solid #E2E8F0",
                          padding: 4,
                          overflow: "hidden",
                          position: "relative",
                          width: "100%",
                          boxSizing: "border-box",
                        }}
                      >
                        <img
                          src={serviceType.image}
                          alt={serviceType.name}
                          loading="lazy"
                          style={{
                            height: "95%",
                            width: "95%",
                            objectFit: "contain",
                            filter: "drop-shadow(0 4px 8px rgba(0,0,0,.08))",
                          }}
                        />
                        {liveCount > 0 && (
                          <span
                            style={{
                              position: "absolute",
                              top: 6,
                              right: 6,
                              background: "rgba(5,150,105,.95)",
                              color: "#FFFFFF",
                              fontSize: 10,
                              fontWeight: 700,
                              padding: "2px 7px",
                              borderRadius: 999,
                            }}
                          >
                            {liveCount} Active
                          </span>
                        )}
                      </div>

                      <div style={{ flex: 1, marginBottom: 10, padding: "0 2px" }}>
                        <h3
                          style={{
                            fontSize: 14,
                            fontWeight: 800,
                            color: "#0F172A",
                            margin: "0 0 4px",
                            lineHeight: 1.25,
                            letterSpacing: "-0.2px",
                          }}
                        >
                          {serviceType.name}
                        </h3>
                        <p
                          style={{
                            fontSize: 11,
                            color: "#475569",
                            fontWeight: 500,
                            margin: 0,
                            lineHeight: 1.4,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {serviceType.description}
                        </p>
                      </div>

                      <div>
                        <span
                          style={{
                            background: liveCount > 0 ? "#ECFDF5" : "#F8FAFC",
                            border: `1.5px solid ${liveCount > 0 ? "#059669" : "#CBD5E1"}`,
                            color: liveCount > 0 ? "#065F46" : "#475569",
                            fontSize: 11,
                            fontWeight: 800,
                            padding: "4px 10px",
                            borderRadius: 999,
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                          }}
                        >
                          <span>
                            {liveCount > 0
                              ? `${liveCount} ${liveCount === 1 ? "Service" : "Services"} Available`
                              : `Explore (${serviceType.categories.length} Categories)`}
                          </span>
                          <ArrowRight size={12} color={liveCount > 0 ? "#059669" : "#94A3B8"} />
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {step === 2 && selectedServiceType && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button
                    type="button"
                    onClick={handleWizardBack}
                    disabled={submitting}
                    aria-label="Back to service types"
                    title="Back to service types"
                    style={{
                      border: "1px solid #CBD5E1",
                      background: "#FFFFFF",
                      borderRadius: 9,
                      padding: 8,
                      color: "#334155",
                      cursor: submitting ? "not-allowed" : "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <ArrowLeft size={16} />
                  </button>
                  <div>
                    <div style={{ color: "#64748B", fontSize: 11, fontWeight: 700 }}>SERVICE TYPE / {selectedServiceType.code}</div>
                    <h3 style={{ margin: "2px 0 0", color: "#0F172A", fontSize: 17, fontWeight: 800 }}>Step 2: {selectedServiceType.name} Categories</h3>
                  </div>
                </div>
                <div style={{ position: "relative", width: "min(330px, 100%)" }}>
                  <Search size={15} color="#94A3B8" style={{ position: "absolute", top: 11, left: 11 }} />
                  <input value={categorySearch} onChange={(event) => setCategorySearch(event.target.value)} placeholder="Search categories..." style={{ width: "100%", boxSizing: "border-box", padding: "9px 12px 9px 34px", border: "1px solid #CBD5E1", borderRadius: 9, fontSize: 12.5, outline: "none" }} />
                </div>
              </div>
              {selectedCategoryCount > 0 && (
                <div style={{ marginBottom: 14, display: "flex", flexWrap: "wrap", gap: 7 }}>
                  {selectedServiceType.categories.filter((category) => (selectedIssuesByCategory[category.id] || []).length > 0).map((category) => (
                    <span key={category.id} style={{ display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 99, background: "#ECFDF5", border: "1px solid #A7F3D0", color: "#047857", padding: "5px 9px", fontSize: 11, fontWeight: 700 }}>
                      {category.name} ({selectedIssuesByCategory[category.id].length})
                      <button type="button" onClick={() => removeCategorySelection(category.id)} aria-label={`Remove ${category.name}`} style={{ border: 0, background: "transparent", padding: 0, color: "#047857", cursor: "pointer", display: "inline-flex" }}><X size={12} /></button>
                    </span>
                  ))}
                </div>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(205px, 1fr))", gap: 13 }}>
                {visibleCategories.map((category) => {
                  const selectedCount = (selectedIssuesByCategory[category.id] || []).length;
                  const imagePath = getCategoryCardImage(category.id, selectedServiceType.id);
                  return (
                    <button key={category.id} type="button" onClick={() => openCategory(category)} style={{ ...cardBase, borderColor: selectedCount > 0 ? "#059669" : "#E2E8F0", boxShadow: selectedCount > 0 ? "0 0 0 2px rgba(5,150,105,.10)" : "0 1px 3px rgba(15,23,42,.03)" }}>
                      <div style={{ height: 112, position: "relative", background: "#F1F5F9", overflow: "hidden" }}>
                        <img src={imagePath} alt={category.name} loading="lazy" style={{ display: "block", width: "100%", height: "100%", objectFit: "contain", objectPosition: "center" }} />
                      </div>
                      <div style={{ padding: "10px 11px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ color: "#0F172A", fontWeight: 800, fontSize: 12.5 }}>{category.name}</span>
                        <span style={{ fontSize: 10.5, color: selectedCount > 0 ? "#047857" : "#64748B", fontWeight: 800, whiteSpace: "nowrap" }}>{selectedCount > 0 ? `${selectedCount} selected` : `${category.issues.length} issues`}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {step === 3 && selectedServiceType && activeCategory && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 15 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button
                    type="button"
                    onClick={handleWizardBack}
                    disabled={submitting}
                    aria-label="Back to categories"
                    title="Back to categories"
                    style={{
                      border: "1px solid #CBD5E1",
                      background: "#FFFFFF",
                      borderRadius: 9,
                      padding: 8,
                      color: "#334155",
                      cursor: submitting ? "not-allowed" : "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <ArrowLeft size={16} />
                  </button>
                  <div>
                    <div style={{ color: "#64748B", fontSize: 11, fontWeight: 700 }}>{selectedServiceType.name} / CATEGORY</div>
                    <h3 style={{ margin: "2px 0 0", color: "#0F172A", fontSize: 17, fontWeight: 800 }}>Step 3: {activeCategory.name}</h3>
                    <p style={{ margin: "3px 0 0", color: "#64748B", fontSize: 11.5 }}>Select the issues your organization will provide.</p>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <div style={{ position: "relative", width: "min(280px, 100%)" }}>
                    <Search size={15} color="#94A3B8" style={{ position: "absolute", top: 11, left: 11 }} />
                    <input value={issueSearch} onChange={(event) => setIssueSearch(event.target.value)} placeholder="Search issues..." style={{ width: "100%", boxSizing: "border-box", padding: "9px 12px 9px 34px", border: "1px solid #CBD5E1", borderRadius: 9, fontSize: 12.5, outline: "none" }} />
                  </div>
                  <button type="button" onClick={selectAllVisibleIssues} style={{ border: "1px solid #059669", color: "#047857", background: "#ECFDF5", borderRadius: 9, padding: "8px 11px", fontSize: 11.5, fontWeight: 800, cursor: "pointer" }}>Select All</button>
                  <button type="button" onClick={clearActiveCategory} style={{ border: "1px solid #CBD5E1", color: "#475569", background: "#FFFFFF", borderRadius: 9, padding: "8px 11px", fontSize: 11.5, fontWeight: 700, cursor: "pointer" }}>Deselect All</button>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 13 }}>
                <span style={{ borderRadius: 99, padding: "5px 10px", background: "#ECFDF5", border: "1px solid #A7F3D0", color: "#047857", fontSize: 11, fontWeight: 800 }}>{(selectedIssuesByCategory[activeCategory.id] || []).length} of {activeCategory.issues.length} selected</span>
                <button
                  type="button"
                  onClick={handleWizardBack}
                  disabled={submitting}
                  style={{
                    border: 0,
                    background: "transparent",
                    color: "#047857",
                    fontSize: 11.5,
                    fontWeight: 800,
                    cursor: submitting ? "not-allowed" : "pointer",
                  }}
                >
                  Choose another category
                </button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
                {visibleIssues.map((issue, index) => {
                  const selected = isIssueSelected(issue);
                  const imagePath = getIssueCardImage(issue, activeCategory.id, selectedServiceType.id, activeCategory.issues.indexOf(issue));
                  return (
                    <button key={issue} type="button" onClick={() => toggleIssue(issue)} style={{ ...cardBase, borderColor: selected ? "#059669" : "#E2E8F0", boxShadow: selected ? "0 0 0 2px rgba(5,150,105,.12)" : "0 1px 3px rgba(15,23,42,.03)" }}>
                      <div style={{ height: 112, position: "relative", background: "#F1F5F9", overflow: "hidden" }}>
                        <img src={imagePath} alt={issue} loading="lazy" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                        <span style={{ position: "absolute", top: 8, right: 8, width: 23, height: 23, borderRadius: 7, display: "grid", placeItems: "center", background: selected ? "#059669" : "rgba(255,255,255,.96)", border: `1px solid ${selected ? "#059669" : "#94A3B8"}`, color: selected ? "#FFFFFF" : "transparent" }}><Check size={14} /></span>
                      </div>
                      <div style={{ padding: "10px 11px", minHeight: 48, display: "flex", alignItems: "center", color: "#0F172A", fontSize: 12, fontWeight: 800, lineHeight: 1.35 }}>{issue}</div>
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {errorMessage && <div role="alert" style={{ marginTop: 14, border: "1px solid #FECACA", background: "#FEF2F2", color: "#B91C1C", borderRadius: 9, padding: "10px 12px", fontSize: 12.5 }}>{errorMessage}</div>}
        </main>

        {/* Persistent selection summary and actions */}
        <footer style={{ background: "#FFFFFF", borderTop: "1px solid #E2E8F0", padding: "13px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <strong style={{ color: "#0F172A", fontSize: 12.5 }}>Selected:</strong>
            <span style={{ background: "#ECFDF5", color: "#047857", borderRadius: 99, padding: "6px 10px", fontSize: 11.5, fontWeight: 800 }}>{selectedServiceType ? selectedServiceType.name : "No service type"}</span>
            <span style={{ color: "#64748B", fontSize: 11.5 }}>{selectedCategoryCount} categories</span>
            <span style={{ color: "#64748B", fontSize: 11.5 }}>{selectedIssueCount} issues</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>

            {step === 1 ? (
              <button type="button" disabled style={{ padding: "9px 17px", border: 0, borderRadius: 9, color: "#FFFFFF", background: "#94A3B8", fontSize: 12.5, fontWeight: 800, cursor: "not-allowed" }}>Choose a Service Type</button>
            ) : (
              <button type="button" onClick={handleAddSelected} disabled={submitting} style={{ padding: "9px 18px", border: 0, borderRadius: 9, color: "#FFFFFF", background: !submitting ? "#059669" : "#94A3B8", fontSize: 12.5, fontWeight: 800, cursor: !submitting ? "pointer" : "not-allowed", display: "inline-flex", alignItems: "center", gap: 7 }}>
                Save
              </button>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}

interface SuperAdminServicesPageProps {
  readOnly?: boolean;
}

export default function SuperAdminServicesPage({ readOnly = false }: SuperAdminServicesPageProps) {
  const { addToast } = useToast();
  const user = useAuthStore((state) => state.user);
  // Dispatchers are read-only for existing catalogue management, but may add offerings.
  const canCreateServices = !readOnly || user?.role === "dispatcher";
  const [services, setServices] = useState<ServiceCatalogItem[]>([]);
  const [taxonomySuggestions, setTaxonomySuggestions] = useState<TaxonomySuggestionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");

  // Open the customer-catalogue offering workspace immediately when Services is entered.
  // Closing it returns to the existing organization service-management view.
  const [isModalOpen, setIsModalOpen] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Form State: 1 Service Type, Multiple Categories, Multiple Issues
  const [selectedType, setSelectedType] = useState("");
  const [customType, setCustomType] = useState("");

  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [newCatInput, setNewCatInput] = useState("");

  const [selectedIssuesByCat, setSelectedIssuesByCat] = useState<Record<string, string[]>>({});
  const [newIssueInputs, setNewIssueInputs] = useState<Record<string, string>>({});
  const [activeCategory, setActiveCategory] = useState<string>("");
  const [categorySearch, setCategorySearch] = useState<string>("");
  const [issueSearch, setIssueSearch] = useState<string>("");

  // Load organization-scoped services
  const loadServices = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await getAdminServices();
      setServices(Array.isArray(data) ? data : []);
    } catch (err: any) {
      if (!silent) addToast(err?.response?.data?.detail || "Failed to load services catalog", "error");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadServices();
    getTaxonomySuggestions()
      .then((data) => setTaxonomySuggestions(data))
      .catch((err) => console.warn("Failed to load taxonomy suggestions", err));
  }, []);
  useActiveAutoRefresh(() => loadServices(true), !isModalOpen && !submitting);

  // Compute Metrics dynamically for logged-in organization
  const visibleServices = (services || []).filter(isCurrentManagedCatalogIssue);
  const totalCount = visibleServices.length;
  const uniqueTypes = useMemo(
    () => Array.from(new Set((services || []).map((s) => s?.service_type).filter(Boolean))),
    [services]
  );
  const uniqueCategories = useMemo(
    () =>
      Array.from(
        new Set(
          (services || [])
            .map((s) => `${s?.service_type || ""}::${getCategoryLabel(s?.service_type, s?.category)}`)
            .filter((x) => x !== "::")
        )
      ),
    [services]
  );
  const configuredIssuesCount = visibleServices.length;

  // Filtered Services List
  const filteredServices = useMemo(() => {
    if (!Array.isArray(services)) return [];
    return services.filter((s) => {
      if (!s) return false;
      if (!isCurrentManagedCatalogIssue(s)) return false;
      if (typeFilter !== "ALL" && s.service_type !== typeFilter) return false;
      if (searchTerm.trim()) {
        const query = searchTerm.toLowerCase();
        const text = `${s.service_type || ""} ${s.category || ""} ${s.issue || ""} ${s.description || ""}`.toLowerCase();
        return text.includes(query);
      }
      return true;
    });
  }, [services, typeFilter, searchTerm]);

  // Grouped Structure: Service Type -> Categories -> Issues (ONLY VIEW)
  const groupedServices = useMemo(() => {
    if (!Array.isArray(filteredServices)) return [];
    const map: Record<string, Record<string, ServiceCatalogItem[]>> = {};

    filteredServices.forEach((item) => {
      if (!item) return;
      const st = item.service_type || "General";
      const cat = getCategoryLabel(st, item.category);
      if (!map[st]) map[st] = {};
      if (!map[st][cat]) map[st][cat] = [];
      map[st][cat].push(item);
    });

    return Object.keys(map).map((st) => ({
      service_type: st,
      categories: Object.keys(map[st]).map((cat) => ({
        category: cat,
        items: map[st][cat],
      })),
    }));
  }, [filteredServices]);

  // Available Service Types list for Modal Dropdown
  const availableServiceTypes = useMemo(() => {
    const fromSuggestions = taxonomySuggestions?.service_types || [];
    const fromMap = Object.keys(KNOWN_CATEGORIES_MAP);
    const fromExisting = (services || []).map((s) => s?.service_type).filter(Boolean);
    return Array.from(new Set([...fromSuggestions, ...fromMap, ...fromExisting]));
  }, [taxonomySuggestions, services]);

  // Categories available for currently selected Service Type
  const effectiveType = selectedType === "__NEW__" ? customType.trim() : selectedType;
  const availableCategoriesForType = useMemo(() => {
    if (!effectiveType) return [];
    const fromSuggestions = (taxonomySuggestions?.categories_by_type?.[effectiveType] || [])
      .map((category) => getCategoryLabel(effectiveType, category));
    const fromMap = KNOWN_CATEGORIES_MAP[effectiveType] || [];
    const fromExisting = (services || [])
      .filter((s) => s?.service_type === effectiveType)
      .map((s) => getCategoryLabel(s?.service_type, s?.category))
      .filter(Boolean);
    return Array.from(new Set([...fromSuggestions, ...fromMap, ...fromExisting]))
      .filter((category) => !(effectiveType.trim().toLowerCase() === "electrical" && isRemovedElectricalCategory(category)));
  }, [effectiveType, taxonomySuggestions, services]);

  // Issues available for a category
  const getAvailableIssuesForCategory = (catName: string) => {
    const selectedTaxonomy = SERVICE_CATALOGUE_TAXONOMY.find(
      (entry) => entry.name.toLowerCase() === effectiveType.toLowerCase()
    );
    const categoryHasFixedIssues = selectedTaxonomy?.id === "plumbing"
      || selectedTaxonomy?.id === "ac_refrigeration"
      || selectedTaxonomy?.id === "carpentry"
      || (selectedTaxonomy?.id === "electrical" && selectedTaxonomy.categories.some((category) =>
        [
          "lights_lighting",
          "wiring_cabling",
          "switches_sockets",
          "fans_ventilation",
          "mcb_fuse_db",
          "inverter_ups",
          "appliance_points",
          "doorbell_intercom",
          "safety_earthing",
        ].includes(category.id) && category.name === catName
      ));
    if (categoryHasFixedIssues) {
      return KNOWN_ISSUES_MAP[catName] || [];
    }
    const legacyCategoryName = Object.keys(ELECTRICAL_CATEGORY_LABELS).find(
      (legacyName) => ELECTRICAL_CATEGORY_LABELS[legacyName] === catName
    );
    const fromSuggestions = taxonomySuggestions?.issues_by_category?.[catName]
      || (legacyCategoryName ? taxonomySuggestions?.issues_by_category?.[legacyCategoryName] : undefined)
      || [];
    const fromMap = KNOWN_ISSUES_MAP[catName] || [];
    const fromExisting = (services || [])
      .filter((s) => getCategoryLabel(s?.service_type, s?.category) === catName)
      .map((s) => s?.issue)
      .filter(Boolean);
    return Array.from(new Set(
      [...fromSuggestions, ...fromMap, ...fromExisting]
        .map((issue) => getIssueLabel(effectiveType, catName, issue))
    ));
  };

  // Open modal - cleanly resets all fields
  const handleOpenCreateModal = () => {
    setIsModalOpen(true);
  };

  // Select all issues for active category
  const handleSelectAllIssues = (catName: string) => {
    const allIss = getAvailableIssuesForCategory(catName);
    setSelectedIssuesByCat((prev) => ({
      ...prev,
      [catName]: allIss,
    }));
    if (!selectedCategories.includes(catName)) {
      setSelectedCategories((prev) => [...prev, catName]);
    }
  };

  // Clear all issues for active category
  const handleClearIssues = (catName: string) => {
    setSelectedIssuesByCat((prev) => ({
      ...prev,
      [catName]: [],
    }));
  };

  // Toggle Category selection (multi-select) - NO AUTOMATIC ISSUE SELECTION!
  const handleToggleCategory = (catName: string) => {
    if (selectedCategories.includes(catName)) {
      setSelectedCategories((prev) => prev.filter((c) => c !== catName));
      setSelectedIssuesByCat((prev) => {
        const copy = { ...prev };
        delete copy[catName];
        return copy;
      });
    } else {
      setSelectedCategories((prev) => [...prev, catName]);
      // Explicitly start with EMPTY issues list - user must manually choose issues!
      setSelectedIssuesByCat((prev) => ({
        ...prev,
        [catName]: [],
      }));
    }
  };

  // Add custom category
  const handleAddCustomCategory = () => {
    const trimmed = newCatInput.trim();
    if (!trimmed) return;
    if (!selectedCategories.includes(trimmed)) {
      setSelectedCategories((prev) => [...prev, trimmed]);
      setSelectedIssuesByCat((prev) => ({ ...prev, [trimmed]: [] }));
    }
    setNewCatInput("");
  };

  // Toggle Issue selection for a specific category (multi-select)
  const handleToggleIssue = (catName: string, issueName: string) => {
    setSelectedIssuesByCat((prev) => {
      const currentList = prev[catName] || [];
      let updated: string[];
      if (currentList.includes(issueName)) {
        updated = currentList.filter((i) => i !== issueName);
      } else {
        updated = [...currentList, issueName];
      }
      return {
        ...prev,
        [catName]: updated,
      };
    });

    // Ensure category is in selectedCategories if an issue is selected
    if (!selectedCategories.includes(catName)) {
      setSelectedCategories((prev) => [...prev, catName]);
    }
  };

  // Add custom issue to a category
  const handleAddCustomIssue = (catName: string) => {
    const inputVal = (newIssueInputs[catName] || "").trim();
    if (!inputVal) return;
    setSelectedIssuesByCat((prev) => {
      const currentList = prev[catName] || [];
      if (!currentList.includes(inputVal)) {
        return {
          ...prev,
          [catName]: [...currentList, inputVal],
        };
      }
      return prev;
    });
    setNewIssueInputs((prev) => ({ ...prev, [catName]: "" }));
  };

  // Toggle Active/Inactive status
  const handleToggleActive = async (id: number) => {
    if (readOnly) return;
    try {
      const updated = await toggleServiceActive(id);
      setServices((prev) => prev.map((s) => (s.id === id ? updated : s)));
      addToast(
        updated.is_active
          ? "✓ Service is Active & visible in customer booking"
          : "Service is Inactive (hidden from customers)",
        "info"
      );
    } catch (err: any) {
      addToast(err?.response?.data?.detail || "Failed to update service status", "error");
    }
  };

  // Delete service
  const handleDeleteService = (id: number, issueName: string) => {
    if (readOnly) return;
    setDeleteTarget({ id, name: issueName });
  };

  const confirmDeleteService = async () => {
    if (!deleteTarget) return;
    const { id, name: issueName } = deleteTarget;
    setDeleteBusy(true);
    try {
      await deleteAdminService(id);
      setServices((prev) => prev.filter((s) => s.id !== id));
      addToast(`✓ Service "${issueName}" deleted`, "info");
      setDeleteTarget(null);
    } catch (err: any) {
      addToast(err?.response?.data?.detail || "Failed to delete service", "error");
    } finally {
      setDeleteBusy(false);
    }
  };

  // Total issues selected in modal
  const totalSelectedIssuesCount = useMemo(() => {
    let count = 0;
    Object.values(selectedIssuesByCat).forEach((arr) => {
      count += arr.length;
    });
    return count;
  }, [selectedIssuesByCat]);

  // Publish Service Batch (SAFE: never redirects to blank page, stays cleanly on grouped services page)
  const handlePublishServices = async (e?: React.MouseEvent) => {
    if (readOnly) return;
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    if (!effectiveType) {
      addToast("Please select or enter a Service Type", "error");
      return;
    }

    if (selectedCategories.length === 0) {
      addToast("Please select or add at least one Category", "error");
      return;
    }

    const groups: { category: string; issues: string[] }[] = [];
    for (const cat of selectedCategories) {
      const issues = selectedIssuesByCat[cat] || [];
      if (issues.length > 0) {
        groups.push({
          category: cat,
          issues: issues,
        });
      }
    }

    if (groups.length === 0) {
      addToast("Please select or add at least one Issue for your categories", "error");
      return;
    }

    try {
      setSubmitting(true);
      await createAdminServicesBatch({
        service_type: effectiveType,
        groups: groups,
      });

      // 1. Close modal
      setIsModalOpen(false);

      // 2. Immediately re-fetch organization services to update grouped list in-place
      await loadServices();

      // 3. Refresh suggestions in background
      getTaxonomySuggestions().then(setTaxonomySuggestions).catch(() => {});

      addToast(
        `✓ Successfully published ${totalSelectedIssuesCount} services under "${effectiveType}"!`,
        "success"
      );
    } catch (err: any) {
      addToast(err?.response?.data?.detail || "Failed to publish services", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const getIconForType = (type: string) => {
    const t = (type || "").toLowerCase();
    if (t.includes("electric")) return <Zap size={18} color="#D97706" />;
    if (t.includes("plumb")) return <Droplet size={18} color="#0284C7" />;
    if (t.includes("ac") || t.includes("hvac")) return <Snowflake size={18} color="#059669" />;
    if (t.includes("appliance")) return <Plug size={18} color="#7C3AED" />;
    if (t.includes("carpent")) return <Hammer size={18} color="#B45309" />;
    if (t.includes("smart") || t.includes("secur")) return <Shield size={18} color="#2563EB" />;
    return <Wrench size={18} color="#4B5563" />;
  };

  // The Add Service Offering wizard is the default Services workspace.
  // Returning it directly keeps it inside App.tsx's existing header/sidebar
  // layout instead of rendering it as a viewport-covering modal.
  if (canCreateServices) {
    return (
      <ServiceCatalogueAddWizard
        configuredServices={services}
        onClose={() => {}}
        onSaved={async (issueCount, serviceTypeName) => {
          await loadServices();

          getTaxonomySuggestions()
            .then(setTaxonomySuggestions)
            .catch(() => {});

          addToast(
            `Successfully saved ${issueCount} selected issues under "${serviceTypeName}".`,
            "success"
          );

          // Keep the Add Service Offering workspace open.
          // Do not set isModalOpen to false here.
        }}
      />
    );
  }

  return (
    <div style={{ flex: 1, height: "100%", minHeight: 0, minWidth: 0, overflowY: "auto", background: "#F8FAFC", padding: "18px 24px" }}>
      {/* 1. Header Bar with Create Service Button */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <h2 style={{ fontSize: "20px", fontWeight: 800, color: "#0F172A", margin: 0, letterSpacing: "-0.01em" }}>
            Services
          </h2>
          {user?.organization_name && (
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                background: "#EFF6FF",
                color: "#1D4ED8",
                border: "1px solid #BFDBFE",
                padding: "2px 8px",
                borderRadius: "12px",
                textTransform: "uppercase",
                letterSpacing: "0.3px",
              }}
            >
              Org: {user.organization_name}
            </span>
          )}
        </div>

        {canCreateServices && <button
          onClick={handleOpenCreateModal}
          style={{
            background: "#069660",
            color: "#FFFFFF",
            border: "none",
            borderRadius: "8px",
            padding: "9px 18px",
            fontSize: "13px",
            fontWeight: 700,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            boxShadow: "0 2px 6px rgba(6, 150, 96, 0.2)",
            transition: "all 0.15s ease",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#058353")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#069660")}
        >
          <PlusCircle size={16} strokeWidth={2.5} />
          <span>Create Service</span>
        </button>}
      </div>

      {/* 2. 4 Metric Cards (Matching screenshot) */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "14px",
          marginBottom: "18px",
        }}
      >
        {/* TOTAL SERVICES */}
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E2E8F0",
            borderRadius: "14px",
            padding: "16px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
          }}
        >
          <div>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", letterSpacing: "0.04em" }}>
              TOTAL SERVICES
            </div>
            <div style={{ fontSize: "28px", fontWeight: 800, color: "#0F172A", margin: "2px 0" }}>
              {totalCount}
            </div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "#059669" }}>Configured for Organization</div>
          </div>
          <div
            style={{
              width: "42px",
              height: "42px",
              borderRadius: "12px",
              background: "#ECFDF5",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#059669",
            }}
          >
            <CheckCircle2 size={22} strokeWidth={2.4} />
          </div>
        </div>

        {/* SERVICE TYPES */}
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E2E8F0",
            borderRadius: "14px",
            padding: "16px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
          }}
        >
          <div>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", letterSpacing: "0.04em" }}>
              SERVICE TYPES
            </div>
            <div style={{ fontSize: "28px", fontWeight: 800, color: "#0F172A", margin: "2px 0" }}>
              {uniqueTypes.length}
            </div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "#2563EB" }}>Trade Domains</div>
          </div>
          <div
            style={{
              width: "42px",
              height: "42px",
              borderRadius: "12px",
              background: "#EFF6FF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#2563EB",
            }}
          >
            <Share2 size={20} strokeWidth={2.2} />
          </div>
        </div>

        {/* CATEGORIES */}
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E2E8F0",
            borderRadius: "14px",
            padding: "16px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
          }}
        >
          <div>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", letterSpacing: "0.04em" }}>
              CATEGORIES
            </div>
            <div style={{ fontSize: "28px", fontWeight: 800, color: "#0F172A", margin: "2px 0" }}>
              {uniqueCategories.length}
            </div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "#D97706" }}>Sub-domain Groups</div>
          </div>
          <div
            style={{
              width: "42px",
              height: "42px",
              borderRadius: "12px",
              background: "#FFFBEB",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#D97706",
            }}
          >
            <Layers size={20} strokeWidth={2.2} />
          </div>
        </div>

        {/* CONFIGURED ISSUES */}
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E2E8F0",
            borderRadius: "14px",
            padding: "16px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
          }}
        >
          <div>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", letterSpacing: "0.04em" }}>
              CONFIGURED ISSUES
            </div>
            <div style={{ fontSize: "28px", fontWeight: 800, color: "#0F172A", margin: "2px 0" }}>
              {configuredIssuesCount}
            </div>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "#7C3AED" }}>Diagnostics Items</div>
          </div>
          <div
            style={{
              width: "42px",
              height: "42px",
              borderRadius: "12px",
              background: "#F5F3FF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#7C3AED",
            }}
          >
            <AlertCircle size={20} strokeWidth={2.2} />
          </div>
        </div>
      </div>

      {/* 3. Filter Bar (No Cards View button, only clean filters + search) */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
          marginBottom: "16px",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{
              padding: "8px 14px",
              borderRadius: "8px",
              border: "1px solid #CBD5E1",
              fontSize: "13px",
              color: "#334155",
              background: "#FFFFFF",
              fontWeight: 600,
              outline: "none",
              cursor: "pointer",
            }}
          >
            <option value="ALL">All Service Types ({uniqueTypes.length})</option>
            {uniqueTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>

          <span style={{ fontSize: "12px", color: "#64748B", fontWeight: 600 }}>
            Showing {filteredServices.length} of {visibleServices.length} services
          </span>
        </div>

        <div style={{ position: "relative", minWidth: "260px" }}>
          <Search
            size={15}
            style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "#94A3B8" }}
          />
          <input
            type="text"
            placeholder="Search category or issue..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px 8px 34px",
              borderRadius: "8px",
              border: "1px solid #CBD5E1",
              fontSize: "13px",
              background: "#FFFFFF",
              outline: "none",
            }}
          />
        </div>
      </div>

      {/* 4. MAIN CONTENT AREA: ONLY GROUPED VIEW (Matching user screenshot media_1792732211767_9dcabde7.png) */}
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "60px 0" }}>
          <LoadingSpinner />
        </div>
      ) : filteredServices.length === 0 ? (
        <div
          style={{
            background: "#FFFFFF",
            border: "1px dashed #CBD5E1",
            borderRadius: "14px",
            padding: "48px 24px",
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: "52px",
              height: "52px",
              borderRadius: "12px",
              background: "#F1F5F9",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 14px",
              color: "#64748B",
            }}
          >
            <Wrench size={24} />
          </div>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#1E293B", margin: "0 0 6px" }}>
            No Services Configured
          </h3>
          <p style={{ fontSize: "13px", color: "#64748B", margin: "0 0 16px" }}>
            {readOnly ? "No services have been published for your organization yet." : "Create services for your organization so customers can book them."}
          </p>
          {canCreateServices && <button
            onClick={handleOpenCreateModal}
            style={{
              background: "#069660",
              color: "#FFFFFF",
              border: "none",
              borderRadius: "8px",
              padding: "9px 20px",
              fontSize: "13px",
              fontWeight: 700,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <PlusCircle size={15} />
            <span>Create First Service</span>
          </button>}
        </div>
      ) : (
        /* EXACT HIERARCHICAL GROUPED VIEW */
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {groupedServices.map((domainGroup) => (
            <div
              key={domainGroup.service_type}
              style={{
                background: "#FFFFFF",
                border: "1px solid #E2E8F0",
                borderRadius: "14px",
                padding: "22px 24px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
              }}
            >
              {/* Domain Header (e.g. ELECTRICAL) */}
              <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "18px" }}>
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "10px",
                    background: "#FFFBEB",
                    border: "1px solid #FEF3C7",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {getIconForType(domainGroup.service_type)}
                </div>

                <div>
                  <h3
                    style={{
                      fontSize: "15px",
                      fontWeight: 800,
                      color: "#0F172A",
                      margin: 0,
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                    }}
                  >
                    {getServiceTypeLabel(domainGroup.service_type)}
                  </h3>
                  <div style={{ fontSize: "12px", color: "#64748B", fontWeight: 500, marginTop: "2px" }}>
                    {domainGroup.categories.length} Categories in Domain
                  </div>
                </div>
              </div>

              {/* Categories Sub-Cards */}
              <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                {domainGroup.categories.map((catGroup) => (
                  <div
                    key={catGroup.category}
                    style={{
                      background: "#FAFCFF",
                      border: "1px solid #EDF2F7",
                      borderRadius: "12px",
                      padding: "16px 20px",
                    }}
                  >
                    {/* Category Header Row */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        paddingBottom: "12px",
                        borderBottom: "1px solid #EDF2F7",
                        marginBottom: "4px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <Layers size={16} color="#D97706" />
                        <span style={{ fontSize: "14px", fontWeight: 700, color: "#1E293B" }}>
                          {catGroup.category}
                        </span>
                      </div>

                      <span
                        style={{
                          background: "#FFFFFF",
                          border: "1px solid #E2E8F0",
                          padding: "2px 10px",
                          borderRadius: "14px",
                          fontSize: "11.5px",
                          fontWeight: 700,
                          color: "#475569",
                        }}
                      >
                        {catGroup.items.length} Issues
                      </span>
                    </div>

                    {/* Issues List under this Category */}
                    <div style={{ display: "flex", flexDirection: "column" }}>
                      {catGroup.items.map((item, idx) => (
                        <div
                          key={item.id}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            padding: "12px 4px",
                            borderBottom: idx !== catGroup.items.length - 1 ? "1px solid #F1F5F9" : "none",
                          }}
                        >
                          {/* Issue Left: Green Bullet Dot + Title */}
                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <div
                              style={{
                                width: "6px",
                                height: "6px",
                                borderRadius: "50%",
                                background: item.is_active ? "#10B981" : "#94A3B8",
                                flexShrink: 0,
                              }}
                            />
                            <span style={{ fontSize: "13.5px", fontWeight: 600, color: "#0F172A" }}>
                              {getIssueLabel(domainGroup.service_type, catGroup.category, item.issue)}
                            </span>
                          </div>

                          {/* Issue Right: Active/Inactive Toggle + Delete Icon */}
                          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                            <span
                              style={{
                                fontSize: "12px",
                                fontWeight: 600,
                                color: item.is_active ? "#059669" : "#64748B",
                              }}
                            >
                              {item.is_active ? "Active" : "Inactive"}
                            </span>

                            {!readOnly && <button
                              type="button"
                              onClick={() => handleToggleActive(item.id)}
                              style={{
                                width: "36px",
                                height: "20px",
                                borderRadius: "20px",
                                background: item.is_active ? "#069660" : "#CBD5E1",
                                border: "none",
                                cursor: "pointer",
                                position: "relative",
                                padding: 0,
                                transition: "background 0.2s ease",
                              }}
                              title={item.is_active ? "Deactivate" : "Activate"}
                            >
                              <div
                                style={{
                                  width: "16px",
                                  height: "16px",
                                  borderRadius: "50%",
                                  background: "#FFFFFF",
                                  position: "absolute",
                                  top: "2px",
                                  left: item.is_active ? "18px" : "2px",
                                  transition: "left 0.2s ease",
                                  boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                                }}
                              />
                            </button>}

                            {!readOnly && <button
                              type="button"
                              onClick={() => handleDeleteService(item.id, item.issue)}
                              style={{
                                background: "transparent",
                                border: "none",
                                color: "#94A3B8",
                                cursor: "pointer",
                                padding: "4px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                transition: "color 0.15s ease",
                              }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = "#EF4444")}
                              onMouseLeave={(e) => (e.currentTarget.style.color = "#94A3B8")}
                              title="Delete Issue"
                            >
                              <Trash2 size={16} />
                            </button>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmationDialog
        open={deleteTarget !== null}
        title="Delete service issue?"
        message={deleteTarget ? `Are you sure you want to delete “${deleteTarget.name}”? This change cannot be undone.` : ""}
        busy={deleteBusy}
        onConfirm={confirmDeleteService}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
