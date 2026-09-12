import { useState, useEffect } from "react";
import {
  FileText,
  PlusCircle,
  XCircle,
  Edit3,
  AlertCircle,
  CheckCircle,
  X,
  Clock,
  Send,
  MapPin,
} from "lucide-react";

import {
  getServiceRequests,
  createServiceRequest,
  updateServiceRequest,
  cancelServiceRequest,
} from "../../services/customerPortalService";

import api from "../../services/api";

const badge = (status: string) => {
  const c: Record<string, string> = {
    UNASSIGNED: "#DD6B20",
    "AWAITING ACCEPTANCE": "#1E40AF",
    ASSIGNED: "#1E40AF",
    "EN ROUTE": "#7C3AED",
    "IN_PROGRESS": "#92400E",
    COMPLETED: "#065F46",
    CANCELLED: "#991B1B",
  };

  const displayStatus =
    status === "CREATED"
      ? "UNASSIGNED"
      : status === "ASSIGNED"
      ? "AWAITING ACCEPTANCE"
      : status === "ACCEPTED"
      ? "ASSIGNED"
      : status === "EN_ROUTE"
      ? "EN ROUTE"
      : status === "IN_PROGRESS"
      ? "IN_PROGRESS"
      : status;

  return {
    fontSize: "11px",
    fontWeight: 600,
    padding: "3px 10px",
    borderRadius: "20px",
    background: (c[displayStatus] || "#6B7280") + "18",
    color: c[displayStatus] || "#6B7280",
    display: "inline-block",
  };
};


interface CustomerServiceRequestsPageProps {
  createOnly?: boolean;
  onNavigate?: (tab: string) => void;
}

