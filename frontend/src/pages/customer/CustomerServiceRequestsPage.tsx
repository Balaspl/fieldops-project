import { useState, useEffect, useRef } from "react";
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
import { OlaMaps } from "olamaps-web-sdk";

const OLA_STYLE = "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

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
  const [locationSearch, setLocationSearch] = useState("");
  const [locationResults, setLocationResults] = useState<any[]>([]);
  const [isSearchingLocations, setIsSearchingLocations] = useState(false);
  const [locationSearchError, setLocationSearchError] = useState("");
  const [selectedLocationName, setSelectedLocationName] = useState("");
  const [locationConfirmed, setLocationConfirmed] = useState(false);
  const [mapVisible, setMapVisible] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [mapTarget, setMapTarget] = useState<{ latitude: number; longitude: number } | null>(null);
  const [isResolvingMapCenter, setIsResolvingMapCenter] = useState(false);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const olaMapRef = useRef<any>(null);
  const programmaticMapMove = useRef(false);
  const reverseGeocodeSequence = useRef(0);
  const mapRequestId = useRef(0);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    const query = locationSearch.trim();
    if (query.length < 2) {
      setLocationResults([]);
      setIsSearchingLocations(false);
      setLocationSearchError("");
      return;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      const requestId = ++mapRequestId.current;
      setIsSearchingLocations(true);
      setLocationSearchError("");
      try {
        const response = await api.get("/organizations/location-search", { params: { q: query } });
        if (active && requestId === mapRequestId.current) setLocationResults(response.data?.results || []);
      } catch {
        if (active && requestId === mapRequestId.current) {
          setLocationResults([]);
          setLocationSearchError("Unable to search locations. Try again.");
        }
      } finally {
        if (active && requestId === mapRequestId.current) setIsSearchingLocations(false);
      }
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [locationSearch]);

  useEffect(() => {
    if (!mapVisible || siteLatitude == null || siteLongitude == null || !mapContainerRef.current) return;
    let cancelled = false;
    const apiKey = import.meta.env.VITE_OLA_MAPS_API_KEY;
    if (!apiKey) { setMapError(true); return; }
    try {
      const ola = new OlaMaps({ apiKey });
      void ola.init({ style: OLA_STYLE, container: mapContainerRef.current, center: [siteLongitude, siteLatitude], zoom: 16 })
        .then((map: any) => {
          if (cancelled) { map.remove?.(); return; }
          olaMapRef.current?.remove?.();
          olaMapRef.current = map;
          map.dragPan?.enable?.();
          map.scrollZoom?.enable?.();
          map.doubleClickZoom?.enable?.();
          const onMoveEnd = () => {
            const center = map.getCenter?.();
            if (!center || !Number.isFinite(center.lat) || !Number.isFinite(center.lng)) return;
            setSiteLatitude(center.lat);
            setSiteLongitude(center.lng);
            if (programmaticMapMove.current) {
              programmaticMapMove.current = false;
              return;
            }
            void resolveMapCenter(center.lat, center.lng);
          };
          map.on("moveend", onMoveEnd);
          map.__customerLocationMoveEnd = onMoveEnd;
          setMapError(false);
        })
        .catch(() => { if (!cancelled) setMapError(true); });
    } catch { setMapError(true); }
    return () => {
      cancelled = true;
      if (olaMapRef.current?.__customerLocationMoveEnd) {
        olaMapRef.current.off?.("moveend", olaMapRef.current.__customerLocationMoveEnd);
      }
      olaMapRef.current?.remove?.();
      olaMapRef.current = null;
    };
  }, [mapVisible]);

  useEffect(() => {
    const map = olaMapRef.current;
    if (!map || !mapTarget) return;
    const center = map.getCenter?.();
    const changed = !center || Math.abs(center.lat - mapTarget.latitude) > 0.000001 || Math.abs(center.lng - mapTarget.longitude) > 0.000001;
    if (changed) {
      programmaticMapMove.current = true;
      map.easeTo({ center: [mapTarget.longitude, mapTarget.latitude], duration: 350 });
    }
  }, [mapTarget]);

  const resolveMapCenter = async (
  latitude: number,
  longitude: number,
): Promise<boolean> => {
  const requestId =
    ++reverseGeocodeSequence.current;

  setIsResolvingMapCenter(true);
  setLocationSearchError("Finding address...");

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
      requestId !==
      reverseGeocodeSequence.current
    ) {
      return false;
    }

    if (
      response.data?.verified &&
      response.data?.address
    ) {
      const address =
        response.data.formatted_address ||
        response.data.address;

      // Save exact coordinates
      setSiteLatitude(latitude);
      setSiteLongitude(longitude);

      // Save location name
      setSelectedLocationName(
        response.data.name || "",
      );

      // Save address into form
      upd("location", address);

      // IMPORTANT:
      // The location has now been selected
      // and successfully resolved.
      setLocationConfirmed(true);

      setLocationSearchError("");

      return true;
    }

    setLocationConfirmed(false);

    setLocationSearchError(
      "Unable to determine an address for this location.",
    );

    return false;
  } catch (error) {
    if (
      requestId ===
      reverseGeocodeSequence.current
    ) {
      setLocationConfirmed(false);

      setLocationSearchError(
        "Unable to determine an address for this location.",
      );
    }

    return false;
  } finally {
    if (
      requestId ===
      reverseGeocodeSequence.current
    ) {
      setIsResolvingMapCenter(false);
    }
  }
};

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
    setSiteLatitude(null);
    setSiteLongitude(null);
    setLocationSearch("");
    setLocationResults([]);
    setSelectedLocationName("");
    setLocationConfirmed(false);
    setMapVisible(false);
    setMapTarget(null);
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

    setSiteLatitude(null);
    setSiteLongitude(null);
    setLocationSearch("");
    setLocationResults([]);
    setSelectedLocationName("");
    setLocationConfirmed(false);
    setMapVisible(false);
    setMapTarget(null);
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
    if (!locationConfirmed || siteLatitude == null || siteLongitude == null) {
      setError("Please select a location and click 'Use This Location' before creating the job.");
      return;
    }

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
    setLocationConfirmed(Boolean(sr.site_latitude != null && sr.site_longitude != null));
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

                <button
                  type="button"
                  disabled={isGettingLocation}
                  onClick={() => {
                    if (!navigator.geolocation) {
                      setLocationSearchError(
                        "This browser does not support location access.",
                      );
                      return;
                    }

                    setLocationSearchError("");
                    setIsGettingLocation(true);
                    setSelectedLocationName("");
                    setLocationSearch("");
                    setLocationResults([]);

                    let watchId: number | null = null;
                    let timeoutId: number | null = null;
                    let finished = false;
                    let bestAccuracy = Infinity;

                    const finish = () => {
                      if (finished) {
                        return;
                      }

                      finished = true;

                      if (watchId !== null) {
                        navigator.geolocation.clearWatch(watchId);
                      }

                      if (timeoutId !== null) {
                        window.clearTimeout(timeoutId);
                      }

                      setIsGettingLocation(false);
                    };

                    watchId = navigator.geolocation.watchPosition(
                      (position) => {
                        if (finished) {
                          return;
                        }

                        const {
                          latitude,
                          longitude,
                          accuracy,
                        } = position.coords;

                        console.log(
                          "[CURRENT LOCATION] GPS fix:",
                          {
                            latitude,
                            longitude,
                            accuracy,
                          },
                        );

                        if (
                          !Number.isFinite(latitude) ||
                          !Number.isFinite(longitude) ||
                          !Number.isFinite(accuracy)
                        ) {
                          return;
                        }

                        if (accuracy < bestAccuracy) {
                          bestAccuracy = accuracy;
                        }

                        // Do not accept a poor first GPS fix.
                        // Wait for a fresh fix at 100m accuracy or better.
                        if (accuracy > 120) {
                          setLocationSearchError(
                            `Getting a more accurate location... current accuracy ${Math.round(
                              accuracy,
                            )}m`,
                          );
                          return;
                        }

                        console.log(
                          "[CURRENT LOCATION] Accurate GPS accepted:",
                          {
                            latitude,
                            longitude,
                            accuracy,
                          },
                        );

                        setSiteLatitude(latitude);
                        setSiteLongitude(longitude);
                        setMapTarget({ latitude, longitude });
                        setMapVisible(true);
                        setLocationSearchError("");

                        finish();

                        void resolveMapCenter(
                          latitude,
                          longitude,
                        );
                      },
                      (geoError) => {
                        if (finished) {
                          return;
                        }

                        console.error(
                          "[CURRENT LOCATION] GPS error:",
                          geoError,
                        );

                        const messages: Record<number, string> = {
                          1: "Location permission was denied. Allow access and try again.",
                          2: "Your location is unavailable. Please try again.",
                          3: "Location request timed out. Please try again.",
                        };

                        setLocationSearchError(
                          messages[geoError.code] ||
                            "Unable to get your location.",
                        );

                        finish();
                      },
                      {
                        enableHighAccuracy: true,
                        maximumAge: 0,
                        timeout: 30000,
                      },
                    );

                    // Safety timeout. If no accurate fix is available,
                    // do not use a bad location.
                    timeoutId = window.setTimeout(() => {
                      if (finished) {
                        return;
                      }

                      const accuracyMessage =
                        bestAccuracy !== Infinity
                          ? `GPS accuracy is still ${Math.round(
                              bestAccuracy,
                            )}m. Please try again in an open area.`
                          : "Unable to get your current location. Please try again.";

                      setLocationSearchError(accuracyMessage);
                      finish();
                    }, 30000);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "#5C9470",
                    cursor: "pointer",
                    border: 0,
                    background: "transparent",
                    padding: 0,
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
                      <span>Getting your location...</span>
                    </>
                  ) : (
                    <>
                      <MapPin size={14} />
                      <span>Use current location</span>
                    </>
                  )}
                </button>
              </div>

              <input
                style={inputStyle}
                value={locationSearch}
                onChange={(e) => {
                  setLocationSearch(e.target.value);
                  setLocationResults([]);
                }}
                placeholder="Search building, street or area"
              />
              {isSearchingLocations && <div style={{ fontSize: 12, color: "#64748B", padding: "8px 2px" }}>Searching...</div>}
              {locationSearchError && <div style={{ fontSize: 12, color: "#B45309", padding: "8px 2px" }}>{locationSearchError}</div>}
              {!isSearchingLocations && locationSearch.trim().length >= 2 && !locationSearchError && locationResults.length === 0 && <div style={{ fontSize: 12, color: "#64748B", padding: "8px 2px" }}>No locations found</div>}
              {locationResults.length > 0 && <div style={{ border: "1px solid #D1D5DB", borderRadius: 8, marginTop: 4, overflow: "hidden" }}>
                {locationResults.map((result, index) => <button key={result.place_id || `${result.latitude}-${result.longitude}-${index}`} type="button" onClick={() => {
                  setSiteLatitude(Number(result.latitude)); setSiteLongitude(Number(result.longitude));
                  setMapTarget({ latitude: Number(result.latitude), longitude: Number(result.longitude) });
                  setSelectedLocationName(result.name || ""); upd("location", result.formatted_address || result.name || "");
                  setLocationSearch(""); setLocationResults([]); setMapVisible(true); setLocationSearchError("");
                }} style={{ display: "block", width: "100%", textAlign: "left", border: 0, borderBottom: "1px solid #E5E7EB", background: "#fff", padding: "10px 12px", cursor: "pointer" }}>
                  <strong style={{ display: "block", color: "#1F2933", fontSize: 13 }}>{result.name || result.formatted_address}</strong>
                  <span style={{ color: "#64748B", fontSize: 12 }}>{result.formatted_address}</span>
                </button>)}
              </div>}
              {form.location && <div style={{ marginTop: 10, padding: 10, background: "#F8FAFC", borderRadius: 8, fontSize: 13 }}>
                {selectedLocationName && <strong style={{ display: "block", marginBottom: 3 }}>{selectedLocationName}</strong>}
                <span>{form.location}</span>
              </div>}
              {mapVisible && <div style={{ marginTop: 12 }}>
                {mapError ? <div style={{ padding: 10, background: "#FEF3C7", color: "#92400E", borderRadius: 8, fontSize: 12 }}>Map could not be loaded, but your location was selected.</div> : <>
                  <div style={{ position: "relative", height: 300, borderRadius: 10, overflow: "hidden", background: "#F1F5F9" }}>
                    <div ref={mapContainerRef} style={{ width: "100%", height: "100%", touchAction: "pan-x pan-y" }} />
                    <div aria-hidden="true" style={{ position: "absolute", zIndex: 2, left: "50%", top: "50%", transform: "translate(-50%, -100%)", pointerEvents: "none", color: "#DC2626", filter: "drop-shadow(0 2px 2px rgba(0,0,0,.35))" }}>
                      <MapPin size={34} fill="#DC2626" stroke="white" strokeWidth={1.5} />
                    </div>
                  </div>
                  <button type="button" onClick={() => {
                    const center = olaMapRef.current?.getCenter?.();
                    if (!center) return;
                    setSiteLatitude(center.lat);
                    setSiteLongitude(center.lng);
                    void resolveMapCenter(center.lat, center.lng);
                  }} disabled={isResolvingMapCenter} style={{ marginTop: 10, padding: "9px 14px", border: 0, borderRadius: 8, background: "#5C9470", color: "white", fontSize: 13, fontWeight: 700, cursor: isResolvingMapCenter ? "wait" : "pointer", opacity: isResolvingMapCenter ? 0.7 : 1 }}>
                    {isResolvingMapCenter ? "Finding address..." : "Use This Location"}
                  </button>
                </>}
              </div>}
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
              {["CREATED", "UNASSIGNED", "ASSIGNED", "AWAITING ACCEPTANCE", "ACCEPTED"].includes(
                String(sr.status || "").toUpperCase().trim()
              ) && (
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
