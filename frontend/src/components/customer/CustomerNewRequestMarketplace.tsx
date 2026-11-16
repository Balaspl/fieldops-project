import React, { useState, useEffect, useMemo } from "react";
import {
  Search,
  LayoutGrid,
  ChevronRight,
  PackageSearch,
  X,
  MapPin,
  Phone,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Wrench,
  Send,
  ArrowLeft,
  Sparkles,
  Map as MapIcon,
  Navigation,
  Check,
} from "lucide-react";
import {
  getCustomerCatalog,
  type ServiceCatalogItem,
} from "../../services/servicesCatalogService";
import {
  createServiceRequest,
  getCustomerProfile,
  reverseLocation,
} from "../../services/customerPortalService";
import LocationPickerMap from "../customer-tracking/LocationPickerMap";
import {
  SERVICE_CATALOGUE_TAXONOMY,
  type TaxonomyServiceType,
  type TaxonomyCategory,
} from "../../data/serviceCatalogueTaxonomy";
import CategoryUniqueVisual from "./CategoryUniqueVisual";
import { getCategoryCardImage, getIssueCardImage } from "../../data/categoryImages";
import { getServiceTypeHdImage } from "../../data/serviceTypeHdImages";
import { Lock, ShieldAlert, Filter, Edit2, RotateCcw } from "lucide-react";
import { useOptionalToast } from "../../hooks/useToast";

interface CustomerNewRequestMarketplaceProps {
  onNavigate?: (tab: string) => void;
}

const SECURITY_ISSUE_DESCRIPTIONS: Record<string, string> = {
  "No Picture / Video Feed": "Camera is powered on, but no picture appears on the monitor.",
  "Blurry Camera Footage": "Check focus, lens condition and camera settings to restore a clear image.",
  "Night Vision Not Working": "Inspect the infrared lights and night recording settings.",
  "Camera Offline / Disconnected": "Restore the camera's power or network connection.",
  "New CCTV Camera Installation": "Install and configure a CCTV camera at the required location.",
  "Camera Angle Adjustment / Relocation": "Adjust the viewing angle or move the camera to a better position.",
  "Camera Cable Damaged": "Inspect and replace damaged CCTV cable or connectors.",
  "Camera Lens Cleaning / Fogging": "Clean the lens and check for moisture or fogging in the housing.",
  "Camera Microphone / Audio Fault": "Check the camera microphone, audio wiring and recording settings.",
  "PTZ Camera Movement Not Working": "Repair pan, tilt or zoom movement and check the camera controls.",
  "Other CCTV Camera Issue": "Describe the camera issue so a technician can assess it.",
  "Camera Power Supply Fault": "Check the camera adapter, power connection and voltage supply.",
  "Camera Not Recording": "Check camera recording settings, connections and storage on the recorder.",
  "DVR / NVR Not Turning On": "Diagnose the recorder power supply and startup fault.",
  "Hard Disk Not Detected": "Check the recorder hard disk, connections and storage health.",
  "No Display on Monitor": "Check the video output cable, monitor input and recorder display settings.",
  "Recording Storage Full": "Review storage capacity and recording retention settings.",
  "DVR / NVR Password Reset": "Reset recorder access credentials and restore authorised access.",
  "Recorded Video Not Playing": "Diagnose playback, recording and timeline settings on the recorder.",
  "Mobile / Remote Viewing Setup": "Configure secure CCTV viewing on a phone or remote device.",
  "Date & Time Incorrect": "Correct the recorder clock, time zone and synchronisation settings.",
  "CCTV Mobile App Not Connecting": "Restore the app connection to the recorder and camera system.",
  "Video Recording Backup / Export": "Export selected recordings to a suitable storage device.",
  "Other DVR / NVR Issue": "Describe the recorder issue so a technician can assess it.",
  "Fingerprint Not Recognized": "Check the fingerprint reader and improve recognition reliability.",
  "Access Door Lock Not Working": "Inspect the access-controlled door lock and its power connection.",
  "Access Card Not Reading": "Check the card reader and access card configuration.",
  "Face Recognition Not Working": "Check camera positioning, lighting and face recognition settings.",
  "Attendance Data Not Syncing": "Restore attendance data synchronisation with the management system.",
  "Magnetic Door Lock Not Working": "Inspect the magnetic lock, power supply and access controller.",
  "New Access Control Installation": "Install and configure an access control system at the site.",
  "User Registration / Access Management": "Add users and configure their access permissions.",
  "Other Biometric / Access Control Issue": "Describe the access control issue for technician assessment.",
  "False Alarm Triggering": "Check alarm settings and sensors that are triggering false alerts.",
  "Alarm Siren Not Working": "Inspect the siren, wiring and alarm control panel.",
  "Motion Sensor Not Detecting": "Check sensor placement, power and motion detection settings.",
  "Door / Window Sensor Not Working": "Inspect the contact sensor and its connection to the alarm panel.",
  "Fire Alarm Control Panel Fault": "Diagnose the fire alarm panel, zones and connected devices.",
  "Smoke Detector Beeping / Low Battery": "Check the detector battery and confirm the unit is operating normally.",
  "Gas Leak Detector Not Working": "Check the gas detector power, sensor status and alarm connection.",
  "Emergency Panic Button Not Working": "Test the panic button and confirm its alert reaches the control panel.",
  "Other Alarm / Sensor Issue": "Describe the alarm or sensor issue for technician assessment.",
  "Indoor Monitor Screen Not Working": "Check the indoor monitor display, power and video connection.",
  "No Sound / Audio Not Working": "Inspect the microphone, speaker and audio wiring.",
  "Doorbell Call Not Ringing": "Check the call button, chime and indoor monitor connection.",
  "New Video Door Phone Installation": "Install and configure a video door phone at the entrance.",
  "Door Phone Wiring / Cable Fault": "Inspect and repair the door phone cable or wiring connection.",
  "Door Unlock Button Not Working": "Check the unlock control and its connection to the door lock.",
  "Indoor Monitor Replacement": "Replace and configure a faulty indoor monitor.",
  "Other Video Door Phone Issue": "Describe the door phone issue for technician assessment.",
  "Sliding Gate Motor Not Working": "Diagnose the sliding gate motor, power and drive mechanism.",
  "Gate Remote Not Working": "Check the gate receiver and pair or repair the remote.",
  "Swing Gate Motor Not Working": "Inspect the swing gate motor, arms and control unit.",
  "Boom Barrier Not Opening / Closing": "Diagnose the barrier motor, controls and safety devices.",
  "Gate Limit Switch Fault": "Adjust or replace the gate limit switch to restore travel limits.",
  "Safety Sensor Not Working": "Check and align the gate safety sensor and its wiring.",
  "Gate Stops or Reverses Midway": "Inspect gate travel, obstruction detection and motor settings.",
  "Additional Remote Programming": "Pair an additional authorised remote with the gate receiver.",
  "Other Gate Automation Issue": "Describe the gate automation issue for technician assessment.",
  "Electric Fence Has No Power": "Check the energizer, fence circuit and power connection.",
  "Electric Fence False Alarm": "Inspect fence zones and connections causing repeated alerts.",
  "Fence Energizer Not Working": "Diagnose the energizer and its power and output connections.",
  "Electric Fence Wire Damaged": "Inspect and repair damaged fence wire and insulators.",
  "New Electric Fence Installation": "Install an electric fence and verify its operation.",
  "Other Electric Fence Issue": "Describe the fence issue for technician assessment.",
  "Electric Fence Voltage Too Low": "Measure fence output and check for leakage or poor connections.",
  "Electric Fence Short Circuit / Ground Fault": "Locate and repair a short or ground fault in the fence circuit.",
  "Electric Fence Maintenance & Inspection": "Inspect the energizer, wiring, insulators and fence output.",
};

const getIssueDescription = (serviceTypeId: string, categoryId: string, issueTitle: string) => {
  if (serviceTypeId !== "security_systems") {
    return `Troubleshooting & verified repair for ${issueTitle.toLowerCase()}.`;
  }

  const description = SECURITY_ISSUE_DESCRIPTIONS[issueTitle]
    || `Service and repair for ${issueTitle.toLowerCase()}.`;
  return categoryId === "electric_fence"
    ? `${description} High-voltage fence work must be handled by a qualified technician.`
    : description;
};

// 30-minute interval slots from 08:00 AM to 07:00 PM
const TIME_SLOTS = [
  "08:00 AM",
  "08:30 AM",
  "09:00 AM",
  "09:30 AM",
  "10:00 AM",
  "10:30 AM",
  "11:00 AM",
  "11:30 AM",
  "12:00 PM",
  "12:30 PM",
  "01:00 PM",
  "01:30 PM",
  "02:00 PM",
  "02:30 PM",
  "03:00 PM",
  "03:30 PM",
  "04:00 PM",
  "04:30 PM",
  "05:00 PM",
  "05:30 PM",
  "06:00 PM",
  "06:30 PM",
  "07:00 PM",
];

const CHENNAI_SERVICE_CENTER = { lat: 13.0827, lng: 80.2707 };
const CHENNAI_SERVICE_RADIUS_KM = 100;
const CHENNAI_SERVICE_ERROR = "Select a location within 100 km of Chennai. We do not provide service outside this area.";

const isWithinChennaiServiceArea = (lat: number, lng: number): boolean => {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const latDelta = toRadians(lat - CHENNAI_SERVICE_CENTER.lat);
  const lngDelta = toRadians(lng - CHENNAI_SERVICE_CENTER.lng);
  const a = Math.sin(latDelta / 2) ** 2 +
    Math.cos(toRadians(CHENNAI_SERVICE_CENTER.lat)) * Math.cos(toRadians(lat)) *
    Math.sin(lngDelta / 2) ** 2;
  const distanceKm = 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return distanceKm <= CHENNAI_SERVICE_RADIUS_KM;
};

// Convert slot strings like "08:30 AM" / "07:00 PM" to minutes since midnight
const parseSlotMinutes = (slot: string): number => {
  const match = slot.trim().match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return -1;
  let hours = Number(match[1]);
  const minutes = Number(match[2]);
  const period = match[3].toUpperCase();
  if (period === "PM" && hours !== 12) hours += 12;
  if (period === "AM" && hours === 12) hours = 0;
  return hours * 60 + minutes;
};

// Format local calendar date as YYYY-MM-DD (avoids UTC date shift)
const formatLocalDateStr = (d: Date): string => {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
};

