import { useState, useEffect } from "react";
import { User, Key, Save, AlertCircle, CheckCircle, Shield, Briefcase, MapPin } from "lucide-react";
import {
  getTechnicianProfile,
  createTechnicianProfile,
  updateTechnicianProfile,
  changeTechnicianPassword,
} from "../../services/technicianPortalService";
import useAuthStore from "../../store/authStore";
import { SkillComboSelect } from "../../components/ui/SkillComboSelect";

export default function TechnicianSettingsPage() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"profile" | "security">("profile");

  // Profile State
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

  // Password State
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState("");
  const [pwSuccess, setPwSuccess] = useState("");

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
          if (p.age) setAge(p.age);
        } else {
          setProfileForm((f) => ({
            ...f,
            full_name: user ? `${user.first_name} ${user.last_name}` : "",
          }));
        }
      })
      .catch(() => {})
      .finally(() => setProfileLoading(false));
  }, []);

  const calcAge = (dob: string) => {
    if (!dob) return null;
    const d = new Date(dob);
    const t = new Date();
    let a = t.getFullYear() - d.getFullYear();
    if (
      t.getMonth() < d.getMonth() ||
      (t.getMonth() === d.getMonth() && t.getDate() < d.getDate())
    )
      a--;
    return a;
  };

  const handleDobChange = (val: string) => {
    setProfileForm((f) => ({ ...f, date_of_birth: val }));
    setAge(calcAge(val));
  };

  const handleSaveProfile = async () => {
    setProfileError("");
    setProfileSuccess("");
    setProfileSaving(true);
    try {
      if (age !== null && age < 18) {
        setProfileError("Technician must be at least 18 years old");
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
          ? profileForm.skills.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        certifications: profileForm.certifications
          ? profileForm.certifications.split(",").map((s) => s.trim()).filter(Boolean)
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
      setProfileError(err.response?.data?.detail || "Failed to save profile");
    } finally {
      setProfileSaving(false);
    }
  };

  const handleChangePassword = async () => {
    setPwError("");
    setPwSuccess("");
    if (newPw.length < 8) {
      setPwError("New password must be at least 8 characters");
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
      setPwError(e.response?.data?.detail || "Failed to change password");
    } finally {
      setPwSaving(false);
    }
  };

  const updProf = (key: string, val: string) =>
    setProfileForm((f) => ({ ...f, [key]: val }));

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
      {/* 1. Unified Top Header Banner */}
      <div
        style={{
          background: "#FFFFFF",
          borderRadius: "12px",
          padding: "14px 20px",
          border: "1px solid #E3ECE7",
          boxShadow: "0 1px 4px rgba(47, 79, 62, 0.03)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
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
              boxShadow: "0 2px 8px rgba(47, 79, 62, 0.15)",
            }}
          >
            {user?.first_name ? user.first_name[0].toUpperCase() : "T"}
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <h1
                style={{
                  fontSize: "18px",
                  fontWeight: 700,
                  margin: 0,
                  color: "#2F4F3E",
                }}
              >
                {profileForm.full_name || `${user?.first_name} ${user?.last_name}`}
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
            <span style={{ fontSize: "12px", color: "#5C9470", fontWeight: 500 }}>
              {user?.email}
            </span>
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <span style={{ fontSize: "11px", color: "#5C9470", display: "block" }}>
            Tenant ID
          </span>
          <span style={{ fontSize: "13px", fontWeight: 700, color: "#2F4F3E" }}>
            {user?.tenant_id || "tenant-1"}
          </span>
        </div>
      </div>

      {/* 2. Compact Tabs Bar */}
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
            background: activeTab === "profile" ? "#2F4F3E" : "transparent",
            color: activeTab === "profile" ? "#FFFFFF" : "#5C9470",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            transition: "all 0.2s ease",
          }}
        >
          <User size={14} /> Profile Details
        </button>

        <button
          onClick={() => setActiveTab("security")}
          style={{
            padding: "6px 16px",
            borderRadius: "7px",
            fontSize: "12px",
            fontWeight: 600,
            border: "none",
            background: activeTab === "security" ? "#2F4F3E" : "transparent",
            color: activeTab === "security" ? "#FFFFFF" : "#5C9470",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            transition: "all 0.2s ease",
          }}
        >
          <Key size={14} /> Security & Password
        </button>
      </div>

      {/* 3. Main Single Panel Container */}
      <div
        style={{
          background: "#FFFFFF",
          borderRadius: "12px",
          padding: "24px",
          border: "1px solid #E3ECE7",
          boxShadow: "0 1px 4px rgba(47, 79, 62, 0.03)",
          flex: 1,
          boxSizing: "border-box",
        }}
      >
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
                borderBottom: "1px solid #E3ECE7",
              }}
            >
              <User size={16} /> Personal & Professional Details
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
                <AlertCircle size={16} /> {profileError}
              </div>
            )}
            {profileSuccess && (
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
                <CheckCircle size={16} /> {profileSuccess}
              </div>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "16px",
              }}
            >
              {/* Personal Details */}
              <div style={{ gridColumn: "1 / -1" }}>
                <label style={labelStyle}>Full Name *</label>
                <input
                  style={inputStyle}
                  value={profileForm.full_name}
                  onChange={(e) => updProf("full_name", e.target.value)}
                  placeholder="Enter full name"
                />
              </div>

              <div>
                <label style={labelStyle}>Mobile Number *</label>
                <input
  style={inputStyle}
  value={profileForm.mobile_number}
  onChange={(e) => {
    const value = e.target.value;
    if (/^\d{0,10}$/.test(value)) {
      updProf("mobile_number", value);
    }
  }}
  maxLength={10}
  inputMode="numeric"
  placeholder="10-digit mobile number"
