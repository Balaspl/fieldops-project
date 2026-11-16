import React, { useState, useEffect, useCallback } from "react";
import {
  Mail,
  Phone,
  MapPin,
  Navigation,
  Edit2,
  X,
  CheckCircle,
  AlertCircle,
  Save,
  Compass,
} from "lucide-react";
import {
  getCustomerProfile,
  createCustomerProfile,
  updateCustomerProfile,
  reverseLocation,
} from "../../services/customerPortalService";
import useAuthStore from "../../store/authStore";
import LocationPickerMap from "../../components/customer-tracking/LocationPickerMap";
import { useOptionalToast } from "../../hooks/useToast";

const inputStyle = {
  width: "100%",
  padding: "11px 14px",
  border: "1.5px solid #E2E8F0",
  borderRadius: "10px",
  fontSize: "14px",
  fontFamily: "'Inter', sans-serif",
  color: "#0F172A",
  background: "#FFFFFF",
  outline: "none",
  boxSizing: "border-box" as const,
  transition: "border-color 0.2s, box-shadow 0.2s",
};

const labelStyle = {
  fontSize: "12px",
  fontWeight: 600,
  color: "#475569",
  marginBottom: "6px",
  display: "block" as const,
};

const requiredStarStyle = {
  color: "#DC2626",
  marginLeft: "3px",
};

interface CustomerProfilePageProps {
  onClose?: () => void;
  onNavigate?: (tab: string) => void;
}

