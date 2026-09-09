import { useState, useEffect } from "react";
import {
  User,
  Save,
  Camera,
  Shield,
  AlertCircle,
  CheckCircle,
} from "lucide-react";
import {
  getTechnicianProfile,
  createTechnicianProfile,
  updateTechnicianProfile,
} from "../../services/technicianPortalService";
import useAuthStore from "../../store/authStore";
import { SkillComboSelect } from "../../components/ui/SkillComboSelect";

const s = {
  page: {
    padding: "24px",
    height: "100%",
    overflowY: "auto" as const,
    background: "#EEF4F1",
    fontFamily: "'Inter', sans-serif",
  },
  card: {
    background: "#fff",
    borderRadius: "14px",
    padding: "28px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    border: "1px solid #E3ECE7",
    maxWidth: "700px",
    margin: "0 auto",
  },
  title: {
    fontSize: "22px",
    fontWeight: 700,
    color: "#1F2933",
    margin: "0 0 4px",
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },
  subtitle: { fontSize: "13px", color: "#6B7280", marginBottom: "24px" },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" },
  fullWidth: { gridColumn: "1 / -1" },
  label: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "4px",
    display: "block",
  },
  input: {
    width: "100%",
    padding: "10px 12px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    fontFamily: "'Inter', sans-serif",
    outline: "none",
    boxSizing: "border-box" as const,
    transition: "border-color 0.2s",
  },
  select: {
    width: "100%",
    padding: "10px 12px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    background: "#fff",
    outline: "none",
    boxSizing: "border-box" as const,
  },
  textarea: {
    width: "100%",
    padding: "10px 12px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    fontFamily: "'Inter', sans-serif",
    minHeight: "80px",
    resize: "vertical" as const,
    boxSizing: "border-box" as const,
    outline: "none",
  },
  btn: {
    padding: "12px 28px",
    border: "none",
    borderRadius: "10px",
    fontSize: "14px",
    fontWeight: 700,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    transition: "all 0.2s",
  },
  btnPrimary: { background: "#7AAE8A", color: "#fff" },
  error: {
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
  },
  success: {
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
  },
  section: {
    fontSize: "14px",
    fontWeight: 700,
    color: "#2F4F3E",
    margin: "20px 0 12px",
    paddingTop: "16px",
    borderTop: "1px solid #E3ECE7",
  },
  ageDisplay: { fontSize: "13px", color: "#6B7280", marginTop: "4px" },
};

