import { useState, useEffect, useRef } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  User,
  Key,
  Save,
  AlertCircle,
  CheckCircle,
  Shield,
  Briefcase,
  MapPin,
} from "lucide-react";
import {
  getTechnicianProfile,
  createTechnicianProfile,
  updateTechnicianProfile,
  changeTechnicianPassword,
} from "../../services/technicianPortalService";
import useAuthStore from "../../store/authStore";
import api from "../../services/api";
import { SkillComboSelect } from "../../components/ui/SkillComboSelect";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;

          renderButton: (
            parent: HTMLElement,
            options: {
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "large" | "medium" | "small";
              text?:
                | "signin_with"
                | "signup_with"
                | "continue_with"
                | "signin";
              shape?: "rectangular" | "pill" | "circle" | "square";
              width?: number;
            }
          ) => void;
        };
      };
    };
  }
}

export default function TechnicianSettingsPage() {
  const { user } = useAuthStore();

  const [activeTab, setActiveTab] = useState<"profile" | "security">(
    "profile"
  );

  // =========================================================
  // PROFILE STATE
  // =========================================================

  const [isNewProfile, setIsNewProfile] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");

  const [profileForm, setProfileForm] = useState({
    full_name: "",
    mobile_number: "",
    date_of_birth: "",
    gender: "",
    address: "",
    city: "",
    state: "",
    pincode: "",
    emergency_contact: "",
    skills: "",
    experience: "",
    certifications: "",
    profile_photo: "",
  });

  const [age, setAge] = useState<number | null>(null);

  // =========================================================
  // PASSWORD STATE
  // =========================================================

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");

  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState("");
  const [pwSuccess, setPwSuccess] = useState("");

  const [mfaLoading, setMfaLoading] = useState(false);
const [mfaError, setMfaError] = useState("");
const [mfaSuccess, setMfaSuccess] = useState("");

const [mfaEnrolled, setMfaEnrolled] = useState(false);
const [mfaEnabled, setMfaEnabled] = useState(false);

const [mfaSecret, setMfaSecret] = useState("");
const [mfaProvisioningUri, setMfaProvisioningUri] = useState("");

const [mfaCode, setMfaCode] = useState("");
const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);