export default function CustomerProfilePage({ onClose, onNavigate }: CustomerProfilePageProps = {}) {
  const { user } = useAuthStore();
  const { addToast } = useOptionalToast();

  const [isNew, setIsNew] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [showMapModal, setShowMapModal] = useState(false);
  const [tempCoords, setTempCoords] = useState<{ lat?: number; lng?: number }>({ lat: 13.0827, lng: 80.2707 });
  const [tempAddress, setTempAddress] = useState<string>("");

  const [error, setError] = useState("");

  const [form, setForm] = useState({
    full_name: "",
    mobile_number: "1234567098",
    address: "Tamilnadu",
    city: "Pudukkottai",
    state: "Tamil Nadu",
    pincode: "622309",
  });

  const [editForm, setEditForm] = useState({
    full_name: "",
    mobile_number: "1234567098",
    address: "Tamilnadu",
    city: "Pudukkottai",
    state: "Tamil Nadu",
    pincode: "622309",
  });

  const applyProfileResponse = useCallback(
    (profile: any) => {
      if (profile) {
        setIsNew(!profile.profile_completed);

        const loadedData = {
          full_name:
            profile.full_name ||
            `${user?.first_name || ""} ${user?.last_name || ""}`.trim(),
          mobile_number: profile.mobile_number || "1234567098",
          address: profile.address || "Tamilnadu",
          city: profile.city || "Pudukkottai",
          state: profile.state || "Tamil Nadu",
          pincode: profile.pincode || "622309",
        };

        setForm(loadedData);
        setEditForm(loadedData);
        return;
      }

      setIsNew(true);
      const defaultData = {
        full_name:
          `${user?.first_name || ""} ${user?.last_name || ""}`.trim(),
        mobile_number: "1234567098",
        address: "Tamilnadu",
        city: "Pudukkottai",
        state: "Tamil Nadu",
        pincode: "622309",
      };
      setForm(defaultData);
      setEditForm(defaultData);
    },
    [user],
  );

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await getCustomerProfile();
      applyProfileResponse(response?.data);
    } catch {
      // If error or uninitialized, fallback cleanly
      applyProfileResponse(null);
    } finally {
      setLoading(false);
    }
  }, [applyProfileResponse]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  // Sync edit form when opening modal
  const handleOpenEdit = () => {
    setEditForm({ ...form });
    setError("");
    setIsEditing(true);
  };

  const handleCloseEdit = () => {
    if (saving) return;
    setIsEditing(false);
    setError("");
  };

  const updEdit = (key: string, value: string) => {
    setEditForm((prev) => ({
      ...prev,
      [key]: value,
    }));
    if (error) setError("");
  };

  // Validation
  const validateForm = () => {
    const fullName = editForm.full_name.trim();
    const mobileNumber = editForm.mobile_number.trim();
    const address = editForm.address.trim();
    const city = editForm.city.trim();
    const state = editForm.state.trim();
    const pincode = editForm.pincode.trim();

    const failValidation = (msg: string) => {
      setError(msg);
      addToast({ title: "Profile Validation", message: msg, type: "error" });
      return false;
    };

    if (!fullName) {
      return failValidation("Full name is required");
    }

    if (!mobileNumber) {
      return failValidation("Mobile number is required");
    }

    if (!/^\d{10}$/.test(mobileNumber)) {
      return failValidation("Mobile number must contain exactly 10 digits");
    }

    if (!address) {
      return failValidation("Street address is required");
    }

    if (!city) {
      return failValidation("City / District is required. Use GPS or Pick on a Map.");
    }

    if (!state) {
      return failValidation("State / Region is required. Use GPS or Pick on a Map.");
    }

    if (!pincode) {
      return failValidation("Pincode is required. Use GPS or Pick on a Map.");
    }

    return true;
  };

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (saving) return;

    setError("");

    if (!validateForm()) {
      return;
    }

    setSaving(true);

    try {
      const payload = {
        full_name: editForm.full_name.trim(),
        mobile_number: editForm.mobile_number.trim(),
        address: editForm.address.trim(),
        city: editForm.city.trim(),
        state: editForm.state.trim(),
        pincode: editForm.pincode.trim(),
      };

      let response: any;
      if (isNew) {
        response = await createCustomerProfile(payload);
      } else {
        response = await updateCustomerProfile(payload);
      }

      const updated = response?.data || payload;
      setForm({
        full_name: updated.full_name || payload.full_name,
        mobile_number: updated.mobile_number || payload.mobile_number,
        address: updated.address || payload.address,
        city: updated.city || payload.city,
        state: updated.state || payload.state,
        pincode: updated.pincode || payload.pincode,
      });

      setIsNew(false);

      // Dispatch event to update navbar instantly
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("customer-profile-updated", {
            detail: updated,
          }),
        );
      }

      addToast({
        title: "Profile Updated",
        message: "Profile updated successfully!",
        type: "success",
      });
      setIsEditing(false);
    } catch (requestError: any) {
      const saveErrMsg =
        requestError?.response?.data?.message ||
        requestError?.response?.data?.detail ||
        "We couldn't save your profile. Please try again.";
      setError(saveErrMsg);
      addToast({
        title: "Profile Update Failed",
        message: saveErrMsg,
        type: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  // Reverse geocoding GPS
  const handleUseCurrentLocation = () => {
    if (saving || locating) return;

    if (!navigator.geolocation) {
      setError("Geolocation is not supported by your browser.");
      return;
    }

    setLocating(true);
    setError("");

    const resolveGeoDetails = async (lat: number, lng: number) => {
      let address = "";
      let city = "";
      let state = "";
      let pincode = "";

      try {
        const response = await reverseLocation(lat, lng);
        if (response?.data) {
          address =
            (response.data.verified
              ? response.data.address || response.data.formatted_address || ""
              : response.data.address || response.data.formatted_address || "") || "";
          city = response.data.city || "";
          state = response.data.state || "";
          pincode =
            response.data.pincode || address.match(/\b\d{6}\b/)?.[0] || "";
        }
      } catch {
        // Fallback to OSM Nominatim below
      }

      if (!city || !state || !pincode || !address) {
        try {
          const osmRes = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`
          );
          const osm = await osmRes.json();
          const addrObj = osm?.address || {};
          if (!address && osm?.display_name) address = osm.display_name;
          if (!city) {
            city =
              addrObj.city ||
              addrObj.town ||
              addrObj.village ||
              addrObj.state_district ||
              addrObj.county ||
              "";
          }
          if (!state) state = addrObj.state || "";
          if (!pincode) {
            pincode =
              addrObj.postcode || address.match(/\b\d{6}\b/)?.[0] || "";
          }
        } catch {
          // Ignore network fallback error
        }
      }

      return { address, city, state, pincode };
    };

    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          const resolved = await resolveGeoDetails(
            coords.latitude,
            coords.longitude,
          );

          setEditForm((prev) => ({
            ...prev,
            address: resolved.address || prev.address,
            city: resolved.city || prev.city,
            state: resolved.state || prev.state,
            pincode: resolved.pincode || prev.pincode,
          }));
          addToast({
            title: "Location Acquired",
            message: "Address, district, state, and pincode updated from GPS.",
            type: "success",
          });
        } catch {
          const msg = "Unable to auto-detect location. Please pick on the map.";
          setError(msg);
          addToast({ title: "Location Error", message: msg, type: "error" });
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocating(false);
        const msg = "Location permission denied or timed out.";
        setError(msg);
        addToast({ title: "Location Error", message: msg, type: "error" });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  if (loading) {
    return (
      <div
        style={{
          padding: "32px",
          background: "#F8FAFC",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#94A3B8",
          fontSize: "14px",
        }}
      >
        Loading customer profile...
      </div>
    );
  }

  const initialLetter = form.full_name ? form.full_name.trim()[0].toUpperCase() : "L";

  return (
    <div
      style={{
        padding: "32px 24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
        boxSizing: "border-box",
      }}
    >
      {/* Profile Header with Close button */}
      <div
        style={{
          maxWidth: "1150px",
          margin: "0 auto 20px auto",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <h2 style={{ margin: 0, fontSize: "22px", fontWeight: 700, color: "#0F172A" }}>
            Customer Profile
          </h2>
          <span style={{ fontSize: "13px", color: "#64748B" }}>
            Manage your personal details & location
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <button
            type="button"
            onClick={handleOpenEdit}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 16px",
              background: "#059669",
              border: "1px solid #059669",
              borderRadius: "10px",
              fontSize: "13px",
              fontWeight: 700,
              color: "#FFFFFF",
              cursor: "pointer",
              boxShadow: "0 1px 3px rgba(5, 150, 105, 0.25)",
              transition: "all 0.15s ease",
            }}
          >
            <Edit2 size={15} />
            <span>Edit</span>
          </button>

          <button
            type="button"
            onClick={() => {
              if (onClose) {
                if (window.history.state?.fieldOps?.appNavigation) window.history.back();
                else onClose();
              } else if (onNavigate) {
                onNavigate("cust_create_request");
              } else {
                window.history.back();
              }
            }}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 16px",
              background: "#FFFFFF",
              border: "1px solid #CBD5E1",
              borderRadius: "10px",
              fontSize: "13px",
              fontWeight: 600,
              color: "#475569",
              cursor: "pointer",
              boxShadow: "0 1px 2px rgba(0, 0, 0, 0.05)",
              transition: "all 0.15s ease",
            }}
          >
            <X size={16} />
            <span>Close</span>
          </button>
        </div>
      </div>

      {/* Main 2-Card Layout matching Reference Image 100% */}
      <div
        style={{
          maxWidth: "1150px",
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "330px 1fr",
          gap: "24px",
          alignItems: "start",
        }}
      >
        {/* Left Card: Customer Profile Summary */}
        <div
          style={{
            background: "#FFFFFF",
            borderRadius: "16px",
            padding: "36px 24px",
            border: "1px solid #E2E8F0",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.03)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            textAlign: "center",
          }}
        >
          {/* Large Avatar Circle */}
          <div
            style={{
              width: "92px",
              height: "92px",
              borderRadius: "50%",
              background: "#12847D",
              color: "#FFFFFF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "36px",
              fontWeight: 700,
              marginBottom: "16px",
              boxShadow: "0 4px 10px rgba(18, 132, 125, 0.2)",
            }}
          >
            {initialLetter}
          </div>

          {/* Customer Full Name */}
          <h2
            style={{
              fontSize: "20px",
              fontWeight: 700,
              color: "#0F172A",
              margin: "0 0 6px",
            }}
          >
            {form.full_name || "Customer"}
          </h2>

          {/* Customer Badge */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              padding: "4px 14px",
              borderRadius: "999px",
              background: "#ECFDF5",
              color: "#0E7465",
              border: "1px solid #A7F3D0",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.08em",
              marginBottom: "24px",
            }}
          >
            CUSTOMER
          </div>

          {/* Divider Line */}
          <div
            style={{
              width: "100%",
              height: "1px",
              background: "#F1F5F9",
              marginBottom: "20px",
            }}
          />

          {/* Contact Details List */}
          <div
            style={{
              width: "100%",
              display: "flex",
              flexDirection: "column",
              gap: "14px",
              textAlign: "left",
              marginBottom: "26px",
            }}
          >
            {/* Email */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                color: "#64748B",
                fontSize: "13px",
              }}
            >
              <Mail size={16} color="#64748B" style={{ flexShrink: 0 }} />
              <span
                style={{
                  color: "#334155",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {user?.email || "customer@fieldops.com"}
              </span>
            </div>

            {/* Mobile Number */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                color: "#64748B",
                fontSize: "13px",
              }}
            >
              <Phone size={16} color="#64748B" style={{ flexShrink: 0 }} />
              <span style={{ color: "#334155" }}>
                {form.mobile_number || "1234567098"}
              </span>
            </div>

            {/* City / State Location */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                color: "#64748B",
                fontSize: "13px",
              }}
            >
              <MapPin size={16} color="#64748B" style={{ flexShrink: 0 }} />
              <span style={{ color: "#334155" }}>
                {form.city && form.state
                  ? `${form.city}, ${form.state}`
                  : form.city || form.address || "Pudukkottai, Tamil Nadu"}
              </span>
            </div>
          </div>


        </div>

        {/* Right Card: Service Location Coordinates */}
        <div
          style={{
            background: "#FFFFFF",
            borderRadius: "16px",
            padding: "28px",
            border: "1px solid #E2E8F0",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.03)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Header row */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "24px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Navigation size={18} color="#127471" />
              <span
                style={{
                  fontSize: "13px",
                  fontWeight: 700,
                  color: "#127471",
                  letterSpacing: "0.06em",
                }}
              >
                SERVICE LOCATION COORDINATES
              </span>
            </div>

            <div
              style={{
                background: "#ECFDF5",
                color: "#127471",
                border: "1px solid #A7F3D0",
                borderRadius: "6px",
                padding: "5px 12px",
                fontSize: "12px",
                fontWeight: 700,
                letterSpacing: "0.04em",
              }}
            >
              PIN: {form.pincode || "622309"}
            </div>
          </div>

          {/* Street Address Box */}
          <div style={{ marginBottom: "20px" }}>
            <label
              style={{
                fontSize: "12px",
                fontWeight: 600,
                color: "#94A3B8",
                marginBottom: "6px",
                display: "block",
              }}
            >
              Street Address
            </label>
            <div
              style={{
                background: "#F8FAFC",
                border: "1px solid #E2E8F0",
                borderRadius: "10px",
                padding: "16px 18px",
                color: "#0F172A",
                fontSize: "15px",
                fontWeight: 600,
              }}
            >
              {form.address || "Tamilnadu"}
            </div>
          </div>

          {/* City / State 2-Column Row */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "18px",
            }}
          >
            <div>
              <label
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#94A3B8",
                  marginBottom: "6px",
                  display: "block",
                }}
              >
                City / District
              </label>
              <div
                style={{
                  background: "#F8FAFC",
                  border: "1px solid #E2E8F0",
                  borderRadius: "10px",
                  padding: "16px 18px",
                  color: "#0F172A",
                  fontSize: "15px",
                  fontWeight: 600,
                }}
              >
                {form.city || "Pudukkottai"}
              </div>
            </div>

            <div>
              <label
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#94A3B8",
                  marginBottom: "6px",
                  display: "block",
                }}
              >
                State / Region
              </label>
              <div
                style={{
                  background: "#F8FAFC",
                  border: "1px solid #E2E8F0",
                  borderRadius: "10px",
                  padding: "16px 18px",
                  color: "#0F172A",
                  fontSize: "15px",
                  fontWeight: 600,
                }}
              >
                {form.state || "Tamil Nadu"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Location Picker Map Modal for Customer Profile */}
      {showMapModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(15, 23, 42, 0.65)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
            zIndex: 1300,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowMapModal(false);
          }}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "20px",
              width: "100%",
              maxWidth: "620px",
              overflow: "hidden",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            }}
          >
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid #E2E8F0",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <MapPin size={20} color="#059669" />
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 800, color: "#0F172A" }}>
                  Pick Service Location on Map
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowMapModal(false)}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#64748B" }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ padding: "16px" }}>
              <LocationPickerMap
                latitude={tempCoords.lat ?? 13.0827}
                longitude={tempCoords.lng ?? 80.2707}
                onChange={(lat, lng, address) => {
                  setTempCoords({ lat, lng });
                  if (address) {
                    setTempAddress(address);
                  } else {
                    reverseLocation(lat, lng)
                      .then((res) => {
                        if (res?.data?.address) setTempAddress(res.data.address);
                      })
                      .catch(() => {});
                  }
                }}
              />

              {tempAddress && (
                <div
                  style={{
                    marginTop: "12px",
                    padding: "10px 14px",
                    background: "#F8FAFC",
                    border: "1px solid #E2E8F0",
                    borderRadius: "10px",
                    fontSize: "12.5px",
                    color: "#334155",
                    fontWeight: 600,
                  }}
                >
                  📍 {tempAddress}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "16px" }}>
                <button
                  type="button"
                  onClick={() => setShowMapModal(false)}
                  style={{
                    padding: "9px 18px",
                    borderRadius: "10px",
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
                  onClick={async () => {
                    if (tempCoords.lat && tempCoords.lng) {
                      let addr = tempAddress || "";
                      let city = "";
                      let state = "";
                      let pincode = addr.match(/\b\d{6}\b/)?.[0] || "";
                      try {
                        const res = await reverseLocation(tempCoords.lat, tempCoords.lng);
                        addr = addr || res?.data?.address || res?.data?.formatted_address || "";
                        city = res?.data?.city || "";
                        state = res?.data?.state || "";
                        pincode = res?.data?.pincode || addr.match(/\b\d{6}\b/)?.[0] || pincode;
                      } catch {
                        // Fallback below
                      }
                      if (!city || !state || !pincode) {
                        try {
                          const osmRes = await fetch(
                            `https://nominatim.openstreetmap.org/reverse?format=json&lat=${tempCoords.lat}&lon=${tempCoords.lng}&zoom=18&addressdetails=1`
                          );
                          const osm = await osmRes.json();
                          const addrObj = osm?.address || {};
                          if (!addr && osm?.display_name) addr = osm.display_name;
                          if (!city) {
                            city =
                              addrObj.city ||
                              addrObj.town ||
                              addrObj.village ||
                              addrObj.state_district ||
                              addrObj.county ||
                              "";
                          }
                          if (!state) state = addrObj.state || "";
                          if (!pincode) {
                            pincode =
                              addrObj.postcode || addr.match(/\b\d{6}\b/)?.[0] || "";
                          }
                        } catch {
                          // Ignore fallback error
                        }
                      }
                      setEditForm((prev) => ({
                        ...prev,
                        address: addr || prev.address,
                        city: city || prev.city,
                        state: state || prev.state,
                        pincode: pincode || prev.pincode,
                      }));
                      addToast({
                        title: "Location Selected",
                        message: "Address, district, state, and pincode updated from map.",
                        type: "success",
                      });
                    }
                    setShowMapModal(false);
                  }}
                  style={{
                    padding: "9px 20px",
                    borderRadius: "10px",
                    border: "none",
                    background: "#059669",
                    color: "#FFFFFF",
                    fontSize: "13px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  Confirm Location
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Profile Modal Dialog */}
      {isEditing && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.45)",
            backdropFilter: "blur(3px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "16px",
            boxSizing: "border-box",
          }}
          onClick={handleCloseEdit}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "16px",
              width: "100%",
              maxWidth: "560px",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
              border: "1px solid #E2E8F0",
              display: "flex",
              flexDirection: "column",
              maxHeight: "90vh",
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "20px 24px",
                borderBottom: "1px solid #F1F5F9",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <Edit2 size={20} color="#127471" />
                <h3
                  style={{
                    fontSize: "17px",
                    fontWeight: 700,
                    color: "#0F172A",
                    margin: 0,
                  }}
                >
                  Edit Profile Information
                </h3>
              </div>

              <button
                type="button"
                onClick={handleCloseEdit}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "#94A3B8",
                  padding: "4px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRadius: "6px",
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Body */}
            <form
              onSubmit={handleSave}
              style={{
                padding: "24px",
                overflowY: "auto",
                display: "flex",
                flexDirection: "column",
                gap: "16px",
              }}
            >
              {/* Error Message */}
              {error && (
                <div
                  style={{
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    color: "#991B1B",
                    fontSize: "13px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <AlertCircle size={16} />
                  <span>{error}</span>
                </div>
              )}

              {/* Full Name */}
              <div>
                <label style={labelStyle}>
                  Full Name
                  <span style={requiredStarStyle}>*</span>
                </label>
                <input
                  type="text"
                  style={inputStyle}
                  value={editForm.full_name}
                  onChange={(e) => updEdit("full_name", e.target.value)}
                  placeholder="Enter your name"
                  disabled={saving}
                />
              </div>

              {/* Mobile Number */}
              <div>
                <label style={labelStyle}>
                  Mobile Number (10 digits)
                  <span style={requiredStarStyle}>*</span>
                </label>
                <input
                  type="tel"
                  style={inputStyle}
                  value={editForm.mobile_number}
                  onChange={(e) =>
                    updEdit(
                      "mobile_number",
                      e.target.value.replace(/\D/g, "").slice(0, 10),
                    )
                  }
                  placeholder="e.g. 1234567098"
                  maxLength={10}
                  disabled={saving}
                />
              </div>

              {/* Street Address */}
              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "6px",
                  }}
                >
                  <label style={{ ...labelStyle, marginBottom: 0 }}>
                    Street Address
                    <span style={requiredStarStyle}>*</span>
                  </label>

                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <button
                      type="button"
                      onClick={handleUseCurrentLocation}
                      disabled={locating || saving}
                      style={{
                        background: "#ECFDF5",
                        border: "1px solid #A7F3D0",
                        color: "#059669",
                        fontSize: "11px",
                        fontWeight: 700,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: "3px 8px",
                        borderRadius: "6px",
                      }}
                    >
                      <Compass size={12} color="#059669" />
                      {locating ? "Detecting..." : "Choose Current Location"}
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowMapModal(true)}
                      disabled={saving}
                      style={{
                        background: "#EFF6FF",
                        border: "1px solid #BFDBFE",
                        color: "#2563EB",
                        fontSize: "11px",
                        fontWeight: 700,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: "3px 8px",
                        borderRadius: "6px",
                      }}
                    >
                      <MapPin size={12} color="#2563EB" />
                      Pick on a Map
                    </button>
                  </div>
                </div>
                <input
                  type="text"
                  style={inputStyle}
                  value={editForm.address}
                  onChange={(e) => updEdit("address", e.target.value)}
                  placeholder="e.g. Tamilnadu or 12, Main Street"
                  disabled={saving}
                />
              </div>

              {/* City and State Row (Auto-filled from GPS / Map Picker, not manually editable) */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "14px",
                }}
              >
                <div>
                  <label style={labelStyle}>
                    City / District
                    <span style={requiredStarStyle}>*</span>
                  </label>
                  <input
                    type="text"
                    readOnly
                    title="Auto-filled from Choose Current Location or Pick on a Map"
                    style={{
                      ...inputStyle,
                      background: "#F8FAFC",
                      color: "#475569",
                      cursor: "not-allowed",
                    }}
                    value={editForm.city}
                    placeholder="Auto-filled from location"
                  />
                </div>

                <div>
                  <label style={labelStyle}>
                    State / Region
                    <span style={requiredStarStyle}>*</span>
                  </label>
                  <input
                    type="text"
                    readOnly
                    title="Auto-filled from Choose Current Location or Pick on a Map"
                    style={{
                      ...inputStyle,
                      background: "#F8FAFC",
                      color: "#475569",
                      cursor: "not-allowed",
                    }}
                    value={editForm.state}
                    placeholder="Auto-filled from location"
                  />
                </div>
              </div>

              {/* Pincode (Auto-filled from GPS / Map Picker, not manually editable) */}
              <div>
                <label style={labelStyle}>
                  Pincode
                  <span style={requiredStarStyle}>*</span>
                </label>
                <input
                  type="text"
                  readOnly
                  title="Auto-filled from Choose Current Location or Pick on a Map"
                  style={{
                    ...inputStyle,
                    background: "#F8FAFC",
                    color: "#475569",
                    cursor: "not-allowed",
                  }}
                  value={editForm.pincode}
                  placeholder="Auto-filled from location"
                  maxLength={6}
                />
                <div style={{ fontSize: "11px", color: "#64748B", marginTop: "4px" }}>
                  City / District, State, and Pincode update automatically when you use Choose Current Location or Pick on a Map.
                </div>
              </div>

              {/* Modal Footer Buttons */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "flex-end",
                  gap: "12px",
                  marginTop: "12px",
                  paddingTop: "16px",
                  borderTop: "1px solid #F1F5F9",
                }}
              >
                <button
                  type="button"
                  onClick={handleCloseEdit}
                  disabled={saving}
                  style={{
                    padding: "10px 18px",
                    borderRadius: "8px",
                    background: "#F1F5F9",
                    color: "#475569",
                    border: "none",
                    fontSize: "14px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={saving}
                  style={{
                    padding: "10px 22px",
                    borderRadius: "8px",
                    background: "#127471",
                    color: "#FFFFFF",
                    border: "none",
                    fontSize: "14px",
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    boxShadow: "0 1px 3px rgba(18, 116, 113, 0.2)",
                  }}
                >
                  <Save size={16} />
                  {saving ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