export default function CustomerServiceRequestsPage({
  createOnly = false,
  onNavigate,
}: CustomerServiceRequestsPageProps) {
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(!createOnly);

  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    service_type: "",
    priority: "select priority",
    preferred_visit_date: "",
    location: "",
    contact_number: "",
  });
  const [siteLatitude, setSiteLatitude] = useState<number | null>(null);
  const [siteLongitude, setSiteLongitude] = useState<number | null>(null);
  const [isGettingLocation, setIsGettingLocation] = useState(false);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = () => {
    setLoading(true);

    getServiceRequests()
      .then((r) => setRequests(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!createOnly) {
      load();
    }
  }, [createOnly]);

  const reset = () => {
    setForm({
      title: "",
      description: "",
      service_type: "",
      priority: "select priority",
      preferred_visit_date: "",
      location: "",
      contact_number: "",
    });

    setShowCreate(false);
    setEditId(null);
    setError("");
  };

  const clearFormOnly = () => {
    setForm({
      title: "",
      description: "",
      service_type: "",
      priority: "select priority",
      preferred_visit_date: "",
      location: "",
      contact_number: "",
    });

    setError("");
  };

  const getTodayDate = () => {
    const today = new Date();

    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
  };

  const handleSubmit = async () => {
    setError("");

    const title = form.title.trim();
    const description = form.description.trim();
    const location = form.location.trim();
    const contactNumber = form.contact_number.trim();

    // TITLE VALIDATION
    if (!title) {
      setError("Title is required");
      return;
    }

    if (title.length < 10) {
      setError("Title must be at least 10 characters");
      return;
    }

    // DESCRIPTION VALIDATION
    if (!description) {
      setError("Description is required");
      return;
    }

    if (description.trim().length < 25) {
      setError("Description minimum 25 characters required");
      return;
    }

    // SERVICE TYPE VALIDATION
    if (!form.service_type) {
      setError("Please select a service type");
      return;
    }

    // PRIORITY VALIDATION
    if (!form.priority || form.priority === "select priority") {
      setError("Please select a priority");
      return;
    }

    // PREFERRED DATE VALIDATION
    if (!form.preferred_visit_date) {
      setError("Preferred date is required");
      return;
    }

    if (form.preferred_visit_date < getTodayDate()) {
      setError("Preferred date cannot be before today");
      return;
    }

    // CONTACT NUMBER VALIDATION
    if (!contactNumber) {
      setError("Contact number is required");
      return;
    }

    if (!/^\d+$/.test(contactNumber)) {
      setError("Contact number must contain numbers only");
      return;
    }

    if (contactNumber.length !== 10) {
      setError("Contact number must be exactly 10 digits");
      return;
    }

    // LOCATION VALIDATION
    if (!location) {
      setError("Location / Address is required");
      return;
    }

    setSaving(true);

    try {
      const payload = {
        ...form,
        title,
        description,
        location,
        contact_number: contactNumber,
        preferred_visit_date: form.preferred_visit_date || null,
        site_latitude: siteLatitude,
        site_longitude: siteLongitude,
      };

      if (editId) {
        await updateServiceRequest(editId, payload);

        setSuccess("Request updated!");

        setShowCreate(false);
        setEditId(null);

        setForm({
          title: "",
          description: "",
          service_type: "",
          priority: "select priority",
          preferred_visit_date: "",
          location: "",
          contact_number: "",
        });

        load();
      } else {
        await createServiceRequest(payload);

        if (createOnly) {
          onNavigate?.("cust_requests");
          return;
        }

        setSuccess("Request created!");
        reset();
        load();
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || "Failed");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = async (id: number) => {
    if (!confirm("Cancel this service request?")) return;

    try {
      await cancelServiceRequest(id);
      load();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Failed");
    }
  };

  const startEdit = (sr: any) => {
    setForm({
      title: sr.title,
      description: sr.description,
      service_type: sr.service_type || "",
      priority: sr.priority || "select priority",
      preferred_visit_date: sr.preferred_visit_date
        ? String(sr.preferred_visit_date).slice(0, 10)
        : "",
      location: sr.location || "",
      contact_number: sr.contact_number || "",
    });

    setEditId(sr.id);
    setShowCreate(true);
    setError("");
  };

  const upd = (k: string, v: string) => {
    setForm((f) => ({
      ...f,
      [k]: v,
    }));
  };

  const inputStyle = {
    width: "100%",
    padding: "10px 12px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    boxSizing: "border-box" as const,
    outline: "none",
    fontFamily: "'Inter', sans-serif",
  };

  const labelStyle = {
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "4px",
    display: "block" as const,
  };

  const requiredStar = {
    color: "#DC2626",
  };

  if (createOnly) {
    return (
      <div
        style={{
          padding: "24px",
          height: "100%",
          overflowY: "auto",
          background: "#EEF4F1",
          fontFamily: "'Inter', sans-serif",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "760px",
            margin: "0 auto",
            padding: "10px 0 40px",
          }}
        >
          <h2
            style={{
              fontSize: "26px",
              fontWeight: 700,
              color: "#1F2933",
              marginBottom: "28px",
            }}
          >
            Create Service Request
          </h2>

          {error && (
            <div
              style={{
                background: "#FEF2F2",
                border: "1px solid #FECACA",
                borderRadius: "8px",
                padding: "10px",
                color: "#991B1B",
                fontSize: "13px",
                marginBottom: "14px",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "18px",
            }}
          >
            <div>
              <label style={labelStyle}>
                Title <span style={requiredStar}>*</span>
              </label>

              <input
                style={inputStyle}
                value={form.title}
                onChange={(e) => upd("title", e.target.value)}
                placeholder="Brief title for your request"
              />
            </div>

            <div>
              <label style={labelStyle}>
                Description <span style={requiredStar}>*</span>
              </label>

              <textarea
                style={{
                  ...inputStyle,
                  minHeight: "120px",
                  resize: "vertical",
                }}
                value={form.description}
                onChange={(e) => upd("description", e.target.value)}
                placeholder="Describe the issue in detail..."
              />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "16px",
              }}
            >
              <div>
                <label style={labelStyle}>
                  Service Type <span style={{ color: "red" }}>*</span>
                </label>

                <select
                  required
                  style={{
                    ...inputStyle,
                    color: form.service_type ? "#111827" : "#9CA3AF",
                  }}
                  value={form.service_type}
                  onChange={(e) => upd("service_type", e.target.value)}
                >
                  <option value="">select service</option>
                  <option value="HVAC Repair">HVAC Repair</option>
                  <option value="Electrical">Electrical</option>
                  <option value="Plumbing">Plumbing</option>
                  <option value="Network Support">Network Support</option>
                  <option value="General Maintenance">
                    General Maintenance
                  </option>
                  <option value="Appliance Repair">Appliance Repair</option>
                  <option value="CCTV & Security">CCTV & Security</option>
                  <option value="Roofing & Carpentry">
                    Roofing & Carpentry
                  </option>
                </select>
              </div>

              <div>
                <label style={labelStyle}>
                  Priority <span style={requiredStar}>*</span>
                </label>

                <select
                  style={{
                    ...inputStyle,
                    color:
                      form.priority === "select priority"
                        ? "#9CA3AF"
                        : "#111827",
                  }}
                  value={form.priority}
                  onChange={(e) => upd("priority", e.target.value)}
                >
                  <option value="select priority">select priority</option>
                  <option value="LOW">LOW</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="HIGH">HIGH</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "16px",
              }}
            >
              <div>
                <label style={labelStyle}>
                  Preferred Date <span style={requiredStar}>*</span>
                </label>

                <input
                  type="date"
                  min={getTodayDate()}
                  style={{
                    ...inputStyle,
                    color: form.preferred_visit_date
                      ? "#111827"
                      : "#9CA3AF",
                  }}
                  value={form.preferred_visit_date}
                  onChange={(e) =>
                    upd("preferred_visit_date", e.target.value)
                  }
                />
              </div>

              <div>
                <label style={labelStyle}>
                  Contact Number <span style={requiredStar}>*</span>
                </label>

                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={10}
                  style={inputStyle}
                  value={form.contact_number}
                  onChange={(e) => {
                    const value = e.target.value.replace(/\D/g, "");
                    upd("contact_number", value);
                  }}
                  placeholder="10 digit mobile number"
                />
              </div>
            </div>

            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "6px",
                }}
              >
                <label style={labelStyle}>
                  Location / Address <span style={requiredStar}>*</span>
                </label>

                <div
                  onClick={() => {
                    if (!navigator.geolocation) {
                      setError("Geolocation is not supported by this browser.");
                      return;
                    }

                    setError("");
                    setIsGettingLocation(true);

                    navigator.geolocation.getCurrentPosition(
                      async (position) => {
                        let latitude = position.coords.latitude;
                        let longitude = position.coords.longitude;

                        setSiteLatitude(latitude);
                        setSiteLongitude(longitude);

                        try {
                          const response = await api.get(
                            "/organizations/reverse-location",
                            {
                              params: {
                                latitude,
                                longitude,
                              },
                            },
                          );

                          if (
                            response.data?.verified &&
                            response.data?.address
                          ) {
                            upd("location", response.data.address);
                            setError("");
                          } else {
                            setError(
                              "Unable to determine address from your current location.",
                            );
                          }

                          setIsGettingLocation(false);
                        } catch (error) {
                          console.error("Reverse geocoding failed:", error);

                          setError(
                            "Unable to determine address from your current location.",
                          );
                          setIsGettingLocation(false);
                        }
                      },
                      (error) => {
                        console.error("Geolocation error:", error);

                        setError(
                          "Unable to get your current location. Please allow location access.",
                        );
                        setIsGettingLocation(false);
                      },
                      {
                        enableHighAccuracy: true,
                        timeout: 15000,
                        maximumAge: 0,
                      },
                    );
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "#5C9470",
                    cursor: "pointer",
                  }}
                >
                  {isGettingLocation ? (
                    <>
                      <span
                        style={{
                          width: "12px",
                          height: "12px",
                          border: "2px solid #5C9470",
                          borderTopColor: "transparent",
                          borderRadius: "50%",
                          display: "inline-block",
                          animation: "spin 0.8s linear infinite",
                        }}
                      />
                      <span>Getting location...</span>
                    </>
                  ) : (
                    <>
                      <MapPin size={14} />
                      <span>Use current location</span>
                    </>
                  )}
                </div>
              </div>

              <input
                style={inputStyle}
                value={form.location}
                onChange={(e) => {
                  upd("location", e.target.value);
                  setSiteLatitude(null);
                  setSiteLongitude(null);
                }}
                placeholder="Enter service location"
              />
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "12px",
                marginTop: "10px",
              }}
            >
              <button
                type="button"
                onClick={clearFormOnly}
                style={{
                  padding: "10px 24px",
                  border: "1px solid #D1D5DB",
                  borderRadius: "8px",
                  background: "#fff",
                  color: "#374151",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Clear
              </button>

              <button
                type="button"
                onClick={handleSubmit}
                disabled={saving}
                style={{
                  padding: "10px 24px",
                  border: "none",
                  borderRadius: "8px",
                  background: "#7AAE8A",
                  color: "#fff",
                  fontSize: "13px",
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  opacity: saving ? 0.7 : 1,
                }}
              >
                <Send size={14} />
                {saving ? "Submitting..." : "Submit"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
        }}
      >
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#1F2933",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <FileText size={22} color="#7AAE8A" />
          My Requests
        </h2>

        <button
          onClick={() => {
            onNavigate?.("cust_create_request");
          }}
          style={{
            padding: "10px 20px",
            border: "none",
            borderRadius: "10px",
            background: "#7AAE8A",
            color: "#fff",
            fontSize: "13px",
            fontWeight: 700,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <PlusCircle size={16} />
          New Request
        </button>
      </div>

      {/* Success */}
      {success && (
        <div
          style={{
            background: "#F0FFF4",
            border: "1px solid #C6F6D5",
            borderRadius: "8px",
            padding: "10px 14px",
            color: "#22543D",
            fontSize: "13px",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <CheckCircle size={16} />
          {success}
        </div>
      )}

      {/* Request Cards */}
      {loading ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
          }}
        >
          Loading...
        </div>
      ) : requests.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
          }}
        >
          No service requests yet. Create your first one!
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "12px",
          }}
        >
          {requests.map((sr) => (
            <div
              key={sr.id}
              style={{
                background: "#fff",
                borderRadius: "14px",
                padding: "18px",
                boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
                border: "1px solid #E3ECE7",
              }}
            >
              {/* Request Header */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  marginBottom: "8px",
                  gap: "10px",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "#9CA3AF",
                    }}
                  >
                    {sr.request_number}
                  </span>

                  <div
                    style={{
                      fontSize: "15px",
                      fontWeight: 700,
                      color: "#1F2933",
                      marginTop: "2px",
                      lineHeight: "20px",
                    }}
                  >
                    {sr.title}
                  </div>
                </div>

                <span style={badge(sr.status) as any}>
                  {sr.status === "CREATED"
                    ? "UNASSIGNED"
                    : sr.status === "ASSIGNED"
                    ? "AWAITING ACCEPTANCE"
                    : sr.status === "ACCEPTED"
                    ? "ASSIGNED"
                    : sr.status === "EN_ROUTE"
                    ? "EN ROUTE"
                    : sr.status === "IN_PROGRESS"
                    ? "IN_PROGRESS"
                    : sr.status}
                </span>
              </div>

              {/* Description */}
              <div
                style={{
                  fontSize: "13px",
                  color: "#6B7280",
                  marginBottom: "10px",
                  lineHeight: 1.5,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {sr.description}
              </div>

              {/* Metadata */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  columnGap: "12px",
                  rowGap: "7px",
                  fontSize: "12px",
                  color: "#8A94A3",
                }}
              >
                {sr.service_type && (
                  <span>
                    Type: {sr.service_type}
                  </span>
                )}

                <span>
                  Priority: {sr.priority}
                </span>

                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    whiteSpace: "nowrap",
                  }}
                >
                  <Clock size={12} />
                  {new Date(sr.created_at).toLocaleDateString()}
                </span>

                {sr.linked_job_id && (
                  <span>
                    Linked Job: #{sr.linked_job_id}
                  </span>
                )}
              </div>

              {/* Actions */}
              {sr.status === "UNASSIGNED" && (
                <div
                  style={{
                    display: "flex",
                    gap: "8px",
                    marginTop: "12px",
                    paddingTop: "10px",
                    borderTop: "1px solid #F0F0F0",
                  }}
                >
                  <button
                    onClick={() => startEdit(sr)}
                    style={{
                      padding: "6px 14px",
                      border: "1px solid #D1D5DB",
                      borderRadius: "6px",
                      background: "#fff",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      color: "#374151",
                    }}
                  >
                    <Edit3 size={12} />
                    Edit
                  </button>

                  <button
                    onClick={() => handleCancel(sr.id)}
                    style={{
                      padding: "6px 14px",
                      border: "none",
                      borderRadius: "6px",
                      background: "#FEE2E2",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      color: "#991B1B",
                    }}
                  >
                    <XCircle size={12} />
                    Cancel
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* EDIT POPUP */}
      {showCreate && editId !== null && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "rgba(0,0,0,0.4)",
            }}
            onClick={reset}
          />

          <div
            style={{
              position: "relative",
              background: "#fff",
              borderRadius: "16px",
              padding: "28px",
              width: "90%",
              maxWidth: "520px",
              zIndex: 1,
              maxHeight: "90vh",
              overflowY: "auto",
            }}
          >
            <button
              onClick={reset}
              style={{
                position: "absolute",
                top: "12px",
                right: "12px",
                background: "none",
                border: "none",
                cursor: "pointer",
              }}
            >
              <X size={20} color="#6B7280" />
            </button>

            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "#1F2933",
                marginBottom: "20px",
              }}
            >
              Edit Request
            </h3>

            {error && (
              <div
                style={{
                  background: "#FEF2F2",
                  border: "1px solid #FECACA",
                  borderRadius: "8px",
                  padding: "10px",
                  color: "#991B1B",
                  fontSize: "13px",
                  marginBottom: "14px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <AlertCircle size={14} />
                {error}
              </div>
            )}

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "14px",
              }}
            >
              <div>
                <label style={labelStyle}>
                  Title <span style={requiredStar}>*</span>
                </label>

                <input
                  style={inputStyle}
                  value={form.title}
                  onChange={(e) => upd("title", e.target.value)}
                  placeholder="Brief title for your request"
                />
              </div>

              <div>
                <label style={labelStyle}>
                  Description <span style={requiredStar}>*</span>
                </label>

                <textarea
                  style={{
                    ...inputStyle,
                    minHeight: "100px",
                    resize: "vertical",
                  }}
                  value={form.description}
                  onChange={(e) => upd("description", e.target.value)}
                  placeholder="Describe the issue in detail..."
                />
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "12px",
                }}
              >
                <div>
                  <label style={labelStyle}>
                    Service Type{" "}
                    <span style={{ color: "#dc2626" }}>*</span>
                  </label>

                  <select
                    required
                    style={{
                      ...inputStyle,
                      color: form.service_type
                        ? "#111827"
                        : "#9CA3AF",
                    }}
                    value={form.service_type}
                    onChange={(e) =>
                      upd("service_type", e.target.value)
                    }
                  >
                    <option value="">select service</option>
                    <option value="HVAC Repair">HVAC Repair</option>
                    <option value="Electrical">Electrical</option>
                    <option value="Plumbing">Plumbing</option>
                    <option value="Network Support">
                      Network Support
                    </option>
                    <option value="General Maintenance">
                      General Maintenance
                    </option>
                    <option value="Appliance Repair">
                      Appliance Repair
                    </option>
                    <option value="CCTV & Security">
                      CCTV & Security
                    </option>
                    <option value="Roofing & Carpentry">
                      Roofing & Carpentry
                    </option>
                  </select>
                </div>

                <div>
                  <label style={labelStyle}>
                    Priority <span style={requiredStar}>*</span>
                  </label>

                  <select
                    style={{
                      ...inputStyle,
                      color:
                        form.priority === "select priority"
                          ? "#9CA3AF"
                          : "#111827",
                    }}
                    value={form.priority}
                    onChange={(e) =>
                      upd("priority", e.target.value)
                    }
                  >
                    <option value="select priority">
                      select priority
                    </option>
                    <option value="LOW">LOW</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="HIGH">HIGH</option>
                    <option value="CRITICAL">CRITICAL</option>
                  </select>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "12px",
                }}
              >
                <div>
                  <label style={labelStyle}>
                    Preferred Date{" "}
                    <span style={requiredStar}>*</span>
                  </label>

                  <input
                    type="date"
                    min={getTodayDate()}
                    style={{
                      ...inputStyle,
                      color: form.preferred_visit_date
                        ? "#111827"
                        : "#9CA3AF",
                    }}
                    value={form.preferred_visit_date}
                    onChange={(e) =>
                      upd("preferred_visit_date", e.target.value)
                    }
                  />
                </div>

                <div>
                  <label style={labelStyle}>
                    Contact Number{" "}
                    <span style={requiredStar}>*</span>
                  </label>

                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={10}
                    style={inputStyle}
                    value={form.contact_number}
                    onChange={(e) => {
                      const value = e.target.value.replace(/\D/g, "");
                      upd("contact_number", value);
                    }}
                    placeholder="10 digit mobile number"
                  />
                </div>
              </div>

              <div>
                <label style={labelStyle}>
                  Location / Address{" "}
                  <span style={requiredStar}>*</span>
                </label>

                <input
                  style={inputStyle}
                  value={form.location}
                  onChange={(e) =>
                    upd("location", e.target.value)
                  }
                />
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "10px",
                  justifyContent: "flex-end",
                  marginTop: "8px",
                }}
              >
                <button
                  type="button"
                  onClick={reset}
                  style={{
                    padding: "10px 20px",
                    border: "1px solid #D1D5DB",
                    borderRadius: "8px",
                    background: "#fff",
                    fontSize: "13px",
                    fontWeight: 600,
                    cursor: "pointer",
                    color: "#374151",
                  }}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={saving}
                  style={{
                    padding: "10px 20px",
                    border: "none",
                    borderRadius: "8px",
                    background: "#7AAE8A",
                    color: "#fff",
                    fontSize: "13px",
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    opacity: saving ? 0.7 : 1,
                  }}
                >
                  <Send size={14} />
                  {saving ? "Updating..." : "Update"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}