import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  ChevronDown,
  Plus,
  X,
  Check,
  Wrench,
  Sparkles,
  Layers,
  Tag,
} from "lucide-react";
import {
  getServicesTaxonomy,
  type ServicesTaxonomyResponse,
  type TaxonomyIssueItem,
} from "../../services/servicesCatalogService";
import useAuthStore from "../../store/authStore";

interface SkillComboSelectProps {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  inputStyle?: React.CSSProperties;
  className?: string;
  hasError?: boolean;
  name?: string;
}

const DEFAULT_SUGGESTIONS = [
  "HVAC Repair",
  "Electrical",
  "Plumbing",
  "Network Support",
  "General Maintenance",
  "Appliance Repair",
  "CCTV & Security",
  "Roofing & Carpentry",
];

export const SkillComboSelect: React.FC<SkillComboSelectProps> = ({
  value,
  onChange,
  placeholder = "e.g. Electrical, Plumbing, HVAC Repair",
  inputStyle,
  className = "",
  hasError = false,
  name,
}) => {
  const { user } = useAuthStore();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Taxonomy state from organization/platform services
  const [taxonomy, setTaxonomy] = useState<ServicesTaxonomyResponse | null>(null);
  const [loadingTaxonomy, setLoadingTaxonomy] = useState(false);

  // Hierarchical selection state: Service Type -> Category -> Issue
  const [selectedServiceType, setSelectedServiceType] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedIssue, setSelectedIssue] = useState<string>("");

  // Fetch organization's services catalog on mount
  useEffect(() => {
    let isMounted = true;
    const fetchTaxonomy = async () => {
      setLoadingTaxonomy(true);
      try {
        const data = await getServicesTaxonomy(user?.tenant_id);
        if (isMounted && data) {
          setTaxonomy(data);
        }
      } catch (err) {
        console.error("Failed to fetch services taxonomy:", err);
      } finally {
        if (isMounted) setLoadingTaxonomy(false);
      }
    };
    fetchTaxonomy();
    return () => {
      isMounted = false;
    };
  }, [user?.tenant_id]);

  // Click outside listener for suggestions dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Parse current skills as array of strings
  const currentSkills = useMemo(() => {
    if (!value) return [];
    return value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }, [value]);

  // Dynamic lists from taxonomy
  const availableServiceTypes = useMemo(() => {
    if (taxonomy && taxonomy.service_types && taxonomy.service_types.length > 0) {
      return taxonomy.service_types;
    }
    return ["Electrical", "Plumbing", "AC & HVAC", "Home Appliances", "Carpentry & Woodwork", "Security & Smart Home", "Cleaning & Maintenance"];
  }, [taxonomy]);

  const availableCategories = useMemo(() => {
    if (!selectedServiceType || !taxonomy?.categories_by_type) return [];
    return taxonomy.categories_by_type[selectedServiceType] || [];
  }, [selectedServiceType, taxonomy]);

  const availableIssues = useMemo(() => {
    if (!selectedCategory || !taxonomy?.issues_by_category) return [];
    return taxonomy.issues_by_category[selectedCategory] || [];
  }, [selectedCategory, taxonomy]);

  // Handle adding skill from hierarchical selector
  const handleAddHierarchicalSkill = () => {
    if (!selectedServiceType) return;

    // We can add the specific issue if chosen, or category, or service type
    const skillsToAdd: string[] = [];

    // Always include service type if not present
    if (!currentSkills.includes(selectedServiceType)) {
      skillsToAdd.push(selectedServiceType);
    }

    if (selectedCategory && !currentSkills.includes(selectedCategory)) {
      skillsToAdd.push(selectedCategory);
    }

    if (selectedIssue && !currentSkills.includes(selectedIssue)) {
      skillsToAdd.push(selectedIssue);
    }

    if (skillsToAdd.length > 0) {
      const updated = [...currentSkills, ...skillsToAdd];
      onChange(updated.join(", "));
    }

    // Reset selection after adding
    setSelectedIssue("");
  };

  // Remove a skill badge
  const handleRemoveSkill = (skillToRemove: string) => {
    const updated = currentSkills.filter((s) => s !== skillToRemove);
    onChange(updated.join(", "));
  };

  // Quick suggestion select
  const handleSelectSuggestion = (suggestion: string) => {
    if (!currentSkills.includes(suggestion)) {
      const updated = [...currentSkills, suggestion];
      onChange(updated.join(", "));
    }
    setIsOpen(false);
  };

  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: "10px" }}>
      {/* ─────────────────────────────────────────────────────────────
          1. Hierarchical Service Catalog Selector (Super Admin linked)
          Service Type ➔ Category ➔ Issues
      ───────────────────────────────────────────────────────────── */}
      <div
        style={{
          background: "#F8FAFC",
          border: "1px solid #E2E8F0",
          borderRadius: "10px",
          padding: "12px 14px",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "10px",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              fontWeight: 700,
              color: "#0F172A",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <Layers size={14} color="#059669" />
            <span>Add Skills from Organization Service Catalog</span>
          </div>
          <span style={{ fontSize: "11px", color: "#64748B" }}>
            Service Type ➔ Category ➔ Issue
          </span>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr)) 100px",
            gap: "10px",
            alignItems: "center",
          }}
        >
          {/* Step 1: Service Type */}
          <div>
            <label
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 600,
                color: "#475569",
                marginBottom: "4px",
              }}
            >
              1. Service Type
            </label>
            <select
              value={selectedServiceType}
              onChange={(e) => {
                setSelectedServiceType(e.target.value);
                setSelectedCategory("");
                setSelectedIssue("");
              }}
              style={{
                width: "100%",
                padding: "8px 10px",
                borderRadius: "7px",
                border: "1px solid #CBD5E1",
                fontSize: "12.5px",
                color: "#1E293B",
                background: "#FFFFFF",
                outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="">Select Service Type...</option>
              {availableServiceTypes.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          </div>

          {/* Step 2: Category */}
          <div>
            <label
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 600,
                color: selectedServiceType ? "#475569" : "#94A3B8",
                marginBottom: "4px",
              }}
            >
              2. Category
            </label>
            <select
              disabled={!selectedServiceType}
              value={selectedCategory}
              onChange={(e) => {
                setSelectedCategory(e.target.value);
                setSelectedIssue("");
              }}
              style={{
                width: "100%",
                padding: "8px 10px",
                borderRadius: "7px",
                border: "1px solid #CBD5E1",
                fontSize: "12.5px",
                color: selectedServiceType ? "#1E293B" : "#94A3B8",
                background: selectedServiceType ? "#FFFFFF" : "#F1F5F9",
                outline: "none",
                cursor: selectedServiceType ? "pointer" : "not-allowed",
              }}
            >
              <option value="">
                {!selectedServiceType
                  ? "Select type first..."
                  : availableCategories.length === 0
                  ? "No categories found"
                  : "Select Category..."}
              </option>
              {availableCategories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          {/* Step 3: Issues */}
          <div>
            <label
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 600,
                color: selectedCategory ? "#475569" : "#94A3B8",
                marginBottom: "4px",
              }}
            >
              3. Specific Issue / Skill
            </label>
            <select
              disabled={!selectedCategory}
              value={selectedIssue}
              onChange={(e) => setSelectedIssue(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 10px",
                borderRadius: "7px",
                border: "1px solid #CBD5E1",
                fontSize: "12.5px",
                color: selectedCategory ? "#1E293B" : "#94A3B8",
                background: selectedCategory ? "#FFFFFF" : "#F1F5F9",
                outline: "none",
                cursor: selectedCategory ? "pointer" : "not-allowed",
              }}
            >
              <option value="">
                {!selectedCategory
                  ? "Select category first..."
                  : availableIssues.length === 0
                  ? "Add category skill directly"
                  : "All Category Issues / Pick..."}
              </option>
              {availableIssues.map((iss) => (
                <option key={iss.id || iss.issue} value={iss.issue}>
                  {iss.issue}
                </option>
              ))}
            </select>
          </div>

          {/* Action: Add Button */}
          <div style={{ paddingTop: "18px" }}>
            <button
              type="button"
              onClick={handleAddHierarchicalSkill}
              disabled={!selectedServiceType}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: "7px",
                border: "none",
                background: selectedServiceType ? "#059669" : "#94A3B8",
                color: "#FFFFFF",
                fontSize: "12px",
                fontWeight: 700,
                cursor: selectedServiceType ? "pointer" : "not-allowed",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "4px",
                boxShadow: selectedServiceType
                  ? "0 2px 6px rgba(5, 150, 105, 0.25)"
                  : "none",
                transition: "background 0.15s ease",
              }}
              title="Add selected service type, category, and issue to technician skills"
            >
              <Plus size={14} />
              <span>+ Add</span>
            </button>
          </div>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          2. Active Skills Badges
      ───────────────────────────────────────────────────────────── */}
      {currentSkills.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "6px",
            padding: "4px 2px",
          }}
        >
          {currentSkills.map((skill) => (
            <span
              key={skill}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "5px",
                background: "#ECFDF5",
                color: "#065F46",
                border: "1px solid #A7F3D0",
                borderRadius: "999px",
                padding: "4px 10px",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              <Tag size={12} color="#059669" />
              <span>{skill}</span>
              <button
                type="button"
                onClick={() => handleRemoveSkill(skill)}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  padding: "0",
                  color: "#059669",
                  marginLeft: "2px",
                }}
                title={`Remove ${skill}`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          3. Raw Comma-Separated Input + Suggestions Fallback
      ───────────────────────────────────────────────────────────── */}
      <div ref={dropdownRef} style={{ position: "relative", width: "100%" }}>
        <div
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            width: "100%",
          }}
        >
          <input
            type="text"
            name={name}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setIsOpen(true)}
            placeholder={placeholder}
            className={className}
            style={{
              ...inputStyle,
              width: "100%",
              paddingRight: "34px",
              borderColor: hasError
                ? "#ef4444"
                : inputStyle?.borderColor || "#e2e8f0",
              boxSizing: "border-box",
            }}
          />
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            tabIndex={-1}
            style={{
              position: "absolute",
              right: "8px",
              top: "50%",
              transform: "translateY(-50%)",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#64748B",
              display: "flex",
              alignItems: "center",
              padding: "4px",
              zIndex: 2,
            }}
          >
            <ChevronDown size={16} />
          </button>
        </div>

        {isOpen && (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              left: 0,
              right: 0,
              background: "#FFFFFF",
              borderRadius: "10px",
              border: "1px solid #E2E8F0",
              boxShadow: "0 10px 25px rgba(0, 0, 0, 0.12)",
              zIndex: 9999,
              maxHeight: "220px",
              overflowY: "auto",
              padding: "4px 0",
            }}
          >
            <div
              style={{
                padding: "6px 12px",
                fontSize: "11px",
                fontWeight: 700,
                color: "#64748B",
                textTransform: "uppercase",
                letterSpacing: "0.5px",
                borderBottom: "1px solid #F1F5F9",
              }}
            >
              Suggested Skills
            </div>
            {DEFAULT_SUGGESTIONS.map((s) => {
              const isSelected = currentSkills.includes(s);

              return (
                <div
                  key={s}
                  onClick={() => handleSelectSuggestion(s)}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = "#F1F5F9")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = "#FFFFFF")
                  }
                  style={{
                    padding: "8px 14px",
                    fontSize: "13px",
                    fontWeight: 600,
                    color: "#1E293B",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    transition: "background 0.15s",
                  }}
                >
                  <span>{s}</span>
                  {isSelected && (
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#16A34A",
                        fontWeight: 700,
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
    </div>
  );
};
