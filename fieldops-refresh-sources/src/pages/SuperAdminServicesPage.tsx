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
  Plus,
  Check,
  ArrowRight,
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
import { useToast } from "../hooks/useToast";
import useAuthStore from "../store/authStore";

// Predefined fallback taxonomy suggestions
const KNOWN_CATEGORIES_MAP: Record<string, string[]> = {
  Electrical: [
    "Wiring & Switchboards",
    "Lighting & Fixtures",
    "Inverter & UPS",
    "MCB & Fuse Box",
    "Ceiling Fans & Regulators",
    "Earthing & Voltage Issue",
  ],
  Plumbing: [
    "Taps & Mixers",
    "Pipe Leakage & Burst",
    "Toilet & Sanitary Fixtures",
    "Water Tank & Motor Pump",
    "Drainage & Pipe Blockage",
    "Water Heater / Geyser Pipe",
  ],
  "AC & HVAC": [
    "Cooling & Compressor",
    "Gas Leakage Detection & Refill",
    "Deep Cleaning & Jet Wash",
    "Water Dripping & Drainage",
    "Thermostat & Remote Control",
  ],
  "Home Appliances": [
    "Washing Machine",
    "Refrigerator & Freezer",
    "Microwave & Induction",
    "Water Purifier (RO/UV)",
    "Chimney & Hob",
  ],
  "Carpentry & Woodwork": [
    "Door Lock & Handle Fitting",
    "Furniture Repair & Assembly",
    "Window & Mosquito Mesh",
    "Modular Kitchen & Drawer Channel",
    "Wall Drilling & TV Hanging",
  ],
  "Security & Smart Home": [
    "CCTV Camera & DVR/NVR",
    "Smart Door Lock & Video Bell",
    "WiFi Router & LAN Cabling",
    "Motion Sensor & Alarm",
  ],
  "Cleaning & Maintenance": [
    "Deep Home Cleaning",
    "Pest Control & Fumigation",
    "Water Tank Cleaning",
    "House Painting & Patchwork",
  ],
};

const KNOWN_ISSUES_MAP: Record<string, string[]> = {
  "Wiring & Switchboards": [
    "Switchboard Rewiring & Short Circuit",
    "Modular Switch Replacement & Sparking Fix",
    "burnt wire",
    "Power Socket 16A Burnt / Heavy Load Trip",
    "Main Distribution Box Inspection",
  ],
  "Lighting & Fixtures": [
    "Ceiling Light Burnt / Holder Loose",
    "Chandelier Assembly & Master Fitting",
    "LED Strip Driver Replacement",
    "Flickering Light & Loose Connection",
    "Tube Light Batten Replacement",
  ],
  "Inverter & UPS": [
    "Inverter Not Charging / Beep Alarm",
    "Battery Acid Top-up & Terminal Cleaning",
    "Automatic Cut-off & Bypass Wire Fix",
  ],
  "MCB & Fuse Box": [
    "MCB Tripping Repeatedly",
    "Main Double-Pole Breaker Burnt",
    "Sub-breaker Sizing & Distribution",
  ],
  "Ceiling Fans & Regulators": [
    "Fan Speed Slow / Capacitor Replacement",
    "Wobbling Fan Noise & Bearing Lubrication",
    "Step Regulator Knob Stuck",
  ],
  "Taps & Mixers": [
    "Continuous Water Dripping & Tap Spout Leak",
    "Wall Mixer Diverter Jammed",
    "Angle Valve Broken Inside Tile",
  ],
  "Pipe Leakage & Burst": [
    "Concealed Wall Pipeline Seepage",
    "PVC/CPVC Joint Crack Leak",
    "Main Water Inlet Pipe Replacement",
  ],
  "Toilet & Sanitary Fixtures": [
    "Flush Tank Siphon Leaking Nonstop",
    "Health Faucet Hose Burst",
    "Wash Basin Waste Coupling Leak",
  ],
  "Cooling & Compressor": [
    "AC Not Cooling / Gas Leakage Detection",
    "Compressor Tripping within 5 minutes",
    "Split AC Indoor Ice Formation",
  ],
  "Washing Machine": [
    "Drum Not Spinning / Drainage Error E02",
    "Excessive Vibration During Spin Cycle",
    "Water Not Filling In Drum",
  ],
};