// Helper to normalize strings for robust fuzzy matching
const normalize = (s?: string) =>
  (s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");

const autoFitPaddedImage = (image: HTMLImageElement) => {
  const source = image.currentSrc || image.src;
  if (image.dataset.autoFitSource === source || !image.naturalWidth || !image.naturalHeight) return;
  image.dataset.autoFitSource = source;
  image.style.transform = "";
  image.style.transformOrigin = "";

  try {
    const scanWidth = 80;
    const scanHeight = 50;
    const canvas = document.createElement("canvas");
    canvas.width = scanWidth;
    canvas.height = scanHeight;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return;
    context.drawImage(image, 0, 0, scanWidth, scanHeight);

    const { data } = context.getImageData(0, 0, scanWidth, scanHeight);
    let minX = scanWidth;
    let minY = scanHeight;
    let maxX = -1;
    let maxY = -1;
    for (let y = 0; y < scanHeight; y += 1) {
      for (let x = 0; x < scanWidth; x += 1) {
        const offset = (y * scanWidth + x) * 4;
        const alpha = data[offset + 3];
        const isNearWhite = data[offset] > 238 && data[offset + 1] > 238 && data[offset + 2] > 238;
        if (alpha > 16 && !isNearWhite) {
          minX = Math.min(minX, x);
          minY = Math.min(minY, y);
          maxX = Math.max(maxX, x);
          maxY = Math.max(maxY, y);
        }
      }
    }

    const contentWidth = maxX - minX + 1;
    const contentHeight = maxY - minY + 1;
    if (contentWidth <= 0 || contentHeight <= 0 || (contentWidth / scanWidth > 0.78 && contentHeight / scanHeight > 0.78)) return;

    const box = image.parentElement;
    if (!box) return;
    const fitScale = Math.min(box.clientWidth / image.naturalWidth, box.clientHeight / image.naturalHeight);
    const widthFraction = contentWidth / scanWidth;
    const heightFraction = contentHeight / scanHeight;
    const zoom = Math.min(
      box.clientWidth / (image.naturalWidth * fitScale * widthFraction),
      box.clientHeight / (image.naturalHeight * fitScale * heightFraction),
      8,
    );
    if (zoom <= 1.15) return;

    image.style.transform = `scale(${zoom})`;
    image.style.transformOrigin = `${((minX + maxX + 1) / 2 / scanWidth) * 100}% ${((minY + maxY + 1) / 2 / scanHeight) * 100}%`;
  } catch {
    // Cross-origin images cannot be scanned; their natural frame still fits in the card.
  }
};

// Check if a catalog item matches a taxonomy service type
const itemMatchesServiceType = (
  item: ServiceCatalogItem,
  sType: TaxonomyServiceType
): boolean => {
  if (!item.is_active) return false;
  const itemStNorm = normalize(item.service_type);
  const typeNameNorm = normalize(sType.name);
  const typeIdNorm = normalize(sType.id);

  if (itemStNorm === typeNameNorm || itemStNorm === typeIdNorm) return true;

  if (
    itemStNorm.includes(typeIdNorm) ||
    typeNameNorm.includes(itemStNorm) ||
    itemStNorm.includes(typeNameNorm)
  )
    return true;

  // Also check if item's category matches any category under this service type
  const itemCatNorm = normalize(item.category);
  return sType.categories.some(
    (cat) =>
      normalize(cat.name) === itemCatNorm ||
      normalize(cat.id) === itemCatNorm ||
      normalize(cat.name).includes(itemCatNorm) ||
      itemCatNorm.includes(normalize(cat.name))
  );
};

// Check if a catalog item matches a specific category
const itemMatchesCategory = (
  item: ServiceCatalogItem,
  cat: TaxonomyCategory
): boolean => {
  if (!item.is_active) return false;
  const itemCatNorm = normalize(item.category);
  const catNameNorm = normalize(cat.name);
  const catIdNorm = normalize(cat.id);

  const cleaningCategoryAliases: Record<string, string> = {
    "sofacarpetmattressandcurtain": "sofacarpetmattresscurtaincleaning",
    "watertankandsumpcleaning": "watertanksumpcleaning",
    "kitchencleaning": "kitchendeepcleaning",
    "bathroomcleaning": "bathroomdeepcleaning",
    "officeandcommercialcleaning": "officecommercialcleaning",
    "specialisedcleaning": "specialisedcleaningservices",
  };
  const itemCategoryAlias = cleaningCategoryAliases[itemCatNorm];

  return (
    itemCatNorm === catNameNorm ||
    itemCategoryAlias === catNameNorm ||
    itemCatNorm === catIdNorm ||
    itemCatNorm.includes(catNameNorm) ||
    catNameNorm.includes(itemCatNorm)
  );
};

export default function CustomerNewRequestMarketplace({
  onNavigate,
}: CustomerNewRequestMarketplaceProps) {
  const { addToast } = useOptionalToast();

  // Search input in hero banner
  const [searchQuery, setSearchQuery] = useState("");

  // Live active catalog items from database
  const [catalogItems, setCatalogItems] = useState<ServiceCatalogItem[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(true);

  // Profile data for pre-populating location and phone number
  const [profileData, setProfileData] = useState<any>(null);

  // "No Services Found" modal for 0-count categories or failed search
  const [noServicesModalName, setNoServicesModalName] = useState<string | null>(null);

  // Multi-level navigation state:
  // LEVEL 1: SERVICES (all 16 service trade cards)
  // LEVEL 2: CATEGORIES (image cards of selected service trade)
  // LEVEL 3: ISSUES (image cards of selected category)
  // LEVEL 4: BOOKING_FORM (date, time chips, address text only, map picker, contact)
  type ViewLevel = "SERVICES" | "CATEGORIES" | "ISSUES" | "BOOKING_FORM";
  const [viewLevel, setViewLevel] = useState<ViewLevel>("SERVICES");

  // Keep browser Back/Forward in sync with the marketplace's nested booking screens.
  const changeViewLevel = (level: ViewLevel) => {
    if (level === viewLevel) return;
    window.history.pushState(
      {
        ...(window.history.state || {}),
        fieldOps: {
          ...(window.history.state?.fieldOps || {}),
          bookingLevel: level,
        },
      },
      "",
      window.location.href,
    );
    setViewLevel(level);
  };

  useEffect(() => {
    const state = window.history.state || {};
    if (state.fieldOps?.bookingLevel !== viewLevel) {
      window.history.replaceState(
        {
          ...state,
          fieldOps: { ...(state.fieldOps || {}), bookingLevel: viewLevel },
        },
        "",
        window.location.href,
      );
    }
    const handleBookingPopState = (event: PopStateEvent) => {
      const level = event.state?.fieldOps?.bookingLevel;
      if (["SERVICES", "CATEGORIES", "ISSUES", "BOOKING_FORM"].includes(level)) {
        setViewLevel(level as ViewLevel);
        if (level !== "BOOKING_FORM") {
          setSearchQuery("");
        }
      }
    };
    window.addEventListener("popstate", handleBookingPopState);
    return () => window.removeEventListener("popstate", handleBookingPopState);
    // Initialize history once for this marketplace instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [selectedServiceType, setSelectedServiceType] = useState<TaxonomyServiceType | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<TaxonomyCategory | null>(null);
  const [selectedIssue, setSelectedIssue] = useState<string>("");

  // Category and Issue filtering switches: ALL | ACTIVE | INACTIVE
  const [unavailableModalIssue, setUnavailableModalIssue] = useState<string | null>(null);

  // 5-Day window options: Today (slots >= 3h from now) + Next 4 Days
  const dayOptions = useMemo(() => {
    const options: {
      dateStr: string;
      dayLabel: string;
      dateDisplay: string;
      isToday: boolean;
      isSelectable: boolean;
    }[] = [];

    const now = new Date();
    for (let i = 0; i < 5; i++) {
      const d = new Date(now);
      d.setDate(now.getDate() + i);
      const dateStr = formatLocalDateStr(d);

      let dayLabel = "";
      if (i === 0) dayLabel = "Today";
      else if (i === 1) dayLabel = "Tomorrow";
      else {
        dayLabel = d.toLocaleDateString("en-US", { weekday: "short" });
      }

      const dateDisplay = d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });

      options.push({
        dateStr,
        dayLabel,
        dateDisplay,
        isToday: i === 0,
        isSelectable: true,
      });
    }
    return options;
  }, []);

  // Priority Options
  const PRIORITY_OPTIONS = [
    {
      value: "LOW",
      label: "Low Priority",
      desc: "Routine & Flexible",
      icon: "🌱",
      color: "#059669",
      bg: "#ECFDF5",
      border: "#A7F3D0",
    },
    {
      value: "MEDIUM",
      label: "Standard",
      desc: "Normal Business Priority",
      icon: "⚡",
      color: "#2563EB",
      bg: "#EFF6FF",
      border: "#BFDBFE",
    },
    {
      value: "HIGH",
      label: "High Priority",
      desc: "Urgent turnaround required",
      icon: "🔥",
      color: "#D97706",
      bg: "#FFFBEB",
      border: "#FDE68A",
    },
    {
      value: "URGENT",
      label: "Emergency",
      desc: "Critical breakdown",
      icon: "🚨",
      color: "#DC2626",
      bg: "#FEF2F2",
      border: "#FECACA",
    },
  ];

  // Form Fields
  // Date and Time must be explicitly chosen by the customer (unselected initially)
  const [preferredDate, setPreferredDate] = useState<string>("");
  const [preferredTimeSlot, setPreferredTimeSlot] = useState<string>("");
  const [priority, setPriority] = useState<string>("MEDIUM");
  const [contactNumber, setContactNumber] = useState<string>("");
  const [locationAddress, setLocationAddress] = useState<string>("");
  const [isEditingLocation, setIsEditingLocation] = useState<boolean>(false);
  const [isEditingPhone, setIsEditingPhone] = useState<boolean>(false);
  const [siteCoords, setSiteCoords] = useState<{ lat?: number; lng?: number }>({});
  const [isLocating, setIsLocating] = useState<boolean>(false);
  const [additionalNotes, setAdditionalNotes] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submissionSuccess, setSubmissionSuccess] = useState<{ id: number } | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Map Picker Modal State
  const [showMapModal, setShowMapModal] = useState<boolean>(false);
  const [tempMarkerCoords, setTempMarkerCoords] = useState<{ lat: number; lng: number }>({
    lat: 13.0827,
    lng: 80.2707,
  });
  const [tempResolvedAddress, setTempResolvedAddress] = useState<string>("");

  // Fetch catalog function
  const fetchActiveCatalog = async () => {
    try {
      const items = await getCustomerCatalog();
      if (Array.isArray(items)) {
        setCatalogItems(items);
      }
    } catch (err) {
      console.error("Failed to load customer catalog:", err);
    } finally {
      setLoadingCatalog(false);
    }
  };

  // Hydrate location & 10-digit phone directly from customer profile
  const loadProfileDefaults = () => {
    const applyProfile = (prof: any) => {
      if (!prof) return;
      const digitsOnly = String(prof.mobile_number || "").replace(/\D/g, "").slice(0, 10);
      setContactNumber(digitsOnly);
      const fullAddr =
        [prof.address, prof.city, prof.state, prof.pincode]
          .filter(Boolean)
          .join(", ") ||
        prof.address ||
        prof.city ||
        "";
      setLocationAddress(fullAddr);
      setIsEditingLocation(false);
      setIsEditingPhone(false);
    };

    if (profileData) {
      applyProfile(profileData);
    }

    getCustomerProfile()
      .then((res) => {
        if (res?.data) {
          setProfileData(res.data);
          applyProfile(res.data);
        }
      })
      .catch(() => {});
  };

  // Load catalog and customer profile on mount
  useEffect(() => {
    fetchActiveCatalog();
    loadProfileDefaults();

    const onFocus = () => fetchActiveCatalog();
    window.addEventListener("focus", onFocus);
    const interval = setInterval(fetchActiveCatalog, 5000);

    return () => {
      window.removeEventListener("focus", onFocus);
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Always refresh default profile location and phone whenever entering the booking form
  useEffect(() => {
    if (
      (viewLevel === "CATEGORIES" && !selectedServiceType) ||
      (viewLevel === "ISSUES" && (!selectedServiceType || !selectedCategory)) ||
      (viewLevel === "BOOKING_FORM" &&
        (!selectedServiceType || !selectedCategory || !selectedIssue))
    ) {
      setViewLevel("SERVICES");
    }
  }, [viewLevel, selectedServiceType, selectedCategory, selectedIssue]);

  useEffect(() => {
    if (viewLevel === "BOOKING_FORM") {
      loadProfileDefaults();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewLevel]);

  // An issue is available when at least one organization currently offers it.
  const isTaxonomyIssueActive = (
    sType: TaxonomyServiceType,
    category: TaxonomyCategory,
    issueName: string,
  ): boolean => {
    const normIssue = normalize(issueName);
    return catalogItems.some((item) => {
      const itemIssue = normalize(item.issue || item.category || item.service_type);
      const matchesIssue = normIssue.length > 0 && (
        itemIssue === normIssue ||
        itemIssue.includes(normIssue) ||
        normIssue.includes(itemIssue)
      );
      return itemMatchesServiceType(item, sType) && itemMatchesCategory(item, category) && matchesIssue;
    });
  };

  // Count each taxonomy issue once, even when several organizations offer it.
  const getActiveCountForCategory = (sType: TaxonomyServiceType, cat: TaxonomyCategory) =>
    cat.issues.filter((issue) => isTaxonomyIssueActive(sType, cat, issue)).length;

  const getActiveCountForServiceType = (sType: TaxonomyServiceType) =>
    sType.categories.reduce((count, cat) => count + getActiveCountForCategory(sType, cat), 0);

  // Handle clicking a Service Type Card (Level 1 ➔ Level 2)
  const handleServiceTypeClick = (sType: TaxonomyServiceType) => {
    setSelectedServiceType(sType);
    setSelectedCategory(null);
    setSelectedIssue("");
    changeViewLevel("CATEGORIES");
  };

  const isIssueActive = (issueName: string): boolean =>
    Boolean(selectedServiceType && selectedCategory && isTaxonomyIssueActive(selectedServiceType, selectedCategory, issueName));

  // Open the issue list for the selected available category.
  const handleCategoryClick = (cat: TaxonomyCategory) => {
    if (!selectedServiceType) return;
    setSelectedCategory(cat);
    setSelectedIssue("");
    changeViewLevel("ISSUES");
  };

  // Handle selecting an issue: Active issues proceed to Booking, Inactive issues trigger Unavailable modal
  const handleIssueSelect = (issueName: string) => {
    if (!isIssueActive(issueName)) {
      setUnavailableModalIssue(issueName);
      return;
    }
    setSelectedIssue(issueName);
    setPreferredDate("");
    setPreferredTimeSlot("");
    setSubmissionSuccess(null);
    setSubmitError(null);
    loadProfileDefaults();
    changeViewLevel("BOOKING_FORM");
  };

  // Handle Search Submission in Hero Banner
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      setNoServicesModalName("All Services");
      return;
    }

    // Match query with active items in catalog
    const matchingItem = catalogItems.find(
      (it) =>
        it.is_active &&
        (it.issue.toLowerCase().includes(query) ||
          it.category.toLowerCase().includes(query) ||
          it.service_type.toLowerCase().includes(query))
    );

    if (matchingItem) {
      const matchedType = SERVICE_CATALOGUE_TAXONOMY.find((st) =>
        itemMatchesServiceType(matchingItem, st)
      );
      if (matchedType) {
        const matchedCat = matchedType.categories.find((cat) =>
          itemMatchesCategory(matchingItem, cat)
        );
        setSelectedServiceType(matchedType);
        setSelectedCategory(matchedCat || matchedType.categories[0]);
        setSelectedIssue(matchingItem.issue);
        setPreferredDate("");
        setPreferredTimeSlot("");
        loadProfileDefaults();
        changeViewLevel("BOOKING_FORM");
        setSubmissionSuccess(null);
        setSubmitError(null);
        return;
      }
    }

    // If query matches a taxonomy category name directly
    for (const st of SERVICE_CATALOGUE_TAXONOMY) {
      for (const cat of st.categories) {
        if (cat.name.toLowerCase().includes(query)) {
          setSelectedServiceType(st);
          handleCategoryClick(cat);
          return;
        }
      }
    }

    // No matching services found
    setNoServicesModalName(searchQuery.trim());
  };

  // GPS "Use Current Location" button
  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      addToast({
        title: "GPS Not Supported",
        message: "Your browser does not support geolocation.",
        type: "error",
      });
      return;
    }

    setIsLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        if (!isWithinChennaiServiceArea(lat, lng)) {
          setIsLocating(false);
          addToast({ title: "Outside Service Area", message: CHENNAI_SERVICE_ERROR, type: "error" });
          return;
        }
        setSiteCoords({ lat, lng });

        try {
          const res = await reverseLocation(lat, lng);
          const resolved =
            res.data?.verified &&
            (res.data.address || res.data.formatted_address || res.data.name);

          if (resolved) {
            setLocationAddress(resolved);
            addToast({
              title: "Location Acquired",
              message: "Street address identified successfully.",
              type: "success",
            });
          } else {
            const osm = await fetch(
              `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`
            );
            const osmData = await osm.json();
            if (osmData?.display_name) {
              setLocationAddress(osmData.display_name);
              addToast({
                title: "Location Acquired",
                message: "Street address identified successfully.",
                type: "success",
              });
            } else {
              addToast({
                title: "GPS Tagged",
                message: "Coordinates captured for dispatch. Please confirm your street address text.",
                type: "info",
              });
            }
          }
        } catch (e) {
          addToast({
            title: "GPS Tagged",
            message: "Coordinates captured for dispatch. Please enter your street address.",
            type: "info",
          });
        } finally {
          setIsLocating(false);
        }
      },
      (err) => {
        setIsLocating(false);
        addToast({
          title: "GPS Access Denied",
          message: "Could not retrieve GPS coordinates. Please enter your address manually.",
          type: "error",
        });
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  // Open "Pick on a Map" Modal
  const handleOpenMapPicker = () => {
    const lat = siteCoords.lat || (profileData?.latitude ? Number(profileData.latitude) : 13.0827);
    const lng = siteCoords.lng || (profileData?.longitude ? Number(profileData.longitude) : 80.2707);
    setTempMarkerCoords({ lat, lng });
    setTempResolvedAddress(locationAddress || "");
    setShowMapModal(true);
  };

  // Confirm Location from Map Modal
  const handleConfirmMapLocation = () => {
    if (!isWithinChennaiServiceArea(tempMarkerCoords.lat, tempMarkerCoords.lng)) {
      addToast({ title: "Outside Service Area", message: CHENNAI_SERVICE_ERROR, type: "error" });
      return;
    }
    setSiteCoords(tempMarkerCoords);
    if (tempResolvedAddress) {
      setLocationAddress(tempResolvedAddress);
    }
    setShowMapModal(false);
    addToast({
      title: "Location Confirmed",
      message: "Selected map location tagged successfully.",
      type: "success",
    });
  };

  // Submit booking form
  const handleBookingSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedServiceType || !selectedCategory) return;

    const showValidationToast = (message: string, title = "Missing Required Field") => {
      setSubmitError(null);
      addToast({ title, message, type: "error" });
    };

    if (siteCoords.lat != null && siteCoords.lng != null &&
        !isWithinChennaiServiceArea(siteCoords.lat, siteCoords.lng)) {
      showValidationToast(CHENNAI_SERVICE_ERROR, "Outside Service Area");
      return;
    }

    if (!selectedIssue) {
      showValidationToast("Please select a diagnostic issue.");
      return;
    }
    if (!preferredDate) {
      showValidationToast("Please select your preferred appointment date.");
      return;
    }
    if (!preferredTimeSlot) {
      showValidationToast("Please select your preferred appointment time slot.");
      return;
    }

    const now = new Date();
    const todayStr = formatLocalDateStr(now);
    const nowMinutes = now.getHours() * 60 + now.getMinutes();
    if (preferredDate === todayStr) {
      if (now.getHours() >= 19) {
        addToast({
          title: "Today's Service Closed",
          message:
            "Service is unavailable after 7:00 PM for today. Please select tomorrow's date and time.",
          type: "warning",
        });
        return;
      }
      if (parseSlotMinutes(preferredTimeSlot) < nowMinutes + 180) {
        showValidationToast(
          "Selected time slot is unavailable for today. Please choose another available slot.",
          "Slot Unavailable",
        );
        return;
      }
    }

    if (!locationAddress.trim()) {
      showValidationToast("Please provide your service location address.");
      return;
    }

    const cleanedPhone = contactNumber.replace(/\D/g, "").trim();
    if (!cleanedPhone) {
      showValidationToast("Please provide a contact phone number.");
      return;
    }
    if (!/^\d{10}$/.test(cleanedPhone)) {
      showValidationToast(
        "Contact phone number must be exactly 10 digits.",
        "Invalid Phone Number",
      );
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const constructedDescription = `${selectedIssue} - ${selectedCategory.name} (${selectedServiceType.name} Service). ${additionalNotes.trim()}`.trim();

    const payload = {
      service_type: selectedServiceType.name,
      title: selectedCategory.name,
      category: selectedCategory.name,
      issue: selectedIssue,
      description: constructedDescription,
      priority: priority || "MEDIUM",
      preferred_visit_date: preferredDate || undefined,
      preferred_visit_time: preferredTimeSlot || undefined,
      contact_number: cleanedPhone,
      location: locationAddress.trim(),
      site_latitude: siteCoords.lat,
      site_longitude: siteCoords.lng,
    };

    try {
      const res = await createServiceRequest(payload);
      const createdId =
        res.data?.created_job?.id ??
        res.data?.linked_job_id ??
        res.data?.id ??
        101;
      setSubmissionSuccess({ id: createdId });
      addToast({
        title: "Request Submitted Successfully",
        message: `Service request #${createdId} created. AI Planning Agent is matching eligible technicians by live location.`,
        type: "success",
      });
    } catch (err: any) {
      console.error("Failed to create service request:", err);
      const detail = err.response?.data?.detail;
      const errorMsg =
        typeof detail === "string"
          ? detail
          : detail?.message ||
            "Failed to submit service request. Please check your inputs and try again.";
      setSubmitError(null);
      addToast({
        title: "Submission Failed",
        message: errorMsg,
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        padding: "20px 24px 40px 24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        boxSizing: "border-box",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <div style={{ maxWidth: "1220px", margin: "0 auto" }}>
        {/* User-Provided Hero Banner: ONLY displayed on LEVEL 1 Home View */}
        {viewLevel === "SERVICES" ? (
          <div
            style={{
              position: "relative",
              width: "100%",
              borderRadius: "16px",
              overflow: "hidden",
              boxShadow: "0 2px 10px rgba(0, 0, 0, 0.04)",
              marginBottom: "22px",
              border: "1px solid #E2E8F0",
              backgroundImage: "url('/services/user_banner.png')",
              backgroundSize: "cover",
              backgroundPosition: "center",
              backgroundRepeat: "no-repeat",
              minHeight: "200px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "28px 20px 24px 20px",
              boxSizing: "border-box",
              textAlign: "center",
            }}
          >
            {/* 1. Title */}
            <h1
              style={{
                fontSize: "27px",
                fontWeight: 800,
                color: "#0F172A",
                margin: "0 0 6px 0",
                letterSpacing: "-0.5px",
                fontFamily: "'Inter', sans-serif",
              }}
            >
              What service do you need today?
            </h1>

            {/* 2. Subtitle */}
            <p
              style={{
                fontSize: "13.5px",
                fontWeight: 600,
                color: "#334155",
                margin: "0 0 18px 0",
                maxWidth: "540px",
              }}
            >
              Search for a service or choose a category to get matched with a
              technician
            </p>

            {/* 3. Search Bar */}
            <form
              onSubmit={handleSearchSubmit}
              style={{
                width: "100%",
                maxWidth: "580px",
                background: "#FFFFFF",
                borderRadius: "999px",
                border: "1.5px solid #CBD5E1",
                boxShadow: "0 4px 16px rgba(0, 0, 0, 0.08)",
                display: "flex",
                alignItems: "center",
                padding: "4px 6px 4px 18px",
                gap: "10px",
                boxSizing: "border-box",
              }}
            >
              <Search size={18} color="#059669" style={{ flexShrink: 0 }} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search for a service (e.g. AC repair, plumber, electrical, wiring...)"
                style={{
                  flex: 1,
                  border: "none",
                  outline: "none",
                  fontSize: "13.5px",
                  fontWeight: 500,
                  color: "#0F172A",
                  background: "transparent",
                  minWidth: 0,
                }}
              />
              {searchQuery && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => setSearchQuery("")}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "#64748B",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "4px",
                    cursor: "pointer",
                  }}
                >
                  <X size={15} />
                </button>
              )}
              <button
                type="submit"
                style={{
                  background: "#047857",
                  color: "#FFFFFF",
                  border: "none",
                  borderRadius: "999px",
                  padding: "9px 24px",
                  fontSize: "13.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                  transition: "background 0.15s ease",
                  flexShrink: 0,
                  boxShadow: "0 2px 4px rgba(4, 120, 87, 0.2)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "#065F46";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "#047857";
                }}
              >
                Search
              </button>
            </form>
          </div>
        ) : null}

                {/* ─────────────────────────────────────────────────────────────
            LEVEL 1: BROWSE SERVICE TYPES (High Contrast, Rich Real App Cards)
            NO ELE, PLU, ACR BADGES!
        ───────────────────────────────────────────────────────────── */}
        {viewLevel === "SERVICES" && (
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "16px",
              border: "1.5px solid #CBD5E1",
              padding: "20px 22px 28px 22px",
              boxShadow: "0 4px 18px rgba(15, 23, 42, 0.04)",
            }}
          >
            {/* Header Row */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "18px",
                flexWrap: "wrap",
                gap: "10px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div
                  style={{
                    width: "34px",
                    height: "34px",
                    borderRadius: "10px",
                    background: "#0F172A",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <LayoutGrid size={18} color="#FFFFFF" />
                </div>
                <div>
                  <h2
                    style={{
                      fontSize: "17.5px",
                      fontWeight: 800,
                      color: "#0F172A",
                      margin: 0,
                      letterSpacing: "-0.3px",
                    }}
                  >
                    Browse Service Categories
                  </h2>
                  <span style={{ fontSize: "12px", color: "#475569", fontWeight: 500 }}>
                    Select a service category to view specialized diagnostic issues
                  </span>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "12px",
                  fontWeight: 700,
                  color: "#0F172A",
                  background: "#F1F5F9",
                  border: "1px solid #CBD5E1",
                  padding: "5px 12px",
                  borderRadius: "999px",
                }}
              >
                <Sparkles size={13} color="#059669" />
                <span>Available Service Types ({SERVICE_CATALOGUE_TAXONOMY.filter((sType) => getActiveCountForServiceType(sType) > 0).length})</span>
              </div>
            </div>

            {/* 16 Service Types Grid (Compact, Sleek, Proper Verified Cards) */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(195px, 1fr))",
                gap: "14px",
              }}
            >
              {loadingCatalog && catalogItems.length === 0 ? (
                <div style={{ gridColumn: "1 / -1", color: "#64748B", fontSize: "13px", padding: "16px" }}>
                  Loading available services...
                </div>
              ) : null}
              {!loadingCatalog && SERVICE_CATALOGUE_TAXONOMY.every((sType) => getActiveCountForServiceType(sType) === 0) ? (
                <div style={{ gridColumn: "1 / -1", color: "#64748B", fontSize: "13px", padding: "16px" }}>
                  No services are currently available to book.
                </div>
              ) : null}
              {SERVICE_CATALOGUE_TAXONOMY.filter((sType) => getActiveCountForServiceType(sType) > 0).map((sType) => {
                const liveCount = getActiveCountForServiceType(sType);

                return (
                  <div
                    key={sType.id}
                    onClick={() => handleServiceTypeClick(sType)}
                    style={{
                      background: "#FFFFFF",
                      border: "1.5px solid #E2E8F0",
                      borderRadius: "14px",
                      padding: "10px 10px 12px 10px",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      cursor: "pointer",
                      transition: "all 0.2s ease",
                      boxShadow: "0 2px 8px rgba(15, 23, 42, 0.03)",
                      position: "relative",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = "translateY(-3px)";
                      e.currentTarget.style.boxShadow =
                        "0 10px 22px -4px rgba(15, 23, 42, 0.10)";
                      e.currentTarget.style.borderColor = "#059669";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = "translateY(0)";
                      e.currentTarget.style.boxShadow =
                        "0 2px 8px rgba(15, 23, 42, 0.03)";
                      e.currentTarget.style.borderColor = "#E2E8F0";
                    }}
                  >
                    {/* Proper Verified Trade Illustration Container */}
                    <div
                      style={{
                        height: "105px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        marginBottom: "8px",
                        background: "#F8FAFC",
                        borderRadius: "10px",
                        border: "1px solid #E2E8F0",
                        padding: "4px",
                        overflow: "hidden",
                        position: "relative",
                      }}
                    >
                      <img
                        src={sType.image}
                        alt={sType.name}
                        loading="lazy"
                        onLoad={(e) => autoFitPaddedImage(e.currentTarget)}
                        style={{
                          height: "95%",
                          width: "95%",
                          objectFit: "contain",
                          filter: "drop-shadow(0 4px 8px rgba(0, 0, 0, 0.08))",
                        }}
                      />
                      {liveCount > 0 && (
                        <div
                          style={{
                            position: "absolute",
                            top: "6px",
                            right: "6px",
                            background: "rgba(5, 150, 105, 0.95)",
                            color: "#FFFFFF",
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 7px",
                            borderRadius: "999px",
                          }}
                        >
                          {liveCount} Active
                        </div>
                      )}
                    </div>

                    {/* Service Name & Description (Compact, Crisp Dark Text) */}
                    <div style={{ flex: 1, marginBottom: "10px", padding: "0 2px" }}>
                      <h3
                        style={{
                          fontSize: "14px",
                          fontWeight: 800,
                          color: "#0F172A",
                          margin: "0 0 4px 0",
                          lineHeight: 1.25,
                          letterSpacing: "-0.2px",
                        }}
                      >
                        {sType.name}
                      </h3>
                      <p
                        style={{
                          fontSize: "11px",
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
                        {sType.description}
                      </p>
                    </div>

                    {/* Compact Status Pill */}
                    <div>
                      {liveCount > 0 ? (
                        <span
                          style={{
                            background: "#ECFDF5",
                            border: "1.5px solid #059669",
                            color: "#065F46",
                            fontSize: "11px",
                            fontWeight: 800,
                            padding: "4px 10px",
                            borderRadius: "999px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                            boxShadow: "0 1px 3px rgba(5, 150, 105, 0.10)",
                          }}
                        >
                          <span>{liveCount} {liveCount === 1 ? "Service" : "Services"} Available</span>
                          <ChevronRight size={12} color="#059669" />
                        </span>
                      ) : (
                        <span
                          style={{
                            background: "#F8FAFC",
                            border: "1px solid #CBD5E1",
                            color: "#475569",
                            fontSize: "10.5px",
                            fontWeight: 700,
                            padding: "4px 8px",
                            borderRadius: "999px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "3px",
                          }}
                        >
                          <span>Explore ({sType.categories.length} Categories)</span>
                          <ChevronRight size={11} color="#94A3B8" />
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ─────────────────────────────────────────────────────────────
            LEVEL 2: CATEGORIES VIEW WITH COMPACT HD CARDS & ACTIVE SWITCH
        ───────────────────────────────────────────────────────────── */}
        {viewLevel === "CATEGORIES" && selectedServiceType && (() => {
          const allCategories = selectedServiceType.categories;
          const activeCategoriesCount = allCategories.filter(
            (c) => getActiveCountForCategory(selectedServiceType, c) > 0
          ).length;
          const displayedCategories = allCategories.filter(
            (cat) => getActiveCountForCategory(selectedServiceType, cat) > 0,
          );

          return (
            <div
              style={{
                background: "#FFFFFF",
                borderRadius: "16px",
                border: "1.5px solid #CBD5E1",
                padding: "20px 22px 28px 22px",
                boxShadow: "0 4px 18px rgba(15, 23, 42, 0.04)",
              }}
            >
              {/* Breadcrumb Navigation & Back Button */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "16px",
                  flexWrap: "wrap",
                  gap: "10px",
                }}
              >
                <button
                  type="button"
                  onClick={() => window.history.back()}
                  style={{
                    background: "#0F172A",
                    border: "none",
                    borderRadius: "8px",
                    padding: "7px 14px",
                    fontSize: "12.5px",
                    fontWeight: 700,
                    color: "#FFFFFF",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    boxShadow: "0 2px 5px rgba(15, 23, 42, 0.2)",
                  }}
                >
                  <ArrowLeft size={14} />
                  <span>Back to All Services</span>
                </button>

                <div
                  style={{
                    fontSize: "13px",
                    color: "#475569",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                  }}
                >
                  <span>Services</span>
                  <ChevronRight size={13} color="#94A3B8" />
                  <strong style={{ color: "#0F172A" }}>
                    {selectedServiceType.name}
                  </strong>
                </div>
              </div>

              {/* Trade Compact Header Banner */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "16px",
                  marginBottom: "18px",
                  background: "#F8FAFC",
                  padding: "12px 16px",
                  borderRadius: "12px",
                  border: "1px solid #E2E8F0",
                }}
              >
                <div
                  style={{
                    width: "52px",
                    height: "52px",
                    borderRadius: "10px",
                    background: "#FFFFFF",
                    border: "1px solid #CBD5E1",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "4px",
                    flexShrink: 0,
                  }}
                >
                  <img
                    src={selectedServiceType.image}
                    alt={selectedServiceType.name}
                    onLoad={(e) => autoFitPaddedImage(e.currentTarget)}
                    style={{
                      maxHeight: "90%",
                      maxWidth: "90%",
                      objectFit: "contain",
                    }}
                  />
                </div>

                <div>
                  <h2
                    style={{
                      fontSize: "17.5px",
                      fontWeight: 800,
                      color: "#0F172A",
                      margin: "0 0 3px 0",
                      letterSpacing: "-0.3px",
                    }}
                  >
                    {selectedServiceType.name} Categories
                  </h2>
                  <p
                    style={{
                      fontSize: "12px",
                      color: "#475569",
                      fontWeight: 500,
                      margin: 0,
                    }}
                  >
                    {selectedServiceType.description}
                  </p>
                </div>
              </div>

              {/* Show available categories only. */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "18px",
                }}
              >
                <span
                  style={{
                    padding: "6px 14px",
                    borderRadius: "999px",
                    fontSize: "12px",
                    fontWeight: 700,
                    border: "1.5px solid #A7F3D0",
                    background: "#ECFDF5",
                    color: "#065F46",
                  }}
                >
                  Available Categories ({activeCategoriesCount})
                </span>
              </div>

              {/* Categories Grid (Compact HD Photographic Cards) */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                  gap: "14px",
                }}
              >
                {displayedCategories.map((cat) => {
                  const catLiveCount = getActiveCountForCategory(
                    selectedServiceType,
                    cat
                  );
                  const catImg = getCategoryCardImage(cat.id, selectedServiceType.id);

                  return (
                    <div
                      key={cat.id}
                      onClick={() => handleCategoryClick(cat)}
                      style={{
                        background: "#FFFFFF",
                        border: "1.5px solid #E2E8F0",
                        borderRadius: "14px",
                        overflow: "hidden",
                        cursor: "pointer",
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        transition: "all 0.2s ease",
                        boxShadow: "0 2px 8px rgba(15, 23, 42, 0.04)",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = "translateY(-3px)";
                        e.currentTarget.style.boxShadow =
                          "0 10px 22px -4px rgba(15, 23, 42, 0.12)";
                        e.currentTarget.style.borderColor =
                          catLiveCount > 0 ? "#059669" : "#0F172A";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = "translateY(0)";
                        e.currentTarget.style.boxShadow =
                          "0 2px 8px rgba(15, 23, 42, 0.04)";
                        e.currentTarget.style.borderColor = "#E2E8F0";
                      }}
                    >
                      {/* Compact HD Photographic Image Container */}
                      <div
                        style={{
                          height: "105px",
                          width: "100%",
                          position: "relative",
                          overflow: "hidden",
                          background: "#F1F5F9",
                        }}
                      >
                        <img
                          src={catImg}
                          alt={cat.name}
                          loading="lazy"
                          style={{
                            display: "block",
                            width: "100%",
                            height: "100%",
                            maxWidth: "100%",
                            maxHeight: "100%",
                            objectFit: "contain",
                            objectPosition: "center",
                          }}
                          onError={(e) => {
                            const image = e.currentTarget;
                            const fallbackImage = selectedServiceType.image;

                            // Try the service image once; if that also fails,
                            // hide the broken image instead of looping onError.
                            if (
                              image.dataset.fallbackApplied === "true" ||
                              !fallbackImage
                            ) {
                              image.style.visibility = "hidden";
                              return;
                            }

                            image.dataset.fallbackApplied = "true";
                            image.src = fallbackImage;
                          }}
                        />
                        {catLiveCount > 0 && (
                          <div
                            style={{
                              position: "absolute",
                              top: "7px",
                              right: "7px",
                              background: "rgba(5, 150, 105, 0.95)",
                              backdropFilter: "blur(4px)",
                              color: "#FFFFFF",
                              fontSize: "10px",
                              fontWeight: 700,
                              padding: "2px 8px",
                              borderRadius: "999px",
                            }}
                          >
                            ● {catLiveCount} Active
                          </div>
                        )}
                      </div>

                      {/* Category Title & Information */}
                      <div
                        style={{
                          padding: "12px",
                          flex: 1,
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                        }}
                      >
                        <div style={{ marginBottom: "10px" }}>
                          <h3
                            style={{
                              fontSize: "14px",
                              fontWeight: 800,
                              color: "#0F172A",
                              margin: "0 0 3px 0",
                              lineHeight: 1.25,
                            }}
                          >
                            {cat.name}
                          </h3>
                          <p
                            style={{
                              fontSize: "11px",
                              color: "#64748B",
                              fontWeight: 500,
                              margin: 0,
                            }}
                          >
                            {cat.issues.filter((issue) => isTaxonomyIssueActive(selectedServiceType, cat, issue)).length} Available Services
                          </p>
                        </div>

                        {/* Active count badge / action button */}
                        <div>
                          {catLiveCount > 0 ? (
                            <span
                              style={{
                                background: "#ECFDF5",
                                border: "1.5px solid #059669",
                                color: "#065F46",
                                fontSize: "11px",
                                fontWeight: 800,
                                padding: "4px 10px",
                                borderRadius: "999px",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "4px",
                              }}
                            >
                              <span>Explore ({catLiveCount} Active)</span>
                              <ArrowRight size={11} color="#059669" />
                            </span>
                          ) : (
                            <span
                              style={{
                                background: "#F8FAFC",
                                border: "1px solid #CBD5E1",
                                color: "#475569",
                                fontSize: "11px",
                                fontWeight: 700,
                                padding: "4px 8px",
                                borderRadius: "999px",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "3px",
                              }}
                            >
                              <span>Explore Issues ({cat.issues.filter((issue) => isTaxonomyIssueActive(selectedServiceType, cat, issue)).length})</span>
                              <ChevronRight size={11} color="#94A3B8" />
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        {/* ─────────────────────────────────────────────────────────────
            LEVEL 3: AVAILABLE DIAGNOSTIC ISSUES
        ───────────────────────────────────────────────────────────── */}
        {viewLevel === "ISSUES" && selectedServiceType && selectedCategory && (() => {
          const allIssues = selectedCategory.issues;
          const activeIssuesCount = allIssues.filter((iss) => isIssueActive(iss)).length;
          const displayedIssues = allIssues.filter((iss) => isIssueActive(iss));

          return (
            <div
              style={{
                background: "#FFFFFF",
                borderRadius: "16px",
                border: "1.5px solid #CBD5E1",
                padding: "20px 22px 28px 22px",
                boxShadow: "0 4px 18px rgba(15, 23, 42, 0.04)",
              }}
            >
              {/* Breadcrumb Navigation & Back Button */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "16px",
                  flexWrap: "wrap",
                  gap: "10px",
                }}
              >
                <button
                  type="button"
                  onClick={() => window.history.back()}
                  style={{
                    background: "#0F172A",
                    border: "none",
                    borderRadius: "8px",
                    padding: "7px 14px",
                    fontSize: "12.5px",
                    fontWeight: 700,
                    color: "#FFFFFF",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    boxShadow: "0 2px 5px rgba(15, 23, 42, 0.2)",
                  }}
                >
                  <ArrowLeft size={14} />
                  <span>Back to Categories</span>
                </button>

                <div
                  style={{
                    fontSize: "13px",
                    color: "#475569",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                  }}
                >
                  <span>{selectedServiceType.name}</span>
                  <ChevronRight size={13} color="#94A3B8" />
                  <strong style={{ color: "#0F172A" }}>
                    {selectedCategory.name}
                  </strong>
                </div>
              </div>

              {/* Category Header */}
              <div style={{ marginBottom: "16px" }}>
                <h2
                  style={{
                    fontSize: "18px",
                    fontWeight: 800,
                    color: "#0F172A",
                    margin: "0 0 4px 0",
                    letterSpacing: "-0.3px",
                  }}
                >
                  {selectedServiceType.id === "painting"
                    ? ({
                        interior_painting: "Select Interior Painting Service",
                        exterior_painting: "Select Exterior Painting Service",
                        wood_metal_painting: "Select Painting Service",
                        wall_defects: "Select Wall Problem",
                        waterproofing: "Select Waterproofing Service",
                        special_finishes: "Select Special Finish",
                      } as Record<string, string>)[selectedCategory.id]
                    : ["custom_furniture", "furniture_assembly"].includes(selectedCategory.id)
                    ? "Select the Service You Need"
                    : selectedServiceType.id === "plumbing"
                    ? `Select a Plumbing Service in ${selectedCategory.name}`
                    : `Select Diagnostic Issue in ${selectedCategory.name}`}
                </h2>
                <p style={{ fontSize: "12.5px", color: "#475569", fontWeight: 500, margin: 0 }}>
                  {selectedServiceType.id === "painting"
                    ? "Choose the service you need to proceed to appointment booking and scheduling."
                    : ["custom_furniture", "furniture_assembly"].includes(selectedCategory.id)
                    ? "Choose the furniture service you need to proceed to appointment booking and scheduling."
                    : "Choose the specific issue you are experiencing to proceed to appointment booking and scheduling."}
                </p>
              </div>

              {/* Show bookable issues only. */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "18px",
                }}
              >
                <span
                  style={{
                    padding: "6px 14px",
                    borderRadius: "999px",
                    fontSize: "12px",
                    fontWeight: 700,
                    border: "1.5px solid #A7F3D0",
                    background: "#ECFDF5",
                    color: "#065F46",
                  }}
                >
                  Available Services ({activeIssuesCount})
                </span>
              </div>

              {/* Available issue cards */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(215px, 1fr))",
                  gap: "14px",
                }}
              >
                {displayedIssues.map((issueTitle, idx) => {
                  const active = isIssueActive(issueTitle);
                  const issueImg = getIssueCardImage(
                    issueTitle,
                    selectedCategory.id,
                    selectedServiceType.id,
                    idx,
                  );

                  return (
                    <div
                      key={issueTitle}
                      onClick={() => handleIssueSelect(issueTitle)}
                      style={{
                        background: "#FFFFFF",
                        border: active ? "1.5px solid #A7F3D0" : "1.5px solid #E2E8F0",
                        borderRadius: "14px",
                        overflow: "hidden",
                        cursor: "pointer",
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        transition: "all 0.2s ease",
                        boxShadow: active
                          ? "0 2px 8px rgba(5, 150, 105, 0.08)"
                          : "0 2px 6px rgba(15, 23, 42, 0.03)",
                        opacity: active ? 1 : 0.9,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = "translateY(-3px)";
                        if (active) {
                          e.currentTarget.style.borderColor = "#059669";
                          e.currentTarget.style.boxShadow =
                            "0 10px 22px -4px rgba(5, 150, 105, 0.16)";
                        } else {
                          e.currentTarget.style.borderColor = "#94A3B8";
                          e.currentTarget.style.boxShadow =
                            "0 8px 16px -4px rgba(15, 23, 42, 0.08)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = "translateY(0)";
                        e.currentTarget.style.borderColor = active ? "#A7F3D0" : "#E2E8F0";
                        e.currentTarget.style.boxShadow = active
                          ? "0 2px 8px rgba(5, 150, 105, 0.08)"
                          : "0 2px 6px rgba(15, 23, 42, 0.03)";
                      }}
                    >
                      {/* Issue HD Image Header (ALL CARDS HAVE A UNIQUE IMAGE!) */}
                      <div
                        style={{
                          height: "105px",
                          width: "100%",
                          position: "relative",
                          overflow: "hidden",
                          background: "#F1F5F9",
                        }}
                      >
                        <img
                          src={issueImg}
                          alt={issueTitle}
                          loading="lazy"
                          onLoad={(e) => autoFitPaddedImage(e.currentTarget)}
                          style={{
                            display: "block",
                            width: "100%",
                            height: "100%",
                            objectFit: "contain",
                            objectPosition: "center",
                            transition: "filter 0.2s ease",
                            filter: active ? "none" : "grayscale(25%)",
                          }}
                          onError={(e) => {
                            e.currentTarget.src = selectedServiceType.image;
                          }}
                        />

                        {/* Top-Left Diagnostic Badge */}
                        <div
                          style={{
                            position: "absolute",
                            top: "7px",
                            left: "7px",
                            width: "24px",
                            height: "24px",
                            borderRadius: "6px",
                            background: active ? "#059669" : "rgba(15, 23, 42, 0.75)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: "#FFFFFF",
                            boxShadow: "0 2px 4px rgba(0,0,0,0.15)",
                          }}
                        >
                          <Wrench size={13} strokeWidth={2.2} />
                        </div>

                        {/* Top-Right Status Tag */}
                        <div
                          style={{
                            position: "absolute",
                            top: "7px",
                            right: "7px",
                            background: active
                              ? "rgba(5, 150, 105, 0.95)"
                              : "rgba(15, 23, 42, 0.75)",
                            backdropFilter: "blur(4px)",
                            color: "#FFFFFF",
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 7px",
                            borderRadius: "999px",
                          }}
                        >
                          {active ? "● Active Service" : "Unavailable"}
                        </div>
                      </div>

                      {/* Issue Name & Description (Compact, Dark Text) */}
                      <div
                        style={{
                          padding: "11px 12px 12px 12px",
                          flex: 1,
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                        }}
                      >
                        <div style={{ marginBottom: "10px" }}>
                          <h3
                            style={{
                              fontSize: "13.5px",
                              fontWeight: 800,
                              color: "#0F172A",
                              margin: "0 0 3px 0",
                              lineHeight: 1.25,
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                              overflow: "hidden",
                            }}
                          >
                            {issueTitle}
                          </h3>
                          <p
                            style={{
                              fontSize: "11px",
                              color: "#64748B",
                              margin: 0,
                              lineHeight: 1.35,
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                              overflow: "hidden",
                            }}
                          >
                            {getIssueDescription(selectedServiceType.id, selectedCategory.id, issueTitle)}
                          </p>
                        </div>

                        {/* Action Button */}
                        <div>
                          {active ? (
                            <div
                              style={{
                                background: "#059669",
                                color: "#FFFFFF",
                                padding: "6px 12px",
                                borderRadius: "8px",
                                fontSize: "11.5px",
                                fontWeight: 800,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: "5px",
                                boxShadow: "0 2px 5px rgba(5, 150, 105, 0.22)",
                              }}
                            >
                              <span>Book This Issue</span>
                              <ArrowRight size={13} color="#FFFFFF" />
                            </div>
                          ) : (
                            <div
                              style={{
                                background: "#F1F5F9",
                                border: "1px solid #CBD5E1",
                                color: "#64748B",
                                padding: "6px 12px",
                                borderRadius: "8px",
                                fontSize: "11.5px",
                                fontWeight: 700,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: "5px",
                              }}
                            >
                              <Lock size={12} />
                              <span>Currently Unavailable</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        {viewLevel === "BOOKING_FORM" &&
          selectedServiceType &&
          selectedCategory &&
          selectedIssue && (
            <div
              style={{
                background: "#FFFFFF",
                borderRadius: "18px",
                border: "1.5px solid #CBD5E1",
                padding: "26px 30px",
                boxShadow: "0 4px 20px rgba(15, 23, 42, 0.04)",
              }}
            >
              {/* Breadcrumb Navigation & Back Button */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "22px",
                  borderBottom: "1px solid #E2E8F0",
                  paddingBottom: "16px",
                }}
              >
                <button
                  type="button"
                  onClick={() => window.history.back()}
                  disabled={submitting}
                  style={{
                    background: "#0F172A",
                    border: "none",
                    borderRadius: "10px",
                    padding: "8px 16px",
                    fontSize: "13px",
                    fontWeight: 700,
                    color: "#FFFFFF",
                    cursor: submitting ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    boxShadow: "0 2px 6px rgba(15, 23, 42, 0.2)",
                  }}
                >
                  <ArrowLeft size={15} />
                  <span>Back to Issues</span>
                </button>

                <div
                  style={{
                    fontSize: "13.5px",
                    color: "#475569",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <span>{selectedServiceType.name}</span>
                  <ChevronRight size={14} color="#94A3B8" />
                  <span>{selectedCategory.name}</span>
                  <ChevronRight size={14} color="#94A3B8" />
                  <strong style={{ color: "#0F172A" }}>Book Appointment</strong>
                </div>
              </div>

              {/* The Booking Form */}
              <form noValidate onSubmit={handleBookingSubmit}>
                  {/* Selected Issue Summary Banner (NO CODE BADGES) */}
                  <div
                    style={{
                      background: "#F0FDF4",
                      border: "1.5px solid #BBF7D0",
                      borderRadius: "14px",
                      padding: "16px 20px",
                      marginBottom: "24px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontSize: "11.5px",
                          fontWeight: 800,
                          color: "#166534",
                          textTransform: "uppercase",
                          letterSpacing: "0.5px",
                        }}
                      >
                        Selected Problem Details
                      </div>
                      <div
                        style={{
                          fontSize: "16px",
                          fontWeight: 800,
                          color: "#0F172A",
                          marginTop: "2px",
                        }}
                      >
                        {selectedServiceType.name} ➔ {selectedCategory.name} ➔{" "}
                        <span style={{ color: "#059669" }}>{selectedIssue}</span>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => window.history.back()}
                      style={{
                        background: "#FFFFFF",
                        border: "1px solid #059669",
                        borderRadius: "8px",
                        color: "#059669",
                        fontSize: "12.5px",
                        fontWeight: 700,
                        padding: "6px 12px",
                        cursor: "pointer",
                      }}
                    >
                      Change Issue
                    </button>
                  </div>

                  {/* 1. Preferred Appointment Date (Today + Next 4 Days, Today requires +3h lead before 7 PM) */}
                  {(() => {
                    const now = new Date();
                    const todayStr = formatLocalDateStr(now);
                    const nowMinutes = now.getHours() * 60 + now.getMinutes();
                    const minTodayMinutes = nowMinutes + 180;
                    const todaySlotsAvailable =
                      now.getHours() < 19 &&
                      TIME_SLOTS.some(
                        (s) => parseSlotMinutes(s) >= minTodayMinutes,
                      );

                    return (
                      <>
                        <div style={{ marginBottom: "26px" }}>
                          <div style={{ marginBottom: "10px" }}>
                            <label
                              style={{
                                display: "block",
                                fontSize: "14px",
                                fontWeight: 800,
                                color: "#0F172A",
                              }}
                            >
                              1. Preferred Appointment Date{" "}
                              <span style={{ color: "#EF4444" }}>*</span>
                            </label>
                            <span style={{ fontSize: "12.5px", color: "#64748B" }}>
                              Choose Today (when available) or any of the next 4 available days.
                            </span>
                          </div>

                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
                              gap: "12px",
                            }}
                          >
                            {dayOptions.map((opt) => {
                              const isSelected = preferredDate === opt.dateStr;
                              const isTodayClosed = opt.isToday && !todaySlotsAvailable;

                              return (
                                <div
                                  key={opt.dateStr}
                                  onClick={() => {
                                    if (isTodayClosed) {
                                      addToast({
                                        title: "Today's Service Unavailable",
                                        message:
                                          "Service is unavailable for today. Please select tomorrow's date and time.",
                                        type: "warning",
                                      });
                                      if (preferredDate === opt.dateStr) {
                                        setPreferredDate("");
                                        setPreferredTimeSlot("");
                                      }
                                      return;
                                    }
                                    setPreferredDate(opt.dateStr);
                                    if (
                                      opt.isToday &&
                                      preferredTimeSlot &&
                                      parseSlotMinutes(preferredTimeSlot) < minTodayMinutes
                                    ) {
                                      setPreferredTimeSlot("");
                                    }
                                  }}
                                  style={{
                                    padding: "14px 10px",
                                    borderRadius: "12px",
                                    background: isTodayClosed
                                      ? "#F8FAFC"
                                      : isSelected
                                      ? "#ECFDF5"
                                      : "#FFFFFF",
                                    border: isSelected
                                      ? "2px solid #059669"
                                      : isTodayClosed
                                      ? "1.5px solid #E2E8F0"
                                      : "1.5px solid #CBD5E1",
                                    textAlign: "center",
                                    cursor: "pointer",
                                    opacity: isTodayClosed ? 0.78 : 1,
                                    transition: "all 0.15s ease",
                                    boxShadow: isSelected
                                      ? "0 4px 12px rgba(5, 150, 105, 0.2)"
                                      : "0 1px 3px rgba(0, 0, 0, 0.02)",
                                  }}
                                >
                                  <div
                                    style={{
                                      fontSize: "12px",
                                      fontWeight: 700,
                                      color: isSelected
                                        ? "#059669"
                                        : isTodayClosed
                                        ? "#64748B"
                                        : "#475569",
                                    }}
                                  >
                                    {opt.dayLabel}
                                  </div>
                                  <div
                                    style={{
                                      fontSize: "15px",
                                      fontWeight: 800,
                                      color: isSelected
                                        ? "#065F46"
                                        : isTodayClosed
                                        ? "#475569"
                                        : "#0F172A",
                                      margin: "2px 0 6px 0",
                                    }}
                                  >
                                    {opt.dateDisplay}
                                  </div>
                                  <span
                                    style={{
                                      fontSize: "10.5px",
                                      fontWeight: 800,
                                      color: isTodayClosed
                                        ? "#B45309"
                                        : isSelected
                                        ? "#059669"
                                        : "#0284C7",
                                      background: isTodayClosed
                                        ? "#FEF3C7"
                                        : isSelected
                                        ? "#D1FAE5"
                                        : "#E0F2FE",
                                      padding: "3px 8px",
                                      borderRadius: "6px",
                                    }}
                                  >
                                    {isTodayClosed
                                      ? "Unavailable"
                                      : isSelected
                                      ? "✓ Selected"
                                      : "Available"}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {/* 2. Preferred Time Slot (30-Minute Box Chips: 08:00 AM - 07:00 PM) */}
                        <div style={{ marginBottom: "26px" }}>
                          <div style={{ marginBottom: "10px" }}>
                            <label
                              style={{
                                display: "block",
                                fontSize: "14px",
                                fontWeight: 800,
                                color: "#0F172A",
                              }}
                            >
                              2. Preferred Time Slot{" "}
                              <span style={{ color: "#EF4444" }}>*</span>
                            </label>
                            <span style={{ fontSize: "12.5px", color: "#64748B" }}>
                              {preferredDate === todayStr
                                ? "Select an available appointment slot for today."
                                : "Select a 30-minute appointment slot between 08:00 AM and 07:00 PM."}
                            </span>
                          </div>

                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns:
                                "repeat(auto-fill, minmax(110px, 1fr))",
                              gap: "10px",
                            }}
                          >
                            {TIME_SLOTS.map((slot) => {
                              const slotDisabled =
                                preferredDate === todayStr &&
                                parseSlotMinutes(slot) < minTodayMinutes;
                              const isSelected =
                                !slotDisabled && preferredTimeSlot === slot;
                              return (
                                <button
                                  key={slot}
                                  type="button"
                                  aria-disabled={slotDisabled}
                                  onClick={() => {
                                    if (slotDisabled) {
                                      addToast({
                                        title: "Slot Unavailable",
                                        message:
                                          "This time slot is unavailable for today. Please choose an available slot or select tomorrow's date.",
                                        type: "warning",
                                      });
                                      return;
                                    }
                                    setPreferredTimeSlot(slot);
                                  }}
                                  style={{
                                    padding: "10px 8px",
                                    borderRadius: "10px",
                                    fontSize: "12.5px",
                                    fontWeight: isSelected ? 800 : 600,
                                    cursor: slotDisabled
                                      ? "not-allowed"
                                      : "pointer",
                                    opacity: slotDisabled ? 0.45 : 1,
                                    border: isSelected
                                      ? "2px solid #059669"
                                      : "1.5px solid #CBD5E1",
                                    background: slotDisabled
                                      ? "#F1F5F9"
                                      : isSelected
                                      ? "#ECFDF5"
                                      : "#FFFFFF",
                                    color: slotDisabled
                                      ? "#94A3B8"
                                      : isSelected
                                      ? "#065F46"
                                      : "#0F172A",
                                    textAlign: "center",
                                    transition: "all 0.12s ease",
                                    boxShadow: isSelected
                                      ? "0 2px 6px rgba(5, 150, 105, 0.15)"
                                      : "none",
                                  }}
                                >
                                  {slot}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </>
                    );
                  })()}

                  {/* 3. Service Priority Level */}
                  <div style={{ marginBottom: "26px" }}>
                    <div style={{ marginBottom: "10px" }}>
                      <label
                        style={{
                          display: "block",
                          fontSize: "14px",
                          fontWeight: 800,
                          color: "#0F172A",
                        }}
                      >
                        3. Service Priority Level{" "}
                        <span style={{ color: "#EF4444" }}>*</span>
                      </label>
                      <span style={{ fontSize: "12.5px", color: "#64748B" }}>
                        Select the urgency level for this job to help technicians prioritize your request.
                      </span>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                        gap: "10px",
                      }}
                    >
                      {PRIORITY_OPTIONS.map((opt) => {
                        const isSelected = priority === opt.value;
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => setPriority(opt.value)}
                            style={{
                              padding: "12px 10px",
                              borderRadius: "12px",
                              fontSize: "13px",
                              fontWeight: isSelected ? 800 : 600,
                              cursor: "pointer",
                              border: isSelected
                                ? `2.5px solid ${opt.color}`
                                : "1.5px solid #CBD5E1",
                              background: isSelected ? opt.bg : "#FFFFFF",
                              color: isSelected ? opt.color : "#1E293B",
                              textAlign: "left",
                              transition: "all 0.15s ease",
                              boxShadow: isSelected
                                ? `0 4px 12px ${opt.color}25`
                                : "none",
                              display: "flex",
                              flexDirection: "column",
                              gap: "4px",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13.5px" }}>
                              <span>{opt.icon}</span>
                              <span style={{ fontWeight: 800 }}>{opt.label}</span>
                            </div>
                            <span style={{ fontSize: "11px", color: isSelected ? opt.color : "#64748B", fontWeight: 500 }}>
                              {opt.desc}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* 4. Service Location Address (NO COORDINATES IN TEXT FIELD!) */}
                  <div style={{ marginBottom: "26px" }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        marginBottom: "8px",
                        flexWrap: "wrap",
                        gap: "8px",
                      }}
                    >
                      <label
                        style={{
                          fontSize: "14px",
                          fontWeight: 800,
                          color: "#0F172A",
                        }}
                      >
                        3. Service Location Address{" "}
                        <span style={{ color: "#EF4444" }}>*</span>
                      </label>

                      {/* Location Tool Buttons */}
                      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          onClick={() => setIsEditingLocation((prev) => !prev)}
                          style={{
                            background: isEditingLocation ? "#059669" : "#FFFFFF",
                            border: "1.5px solid #059669",
                            color: isEditingLocation ? "#FFFFFF" : "#065F46",
                            fontSize: "12.5px",
                            fontWeight: 700,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "5px",
                            padding: "7px 12px",
                            borderRadius: "8px",
                          }}
                        >
                          <Edit2 size={13} />
                          <span>{isEditingLocation ? "Done Editing" : "Edit"}</span>
                        </button>
                        {/* Use Current Location Button */}
                        <button
                          type="button"
                          onClick={handleUseCurrentLocation}
                          disabled={isLocating}
                          style={{
                            background: "#ECFDF5",
                            border: "1.5px solid #059669",
                            color: "#065F46",
                            fontSize: "12.5px",
                            fontWeight: 700,
                            cursor: isLocating ? "not-allowed" : "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            padding: "7px 14px",
                            borderRadius: "8px",
                          }}
                        >
                          <Navigation size={14} />
                          <span>
                            {isLocating ? "Locating..." : "Use Current Location"}
                          </span>
                        </button>

                        {/* Pick on a Map Button */}
                        <button
                          type="button"
                          onClick={handleOpenMapPicker}
                          style={{
                            background: "#0F172A",
                            border: "none",
                            color: "#FFFFFF",
                            fontSize: "12.5px",
                            fontWeight: 700,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            padding: "7px 14px",
                            borderRadius: "8px",
                            boxShadow: "0 2px 6px rgba(15, 23, 42, 0.2)",
                          }}
                        >
                          <MapIcon size={14} color="#34D399" />
                          <span>Pick on a Map</span>
                        </button>
                      </div>
                    </div>

                    {/* Address Text Field - Populated from Profile, editable via Edit / GPS / Map */}
                    <div style={{ position: "relative" }}>
                      <input
                        type="text"
                        required
                        readOnly={!isEditingLocation}
                        value={locationAddress}
                        onChange={(e) => setLocationAddress(e.target.value)}
                        placeholder="Enter door/building, street address, area and city (e.g. 12, Anna Salai, Chennai)"
                        style={{
                          width: "100%",
                          padding: "12px 14px 12px 38px",
                          borderRadius: "10px",
                          border: isEditingLocation ? "1.5px solid #059669" : "1.5px solid #CBD5E1",
                          background: isEditingLocation ? "#FFFFFF" : "#F8FAFC",
                          fontSize: "13.5px",
                          color: "#0F172A",
                          outline: "none",
                          boxSizing: "border-box",
                          cursor: isEditingLocation ? "text" : "default",
                        }}
                      />
                      <MapPin
                        size={17}
                        color="#059669"
                        style={{
                          position: "absolute",
                          left: "12px",
                          top: "50%",
                          transform: "translateY(-50%)",
                        }}
                      />
                    </div>

                    {siteCoords.lat && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "5px",
                          fontSize: "12px",
                          color: "#059669",
                          fontWeight: 700,
                          marginTop: "6px",
                        }}
                      >
                        <CheckCircle2 size={14} />
                        <span>
                          Live GPS position tagged internally for nearest technician matching
                        </span>
                      </div>
                    )}
                  </div>

                  {/* 4. Contact Phone Number (From Profile, Editable via Edit button, strictly 10 digits) */}
                  <div style={{ marginBottom: "26px" }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        maxWidth: "420px",
                        marginBottom: "8px",
                        gap: "8px",
                      }}
                    >
                      <label
                        style={{
                          display: "block",
                          fontSize: "14px",
                          fontWeight: 800,
                          color: "#0F172A",
                        }}
                      >
                        4. Contact Phone Number (10 digits){" "}
                        <span style={{ color: "#EF4444" }}>*</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setIsEditingPhone((prev) => !prev)}
                        style={{
                          background: isEditingPhone ? "#059669" : "#FFFFFF",
                          border: "1.5px solid #059669",
                          color: isEditingPhone ? "#FFFFFF" : "#065F46",
                          fontSize: "12px",
                          fontWeight: 700,
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "5px",
                          padding: "5px 11px",
                          borderRadius: "8px",
                        }}
                      >
                        <Edit2 size={12} />
                        <span>{isEditingPhone ? "Done" : "Edit"}</span>
                      </button>
                    </div>
                    <div style={{ position: "relative", maxWidth: "420px" }}>
                      <input
                        type="tel"
                        required
                        readOnly={!isEditingPhone}
                        value={contactNumber}
                        onChange={(e) =>
                          setContactNumber(
                            e.target.value.replace(/\D/g, "").slice(0, 10),
                          )
                        }
                        placeholder="10-digit mobile number"
                        maxLength={10}
                        inputMode="numeric"
                        style={{
                          width: "100%",
                          padding: "12px 14px 12px 38px",
                          borderRadius: "10px",
                          border: isEditingPhone ? "1.5px solid #059669" : "1.5px solid #CBD5E1",
                          background: isEditingPhone ? "#FFFFFF" : "#F8FAFC",
                          fontSize: "13.5px",
                          color: "#0F172A",
                          outline: "none",
                          boxSizing: "border-box",
                          cursor: isEditingPhone ? "text" : "default",
                        }}
                      />
                      <Phone
                        size={17}
                        color="#64748B"
                        style={{
                          position: "absolute",
                          left: "12px",
                          top: "50%",
                          transform: "translateY(-50%)",
                        }}
                      />
                    </div>
                  </div>

                  {/* 5. Additional Notes (Optional) */}
                  <div style={{ marginBottom: "28px" }}>
                    <label
                      style={{
                        display: "block",
                        fontSize: "14px",
                        fontWeight: 800,
                        color: "#0F172A",
                        marginBottom: "8px",
                      }}
                    >
                      6. Additional Notes or Specific Instructions (Optional)
                    </label>
                    <textarea
                      rows={2}
                      value={additionalNotes}
                      onChange={(e) => setAdditionalNotes(e.target.value)}
                      placeholder="Any specific symptoms, gate/parking instructions, or landmark..."
                      style={{
                        width: "100%",
                        padding: "12px 14px",
                        borderRadius: "10px",
                        border: "1.5px solid #CBD5E1",
                        fontSize: "13px",
                        color: "#0F172A",
                        outline: "none",
                        boxSizing: "border-box",
                        fontFamily: "inherit",
                        resize: "vertical",
                      }}
                    />
                  </div>

                  {/* Form Submission Buttons */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      borderTop: "1px solid #E2E8F0",
                      paddingTop: "22px",
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => window.history.back()}
                      disabled={submitting}
                      style={{
                        padding: "12px 22px",
                        borderRadius: "10px",
                        border: "1.5px solid #CBD5E1",
                        background: "#FFFFFF",
                        color: "#334155",
                        fontSize: "14px",
                        fontWeight: 700,
                        cursor: submitting ? "not-allowed" : "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                      }}
                    >
                      <ArrowLeft size={16} />
                      <span>Back to Issues</span>
                    </button>

                    <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        disabled={submitting}
                        onClick={() => {
                          setPreferredDate("");
                          setPreferredTimeSlot("");
                          setAdditionalNotes("");
                          addToast({
                            title: "Cleared",
                            message: "Selected appointment date and time have been cleared.",
                            type: "info",
                          });
                        }}
                        style={{
                          padding: "12px 20px",
                          borderRadius: "10px",
                          border: "1.5px solid #CBD5E1",
                          background: "#FFFFFF",
                          color: "#334155",
                          fontSize: "14px",
                          fontWeight: 700,
                          cursor: submitting ? "not-allowed" : "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                        }}
                      >
                        <RotateCcw size={15} />
                        <span>Clear</span>
                      </button>

                      <button
                        type="submit"
                        disabled={submitting}
                        style={{
                          padding: "12px 32px",
                          borderRadius: "10px",
                          border: "none",
                          background: submitting ? "#94A3B8" : "#059669",
                          color: "#FFFFFF",
                          fontSize: "14.5px",
                          fontWeight: 800,
                          cursor: submitting ? "not-allowed" : "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          boxShadow: "0 3px 8px rgba(5, 150, 105, 0.3)",
                        }}
                      >
                        <Send size={16} />
                        <span>
                          {submitting
                            ? "Submitting..."
                            : "Submit Service Request ➔"}
                        </span>
                      </button>
                    </div>
                  </div>
                </form>
            </div>
          )}
      </div>

      {/* Cute Below-Medium Submission Success Confirmation Modal */}
      {submissionSuccess && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.65)",
            backdropFilter: "blur(5px)",
            WebkitBackdropFilter: "blur(5px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "16px",
          }}
          onClick={() => {
            setSubmissionSuccess(null);
            changeViewLevel("SERVICES");
          }}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "20px",
              boxShadow: "0 20px 45px rgba(0,0,0,0.22)",
              width: "100%",
              maxWidth: "420px",
              padding: "24px 22px 20px",
              position: "relative",
              textAlign: "center",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Top-Right Close Button */}
            <button
              type="button"
              onClick={() => {
                setSubmissionSuccess(null);
                changeViewLevel("SERVICES");
              }}
              aria-label="Close"
              style={{
                position: "absolute",
                top: "14px",
                right: "14px",
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                background: "#F1F5F9",
                border: "none",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                color: "#64748B",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "#E2E8F0";
                e.currentTarget.style.color = "#0F172A";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "#F1F5F9";
                e.currentTarget.style.color = "#64748B";
              }}
            >
              <X size={18} />
            </button>

            {/* Cute Green Badge */}
            <div
              style={{
                width: "56px",
                height: "56px",
                borderRadius: "50%",
                background: "#ECFDF5",
                border: "2px solid #A7F3D0",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 12px auto",
              }}
            >
              <CheckCircle2 size={32} color="#059669" />
            </div>

            <h3
              style={{
                fontSize: "19px",
                fontWeight: 800,
                color: "#0F172A",
                margin: "0 0 6px 0",
              }}
            >
              Service Request Submitted!
            </h3>

            <p
              style={{
                fontSize: "12.5px",
                color: "#64748B",
                margin: "0 auto 16px auto",
                lineHeight: 1.45,
              }}
            >
              Your request <strong style={{ color: "#059669" }}>#{submissionSuccess.id}</strong> has been logged. Our AI Planning Agent is actively dispatching nearby technicians based on live GPS location.
            </p>

            {/* Compact Summary */}
            <div
              style={{
                background: "#F8FAFC",
                border: "1px solid #E2E8F0",
                borderRadius: "12px",
                padding: "12px 14px",
                marginBottom: "18px",
                textAlign: "left",
                fontSize: "12.5px",
                lineHeight: "1.5",
              }}
            >
              <div style={{ fontWeight: 700, color: "#0F172A", marginBottom: "4px" }}>
                {selectedCategory?.name} <span style={{ color: "#059669" }}>➔</span> {selectedIssue}
              </div>
              <div style={{ color: "#475569" }}>
                📅 <strong>Date:</strong> {preferredDate || "Not set"} ({preferredTimeSlot || "Not set"})
              </div>
              <div style={{ color: "#475569" }}>
                ⚡ <strong>Priority:</strong> <span style={{ fontWeight: 700, color: priority === 'URGENT' ? '#DC2626' : priority === 'HIGH' ? '#D97706' : '#2563EB' }}>{priority}</span>
              </div>
              <div
                style={{
                  color: "#475569",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={locationAddress}
              >
                📍 <strong>Address:</strong> {locationAddress}
              </div>
              <div style={{ color: "#475569" }}>
                📞 <strong>Phone:</strong> {contactNumber}
              </div>
            </div>

            {/* Modal Actions */}
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <button
                type="button"
                onClick={() => {
                  setSubmissionSuccess(null);
                  if (onNavigate) onNavigate("cust_requests");
                }}
                style={{
                  width: "100%",
                  padding: "11px 18px",
                  borderRadius: "10px",
                  background: "#059669",
                  color: "#FFFFFF",
                  border: "none",
                  fontSize: "13.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "6px",
                  boxShadow: "0 2px 8px rgba(5, 150, 105, 0.25)",
                }}
              >
                <span>View in My Requests</span>
                <ArrowRight size={15} />
              </button>

              <button
                type="button"
                onClick={() => {
                  setSubmissionSuccess(null);
                  changeViewLevel("SERVICES");
                }}
                style={{
                  width: "100%",
                  padding: "9px 18px",
                  borderRadius: "10px",
                  background: "#FFFFFF",
                  color: "#475569",
                  border: "1px solid #CBD5E1",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Book Another Service
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Service Currently Unavailable Alert Modal */}
      {unavailableModalIssue && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.65)",
            backdropFilter: "blur(4px)",
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
          }}
          onClick={() => setUnavailableModalIssue(null)}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "20px",
              padding: "32px 28px",
              maxWidth: "460px",
              width: "100%",
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.25)",
              textAlign: "center",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                width: "60px",
                height: "60px",
                borderRadius: "50%",
                background: "#FEF3C7",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 16px auto",
              }}
            >
              <ShieldAlert size={32} color="#D97706" />
            </div>

            <h3
              style={{
                fontSize: "20px",
                fontWeight: 800,
                color: "#0F172A",
                margin: "0 0 10px 0",
              }}
            >
              Service Currently Unavailable
            </h3>

            <p
              style={{
                fontSize: "14px",
                color: "#475569",
                lineHeight: 1.5,
                margin: "0 0 24px 0",
              }}
            >
              <strong>"{unavailableModalIssue}"</strong> cannot be booked at this time.
              No registered service organization in your area currently provides this specific job.
              Please choose an active service from the available services.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <button
                type="button"
                onClick={() => {
                  setUnavailableModalIssue(null);
                }}
                style={{
                  background: "#059669",
                  color: "#FFFFFF",
                  border: "none",
                  borderRadius: "10px",
                  padding: "12px",
                  fontSize: "13.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                Return to Available Services
              </button>
              <button
                type="button"
                onClick={() => setUnavailableModalIssue(null)}
                style={{
                  background: "#F1F5F9",
                  color: "#0F172A",
                  border: "none",
                  borderRadius: "10px",
                  padding: "12px",
                  fontSize: "13.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          Modal 1: No Services Found (When Category count === 0)
      ───────────────────────────────────────────────────────────── */}
      {noServicesModalName && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.55)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "16px",
          }}
          onClick={() => setNoServicesModalName(null)}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "18px",
              width: "100%",
              maxWidth: "440px",
              padding: "28px",
              boxShadow: "0 25px 50px rgba(0, 0, 0, 0.2)",
              textAlign: "center",
              position: "relative",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setNoServicesModalName(null)}
              style={{
                position: "absolute",
                top: "16px",
                right: "16px",
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "#64748B",
                padding: "4px",
                borderRadius: "6px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <X size={20} />
            </button>

            <div
              style={{
                width: "60px",
                height: "60px",
                borderRadius: "50%",
                background: "#F1F5F9",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 16px auto",
              }}
            >
              <PackageSearch size={30} color="#475569" />
            </div>

            <h3
              style={{
                fontSize: "19px",
                fontWeight: 800,
                color: "#0F172A",
                margin: "0 0 8px 0",
              }}
            >
              No services found at this time
            </h3>

            <p
              style={{
                fontSize: "13.5px",
                color: "#475569",
                lineHeight: 1.5,
                margin: "0 0 22px 0",
              }}
            >
              We are actively cataloging verified technicians and service
              packages for{" "}
              <strong style={{ color: "#0F172A" }}>
                {noServicesModalName}
              </strong>
              .
              <br />
              Please check back shortly or reach out through our Support page.
            </p>

            <button
              type="button"
              onClick={() => setNoServicesModalName(null)}
              style={{
                width: "100%",
                padding: "12px 18px",
                borderRadius: "10px",
                background: "#059669",
                color: "#FFFFFF",
                border: "none",
                fontSize: "14px",
                fontWeight: 700,
                cursor: "pointer",
                transition: "background 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "#047857";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "#059669";
              }}
            >
              Got it
            </button>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          Modal 2: Pick on a Map Modal (Google Maps with marker)
      ───────────────────────────────────────────────────────────── */}
      {showMapModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 10000,
            padding: "16px",
          }}
          onClick={() => setShowMapModal(false)}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "18px",
              width: "100%",
              maxWidth: "620px",
              padding: "22px 26px",
              boxShadow: "0 25px 50px rgba(0, 0, 0, 0.25)",
              position: "relative",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <MapPin size={20} color="#059669" />
                <h3
                  style={{
                    fontSize: "17px",
                    fontWeight: 800,
                    color: "#0F172A",
                    margin: 0,
                  }}
                >
                  Pick Service Location on Map
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowMapModal(false)}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#64748B",
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* LocationPickerMap component */}
            <LocationPickerMap
              latitude={tempMarkerCoords.lat}
              longitude={tempMarkerCoords.lng}
              isSelectionAllowed={isWithinChennaiServiceArea}
              onSelectionRejected={() => addToast({ title: "Outside Service Area", message: CHENNAI_SERVICE_ERROR, type: "error" })}
              onChange={(lat, lng, address) => {
                setTempMarkerCoords({ lat, lng });
                if (address) {
                  setTempResolvedAddress(address);
                } else {
                  reverseLocation(lat, lng)
                    .then((res) => {
                      if (
                        res.data?.verified &&
                        (res.data.address || res.data.formatted_address)
                      ) {
                        setTempResolvedAddress(
                          res.data.address || res.data.formatted_address || ""
                        );
                      }
                    })
                    .catch(() => {});
                }
              }}
            />

            {/* Resolved Address Display (Strictly Text ONLY) */}
            {tempResolvedAddress && (
              <div
                style={{
                  marginTop: "14px",
                  padding: "12px 14px",
                  background: "#F8FAFC",
                  border: "1.5px solid #CBD5E1",
                  borderRadius: "10px",
                  fontSize: "13px",
                  color: "#0F172A",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <MapPin size={16} color="#059669" style={{ flexShrink: 0 }} />
                <span style={{ fontWeight: 700 }}>{tempResolvedAddress}</span>
              </div>
            )}

            {/* Modal Actions */}
            <div
              style={{
                marginTop: "20px",
                display: "flex",
                justifyContent: "flex-end",
                gap: "10px",
              }}
            >
              <button
                type="button"
                onClick={() => setShowMapModal(false)}
                style={{
                  padding: "10px 20px",
                  borderRadius: "8px",
                  border: "1.5px solid #CBD5E1",
                  background: "#FFFFFF",
                  color: "#475569",
                  fontSize: "13.5px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleConfirmMapLocation}
                style={{
                  padding: "10px 24px",
                  borderRadius: "8px",
                  border: "none",
                  background: "#059669",
                  color: "#FFFFFF",
                  fontSize: "13.5px",
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  boxShadow: "0 2px 6px rgba(5, 150, 105, 0.25)",
                }}
              >
                <CheckCircle2 size={16} />
                <span>Confirm Location</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