const [showMfaSetup, setShowMfaSetup] = useState(false);

  // =========================================================
  // GOOGLE OIDC STATE
  // =========================================================

  const googleButtonRef = useRef<HTMLDivElement | null>(null);

  const [linkingGoogle, setLinkingGoogle] = useState(false);
  const [googleSuccess, setGoogleSuccess] = useState("");
  const [googleError, setGoogleError] = useState("");

  // =========================================================
  // LOAD TECHNICIAN PROFILE
  // =========================================================

  useEffect(() => {
    getTechnicianProfile()
      .then((res) => {
        const p = res.data;

        if (p.profile_completed) {
          setIsNewProfile(false);

          setProfileForm({
            full_name: p.full_name || "",
            mobile_number: p.mobile_number || "",
            date_of_birth: p.date_of_birth || "",
            gender: p.gender || "",
            address: p.address || "",
            city: p.city || "",
            state: p.state || "",
            pincode: p.pincode || "",
            emergency_contact: p.emergency_contact || "",
            skills: (p.skills || []).join(", "),
            experience: p.experience || "",
            certifications: (p.certifications || []).join(", "),
            profile_photo: p.profile_photo || "",
          });

          if (p.age) {
            setAge(p.age);
          }
        } else {
          setProfileForm((f) => ({
            ...f,
            full_name: user
              ? `${user.first_name} ${user.last_name}`
              : "",
          }));
        }
      })
      .catch(() => {})
      .finally(() => setProfileLoading(false));
  }, []);

  // =========================================================
  // CALCULATE AGE
  // =========================================================

  const calcAge = (dob: string) => {
    if (!dob) return null;

    const d = new Date(dob);
    const t = new Date();

    let a = t.getFullYear() - d.getFullYear();

    if (
      t.getMonth() < d.getMonth() ||
      (t.getMonth() === d.getMonth() &&
        t.getDate() < d.getDate())
    ) {
      a--;
    }

    return a;
  };

  // =========================================================
  // DATE OF BIRTH
  // =========================================================

  const handleDobChange = (val: string) => {
    setProfileForm((f) => ({
      ...f,
      date_of_birth: val,
    }));

    setAge(calcAge(val));
  };

  // =========================================================
  // SAVE PROFILE
  // =========================================================

  const handleSaveProfile = async () => {
    setProfileError("");
    setProfileSuccess("");
    setProfileSaving(true);

    try {
      if (age !== null && age < 18) {
        setProfileError(
          "Technician must be at least 18 years old"
        );

        setProfileSaving(false);
        return;
      }

      if (!profileForm.full_name.trim()) {
        setProfileError("Full name is required");

        setProfileSaving(false);
        return;
      }

      if (!profileForm.mobile_number.trim()) {
        setProfileError("Mobile number is required");

        setProfileSaving(false);
        return;
      }

      const payload = {
        ...profileForm,

        skills: profileForm.skills
          ? profileForm.skills
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],

        certifications: profileForm.certifications
          ? profileForm.certifications
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],

        date_of_birth: profileForm.date_of_birth || null,
      };

      if (isNewProfile) {
        await createTechnicianProfile(payload);

        setIsNewProfile(false);
        setProfileSuccess("Profile created successfully!");
      } else {
        await updateTechnicianProfile(payload);

        setProfileSuccess("Profile updated successfully!");
      }
    } catch (err: any) {
      setProfileError(
        err.response?.data?.detail ||
          "Failed to save profile"
      );
    } finally {
      setProfileSaving(false);
    }
  };

  // =========================================================
  // CHANGE PASSWORD
  // =========================================================

  const handleChangePassword = async () => {
    setPwError("");
    setPwSuccess("");

    if (newPw.length < 8) {
      setPwError(
        "New password must be at least 8 characters"
      );

      return;
    }

    if (newPw !== confirmPw) {
      setPwError("Passwords do not match");

      return;
    }

    setPwSaving(true);

    try {
      await changeTechnicianPassword({
        current_password: currentPw,
        new_password: newPw,
        confirm_password: confirmPw,
      });

      setPwSuccess("Password changed successfully");

      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
    } catch (e: any) {
      setPwError(
        e.response?.data?.detail ||
          "Failed to change password"
      );
    } finally {
      setPwSaving(false);
    }
  };

  // =========================================================
  // MFA STATUS
  // =========================================================

  useEffect(() => {
    if (activeTab !== "security") {
      return;
    }

    let cancelled = false;

    const loadMfaStatus = async () => {
      setMfaLoading(true);
      setMfaError("");

      try {
        const response = await api.get("/auth/mfa/status");

        if (cancelled) {
          return;
        }

        setMfaEnrolled(Boolean(response.data?.enrolled));
        setMfaEnabled(Boolean(response.data?.enabled));
      } catch (err: any) {
        if (cancelled) {
          return;
        }

        setMfaError(
          typeof err.response?.data?.detail === "string"
            ? err.response.data.detail
            : "Failed to load MFA status."
        );
      } finally {
        if (!cancelled) {
          setMfaLoading(false);
        }
      }
    };

    loadMfaStatus();

    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  // =========================================================
  // ENABLE / ENROLL MFA
  // =========================================================

  const handleEnableMFA = async () => {
    setMfaError("");
    setMfaSuccess("");
    setMfaCode("");
    setRecoveryCodes([]);
    setMfaLoading(true);

    try {
      const response = await api.post("/auth/mfa/enroll");

      setMfaSecret(response.data?.secret || "");
      setMfaProvisioningUri(response.data?.provisioning_uri || "");
      setShowMfaSetup(true);

      setMfaSuccess(
        "MFA setup started. Scan the QR code with your authenticator app."
      );
    } catch (err: any) {
      setMfaError(
        typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Failed to start MFA enrollment."
      );
    } finally {
      setMfaLoading(false);
    }
  };

  // =========================================================
  // VERIFY MFA ENROLLMENT
  // =========================================================

  const handleVerifyMFA = async () => {
    setMfaError("");
    setMfaSuccess("");

    const code = mfaCode.trim();

    if (!/^\d{6}$/.test(code)) {
      setMfaError("Enter the 6-digit code from your authenticator app.");
      return;
    }

    setMfaLoading(true);

    try {
      const response = await api.post("/auth/mfa/enroll/verify", {
        code,
      });

      setMfaEnrolled(true);
      setMfaEnabled(true);
      setMfaCode("");
      setMfaSecret("");
      setMfaProvisioningUri("");
      setShowMfaSetup(false);

      const codes = Array.isArray(response.data?.recovery_codes)
        ? response.data.recovery_codes
        : [];

      setRecoveryCodes(codes);

      setMfaSuccess(
        "Multi-Factor Authentication is enabled. It cannot be disabled from this account."
      );
    } catch (err: any) {
      setMfaError(
        typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Invalid MFA code. Please try again."
      );
    } finally {
      setMfaLoading(false);
    }
  };

  // =========================================================
  // GOOGLE OIDC LINK CALLBACK
  // =========================================================

  const handleGoogleCredential = async (
    response: { credential: string }
  ) => {
    setGoogleError("");
    setGoogleSuccess("");

    if (!response.credential) {
      setGoogleError(
        "Google did not return an ID token."
      );

      return;
    }

    setLinkingGoogle(true);

    try {
      const result = await api.post("/auth/oidc/google/link", {
        id_token: response.credential,
      });
    
      if (result.data.status === "ALREADY_LINKED") {
        setGoogleSuccess("Google account is already linked.");
      } else {
        setGoogleSuccess(
          "Google account linked successfully."
        );
      }
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 409) {
        setGoogleError(
          typeof detail === "string"
            ? detail
            : "This Google account is already linked to another FieldOps account."
        );
      } else if (status === 401) {
        setGoogleError(
          typeof detail === "string"
            ? detail
            : "Your FieldOps session has expired. Please log in again."
        );
      } else {
        setGoogleError(
          typeof detail === "string"
            ? detail
            : "Failed to link Google account."
        );
      }
    } finally {
      setLinkingGoogle(false);
    }
  };

  // =========================================================
  // INITIALIZE GOOGLE IDENTITY SERVICES
  // =========================================================

  useEffect(() => {
    if (activeTab !== "security") {
      return;
    }

    const clientId =
      import.meta.env.VITE_GOOGLE_CLIENT_ID;

    if (!clientId) {
      setGoogleError(
        "Google Client ID is not configured."
      );

      return;
    }

    let attempts = 0;

    const maxAttempts = 20;

    const initializeGoogle = () => {
      attempts += 1;

      if (
        !window.google?.accounts?.id ||
        !googleButtonRef.current
      ) {
        if (attempts < maxAttempts) {
          setTimeout(initializeGoogle, 250);
        } else {
          setGoogleError(
            "Google authentication could not be loaded. Please refresh the page."
          );
        }

        return;
      }

      googleButtonRef.current.innerHTML = "";

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: handleGoogleCredential,
      });

      window.google.accounts.id.renderButton(
        googleButtonRef.current,
        {
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: 280,
        }
      );
    };

    initializeGoogle();
  }, [activeTab]);

  // =========================================================
  // PROFILE FIELD UPDATE
  // =========================================================

  const updProf = (
    key: string,
    val: string
  ) =>
    setProfileForm((f) => ({
      ...f,
      [key]: val,
    }));

  // =========================================================
  // LOADING
  // =========================================================

  if (profileLoading) {
    return (
      <div
        style={{
          padding: "24px",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#5C9470",
          fontFamily: "'Inter', sans-serif",
          fontWeight: 600,
        }}
      >
        Loading Profile & Settings...
      </div>
    );
  }

  // =========================================================
  // COMMON STYLES
  // =========================================================

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "9px 12px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "13px",
    fontFamily: "'Inter', sans-serif",
    outline: "none",
    boxSizing: "border-box",
    color: "#1F2933",
    background: "#FFFFFF",
    transition: "border-color 0.2s",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "11px",
    fontWeight: 700,
    color: "#2F4F3E",
    marginBottom: "5px",
    display: "block",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  };

  // =========================================================
  // PAGE
  // =========================================================

  return (
    <div
      style={{
        padding: "16px 20px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
        boxSizing: "border-box",
      }}
    >
      {/* =====================================================
          HEADER
      ===================================================== */}

      <div
        style={{
          background: "#FFFFFF",
          borderRadius: "12px",
          padding: "14px 20px",
          border: "1px solid #E3ECE7",
          boxShadow:
            "0 1px 4px rgba(47, 79, 62, 0.03)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "14px",
          }}
        >
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "50%",
              background: "#2F4F3E",
              color: "#FFFFFF",
              fontSize: "18px",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow:
                "0 2px 8px rgba(47, 79, 62, 0.15)",
            }}
          >
            {user?.first_name
              ? user.first_name[0].toUpperCase()
              : "T"}
          </div>

          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <h1
                style={{
                  fontSize: "18px",
                  fontWeight: 700,
                  margin: 0,
                  color: "#2F4F3E",
                }}
              >
                {profileForm.full_name ||
                  `${user?.first_name} ${user?.last_name}`}
              </h1>

              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 700,
                  padding: "2px 8px",
                  borderRadius: "4px",
                  background: "#EAF4EE",
                  color: "#2F4F3E",
                  textTransform: "uppercase",
                }}
              >
                TECHNICIAN
              </span>
            </div>

            <span
              style={{
                fontSize: "12px",
                color: "#5C9470",
                fontWeight: 500,
              }}
            >
              {user?.email}
            </span>
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <span
            style={{
              fontSize: "11px",
              color: "#5C9470",
              display: "block",
            }}
          >
            Organization
          </span>

          <span
            style={{
              fontSize: "13px",
              fontWeight: 700,
              color: "#2F4F3E",
            }}
          >
            {user?.organization_name ||
              user?.tenant_id}
          </span>
        </div>
      </div>

      {/* =====================================================
          TABS
      ===================================================== */}

      <div
        style={{
          display: "flex",
          gap: "6px",
          background: "#FFFFFF",
          padding: "4px",
          borderRadius: "10px",
          border: "1px solid #E3ECE7",
          width: "fit-content",
          flexShrink: 0,
        }}
      >
        <button
          onClick={() => setActiveTab("profile")}
          style={{
            padding: "6px 16px",
            borderRadius: "7px",
            fontSize: "12px",
            fontWeight: 600,
            border: "none",
            background:
              activeTab === "profile"
                ? "#2F4F3E"
                : "transparent",
            color:
              activeTab === "profile"
                ? "#FFFFFF"
                : "#5C9470",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            transition: "all 0.2s ease",
          }}
        >
          <User size={14} />
          Profile Details
        </button>

        <button
          onClick={() => setActiveTab("security")}
          style={{
            padding: "6px 16px",
            borderRadius: "7px",
            fontSize: "12px",
            fontWeight: 600,
            border: "none",
            background:
              activeTab === "security"
                ? "#2F4F3E"
                : "transparent",
            color:
              activeTab === "security"
                ? "#FFFFFF"
                : "#5C9470",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            transition: "all 0.2s ease",
          }}
        >
          <Key size={14} />
          Security & Password
        </button>
      </div>

      {/* =====================================================
          MAIN PANEL
      ===================================================== */}

      <div
        style={{
          background: "#FFFFFF",
          borderRadius: "12px",
          padding: "24px",
          border: "1px solid #E3ECE7",
          boxShadow:
            "0 1px 4px rgba(47, 79, 62, 0.03)",
          flex: 1,
          boxSizing: "border-box",
        }}
      >
        {/* ===================================================
            PROFILE TAB
        =================================================== */}

        {activeTab === "profile" && (
          <div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: 700,
                color: "#2F4F3E",
                marginBottom: "16px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                paddingBottom: "10px",
                borderBottom:
                  "1px solid #E3ECE7",
              }}
            >
              <User size={16} />
              Personal & Professional Details
            </div>

            {profileError && (
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
                {profileError}
              </div>
            )}

            {profileSuccess && (
              <div
                style={{
                  background: "#F0FFF4",
                  border:
                    "1px solid #C6F6D5",
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
                {profileSuccess}
              </div>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "1fr 1fr",
                gap: "16px",
              }}
            >
              {/* FULL NAME */}

              <div
                style={{
                  gridColumn: "1 / -1",
                }}
              >
                <label style={labelStyle}>
                  Full Name *
                </label>

                <input
                  style={inputStyle}
                  value={profileForm.full_name}
                  onChange={(e) =>
                    updProf(
                      "full_name",
                      e.target.value
                    )
                  }
                  placeholder="Enter full name"
                />
              </div>

              {/* MOBILE */}

              <div>
                <label style={labelStyle}>
                  Mobile Number *
                </label>

                <input
                  style={inputStyle}
                  value={
                    profileForm.mobile_number
                  }
                  onChange={(e) => {
                    const value =
                      e.target.value;

                    if (/^\d{0,10}$/.test(value)) {
                      updProf(
                        "mobile_number",
                        value
                      );
                    }
                  }}
                  maxLength={10}
                  inputMode="numeric"
                  placeholder="10-digit mobile number"
                />
              </div>

              {/* EMAIL */}

              <div>
                <label style={labelStyle}>
                  Email Address
                </label>

                <input
                  style={{
                    ...inputStyle,
                    background: "#F3F8F5",
                    color: "#6B7280",
                  }}
                  value={user?.email || ""}
                  disabled
                />
              </div>

              {/* DOB */}

              <div>
                <label style={labelStyle}>
                  Date of Birth
                </label>

                <input
                  style={inputStyle}
                  type="date"
                  value={
                    profileForm.date_of_birth
                  }
                  onChange={(e) =>
                    handleDobChange(
                      e.target.value
                    )
                  }
                />

                {age !== null && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#5C9470",
                      marginTop: "4px",
                      fontWeight: 500,
                    }}
                  >
                    Age: {age} years{" "}

                    {age < 18 ? (
                      <span
                        style={{
                          color: "#DC2626",
                          fontWeight: 700,
                        }}
                      >
                        (Must be at least 18
                        years old)
                      </span>
                    ) : (
                      ""
                    )}
                  </div>
                )}
              </div>

              {/* GENDER */}

              <div>
                <label style={labelStyle}>
                  Gender
                </label>

                <select
                  style={inputStyle}
                  value={profileForm.gender}
                  onChange={(e) =>
                    updProf(
                      "gender",
                      e.target.value
                    )
                  }
                >
                  <option value="">
                    Select Gender
                  </option>

                  <option value="Male">
                    Male
                  </option>

                  <option value="Female">
                    Female
                  </option>

                  <option value="Other">
                    Other
                  </option>
                </select>
              </div>

              {/* ADDRESS HEADER */}

              <div
                style={{
                  gridColumn: "1 / -1",
                  marginTop: "8px",
                  paddingTop: "14px",
                  borderTop:
                    "1px solid #E3ECE7",
                }}
              >
                <div
                  style={{
                    fontSize: "13px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                    marginBottom: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <MapPin size={14} />
                  Address & Emergency Details
                </div>
              </div>

              {/* ADDRESS */}

              <div
                style={{
                  gridColumn: "1 / -1",
                }}
              >
                <label style={labelStyle}>
                  Street Address
                </label>

                <textarea
                  style={
                    {
                      ...inputStyle,
                      minHeight: "70px",
                      resize: "vertical",
                    } as React.CSSProperties
                  }
                  value={profileForm.address}
                  onChange={(e) =>
                    updProf(
                      "address",
                      e.target.value
                    )
                  }
                  placeholder="Street address or location details"
                />
              </div>

              {/* CITY */}

              <div>
                <label style={labelStyle}>
                  City
                </label>

                <input
                  style={inputStyle}
                  value={profileForm.city}
                  onChange={(e) =>
                    updProf(
                      "city",
                      e.target.value
                    )
                  }
                  placeholder="City"
                />
              </div>

              {/* STATE */}

              <div>
                <label style={labelStyle}>
                  State
                </label>

                <input
                  style={inputStyle}
                  value={profileForm.state}
                  onChange={(e) =>
                    updProf(
                      "state",
                      e.target.value
                    )
                  }
                  placeholder="State"
                />
              </div>

              {/* PINCODE */}

              <div>
                <label style={labelStyle}>
                  Pincode
                </label>

                <input
                  style={inputStyle}
                  value={profileForm.pincode}
                  onChange={(e) =>
                    updProf(
                      "pincode",
                      e.target.value
                    )
                  }
                  maxLength={6}
                  placeholder="6-digit pincode"
                />
              </div>

              {/* EMERGENCY CONTACT */}

              <div>
                <label style={labelStyle}>
                  Emergency Contact
                </label>

                <input
                  style={inputStyle}
                  value={
                    profileForm.emergency_contact
                  }
                  onChange={(e) =>
                    updProf(
                      "emergency_contact",
                      e.target.value
                    )
                  }
                  maxLength={100}
                  placeholder="Contact name & phone"
                />
              </div>

              {/* PROFESSIONAL HEADER */}

              <div
                style={{
                  gridColumn: "1 / -1",
                  marginTop: "8px",
                  paddingTop: "14px",
                  borderTop:
                    "1px solid #E3ECE7",
                }}
              >
                <div
                  style={{
                    fontSize: "13px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                    marginBottom: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <Briefcase size={14} />
                  Professional Skills &
                  Experience
                </div>
              </div>

              {/* SKILLS */}

              <div
                style={{
                  gridColumn: "1 / -1",
                }}
              >
                <label style={labelStyle}>
                  Skills (comma-separated)
                </label>

                <SkillComboSelect
                  value={profileForm.skills}
                  onChange={(val) =>
                    updProf("skills", val)
                  }
                  placeholder="e.g. Electrical, Plumbing, HVAC Repair"
                  inputStyle={inputStyle}
                />
              </div>

              {/* EXPERIENCE */}

              <div>
                <label style={labelStyle}>
                  Years of Experience
                </label>

                <input
                  style={inputStyle}
                  value={
                    profileForm.experience
                  }
                  onChange={(e) =>
                    updProf(
                      "experience",
                      e.target.value
                    )
                  }
                  placeholder="e.g. 5 years"
                />
              </div>

              {/* CERTIFICATIONS */}

              <div>
                <label style={labelStyle}>
                  Certifications
                  (comma-separated)
                </label>

                <input
                  style={inputStyle}
                  value={
                    profileForm.certifications
                  }
                  onChange={(e) =>
                    updProf(
                      "certifications",
                      e.target.value
                    )
                  }
                  placeholder="e.g. EPA 608, OSHA 30"
                />
              </div>
            </div>

            {/* SAVE PROFILE */}

            <div
              style={{
                marginTop: "24px",
                display: "flex",
                justifyContent: "flex-end",
              }}
            >
              <button
                style={{
                  padding: "10px 24px",
                  border: "none",
                  borderRadius: "8px",
                  fontSize: "13px",
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  background: "#7AAE8A",
                  color: "#FFFFFF",
                  opacity:
                    profileSaving ? 0.7 : 1,
                  boxShadow:
                    "0 2px 6px rgba(122, 174, 138, 0.3)",
                }}
                onClick={handleSaveProfile}
                disabled={profileSaving}
              >
                <Save size={15} />

                {profileSaving
                  ? "Saving..."
                  : isNewProfile
                  ? "Save Profile"
                  : "Update Profile"}
              </button>
            </div>
          </div>
        )}

        {/* ===================================================
            SECURITY TAB
        =================================================== */}

        {activeTab === "security" && (
          <div style={{ maxWidth: "620px" }}>
            {/* SECURITY HEADER */}

            <div
              style={{
                fontSize: "15px",
                fontWeight: 700,
                color: "#2F4F3E",
                marginBottom: "16px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                paddingBottom: "10px",
                borderBottom:
                  "1px solid #E3ECE7",
              }}
            >
              <Key size={16} />
              Account Security & Password
            </div>

            {/* PASSWORD ERROR */}

            {pwError && (
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
                {pwError}
              </div>
            )}

            {/* PASSWORD SUCCESS */}

            {pwSuccess && (
              <div
                style={{
                  background: "#F0FFF4",
                  border:
                    "1px solid #C6F6D5",
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
                {pwSuccess}
              </div>
            )}

            {/* PASSWORD FORM */}

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "14px",
              }}
            >
              {/* CURRENT PASSWORD */}

              <div>
                <label style={labelStyle}>
                  Current Password
                </label>

                <input
                  type="password"
                  style={inputStyle}
                  value={currentPw}
                  onChange={(e) =>
                    setCurrentPw(e.target.value)
                  }
                  placeholder="Enter current password"
                />
              </div>

              {/* NEW PASSWORD */}

              <div>
                <label style={labelStyle}>
                  New Password (min 8 chars)
                </label>

                <input
                  type="password"
                  style={inputStyle}
                  value={newPw}
                  onChange={(e) =>
                    setNewPw(e.target.value)
                  }
                  placeholder="Enter new password"
                />
              </div>

              {/* CONFIRM PASSWORD */}

              <div>
                <label style={labelStyle}>
                  Confirm New Password
                </label>

                <input
                  type="password"
                  style={inputStyle}
                  value={confirmPw}
                  onChange={(e) =>
                    setConfirmPw(e.target.value)
                  }
                  placeholder="Confirm new password"
                />
              </div>

              {/* CHANGE PASSWORD BUTTON */}

              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  marginTop: "8px",
                }}
              >
                <button
                  onClick={handleChangePassword}
                  disabled={pwSaving}
                  style={{
                    padding: "10px 24px",
                    border: "none",
                    borderRadius: "8px",
                    fontSize: "13px",
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    background: "#7AAE8A",
                    color: "#FFFFFF",
                    opacity: pwSaving
                      ? 0.7
                      : 1,
                    boxShadow:
                      "0 2px 6px rgba(122, 174, 138, 0.3)",
                  }}
                >
                  <Key size={15} />

                  {pwSaving
                    ? "Updating..."
                    : "Change Password"}
                </button>
              </div>
            </div>

            {/* =================================================
                MULTI-FACTOR AUTHENTICATION
            ================================================= */}

            <div
              style={{
                marginTop: "28px",
                paddingTop: "20px",
                borderTop: "1px solid #E3ECE7",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "8px",
                }}
              >
                <Shield size={16} color="#2F4F3E" />

                <div
                  style={{
                    fontSize: "15px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                  }}
                >
                  Multi-Factor Authentication
                </div>
              </div>

              <div
                style={{
                  fontSize: "12px",
                  color: "#6B7280",
                  marginBottom: "14px",
                  lineHeight: 1.5,
                }}
              >
                Add an authenticator app as an additional security step when
                signing in to FieldOps. MFA is optional until you enable it.
                Once enabled, it cannot be disabled from this account.
              </div>

              {mfaError && (
                <div
                  style={{
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    color: "#991B1B",
                    fontSize: "13px",
                    marginBottom: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <AlertCircle size={16} />
                  {mfaError}
                </div>
              )}

              {mfaSuccess && (
                <div
                  style={{
                    background: "#F0FFF4",
                    border: "1px solid #C6F6D5",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    color: "#22543D",
                    fontSize: "13px",
                    marginBottom: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <CheckCircle size={16} />
                  {mfaSuccess}
                </div>
              )}

              {mfaLoading && !showMfaSetup ? (
                <div
                  style={{
                    padding: "14px",
                    border: "1px solid #E3ECE7",
                    borderRadius: "8px",
                    color: "#5C9470",
                    fontSize: "13px",
                    fontWeight: 600,
                  }}
                >
                  Loading MFA status...
                </div>
              ) : mfaEnabled ? (
                <>
                  <div
                    style={{
                      border: "1px solid #C6F6D5",
                      background: "#F0FFF4",
                      borderRadius: "10px",
                      padding: "16px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                        marginBottom: "8px",
                      }}
                    >
                      <Shield size={20} color="#22543D" />

                      <div
                        style={{
                          fontSize: "14px",
                          fontWeight: 700,
                          color: "#22543D",
                        }}
                      >
                        MFA is ON
                      </div>

                      <span
                        style={{
                          marginLeft: "auto",
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "3px 8px",
                          borderRadius: "5px",
                          background: "#C6F6D5",
                          color: "#22543D",
                        }}
                      >
                        ENABLED
                      </span>
                    </div>

                    <div
                      style={{
                        fontSize: "12px",
                        color: "#276749",
                        lineHeight: 1.5,
                      }}
                    >
                      Your authenticator app is configured. Future logins
                      require your email/password followed by a 6-digit
                      authenticator code.
                    </div>

                    <div
                      style={{
                        marginTop: "10px",
                        fontSize: "12px",
                        fontWeight: 700,
                        color: "#22543D",
                      }}
                    >
                      MFA cannot be disabled from Settings.
                    </div>
                  </div>

                  {recoveryCodes.length > 0 && (
                    <div
                      style={{
                        marginTop: "14px",
                        border: "1px solid #FDE68A",
                        background: "#FFFBEB",
                        borderRadius: "10px",
                        padding: "16px",
                      }}
                    >
                      <div
                        style={{
                          fontSize: "14px",
                          fontWeight: 700,
                          color: "#92400E",
                          marginBottom: "6px",
                        }}
                      >
                        Save your recovery codes
                      </div>

                      <div
                        style={{
                          fontSize: "12px",
                          color: "#78350F",
                          lineHeight: 1.5,
                          marginBottom: "12px",
                        }}
                      >
                        These codes are shown only after MFA enrollment.
                        Store them somewhere safe. Do not share them with
                        anyone.
                      </div>

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr",
                          gap: "8px",
                          padding: "10px",
                          background: "#FFFFFF",
                          border: "1px solid #FDE68A",
                          borderRadius: "8px",
                          fontFamily: "monospace",
                          fontSize: "13px",
                          fontWeight: 700,
                        }}
                      >
                        {recoveryCodes.map((code) => (
                          <div key={code}>{code}</div>
                        ))}
                      </div>

                      <div
                        style={{
                          marginTop: "12px",
                          fontSize: "11px",
                          color: "#92400E",
                          fontWeight: 600,
                        }}
                      >
                        Keep these codes secure. They are not stored in this
                        page after a refresh.
                      </div>
                    </div>
                  )}
                </>
              ) : showMfaSetup ? (
                <div
                  style={{
                    border: "1px solid #E3ECE7",
                    borderRadius: "10px",
                    padding: "18px",
                    background: "#FAFCFB",
                  }}
                >
                  <div
                    style={{
                      fontSize: "14px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      marginBottom: "6px",
                    }}
                  >
                    Set up your authenticator
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#6B7280",
                      lineHeight: 1.5,
                      marginBottom: "16px",
                    }}
                  >
                    Open Google Authenticator, Microsoft Authenticator, or
                    another compatible TOTP app and scan this QR code.
                  </div>

                  {mfaProvisioningUri && (
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "center",
                        padding: "16px",
                        background: "#FFFFFF",
                        border: "1px solid #E3ECE7",
                        borderRadius: "8px",
                        marginBottom: "14px",
                      }}
                    >
                      <QRCodeSVG
                        value={mfaProvisioningUri}
                        size={220}
                        level="M"
                        includeMargin
                      />
                    </div>
                  )}

                  {mfaSecret && (
                    <div style={{ marginBottom: "16px" }}>
                      <label style={labelStyle}>
                        Manual Setup Key
                      </label>

                      <div
                        style={{
                          padding: "10px 12px",
                          background: "#F3F8F5",
                          border: "1px solid #E3ECE7",
                          borderRadius: "8px",
                          fontFamily: "monospace",
                          fontSize: "13px",
                          fontWeight: 700,
                          color: "#2F4F3E",
                          wordBreak: "break-all",
                        }}
                      >
                        {mfaSecret}
                      </div>
                    </div>
                  )}

                  <div>
                    <label style={labelStyle}>
                      Authenticator Code
                    </label>

                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      value={mfaCode}
                      onChange={(e) => {
                        const value = e.target.value
                          .replace(/\D/g, "")
                          .slice(0, 6);

                        setMfaCode(value);
                      }}
                      placeholder="Enter 6-digit code"
                      style={{
                        ...inputStyle,
                        letterSpacing: "0.2em",
                        fontWeight: 700,
                        textAlign: "center",
                      }}
                    />
                  </div>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      gap: "8px",
                      marginTop: "14px",
                    }}
                  >
                    <button
                      onClick={() => {
                        setShowMfaSetup(false);
                        setMfaCode("");
                        setMfaSecret("");
                        setMfaProvisioningUri("");
                        setMfaError("");
                        setMfaSuccess("");
                      }}
                      disabled={mfaLoading}
                      style={{
                        padding: "10px 18px",
                        border: "1px solid #D1D5DB",
                        borderRadius: "8px",
                        fontSize: "13px",
                        fontWeight: 700,
                        cursor: mfaLoading ? "not-allowed" : "pointer",
                        background: "#FFFFFF",
                        color: "#4B5563",
                        opacity: mfaLoading ? 0.6 : 1,
                      }}
                    >
                      Cancel Setup
                    </button>

                    <button
                      onClick={handleVerifyMFA}
                      disabled={mfaLoading || mfaCode.length !== 6}
                      style={{
                        padding: "10px 18px",
                        border: "none",
                        borderRadius: "8px",
                        fontSize: "13px",
                        fontWeight: 700,
                        cursor:
                          mfaLoading || mfaCode.length !== 6
                            ? "not-allowed"
                            : "pointer",
                        background: "#7AAE8A",
                        color: "#FFFFFF",
                        opacity:
                          mfaLoading || mfaCode.length !== 6 ? 0.6 : 1,
                        boxShadow:
                          "0 2px 6px rgba(122, 174, 138, 0.3)",
                      }}
                    >
                      {mfaLoading
                        ? "Verifying..."
                        : "Verify & Enable MFA"}
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    border: "1px solid #E3ECE7",
                    borderRadius: "10px",
                    padding: "16px",
                    background: "#FAFCFB",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      marginBottom: "8px",
                    }}
                  >
                    <Shield size={20} color="#5C9470" />

                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: 700,
                        color: "#2F4F3E",
                      }}
                    >
                      MFA is currently OFF
                    </div>
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#6B7280",
                      lineHeight: 1.5,
                      marginBottom: "14px",
                    }}
                  >
                    Your account currently uses the normal email/password
                    login. Enable MFA to require an authenticator code on
                    future logins.
                  </div>

                  <button
                    onClick={handleEnableMFA}
                    disabled={mfaLoading || mfaEnrolled}
                    style={{
                      padding: "10px 20px",
                      border: "none",
                      borderRadius: "8px",
                      fontSize: "13px",
                      fontWeight: 700,
                      cursor:
                        mfaLoading || mfaEnrolled
                          ? "not-allowed"
                          : "pointer",
                      background: "#7AAE8A",
                      color: "#FFFFFF",
                      opacity: mfaLoading || mfaEnrolled ? 0.6 : 1,
                      boxShadow:
                        "0 2px 6px rgba(122, 174, 138, 0.3)",
                    }}
                  >
                    {mfaLoading ? "Starting..." : "Enable MFA"}
                  </button>
                </div>
              )}
            </div>

            {/* =================================================
                GOOGLE ACCOUNT LINKING
            ================================================= */}

            <div
              style={{
                marginTop: "28px",
                paddingTop: "20px",
                borderTop:
                  "1px solid #E3ECE7",
              }}
            >
              <div
                style={{
                  fontSize: "15px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  marginBottom: "8px",
                }}
              >
                Google Account
              </div>

              <div
                style={{
                  fontSize: "12px",
                  color: "#6B7280",
                  marginBottom: "14px",
                  lineHeight: 1.5,
                }}
              >
                Link your Google account to this
                existing FieldOps account. After
                linking, you can use Google to sign
                in.
              </div>

              {/* GOOGLE ERROR */}

              {googleError && (
                <div
                  style={{
                    background: "#FEF2F2",
                    border:
                      "1px solid #FECACA",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    color: "#991B1B",
                    fontSize: "13px",
                    marginBottom: "12px",
                  }}
                >
                  {googleError}
                </div>
              )}

              {/* GOOGLE SUCCESS */}

              {googleSuccess && (
                <div
                  style={{
                    background: "#F0FFF4",
                    border:
                      "1px solid #C6F6D5",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    color: "#22543D",
                    fontSize: "13px",
                    marginBottom: "12px",
                  }}
                >
                  {googleSuccess}
                </div>
              )}

              {/* GOOGLE GIS BUTTON */}

              <div
                ref={googleButtonRef}
                style={{
                  minHeight: "40px",
                }}
              />

              {/* LINKING STATUS */}

              {linkingGoogle && (
                <div
                  style={{
                    marginTop: "10px",
                    fontSize: "13px",
                    color: "#5C9470",
                    fontWeight: 600,
                  }}
                >
                  Linking Google account...
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}