export default function TechnicianProfilePage() {
  const { user } = useAuthStore();
  const [isNew, setIsNew] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState({
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

  useEffect(() => {
    getTechnicianProfile()
      .then((res) => {
        const p = res.data;
        if (p.profile_completed) {
          setIsNew(false);
          setForm({
            full_name: p.full_name || "",
            mobile_number: String(p.mobile_number || "")
              .replace(/\D/g, "")
              .slice(0, 10),
            date_of_birth: p.date_of_birth || "",
            gender: p.gender || "",
            address: p.address || "",
            city: p.city || "",
            state: p.state || "",
            pincode: p.pincode || "",
            emergency_contact: String(p.emergency_contact || "")
              .replace(/\D/g, "")
              .slice(0, 10),
            skills: (p.skills || []).join(", "),
            experience: p.experience || "",
            certifications: (p.certifications || []).join(", "),
            profile_photo: p.profile_photo || "",
          });
          if (p.age) setAge(p.age);
        } else {
          setForm((f) => ({
            ...f,
            full_name: user ? `${user.first_name} ${user.last_name}` : "",
          }));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
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
    setForm((f) => ({ ...f, date_of_birth: val }));
    setAge(calcAge(val));
  };

  const handleSave = async () => {
    setError("");
    setSuccess("");
    setSaving(true);
    try {
      if (age !== null && age < 18) {
        setError("Technician must be at least 18 years old");
        setSaving(false);
        return;
      }
      if (!form.full_name.trim()) {
        setError("Full name is required");
        setSaving(false);
        return;
      }
      if (!form.mobile_number.trim()) {
        setError("Mobile number is required");
        setSaving(false);
        return;
      }

      const payload = {
        ...form,
        skills: form.skills
          ? form.skills
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
        certifications: form.certifications
          ? form.certifications
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
        date_of_birth: form.date_of_birth || null,
      };

      if (isNew) {
        await createTechnicianProfile(payload);
        setIsNew(false);
        setSuccess("Profile created successfully!");
      } else {
        await updateTechnicianProfile(payload);
        setSuccess("Profile updated successfully!");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to save profile");
    } finally {
      setSaving(false);
    }
  };

  const upd = (key: string, val: string) =>
    setForm((f) => ({ ...f, [key]: val }));

  if (loading)
    return (
      <div style={s.page}>
        <div style={{ textAlign: "center", padding: "60px", color: "#6B7280" }}>
          Loading profile...
        </div>
      </div>
    );

  return (
    <div style={s.page}>
      <div style={s.card}>
        <h2 style={s.title}>
          <User size={22} color="#7AAE8A" />
          {isNew ? "Complete Your Profile" : "Edit Profile"}
        </h2>
        <p style={s.subtitle}>
          {isNew
            ? "Please fill in your details to get started"
            : "Update your profile information"}
        </p>

        {error && (
          <div style={s.error}>
            <AlertCircle size={16} /> {error}
          </div>
        )}
        {success && (
          <div style={s.success}>
            <CheckCircle size={16} /> {success}
          </div>
        )}

        <div style={s.grid}>
          <div style={s.fullWidth}>
            <label style={s.label}>Full Name *</label>
            <input
              style={s.input}
              value={form.full_name}
              onChange={(e) => upd("full_name", e.target.value)}
              placeholder="Enter full name"
            />
          </div>
          <div>
            <label style={s.label}>Mobile Number *</label>
            <input
              type="text"
              style={s.input}
              value={form.mobile_number}
              onChange={(e) => {
                const value = e.target.value;
                if (/^\d{0,10}$/.test(value)) {
                  upd("mobile_number", value);
                }
              }}
              maxLength={10}
              inputMode="numeric"
              placeholder="10-digit mobile"
            />
          </div>
          <div>
            <label style={s.label}>Email</label>
            <input
              style={{ ...s.input, background: "#F3F4F6" }}
              value={user?.email || ""}
              disabled
            />
          </div>
          <div>
            <label style={s.label}>Date of Birth</label>
            <input
              style={s.input}
              type="date"
              value={form.date_of_birth}
              onChange={(e) => handleDobChange(e.target.value)}
            />
            {age !== null && (
              <div style={s.ageDisplay}>
                Age: {age} years{" "}
                {age < 18 ? (
                  <span style={{ color: "#E53E3E" }}>(Must be 18+)</span>
                ) : (
                  ""
                )}
              </div>
            )}
          </div>
          <div>
            <label style={s.label}>Gender</label>
            <select
              style={s.select}
              value={form.gender}
              onChange={(e) => upd("gender", e.target.value)}
            >
              <option value="">Select</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div style={{ ...s.fullWidth, ...{ marginTop: "4px" } }}>
            <div style={s.section}>Address</div>
          </div>
          <div style={s.fullWidth}>
            <label style={s.label}>Address</label>
            <textarea
              style={s.textarea as any}
              value={form.address}
              onChange={(e) => upd("address", e.target.value)}
              placeholder="Street address"
            />
          </div>
          <div>
            <label style={s.label}>City</label>
            <input
              style={s.input}
              value={form.city}
              onChange={(e) => upd("city", e.target.value)}
            />
          </div>
          <div>
            <label style={s.label}>State</label>
            <input
              style={s.input}
              value={form.state}
              onChange={(e) => upd("state", e.target.value)}
            />
          </div>
          <div>
            <label style={s.label}>Pincode</label>
            <input
              style={s.input}
              value={form.pincode}
              onChange={(e) => upd("pincode", e.target.value)}
              maxLength={6}
            />
          </div>
          <div>
            <label style={s.label}>Emergency Contact</label>
            <input
              style={s.input}
              value={form.emergency_contact}
              onChange={(e) => upd("emergency_contact", e.target.value)}
              maxLength={10}
            />
          </div>

          <div style={{ ...s.fullWidth, ...{ marginTop: "4px" } }}>
            <div style={s.section}>Professional Info</div>
          </div>
          <div style={s.fullWidth}>
            <label style={s.label}>Skills (comma-separated)</label>
            <SkillComboSelect
              value={form.skills}
              onChange={(val) => upd("skills", val)}
              placeholder="e.g. Electrical, Plumbing, HVAC"
              inputStyle={s.input}
            />
          </div>
          <div>
            <label style={s.label}>Experience</label>
            <input
              style={s.input}
              value={form.experience}
              onChange={(e) => upd("experience", e.target.value)}
              placeholder="e.g. 5 years"
            />
          </div>
          <div style={s.fullWidth}>
            <label style={s.label}>Certifications (comma-separated)</label>
            <input
              style={s.input}
              value={form.certifications}
              onChange={(e) => upd("certifications", e.target.value)}
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
            style={{ ...s.btn, ...s.btnPrimary, opacity: saving ? 0.7 : 1 }}
            onClick={handleSave}
            disabled={saving}
          >
            <Save size={16} />{" "}
            {saving ? "Saving..." : isNew ? "Complete Profile" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
