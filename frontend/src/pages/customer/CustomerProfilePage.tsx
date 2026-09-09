import { useState, useEffect } from "react";
import { User, Save, AlertCircle, CheckCircle } from "lucide-react";
import {
  getCustomerProfile,
  createCustomerProfile,
  updateCustomerProfile,
} from "../../services/customerPortalService";
import useAuthStore from "../../store/authStore";

const inputStyle = {
  width: "100%",
  padding: "10px 12px",
  border: "1.5px solid #D1D5DB",
  borderRadius: "8px",
  fontSize: "14px",
  fontFamily: "'Inter', sans-serif",
  outline: "none",
  boxSizing: "border-box" as const,
};

const labelStyle = {
  fontSize: "12px",
  fontWeight: 600,
  color: "#374151",
  marginBottom: "4px",
  display: "block" as const,
};

const requiredStarStyle = {
  color: "#DC2626",
  marginLeft: "3px",
};

export default function CustomerProfilePage() {
  const { user } = useAuthStore();

  const [isNew, setIsNew] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    full_name: "",
    mobile_number: "",
    address: "",
    city: "",
    state: "",
    pincode: "",
    company_name: "",
  });

  useEffect(() => {
    getCustomerProfile()
      .then((r) => {
        const p = r.data;

        if (p.profile_completed) {
          setIsNew(false);

          setForm({
            full_name: p.full_name || "",
            mobile_number: p.mobile_number || "",
            address: p.address || "",
            city: p.city || "",
            state: p.state || "",
            pincode: p.pincode || "",
            company_name: p.company_name || "",
          });
        } else {
          setForm((f) => ({
            ...f,
            full_name: user
              ? `${user.first_name} ${user.last_name}`.trim()
              : "",
          }));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user]);

  // -----------------------------------------
  // VALIDATION
  // -----------------------------------------
  const validateForm = () => {
    const fullName = form.full_name.trim();
    const mobileNumber = form.mobile_number.trim();
    const email = (user?.email || "").trim();
    const address = form.address.trim();
    const city = form.city.trim();
    const state = form.state.trim();
    const pincode = form.pincode.trim();

    // Full Name - required
    if (!fullName) {
      setError("Full name is required");
      return false;
    }

    // Full Name - letters and spaces only
    if (!/^[A-Za-z ]+$/.test(fullName)) {
      setError("Full name must contain letters and spaces only");
      return false;
    }

    // Mobile Number - required
    if (!mobileNumber) {
      setError("Mobile number is required");
      return false;
    }

    // Mobile Number - exactly 10 digits
    if (!/^\d{10}$/.test(mobileNumber)) {
      setError("Mobile number must contain exactly 10 digits");
      return false;
    }

    // Email - required
    if (!email) {
      setError("Email is required");
      return false;
    }

    // Email - only fieldops.com or gmail.com
    if (!/^[^\s@]+@(fieldops\.com|gmail\.com)$/i.test(email)) {
      setError("Email must be a valid @fieldops.com or @gmail.com address");
      return false;
    }

    // Address - required
    if (!address) {
      setError("Address is required");
      return false;
    }

    // City - required
    if (!city) {
      setError("City is required");
      return false;
    }

    // State - required
    if (!state) {
      setError("State is required");
      return false;
    }

    // Pincode - required
    if (!pincode) {
      setError("Pincode is required");
      return false;
    }

    // Pincode - exactly 6 digits
    if (!/^\d{6}$/.test(pincode)) {
      setError("Pincode must contain exactly 6 digits");
      return false;
    }

    return true;
  };

  // -----------------------------------------
  // SAVE / CREATE / UPDATE
  // -----------------------------------------
  const handleSave = async () => {
    setError("");
    setSuccess("");

    // Run all validations first
    if (!validateForm()) {
      return;
    }

    setSaving(true);

    try {
      if (isNew) {
        await createCustomerProfile(form);

        // Once profile is created,
        // user stays in Edit Profile mode
        setIsNew(false);

        setSuccess("Profile created successfully!");
      } else {
        await updateCustomerProfile(form);

        setSuccess("Profile updated successfully!");
      }
    } catch (e: any) {
      setError(
        e.response?.data?.detail ||
          e.response?.data?.message ||
          "Failed to save profile",
      );
    } finally {
      setSaving(false);
    }
  };

  // -----------------------------------------
  // INPUT UPDATE
  // -----------------------------------------
  const upd = (key: string, value: string) => {
    setForm((f) => ({
      ...f,
      [key]: value,
    }));

    // Clear old error while user starts correcting
    if (error) {
      setError("");
    }

    if (success) {
      setSuccess("");
    }
  };

  // -----------------------------------------
  // LOADING
  // -----------------------------------------
  if (loading) {
    return (
      <div
        style={{
          padding: "24px",
          background: "#EEF4F1",
          height: "100%",
          textAlign: "center",
          paddingTop: "80px",
          color: "#9CA3AF",
        }}
      >
        Loading...
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
      <div
        style={{
          background: "#fff",
          borderRadius: "14px",
          padding: "45px 20px 20px",
          maxWidth: "1100px",
          margin: "40px auto 0",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
          border: "1px solid #E3ECE7",
        }}
      >
        {/* Header */}
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#1F2933",
            margin: "0 0 4px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <User size={22} color="#7AAE8A" />

          {isNew ? "Complete Your Profile" : "Edit Profile"}
        </h2>

        <p
          style={{
            fontSize: "13px",
            color: "#6B7280",
            marginBottom: "24px",
          }}
        >
          {isNew
            ? "Fill in your details to get started"
            : "Update your information"}
        </p>

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
              marginBottom: "16px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {/* Success Message */}
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

        {/* Fields */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "16px",
          }}
        >
          {/* Full Name */}
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>
              Full Name
              <span style={requiredStarStyle}>*</span>
            </label>

            <input
              type="text"
              style={inputStyle}
              value={form.full_name}
              onChange={(e) => upd("full_name", e.target.value)}
              placeholder="Enter your full name"
            />
          </div>

          {/* Mobile Number */}
          <div>
            <label style={labelStyle}>
              Mobile Number
              <span style={requiredStarStyle}>*</span>
            </label>

            <input
              type="text"
              inputMode="numeric"
              style={inputStyle}
              value={form.mobile_number}
              onChange={(e) => {
                const value = e.target.value.replace(/\D/g, "").slice(0, 10);
                upd("mobile_number", value);
              }}
              maxLength={10}
              placeholder="10 digit mobile number"
            />
          </div>

          {/* Email */}
          <div>
            <label style={labelStyle}>
              Email
              <span style={requiredStarStyle}>*</span>
            </label>

            <input
              type="email"
              style={{
                ...inputStyle,
                background: "#F3F4F6",
              }}
              value={user?.email || ""}
              disabled
            />
          </div>

          {/* Address */}
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>
              Address
              <span style={requiredStarStyle}>*</span>
            </label>

            <textarea
              style={{
                ...inputStyle,
                minHeight: "80px",
                resize: "vertical",
              }}
              value={form.address}
              onChange={(e) => upd("address", e.target.value)}
              placeholder="Enter your address"
            />
          </div>

          {/* City */}
          <div>
            <label style={labelStyle}>
              City
              <span style={requiredStarStyle}>*</span>
            </label>

            <input
              type="text"
              style={inputStyle}
              value={form.city}
              onChange={(e) => upd("city", e.target.value)}
              placeholder="Enter your city"
            />
          </div>

          {/* State */}
          <div>
            <label style={labelStyle}>
              State
              <span style={requiredStarStyle}>*</span>
            </label>

            <input
              type="text"
              style={inputStyle}
              value={form.state}
              onChange={(e) => upd("state", e.target.value)}
              placeholder="Enter your state"
            />
          </div>

          {/* Pincode */}
          <div>
            <label style={labelStyle}>
              Pincode
              <span style={requiredStarStyle}>*</span>
            </label>

            <input
              type="text"
              inputMode="numeric"
              style={inputStyle}
              value={form.pincode}
              onChange={(e) => {
                const value = e.target.value.replace(/\D/g, "").slice(0, 6);
                upd("pincode", value);
              }}
              maxLength={6}
              placeholder="6 digit pincode"
            />
          </div>

          {/* Company - OPTIONAL */}
          <div>
            <label style={labelStyle}>Company (optional)</label>

            <input
              type="text"
              style={inputStyle}
              value={form.company_name}
              onChange={(e) => upd("company_name", e.target.value)}
              placeholder="Enter company name"
            />
          </div>
        </div>

        {/* Save Button */}
        <div
          style={{
            marginTop: "24px",
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: "12px 28px",
              border: "none",
              borderRadius: "10px",
              fontSize: "14px",
              fontWeight: 700,
              cursor: saving ? "not-allowed" : "pointer",
              background: "#7AAE8A",
              color: "#fff",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              opacity: saving ? 0.7 : 1,
            }}
          >
            <Save size={16} />

            {saving ? "Saving..." : isNew ? "Complete Profile" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
