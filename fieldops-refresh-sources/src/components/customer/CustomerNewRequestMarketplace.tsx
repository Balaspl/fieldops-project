import React, { useState, useEffect, useMemo } from "react";
import {
  Search,
  LayoutGrid,
  ChevronRight,
  PackageSearch,
  X,
  MapPin,
  Calendar,
  Clock,
  Phone,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Wrench,
  Send,
  ArrowLeft,
  Sparkles,
} from "lucide-react";
import {
  getCustomerCatalog,
  type ServiceCatalogItem,
} from "../../services/servicesCatalogService";
import {
  createServiceRequest,
  getCustomerProfile,
} from "../../services/customerPortalService";
import { useToast } from "../../hooks/useToast";

interface CustomerNewRequestMarketplaceProps {
  onNavigate?: (tab: string) => void;
}

interface ServiceCategory {
  id: string;
  name: string;
  serviceType: string;
  description: string;
  image: string;
  theme: {
    bg: string;
    color: string;
  };
}

const SERVICE_CATEGORIES: ServiceCategory[] = [
  {
    id: "appliances",
    name: "Home Appliances",
    serviceType: "Home Appliances",
    description: "AC, Refrigerator, Washing Machine...",
    image: "/services/appliances.png",
    theme: {
      bg: "#EFF6FF",
      color: "#2563EB",
    },
  },
  {
    id: "electrical",
    name: "Electrical",
    serviceType: "Electrical",
    description: "Wiring, Fan, Switchboard, MCB, Inverter...",
    image: "/services/electrical.png",
    theme: {
      bg: "#FEF3C7",
      color: "#D97706",
    },
  },
  {
    id: "plumbing",
    name: "Plumbing",
    serviceType: "Plumbing",
    description: "Leakage, Taps, Drainage, Water Pump...",
    image: "/services/plumbing.png",
    theme: {
      bg: "#E0F2FE",
      color: "#0284C7",
    },
  },
  {
    id: "security",
    name: "Security & Smart Home",
    serviceType: "Security & Smart Home",
    description: "CCTV, WiFi, Smart Lock, Video Doorbell...",
    image: "/services/security.png",
    theme: {
      bg: "#DCFCE7",
      color: "#16A34A",
    },
  },
  {
    id: "carpentry",
    name: "Carpentry & Woodwork",
    serviceType: "Carpentry & Woodwork",
    description: "Door Locks, Furniture, Modular Kitchen...",
    image: "/services/carpentry.png",
    theme: {
      bg: "#FFEDD5",
      color: "#EA580C",
    },
  },
  {
    id: "cleaning",
    name: "Cleaning & Maintenance",
    serviceType: "Cleaning & Maintenance",
    description: "House Painting, Pest Control, Waterproofing...",
    image: "/services/cleaning.png",
    theme: {
      bg: "#F3E8FF",
      color: "#9333EA",
    },
  },
];

// Match item service_type to one of the 6 category cards
const matchServiceTypeToCategory = (
  itemServiceType: string,
  catId: string,
  catName?: string
) => {
  const st = (itemServiceType || "").trim().toLowerCase();
  const cid = (catId || "").trim().toLowerCase();
  const cname = (catName || "").trim().toLowerCase();

  if (cid === "electrical" || cname.includes("electr") || cid.includes("electr"))
    return st.includes("electr");
  if (cid === "plumbing" || cname.includes("plumb") || cid.includes("plumb"))
    return st.includes("plumb");
  if (
    cid === "appliances" ||
    cname.includes("appliance") ||
    cid.includes("appliance")
  )
    return st.includes("appliance") || st.includes("hvac") || st.includes("ac");
  if (
    cid === "security" ||
    cname.includes("security") ||
    cid.includes("security")
  )
    return (
      st.includes("security") || st.includes("smart") || st.includes("cctv")
    );
  if (
    cid === "carpentry" ||
    cname.includes("carpent") ||
    cid.includes("carpent")
  )
    return st.includes("carpent") || st.includes("wood");
  if (cid === "cleaning" || cname.includes("clean") || cid.includes("clean"))
    return (
      st.includes("clean") || st.includes("paint") || st.includes("maintenance")
    );
  return st === cid || st === cname || st.includes(cid) || cid.includes(st);
};