/>
              </div>

              <div>
                <label style={labelStyle}>Email Address</label>
                <input
                  style={{ ...inputStyle, background: "#F3F8F5", color: "#6B7280" }}
                  value={user?.email || ""}
                  disabled
                />
              </div>

              <div>
                <label style={labelStyle}>Date of Birth</label>
                <input
                  style={inputStyle}
                  type="date"
                  value={profileForm.date_of_birth}
                  onChange={(e) => handleDobChange(e.target.value)}
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
                      <span style={{ color: "#DC2626", fontWeight: 700 }}>
                        (Must be at least 18 years old)
                      </span>
                    ) : (
                      ""
                    )}
                  </div>
                )}
              </div>

              <div>
                <label style={labelStyle}>Gender</label>
                <select
                  style={inputStyle}
                  value={profileForm.gender}
                  onChange={(e) => updProf("gender", e.target.value)}
                >
                  <option value="">Select Gender</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              {/* Location & Address */}
              <div
                style={{
                  gridColumn: "1 / -1",
                  marginTop: "8px",
                  paddingTop: "14px",
                  borderTop: "1px solid #E3ECE7",
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
                  <MapPin size={14} /> Address & Emergency Details
                </div>
              </div>

              <div style={{ gridColumn: "1 / -1" }}>
                <label style={labelStyle}>Street Address</label>
                <textarea
                  style={{
                    ...inputStyle,
                    minHeight: "70px",
                    resize: "vertical",
                  } as any}
                  value={profileForm.address}
                  onChange={(e) => updProf("address", e.target.value)}
                  placeholder="Street address or location details"
                />
              </div>

              <div>
                <label style={labelStyle}>City</label>
                <input
                  style={inputStyle}
                  value={profileForm.city}
                  onChange={(e) => updProf("city", e.target.value)}
                  placeholder="City"
                />
              </div>

              <div>
                <label style={labelStyle}>State</label>
                <input
                  style={inputStyle}
                  value={profileForm.state}
                  onChange={(e) => updProf("state", e.target.value)}
                  placeholder="State"
                />
              </div>

              <div>
                <label style={labelStyle}>Pincode</label>
                <input
                  style={inputStyle}
                  value={profileForm.pincode}
                  onChange={(e) => updProf("pincode", e.target.value)}
                  maxLength={6}
                  placeholder="6-digit pincode"
                />
              </div>

              <div>
                <div>
                  <label style={labelStyle}>Emergency Contact</label>
                  <input
                    style={inputStyle}
                    value={profileForm.emergency_contact}
                    onChange={(e) => updProf("emergency_contact", e.target.value)}
                    maxLength={100}
                    placeholder="Contact name & phone"
                  />
                </div>
              </div>

              {/* Professional Background */}
              <div
                style={{
                  gridColumn: "1 / -1",
                  marginTop: "8px",
                  paddingTop: "14px",
                  borderTop: "1px solid #E3ECE7",
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
                  <Briefcase size={14} /> Professional Skills & Experience
                </div>
              </div>

              <div style={{ gridColumn: "1 / -1" }}>
                <label style={labelStyle}>Skills (comma-separated)</label>
                <SkillComboSelect
                  value={profileForm.skills}
                  onChange={(val) => updProf("skills", val)}
                  placeholder="e.g. Electrical, Plumbing, HVAC Repair"
                  inputStyle={inputStyle}
                />
              </div>

              <div>
                <label style={labelStyle}>Years of Experience</label>
                <input
                  style={inputStyle}
                  value={profileForm.experience}
                  onChange={(e) => updProf("experience", e.target.value)}
                  placeholder="e.g. 5 years"
                />
              </div>

              <div>
                <label style={labelStyle}>Certifications (comma-separated)</label>
                <input
                  style={inputStyle}
                  value={profileForm.certifications}
                  onChange={(e) => updProf("certifications", e.target.value)}
                  placeholder="e.g. EPA 608, OSHA 30"
                />
              </div>
            </div>

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
                  opacity: profileSaving ? 0.7 : 1,
                  boxShadow: "0 2px 6px rgba(122, 174, 138, 0.3)",
                }}
                onClick={handleSaveProfile}
                disabled={profileSaving}
              >
                <Save size={15} />{" "}
                {profileSaving
                  ? "Saving..."
                  : isNewProfile
                  ? "Save Profile"
                  : "Update Profile"}
              </button>
            </div>
          </div>
        )}

        {activeTab === "security" && (
          <div style={{ maxWidth: "500px" }}>
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
                borderBottom: "1px solid #E3ECE7",
              }}
            >
              <Key size={16} /> Account Security & Password
            </div>

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
                <AlertCircle size={16} /> {pwError}
              </div>
            )}
            {pwSuccess && (
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
                <CheckCircle size={16} /> {pwSuccess}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              <div>
                <label style={labelStyle}>Current Password</label>
                <input
                  type="password"
                  style={inputStyle}
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                  placeholder="Enter current password"
                />
              </div>

              <div>
                <label style={labelStyle}>New Password (min 8 chars)</label>
                <input
                  type="password"
                  style={inputStyle}
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  placeholder="Enter new password"
                />
              </div>

              <div>
                <label style={labelStyle}>Confirm New Password</label>
                <input
                  type="password"
                  style={inputStyle}
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  placeholder="Confirm new password"
                />
              </div>

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
                    opacity: pwSaving ? 0.7 : 1,
                    boxShadow: "0 2px 6px rgba(122, 174, 138, 0.3)",
                  }}
                >
                  <Key size={15} />{" "}
                  {pwSaving ? "Updating..." : "Change Password"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