export default function SuperAdminServicesPage() {
  const { addToast } = useToast();
  const user = useAuthStore((state) => state.user);
  const [services, setServices] = useState<ServiceCatalogItem[]>([]);
  const [taxonomySuggestions, setTaxonomySuggestions] = useState<TaxonomySuggestionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Form State: 1 Service Type, Multiple Categories, Multiple Issues
  const [selectedType, setSelectedType] = useState("");
  const [customType, setCustomType] = useState("");

  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [newCatInput, setNewCatInput] = useState("");

  const [selectedIssuesByCat, setSelectedIssuesByCat] = useState<Record<string, string[]>>({});
  const [newIssueInputs, setNewIssueInputs] = useState<Record<string, string>>({});

  // Load organization-scoped services
  const loadServices = async () => {
    try {
      setLoading(true);
      const data = await getAdminServices();
      setServices(Array.isArray(data) ? data : []);
    } catch (err: any) {
      addToast(err?.response?.data?.detail || "Failed to load services catalog", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadServices();
    getTaxonomySuggestions()
      .then((data) => setTaxonomySuggestions(data))
      .catch((err) => console.warn("Failed to load taxonomy suggestions", err));
  }, []);

  // Compute Metrics dynamically for logged-in organization
  const totalCount = (services || []).length;
  const uniqueTypes = useMemo(
    () => Array.from(new Set((services || []).map((s) => s?.service_type).filter(Boolean))),
    [services]
  );
  const uniqueCategories = useMemo(
    () =>
      Array.from(
        new Set(
          (services || [])
            .map((s) => `${s?.service_type || ""}::${s?.category || ""}`)
            .filter((x) => x !== "::")
        )
      ),
    [services]
  );
  const configuredIssuesCount = (services || []).length;

  // Filtered Services List
  const filteredServices = useMemo(() => {
    if (!Array.isArray(services)) return [];
    return services.filter((s) => {
      if (!s) return false;
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
      const cat = item.category || "General";
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
    const fromSuggestions = taxonomySuggestions?.categories_by_type?.[effectiveType] || [];
    const fromMap = KNOWN_CATEGORIES_MAP[effectiveType] || [];
    const fromExisting = (services || [])
      .filter((s) => s?.service_type === effectiveType)
      .map((s) => s?.category)
      .filter(Boolean);
    return Array.from(new Set([...fromSuggestions, ...fromMap, ...fromExisting]));
  }, [effectiveType, taxonomySuggestions, services]);

  // Issues available for a category
  const getAvailableIssuesForCategory = (catName: string) => {
    const fromSuggestions = taxonomySuggestions?.issues_by_category?.[catName] || [];
    const fromMap = KNOWN_ISSUES_MAP[catName] || [];
    const fromExisting = (services || [])
      .filter((s) => s?.category === catName)
      .map((s) => s?.issue)
      .filter(Boolean);
    return Array.from(new Set([...fromSuggestions, ...fromMap, ...fromExisting]));
  };

  // Open modal - cleanly resets all fields
  const handleOpenCreateModal = () => {
    setSelectedType("");
    setCustomType("");
    setSelectedCategories([]);
    setNewCatInput("");
    setSelectedIssuesByCat({});
    setNewIssueInputs({});
    setIsModalOpen(true);
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
      if (currentList.includes(issueName)) {
        return {
          ...prev,
          [catName]: currentList.filter((i) => i !== issueName),
        };
      } else {
        return {
          ...prev,
          [catName]: [...currentList, issueName],
        };
      }
    });
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
  const handleDeleteService = async (id: number, issueName: string) => {
    if (!window.confirm(`Are you sure you want to delete "${issueName}"?`)) return;
    try {
      await deleteAdminService(id);
      setServices((prev) => prev.filter((s) => s.id !== id));
      addToast(`✓ Service "${issueName}" deleted`, "info");
    } catch (err: any) {
      addToast(err?.response?.data?.detail || "Failed to delete service", "error");
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

  return (
    <div style={{ flex: 1, height: "100%", overflowY: "auto", background: "#F8FAFC", padding: "18px 24px" }}>
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

        <button
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
        </button>
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
            Showing {filteredServices.length} of {services.length} services
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
          <LoadingSpinner size="md" />
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
            Create services for your organization so customers can book them.
          </p>
          <button
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
          </button>
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
                    {domainGroup.service_type}
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
                              {item.issue}
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

                            <button
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
                            </button>

                            <button
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
                            </button>
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

      {/* 5. CREATE SERVICE POP-UP MODAL (DIV CONTAINER - CANNOT SUBMIT FORM OR CAUSE BLANK PAGE) */}
      {isModalOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            zIndex: 2500,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsModalOpen(false);
          }}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "16px",
              width: "680px",
              maxWidth: "96vw",
              maxHeight: "92vh",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "16px 24px",
                borderBottom: "1px solid #E2E8F0",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "#FFFFFF",
              }}
            >
              <div>
                <h3 style={{ fontSize: "17px", fontWeight: 800, color: "#0F172A", margin: "0 0 2px" }}>
                  Create New Service
                </h3>
                <p style={{ fontSize: "12px", color: "#64748B", margin: 0 }}>
                  Configure Trade Domain, Categories, and Diagnostic Issues
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                style={{
                  background: "#F1F5F9",
                  border: "none",
                  borderRadius: "8px",
                  color: "#64748B",
                  cursor: "pointer",
                  padding: "6px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* MINI FLOW DIAGRAM HEADER BANNER */}
            <div
              style={{
                padding: "14px 24px",
                background: "#F8FAFC",
                borderBottom: "1px solid #E2E8F0",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  maxWidth: "560px",
                  margin: "0 auto",
                }}
              >
                {/* Step 1: Service Type */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    background: effectiveType ? "#DCFCE7" : "#FFFFFF",
                    border: effectiveType ? "1.5px solid #16A34A" : "1.5px solid #CBD5E1",
                    borderRadius: "10px",
                    padding: "6px 14px",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                  }}
                >
                  <div
                    style={{
                      width: "20px",
                      height: "20px",
                      borderRadius: "50%",
                      background: effectiveType ? "#16A34A" : "#94A3B8",
                      color: "#FFFFFF",
                      fontSize: "11px",
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    1
                  </div>
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>
                      Trade Domain
                    </div>
                    <div style={{ fontSize: "12.5px", fontWeight: 700, color: effectiveType ? "#15803D" : "#334155" }}>
                      {effectiveType || "Select Type"}
                    </div>
                  </div>
                </div>

                {/* Arrow 1 */}
                <div style={{ display: "flex", alignItems: "center", color: effectiveType ? "#16A34A" : "#CBD5E1" }}>
                  <div style={{ width: "24px", height: "2px", background: effectiveType ? "#16A34A" : "#CBD5E1" }} />
                  <ArrowRight size={14} style={{ marginLeft: "-2px" }} />
                </div>

                {/* Step 2: Categories */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    background: selectedCategories.length > 0 ? "#DCFCE7" : "#FFFFFF",
                    border: selectedCategories.length > 0 ? "1.5px solid #16A34A" : "1.5px solid #CBD5E1",
                    borderRadius: "10px",
                    padding: "6px 14px",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                  }}
                >
                  <div
                    style={{
                      width: "20px",
                      height: "20px",
                      borderRadius: "50%",
                      background: selectedCategories.length > 0 ? "#16A34A" : "#94A3B8",
                      color: "#FFFFFF",
                      fontSize: "11px",
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    2
                  </div>
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>
                      Multi Categories
                    </div>
                    <div
                      style={{
                        fontSize: "12.5px",
                        fontWeight: 700,
                        color: selectedCategories.length > 0 ? "#15803D" : "#334155",
                      }}
                    >
                      {selectedCategories.length > 0 ? `${selectedCategories.length} Selected` : "Categories"}
                    </div>
                  </div>
                </div>

                {/* Arrow 2 */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    color: totalSelectedIssuesCount > 0 ? "#16A34A" : "#CBD5E1",
                  }}
                >
                  <div
                    style={{
                      width: "24px",
                      height: "2px",
                      background: totalSelectedIssuesCount > 0 ? "#16A34A" : "#CBD5E1",
                    }}
                  />
                  <ArrowRight size={14} style={{ marginLeft: "-2px" }} />
                </div>

                {/* Step 3: Issues */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    background: totalSelectedIssuesCount > 0 ? "#DCFCE7" : "#FFFFFF",
                    border: totalSelectedIssuesCount > 0 ? "1.5px solid #16A34A" : "1.5px solid #CBD5E1",
                    borderRadius: "10px",
                    padding: "6px 14px",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                  }}
                >
                  <div
                    style={{
                      width: "20px",
                      height: "20px",
                      borderRadius: "50%",
                      background: totalSelectedIssuesCount > 0 ? "#16A34A" : "#94A3B8",
                      color: "#FFFFFF",
                      fontSize: "11px",
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    3
                  </div>
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>
                      Multi Issues
                    </div>
                    <div
                      style={{
                        fontSize: "12.5px",
                        fontWeight: 700,
                        color: totalSelectedIssuesCount > 0 ? "#15803D" : "#334155",
                      }}
                    >
                      {totalSelectedIssuesCount > 0 ? `${totalSelectedIssuesCount} Selected` : "Issues"}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Body Container (Using DIV instead of FORM to prevent any page reloads) */}
            <div
              style={{
                padding: "20px 24px",
                overflowY: "auto",
                flex: 1,
                display: "flex",
                flexDirection: "column",
                gap: "18px",
              }}
            >
              {/* Field 1: Service Type */}
              <div>
                <label style={{ display: "block", fontSize: "13px", fontWeight: 700, color: "#0F172A", marginBottom: "6px" }}>
                  1. Service Type <span style={{ color: "#DC2626" }}>*</span>
                </label>
                <select
                  required
                  value={selectedType}
                  onChange={(e) => {
                    setSelectedType(e.target.value);
                    setSelectedCategories([]);
                    setSelectedIssuesByCat({});
                  }}
                  style={{
                    width: "100%",
                    padding: "10px 14px",
                    borderRadius: "8px",
                    border: "1.5px solid #CBD5E1",
                    fontSize: "13.5px",
                    color: selectedType ? "#0F172A" : "#64748B",
                    background: "#FFFFFF",
                    fontWeight: selectedType ? 600 : 400,
                    outline: "none",
                  }}
                >
                  <option value="">-- Select Service Type or Enter New --</option>
                  {availableServiceTypes.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                  <option value="__NEW__">+ Enter New Service Type...</option>
                </select>

                {selectedType === "__NEW__" && (
                  <input
                    type="text"
                    required
                    placeholder="e.g. Electrical, Plumbing, HVAC..."
                    value={customType}
                    onChange={(e) => setCustomType(e.target.value)}
                    style={{
                      width: "100%",
                      marginTop: "8px",
                      padding: "10px 14px",
                      borderRadius: "8px",
                      border: "1.5px solid #069660",
                      fontSize: "13.5px",
                      color: "#0F172A",
                      outline: "none",
                    }}
                  />
                )}
              </div>

              {/* Field 2: Categories (Only appears AFTER type is selected) */}
              {effectiveType ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <label style={{ fontSize: "13px", fontWeight: 700, color: "#0F172A" }}>
                      2. Categories for &quot;{effectiveType}&quot; (Multiple Allowed) <span style={{ color: "#DC2626" }}>*</span>
                    </label>
                    <span style={{ fontSize: "11.5px", fontWeight: 700, color: "#059669" }}>
                      {selectedCategories.length} Categories Selected
                    </span>
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
                    {availableCategoriesForType.map((cat) => {
                      const isSelected = selectedCategories.includes(cat);
                      return (
                        <button
                          key={cat}
                          type="button"
                          onClick={() => handleToggleCategory(cat)}
                          style={{
                            background: isSelected ? "#069660" : "#F1F5F9",
                            color: isSelected ? "#FFFFFF" : "#334155",
                            border: isSelected ? "1px solid #069660" : "1px solid #E2E8F0",
                            borderRadius: "20px",
                            padding: "6px 14px",
                            fontSize: "12.5px",
                            fontWeight: 600,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            transition: "all 0.15s ease",
                          }}
                        >
                          {isSelected && <Check size={14} strokeWidth={3} />}
                          <span>{cat}</span>
                        </button>
                      );
                    })}
                  </div>

                  <div style={{ display: "flex", gap: "8px" }}>
                    <input
                      type="text"
                      placeholder="Add custom category name (e.g. Geyser, Inverter, Tank)..."
                      value={newCatInput}
                      onChange={(e) => setNewCatInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddCustomCategory();
                        }
                      }}
                      style={{
                        flex: 1,
                        padding: "8px 12px",
                        borderRadius: "8px",
                        border: "1px solid #CBD5E1",
                        fontSize: "13px",
                        outline: "none",
                      }}
                    />
                    <button
                      type="button"
                      onClick={handleAddCustomCategory}
                      style={{
                        background: "#0F172A",
                        color: "#FFFFFF",
                        border: "none",
                        borderRadius: "8px",
                        padding: "8px 14px",
                        fontSize: "12.5px",
                        fontWeight: 600,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                      }}
                    >
                      <Plus size={14} />
                      <span>Add</span>
                    </button>
                  </div>
                </div>
              ) : null}

              {/* Field 3: Issues (ZERO AUTO-SELECTION: user manually clicks to select!) */}
              {selectedCategories.length > 0 ? (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <label style={{ fontSize: "13px", fontWeight: 700, color: "#0F172A" }}>
                      3. Specific Issues (Click to Select) <span style={{ color: "#DC2626" }}>*</span>
                    </label>
                    <span style={{ fontSize: "11.5px", fontWeight: 700, color: totalSelectedIssuesCount > 0 ? "#059669" : "#64748B" }}>
                      {totalSelectedIssuesCount} Total Issues Selected
                    </span>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {selectedCategories.map((cat) => {
                      const availableIssues = getAvailableIssuesForCategory(cat);
                      const currentSelected = selectedIssuesByCat[cat] || [];

                      return (
                        <div
                          key={cat}
                          style={{
                            background: "#F8FAFC",
                            border: "1px solid #E2E8F0",
                            borderRadius: "10px",
                            padding: "12px 16px",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              marginBottom: "10px",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <Layers size={15} color="#D97706" />
                              <span style={{ fontSize: "13px", fontWeight: 700, color: "#1E293B" }}>
                                {cat}
                              </span>
                            </div>
                            <span style={{ fontSize: "11px", fontWeight: 700, color: currentSelected.length > 0 ? "#059669" : "#64748B" }}>
                              {currentSelected.length} selected
                            </span>
                          </div>

                          {/* Issues Chips: Starts completely unselected */}
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
                            {availableIssues.map((iss) => {
                              const isChecked = currentSelected.includes(iss);
                              return (
                                <button
                                  key={iss}
                                  type="button"
                                  onClick={() => handleToggleIssue(cat, iss)}
                                  style={{
                                    background: isChecked ? "#069660" : "#FFFFFF",
                                    color: isChecked ? "#FFFFFF" : "#334155",
                                    border: isChecked ? "1px solid #069660" : "1px solid #CBD5E1",
                                    borderRadius: "8px",
                                    padding: "6px 12px",
                                    fontSize: "12px",
                                    fontWeight: 600,
                                    cursor: "pointer",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "6px",
                                    textAlign: "left",
                                    transition: "all 0.15s ease",
                                  }}
                                >
                                  {isChecked && <Check size={13} strokeWidth={3} />}
                                  <span>{iss}</span>
                                </button>
                              );
                            })}
                          </div>

                          {/* Add Custom Issue Input */}
                          <div style={{ display: "flex", gap: "8px" }}>
                            <input
                              type="text"
                              placeholder={`Add custom issue for "${cat}" (e.g. burnt wire)...`}
                              value={newIssueInputs[cat] || ""}
                              onChange={(e) =>
                                setNewIssueInputs((prev) => ({
                                  ...prev,
                                  [cat]: e.target.value,
                                }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  handleAddCustomIssue(cat);
                                }
                              }}
                              style={{
                                flex: 1,
                                padding: "7px 10px",
                                borderRadius: "6px",
                                border: "1px solid #CBD5E1",
                                fontSize: "12px",
                                background: "#FFFFFF",
                                outline: "none",
                              }}
                            />
                            <button
                              type="button"
                              onClick={() => handleAddCustomIssue(cat)}
                              style={{
                                background: "#0F172A",
                                color: "#FFFFFF",
                                border: "none",
                                borderRadius: "6px",
                                padding: "7px 12px",
                                fontSize: "12px",
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              Add Issue
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {/* Bottom Actions Row */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  paddingTop: "14px",
                  borderTop: "1px solid #E2E8F0",
                  marginTop: "6px",
                }}
              >
                <div style={{ fontSize: "12px", color: "#64748B", fontWeight: 600 }}>
                  {effectiveType && selectedCategories.length > 0 && totalSelectedIssuesCount > 0 ? (
                    <span style={{ color: "#059669" }}>
                      ✓ 1 Domain • {selectedCategories.length} Categories • {totalSelectedIssuesCount} Issues
                    </span>
                  ) : (
                    <span>Configure Type, Category, and Issues</span>
                  )}
                </div>

                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    style={{
                      padding: "9px 18px",
                      border: "1px solid #CBD5E1",
                      borderRadius: "8px",
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
                    onClick={handlePublishServices}
                    disabled={submitting || totalSelectedIssuesCount === 0}
                    style={{
                      padding: "9px 22px",
                      border: "none",
                      borderRadius: "8px",
                      background: totalSelectedIssuesCount > 0 ? "#069660" : "#94A3B8",
                      color: "#FFFFFF",
                      fontSize: "13px",
                      fontWeight: 700,
                      cursor: submitting || totalSelectedIssuesCount === 0 ? "not-allowed" : "pointer",
                      boxShadow: totalSelectedIssuesCount > 0 ? "0 2px 6px rgba(6, 150, 96, 0.25)" : "none",
                      transition: "all 0.15s ease",
                    }}
                  >
                    {submitting
                      ? "Publishing..."
                      : `Publish Service (${totalSelectedIssuesCount})`}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