export default function CustomerNewRequestMarketplace({
  onNavigate,
}: CustomerNewRequestMarketplaceProps) {
  const { addToast } = useToast();

  // Search input in hero banner
  const [searchQuery, setSearchQuery] = useState("");

  // Live active catalog items from database
  const [catalogItems, setCatalogItems] = useState<ServiceCatalogItem[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(true);

  // Profile data for pre-populating location and phone number
  const [profileData, setProfileData] = useState<any>(null);

  // "No Services Found" modal for 0-count categories or failed search
  const [noServicesModalName, setNoServicesModalName] = useState<string | null>(null);

  // Active Category being booked (when count > 0)
  const [activeBookingCat, setActiveBookingCat] = useState<ServiceCategory | null>(null);

  // Booking Flow Steps:
  // Step 1: SELECT_ISSUE (select Category ➔ select Issue)
  // Step 2: BOOKING_FORM (only after issue selected ➔ preferred date, time, location, phone)
  const [bookingStep, setBookingStep] = useState<"SELECT_ISSUE" | "BOOKING_FORM">("SELECT_ISSUE");

  // Selected Category and Issue
  const [selectedCategoryName, setSelectedCategoryName] = useState<string>("");
  const [selectedIssueName, setSelectedIssueName] = useState<string>("");

  // Form Fields (editable by customer, prefilled from profile)
  const [preferredDate, setPreferredDate] = useState<string>(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split("T")[0];
  });
  const [preferredTimeSlot, setPreferredTimeSlot] = useState<string>("Morning (09:00 AM - 12:00 PM)");
  const [contactNumber, setContactNumber] = useState<string>("");
  const [locationAddress, setLocationAddress] = useState<string>("");
  const [siteCoords, setSiteCoords] = useState<{ lat?: number; lng?: number }>({});
  const [isLocating, setIsLocating] = useState<boolean>(false);
  const [additionalNotes, setAdditionalNotes] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submissionSuccess, setSubmissionSuccess] = useState<{ id: number } | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

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

  // Load catalog and customer profile on mount
  useEffect(() => {
    fetchActiveCatalog();

    getCustomerProfile()
      .then((res) => {
        if (res?.data) {
          const prof = res.data;
          setProfileData(prof);
          if (prof.mobile_number) setContactNumber(prof.mobile_number);
          const fullAddr = [prof.address, prof.city, prof.state, prof.pincode]
            .filter(Boolean)
            .join(", ") || prof.address || prof.city || "";
          if (fullAddr) setLocationAddress(fullAddr);
        }
      })
      .catch(() => {});

    // Live auto-refresh when tab gains focus or on interval so super admin publishes reflect instantly
    const onFocus = () => fetchActiveCatalog();
    window.addEventListener("focus", onFocus);
    const interval = setInterval(fetchActiveCatalog, 5000);

    return () => {
      window.removeEventListener("focus", onFocus);
      clearInterval(interval);
    };
  }, []);

  // Compute live issue counts per category card
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const cat of SERVICE_CATEGORIES) {
      const matchingItems = catalogItems.filter(
        (it) => it.is_active && matchServiceTypeToCategory(it.service_type, cat.id, cat.name)
      );
      counts[cat.id] = matchingItems.length;
    }
    return counts;
  }, [catalogItems]);

  // Handle clicking a service card
  const handleCategoryCardClick = (cat: ServiceCategory) => {
    const count = categoryCounts[cat.id] || 0;
    if (count === 0) {
      // 0 services ➔ Show "No services found at this time" modal
      setNoServicesModalName(cat.name);
    } else {
      // >0 services ➔ Open Step 1 (Select Category & Issue)
      setActiveBookingCat(cat);
      setBookingStep("SELECT_ISSUE");
      setSelectedCategoryName("");
      setSelectedIssueName("");
      setSubmissionSuccess(null);
      setSubmitError(null);

      // Pre-fill profile contact and location if not yet populated
      if (profileData) {
        if (!contactNumber && profileData.mobile_number) {
          setContactNumber(profileData.mobile_number);
        }
        if (!locationAddress) {
          const fullAddr = [profileData.address, profileData.city, profileData.state, profileData.pincode]
            .filter(Boolean)
            .join(", ") || profileData.address || profileData.city || "";
          if (fullAddr) setLocationAddress(fullAddr);
        }
      }
    }
  };

  // Categories created by organization under the active service type
  const availableCategories = useMemo(() => {
    if (!activeBookingCat) return [];
    const itemsForCat = catalogItems.filter(
      (it) =>
        it.is_active &&
        matchServiceTypeToCategory(it.service_type, activeBookingCat.id, activeBookingCat.name)
    );
    return Array.from(new Set(itemsForCat.map((it) => it.category)));
  }, [activeBookingCat, catalogItems]);

  // Issues created under the chosen category
  const availableIssues = useMemo(() => {
    if (!activeBookingCat || !selectedCategoryName) return [];
    return catalogItems.filter(
      (it) =>
        it.is_active &&
        matchServiceTypeToCategory(it.service_type, activeBookingCat.id, activeBookingCat.name) &&
        it.category.toLowerCase() === selectedCategoryName.toLowerCase()
    );
  }, [activeBookingCat, selectedCategoryName, catalogItems]);

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
      const targetCat = SERVICE_CATEGORIES.find((cat) =>
        matchServiceTypeToCategory(matchingItem.service_type, cat.id, cat.name)
      );
      if (targetCat) {
        setActiveBookingCat(targetCat);
        setSelectedCategoryName(matchingItem.category);
        setSelectedIssueName(matchingItem.issue);
        setBookingStep("BOOKING_FORM");
        setSubmissionSuccess(null);
        setSubmitError(null);
        return;
      }
    }

    // No matching services found
    setNoServicesModalName(searchQuery.trim());
  };

  // GPS Current Location helper
  const handleGetLocation = () => {
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
      (pos) => {
        setIsLocating(false);
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        setSiteCoords({ lat, lng });
        if (!locationAddress.trim()) {
          setLocationAddress(`GPS Coordinates: ${lat.toFixed(4)}, ${lng.toFixed(4)}`);
        }
        addToast({
          title: "Location Acquired",
          message: "GPS coordinates tagged successfully.",
          type: "success",
        });
      },
      (err) => {
        setIsLocating(false);
        addToast({
          title: "Location Access Denied",
          message: "Could not retrieve GPS coordinates. You can type your address manually.",
          type: "info",
        });
      },
      { timeout: 8000 }
    );
  };

  // Submit booking form
  const handleBookingSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeBookingCat) return;

    if (!selectedCategoryName) {
      setSubmitError("Please select a service category");
      return;
    }
    if (!selectedIssueName) {
      setSubmitError("Please select a diagnostic issue");
      return;
    }
    if (!locationAddress.trim()) {
      setSubmitError("Please provide your service location address");
      return;
    }
    if (!contactNumber.trim()) {
      setSubmitError("Please provide a contact phone number");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const serviceType = activeBookingCat.serviceType;
    const constructedDescription = `${selectedIssueName} - ${selectedCategoryName} (${serviceType} Service). ${additionalNotes.trim()}`.trim();

    const payload = {
      service_type: serviceType,
      title: selectedCategoryName,
      category: selectedCategoryName,
      issue: selectedIssueName,
      description: constructedDescription,
      priority: "MEDIUM",
      preferred_visit_date: preferredDate || undefined,
      contact_number: contactNumber.trim(),
      location: locationAddress.trim(),
      site_latitude: siteCoords.lat,
      site_longitude: siteCoords.lng,
    };

    try {
      const res = await createServiceRequest(payload);
      const createdId = res.data?.id || res.data?.created_job?.id || 101;
      setSubmissionSuccess({ id: createdId });
      addToast({
        title: "Request Submitted Successfully",
        message: `Service request #${createdId} created. AI Planning Agent is matching eligible technicians.`,
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
      setSubmitError(errorMsg);
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
        background: "#F8FAFC",
        boxSizing: "border-box",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <div style={{ maxWidth: "1140px", margin: "0 auto" }}>
        {/* User-Provided Hero Banner with Crisp Text and Search Bar */}
        <div
          style={{
            position: "relative",
            width: "100%",
            borderRadius: "16px",
            overflow: "hidden",
            boxShadow: "0 2px 10px rgba(0, 0, 0, 0.04)",
            marginBottom: "20px",
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
          {/* 1. Title (Line 1 text) */}
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

          {/* 2. Subtitle (Line 2 text) */}
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

        {/* Browse Service Categories Section */}
        <div
          style={{
            background: "#FFFFFF",
            borderRadius: "16px",
            border: "1px solid #E2E8F0",
            padding: "20px 20px 24px 20px",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.03)",
          }}
        >
          {/* Header Row */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "18px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div
                style={{
                  width: "28px",
                  height: "28px",
                  borderRadius: "8px",
                  background: "#ECFDF5",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <LayoutGrid size={17} color="#059669" />
              </div>
              <h2
                style={{
                  fontSize: "17px",
                  fontWeight: 800,
                  color: "#0F172A",
                  margin: 0,
                }}
              >
                Browse Service Categories
              </h2>
            </div>

            <button
              type="button"
              onClick={() => setNoServicesModalName("All Categories")}
              style={{
                background: "none",
                border: "none",
                color: "#059669",
                fontSize: "13px",
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.textDecoration = "underline";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.textDecoration = "none";
              }}
            >
              <span>View All</span>
              <ChevronRight size={14} />
            </button>
          </div>

          {/* Cards Grid - 6 columns */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
              gap: "14px",
            }}
          >
            {SERVICE_CATEGORIES.map((cat) => {
              const liveCount = categoryCounts[cat.id] || 0;

              return (
                <div
                  key={cat.id}
                  onClick={() => handleCategoryCardClick(cat)}
                  style={{
                    background: "#FFFFFF",
                    border: "1px solid #E2E8F0",
                    borderRadius: "14px",
                    padding: "12px 10px 14px 10px",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    cursor: "pointer",
                    transition: "all 0.2s ease",
                    boxShadow: "0 1px 3px rgba(0, 0, 0, 0.02)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = "translateY(-3px)";
                    e.currentTarget.style.boxShadow =
                      "0 8px 20px rgba(0, 0, 0, 0.06)";
                    e.currentTarget.style.borderColor = "#CBD5E1";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = "translateY(0)";
                    e.currentTarget.style.boxShadow =
                      "0 1px 3px rgba(0, 0, 0, 0.02)";
                    e.currentTarget.style.borderColor = "#E2E8F0";
                  }}
                >
                  {/* Image */}
                  <div
                    style={{
                      height: "75px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      marginBottom: "10px",
                      background: "#F8FAFC",
                      borderRadius: "10px",
                      padding: "4px",
                      overflow: "hidden",
                    }}
                  >
                    <img
                      src={cat.image}
                      alt={cat.name}
                      style={{
                        maxHeight: "100%",
                        maxWidth: "100%",
                        objectFit: "contain",
                      }}
                    />
                  </div>

                  {/* Details */}
                  <div style={{ flex: 1, marginBottom: "12px" }}>
                    <h3
                      style={{
                        fontSize: "14px",
                        fontWeight: 800,
                        color: "#0F172A",
                        margin: "0 0 4px 0",
                        lineHeight: 1.25,
                      }}
                    >
                      {cat.name}
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
                      {cat.description}
                    </p>
                  </div>

                  {/* Live Services Count Pill */}
                  <div>
                    <span
                      style={{
                        background: liveCount > 0 ? "#ECFDF5" : cat.theme.bg,
                        color: liveCount > 0 ? "#059669" : cat.theme.color,
                        fontSize: "11.5px",
                        fontWeight: 700,
                        padding: "4px 10px",
                        borderRadius: "999px",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                      }}
                    >
                      <span>
                        {liveCount} {liveCount === 1 ? "Service" : "Services"}
                      </span>
                      <ChevronRight size={13} />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          Modal 1: No Services Found (When Count === 0)
      ───────────────────────────────────────────────────────────── */}
      {noServicesModalName && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.45)",
            backdropFilter: "blur(3px)",
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
              borderRadius: "16px",
              width: "100%",
              maxWidth: "420px",
              padding: "26px",
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.15)",
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
                top: "14px",
                right: "14px",
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
              <X size={18} />
            </button>

            <div
              style={{
                width: "56px",
                height: "56px",
                borderRadius: "50%",
                background: "#F1F5F9",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 16px auto",
              }}
            >
              <PackageSearch size={28} color="#64748B" />
            </div>

            <h3
              style={{
                fontSize: "18px",
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
                color: "#64748B",
                lineHeight: 1.5,
                margin: "0 0 20px 0",
              }}
            >
              We are actively cataloging verified technicians and service
              packages for{" "}
              <strong style={{ color: "#0F172A" }}>{noServicesModalName}</strong>.
              <br />
              Please check back shortly or reach out through our Support page.
            </p>

            <button
              type="button"
              onClick={() => setNoServicesModalName(null)}
              style={{
                width: "100%",
                padding: "10px 18px",
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
          Modal 2: Two-Step Booking Flow (When Count > 0)
          Step 1: Select Category & Issue
          Step 2 (ONLY after issue selected): Booking Form (Date, Time, Location, Phone)
      ───────────────────────────────────────────────────────────── */}
      {activeBookingCat && (
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
          onClick={() => setActiveBookingCat(null)}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "18px",
              width: "100%",
              maxWidth: "640px",
              maxHeight: "90vh",
              overflowY: "auto",
              boxShadow: "0 25px 50px rgba(0, 0, 0, 0.2)",
              position: "relative",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "18px 24px",
                borderBottom: "1px solid #E2E8F0",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: "#F8FAFC",
                borderTopLeftRadius: "18px",
                borderTopRightRadius: "18px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "10px",
                    background: activeBookingCat.theme.bg,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Wrench size={18} color={activeBookingCat.theme.color} />
                </div>
                <div>
                  <h3
                    style={{
                      fontSize: "16.5px",
                      fontWeight: 800,
                      color: "#0F172A",
                      margin: 0,
                    }}
                  >
                    {activeBookingCat.name}
                  </h3>
                  <span style={{ fontSize: "12px", color: "#64748B" }}>
                    {bookingStep === "SELECT_ISSUE"
                      ? "Step 1 of 2: Select service category and diagnostic issue"
                      : "Step 2 of 2: Confirm appointment date, time, and address"}
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setActiveBookingCat(null)}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#64748B",
                  padding: "6px",
                  borderRadius: "8px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Submission Success Confirmation View */}
            {submissionSuccess ? (
              <div style={{ padding: "36px 28px", textAlign: "center" }}>
                <div
                  style={{
                    width: "60px",
                    height: "60px",
                    borderRadius: "50%",
                    background: "#ECFDF5",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 16px auto",
                  }}
                >
                  <CheckCircle2 size={32} color="#059669" />
                </div>

                <h3
                  style={{
                    fontSize: "20px",
                    fontWeight: 800,
                    color: "#0F172A",
                    margin: "0 0 8px 0",
                  }}
                >
                  Service Request Submitted!
                </h3>

                <p
                  style={{
                    fontSize: "13.5px",
                    color: "#475569",
                    margin: "0 0 16px 0",
                    lineHeight: 1.5,
                  }}
                >
                  Your request <strong>#{submissionSuccess.id}</strong> has been
                  created.
                  <br />
                  Our AI Planning Agent is actively ranking eligible technicians
                  for dispatch.
                </p>

                <div
                  style={{
                    background: "#F8FAFC",
                    border: "1px solid #E2E8F0",
                    borderRadius: "12px",
                    padding: "14px 16px",
                    marginBottom: "24px",
                    textAlign: "left",
                  }}
                >
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#64748B",
                      marginBottom: "4px",
                    }}
                  >
                    Service Category & Issue:
                  </div>
                  <div
                    style={{
                      fontSize: "14px",
                      fontWeight: 700,
                      color: "#0F172A",
                    }}
                  >
                    {selectedCategoryName} ➔ {selectedIssueName}
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#475569",
                      marginTop: "4px",
                    }}
                  >
                    Scheduled: <strong>{preferredDate}</strong> ({preferredTimeSlot})
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#475569",
                      marginTop: "2px",
                    }}
                  >
                    Location: <strong>{locationAddress}</strong>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveBookingCat(null);
                      if (onNavigate) onNavigate("cust_requests");
                    }}
                    style={{
                      flex: 1,
                      padding: "12px 18px",
                      borderRadius: "10px",
                      background: "#059669",
                      color: "#FFFFFF",
                      border: "none",
                      fontSize: "14px",
                      fontWeight: 700,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "6px",
                    }}
                  >
                    <span>View in My Requests</span>
                    <ArrowRight size={16} />
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveBookingCat(null)}
                    style={{
                      padding: "12px 20px",
                      borderRadius: "10px",
                      background: "#F1F5F9",
                      color: "#334155",
                      border: "1px solid #CBD5E1",
                      fontSize: "14px",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : bookingStep === "SELECT_ISSUE" ? (
              /* ─────────────────────────────────────────────────────────────
                  STEP 1: SELECT CATEGORY & ISSUE
                  User picks Category (e.g. Lighting) ➔ picks Issue (e.g. Bulb test)
              ───────────────────────────────────────────────────────────── */
              <div style={{ padding: "20px 24px" }}>
                {/* 1. Category Selection */}
                <div style={{ marginBottom: "18px" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "13px",
                      fontWeight: 700,
                      color: "#0F172A",
                      marginBottom: "8px",
                    }}
                  >
                    1. Select Category <span style={{ color: "#EF4444" }}>*</span>
                  </label>

                  {availableCategories.length === 0 ? (
                    <div
                      style={{
                        padding: "16px",
                        background: "#F8FAFC",
                        borderRadius: "8px",
                        fontSize: "12.5px",
                        color: "#64748B",
                        textAlign: "center",
                      }}
                    >
                      No categories configured under this service trade.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                      {availableCategories.map((catName) => {
                        const isSelected = selectedCategoryName === catName;
                        return (
                          <button
                            key={catName}
                            type="button"
                            onClick={() => {
                              setSelectedCategoryName(catName);
                              setSelectedIssueName(""); // Reset issue on category switch
                            }}
                            style={{
                              padding: "9px 16px",
                              borderRadius: "10px",
                              fontSize: "13px",
                              fontWeight: 600,
                              cursor: "pointer",
                              border: isSelected
                                ? "2px solid #059669"
                                : "1px solid #CBD5E1",
                              background: isSelected ? "#ECFDF5" : "#FFFFFF",
                              color: isSelected ? "#065F46" : "#334155",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "6px",
                              transition: "all 0.15s ease",
                            }}
                          >
                            {isSelected && (
                              <CheckCircle2 size={14} color="#059669" />
                            )}
                            <span>{catName}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* 2. Issue Selection (shows issues under selected category) */}
                <div style={{ marginBottom: "24px" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "13px",
                      fontWeight: 700,
                      color: selectedCategoryName ? "#0F172A" : "#94A3B8",
                      marginBottom: "8px",
                    }}
                  >
                    2. Select Problem / Diagnostic Issue{" "}
                    <span style={{ color: "#EF4444" }}>*</span>
                  </label>

                  {!selectedCategoryName ? (
                    <div
                      style={{
                        padding: "16px",
                        background: "#F8FAFC",
                        borderRadius: "10px",
                        border: "1px dashed #CBD5E1",
                        fontSize: "12.5px",
                        color: "#94A3B8",
                        textAlign: "center",
                      }}
                    >
                      Please select a category above to view diagnostic issues
                    </div>
                  ) : availableIssues.length === 0 ? (
                    <div
                      style={{
                        padding: "16px",
                        background: "#F8FAFC",
                        borderRadius: "10px",
                        fontSize: "12.5px",
                        color: "#64748B",
                        textAlign: "center",
                      }}
                    >
                      No issues cataloged under "{selectedCategoryName}".
                    </div>
                  ) : (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr",
                        gap: "8px",
                        maxHeight: "220px",
                        overflowY: "auto",
                        border: "1px solid #E2E8F0",
                        borderRadius: "12px",
                        padding: "8px",
                        background: "#F8FAFC",
                      }}
                    >
                      {availableIssues.map((it) => {
                        const isSelected = selectedIssueName === it.issue;
                        return (
                          <div
                            key={it.id || it.issue}
                            onClick={() => setSelectedIssueName(it.issue)}
                            style={{
                              padding: "12px 14px",
                              borderRadius: "8px",
                              fontSize: "13.5px",
                              fontWeight: isSelected ? 700 : 500,
                              cursor: "pointer",
                              background: isSelected ? "#FFFFFF" : "#FFFFFF",
                              border: isSelected
                                ? "2px solid #059669"
                                : "1px solid #E2E8F0",
                              color: isSelected ? "#0F172A" : "#334155",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              boxShadow: isSelected
                                ? "0 2px 8px rgba(5, 150, 105, 0.12)"
                                : "none",
                              transition: "all 0.15s ease",
                            }}
                          >
                            <div>
                              <div style={{ fontWeight: 700 }}>{it.issue}</div>
                              {it.description && it.description !== it.issue && (
                                <div
                                  style={{
                                    fontSize: "11.5px",
                                    color: "#64748B",
                                    marginTop: "2px",
                                  }}
                                >
                                  {it.description}
                                </div>
                              )}
                            </div>
                            {isSelected && (
                              <span
                                style={{
                                  fontSize: "12px",
                                  color: "#059669",
                                  fontWeight: 700,
                                  background: "#ECFDF5",
                                  padding: "3px 8px",
                                  borderRadius: "6px",
                                }}
                              >
                                ✓ Selected
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Step 1 Actions */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderTop: "1px solid #F1F5F9",
                    paddingTop: "16px",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setActiveBookingCat(null)}
                    style={{
                      padding: "10px 18px",
                      borderRadius: "8px",
                      border: "1px solid #CBD5E1",
                      background: "#FFFFFF",
                      color: "#475569",
                      fontSize: "13px",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>

                  <button
                    type="button"
                    disabled={!selectedCategoryName || !selectedIssueName}
                    onClick={() => setBookingStep("BOOKING_FORM")}
                    style={{
                      padding: "10px 24px",
                      borderRadius: "8px",
                      border: "none",
                      background:
                        selectedCategoryName && selectedIssueName
                          ? "#059669"
                          : "#94A3B8",
                      color: "#FFFFFF",
                      fontSize: "13px",
                      fontWeight: 700,
                      cursor:
                        selectedCategoryName && selectedIssueName
                          ? "pointer"
                          : "not-allowed",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      boxShadow:
                        selectedCategoryName && selectedIssueName
                          ? "0 2px 6px rgba(5, 150, 105, 0.25)"
                          : "none",
                    }}
                  >
                    <span>Proceed to Schedule & Location</span>
                    <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            ) : (
              /* ─────────────────────────────────────────────────────────────
                  STEP 2: BOOKING FORM
                  Opens ONLY after selecting Category & Issue!
                  Asks: Date, Time, Location (from profile), Phone (from profile)
              ───────────────────────────────────────────────────────────── */
              <form onSubmit={handleBookingSubmit} style={{ padding: "20px 24px" }}>
                {/* Selected Issue Summary Banner with Change Link */}
                <div
                  style={{
                    background: "#F0FDF4",
                    border: "1px solid #BBF7D0",
                    borderRadius: "10px",
                    padding: "12px 16px",
                    marginBottom: "18px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "11px", fontWeight: 700, color: "#166534", textTransform: "uppercase" }}>
                      Selected Problem
                    </div>
                    <div style={{ fontSize: "14px", fontWeight: 700, color: "#0F172A", marginTop: "2px" }}>
                      {selectedCategoryName} ➔ {selectedIssueName}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setBookingStep("SELECT_ISSUE")}
                    style={{
                      background: "none",
                      border: "none",
                      color: "#059669",
                      fontSize: "12px",
                      fontWeight: 700,
                      cursor: "pointer",
                      textDecoration: "underline",
                    }}
                  >
                    Change Issue
                  </button>
                </div>

                {submitError && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "8px",
                      background: "#FEF2F2",
                      border: "1px solid #FCA5A5",
                      borderRadius: "8px",
                      padding: "10px 12px",
                      marginBottom: "16px",
                      color: "#991B1B",
                      fontSize: "12.5px",
                    }}
                  >
                    <AlertCircle size={16} style={{ flexShrink: 0, marginTop: "1px" }} />
                    <span>{submitError}</span>
                  </div>
                )}

                {/* 1. Schedule Grid (Date & Time) */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "12px",
                    marginBottom: "16px",
                  }}
                >
                  {/* Preferred Visit Date */}
                  <div>
                    <label
                      style={{
                        display: "block",
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#475569",
                        marginBottom: "4px",
                      }}
                    >
                      Preferred Date <span style={{ color: "#EF4444" }}>*</span>
                    </label>
                    <input
                      type="date"
                      required
                      value={preferredDate}
                      onChange={(e) => setPreferredDate(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        border: "1px solid #CBD5E1",
                        fontSize: "12.5px",
                        color: "#1E293B",
                        outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>

                  {/* Preferred Time Slot */}
                  <div>
                    <label
                      style={{
                        display: "block",
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#475569",
                        marginBottom: "4px",
                      }}
                    >
                      Preferred Time Slot <span style={{ color: "#EF4444" }}>*</span>
                    </label>
                    <select
                      value={preferredTimeSlot}
                      onChange={(e) => setPreferredTimeSlot(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "8px 10px",
                        borderRadius: "8px",
                        border: "1px solid #CBD5E1",
                        fontSize: "12.5px",
                        color: "#1E293B",
                        outline: "none",
                        boxSizing: "border-box",
                        background: "#FFFFFF",
                      }}
                    >
                      <option value="Morning (09:00 AM - 12:00 PM)">
                        Morning (09:00 AM - 12:00 PM)
                      </option>
                      <option value="Afternoon (12:00 PM - 03:00 PM)">
                        Afternoon (12:00 PM - 03:00 PM)
                      </option>
                      <option value="Evening (03:00 PM - 06:00 PM)">
                        Evening (03:00 PM - 06:00 PM)
                      </option>
                      <option value="Night (06:00 PM - 09:00 PM)">
                        Night (06:00 PM - 09:00 PM)
                      </option>
                    </select>
                  </div>
                </div>

                {/* 2. Contact Phone Number (From Profile, Editable) */}
                <div style={{ marginBottom: "16px" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "12px",
                      fontWeight: 600,
                      color: "#475569",
                      marginBottom: "4px",
                    }}
                  >
                    Contact Phone Number (From Profile, Editable) <span style={{ color: "#EF4444" }}>*</span>
                  </label>
                  <div style={{ position: "relative" }}>
                    <input
                      type="tel"
                      required
                      value={contactNumber}
                      onChange={(e) => setContactNumber(e.target.value)}
                      placeholder="e.g. 9876543210"
                      maxLength={15}
                      style={{
                        width: "100%",
                        padding: "8px 12px 8px 34px",
                        borderRadius: "8px",
                        border: "1px solid #CBD5E1",
                        fontSize: "12.5px",
                        color: "#1E293B",
                        outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                    <Phone
                      size={15}
                      color="#64748B"
                      style={{
                        position: "absolute",
                        left: "10px",
                        top: "50%",
                        transform: "translateY(-50%)",
                      }}
                    />
                  </div>
                </div>

                {/* 3. Service Address / Location (From Profile, Editable) */}
                <div style={{ marginBottom: "16px" }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: "4px",
                    }}
                  >
                    <label
                      style={{
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#475569",
                      }}
                    >
                      Service Location (From Profile, Editable) <span style={{ color: "#EF4444" }}>*</span>
                    </label>
                    <button
                      type="button"
                      onClick={handleGetLocation}
                      disabled={isLocating}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#059669",
                        fontSize: "11.5px",
                        fontWeight: 700,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: 0,
                      }}
                    >
                      <MapPin size={13} />
                      <span>{isLocating ? "Locating..." : "Use Current Location"}</span>
                    </button>
                  </div>

                  <input
                    type="text"
                    required
                    value={locationAddress}
                    onChange={(e) => setLocationAddress(e.target.value)}
                    placeholder="Enter door/building, street address and landmark"
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      borderRadius: "8px",
                      border: "1px solid #CBD5E1",
                      fontSize: "12.5px",
                      color: "#1E293B",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                  {siteCoords.lat && (
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#059669",
                        marginTop: "2px",
                        display: "block",
                      }}
                    >
                      ✓ GPS coordinates tagged ({siteCoords.lat.toFixed(4)}, {siteCoords.lng?.toFixed(4)})
                    </span>
                  )}
                </div>

                {/* 4. Additional Notes (Optional) */}
                <div style={{ marginBottom: "20px" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "12px",
                      fontWeight: 600,
                      color: "#475569",
                      marginBottom: "4px",
                    }}
                  >
                    Additional Notes (Optional)
                  </label>
                  <textarea
                    rows={2}
                    value={additionalNotes}
                    onChange={(e) => setAdditionalNotes(e.target.value)}
                    placeholder="Any specific instructions or symptom description..."
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      borderRadius: "8px",
                      border: "1px solid #CBD5E1",
                      fontSize: "12px",
                      color: "#1E293B",
                      outline: "none",
                      boxSizing: "border-box",
                      fontFamily: "inherit",
                      resize: "vertical",
                    }}
                  />
                </div>

                {/* Form Actions */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderTop: "1px solid #F1F5F9",
                    paddingTop: "16px",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setBookingStep("SELECT_ISSUE")}
                    disabled={submitting}
                    style={{
                      padding: "10px 18px",
                      borderRadius: "8px",
                      border: "1px solid #CBD5E1",
                      background: "#FFFFFF",
                      color: "#475569",
                      fontSize: "13px",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                    }}
                  >
                    <ArrowLeft size={14} />
                    <span>Back to Issues</span>
                  </button>

                  <button
                    type="submit"
                    disabled={submitting || !selectedCategoryName || !selectedIssueName}
                    style={{
                      padding: "10px 24px",
                      borderRadius: "8px",
                      border: "none",
                      background: submitting ? "#94A3B8" : "#059669",
                      color: "#FFFFFF",
                      fontSize: "13px",
                      fontWeight: 700,
                      cursor: submitting ? "not-allowed" : "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      boxShadow: "0 2px 6px rgba(5, 150, 105, 0.25)",
                    }}
                  >
                    <Send size={14} />
                    <span>
                      {submitting ? "Submitting..." : "Submit Service Request ➔"}
                    </span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
