import { useState, useEffect } from "react";
import {
  Award,
  Briefcase,
  CalendarDays,
  Clock3,
  FileText,
  History,
  User,
  Save,
  AlertCircle,
  CheckCircle,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Wrench,
  ArrowLeft,
} from "lucide-react";
import {
  getTechnicianProfile,
  getTechnicianJobHistory,
  getTechnicianDashboard,
  createTechnicianProfile,
  updateTechnicianProfile,
} from "../../services/technicianPortalService";
import useAuthStore from "../../store/authStore";
import { SkillComboSelect } from "../../components/ui/SkillComboSelect";

type TechnicianProfileForm = {
  full_name: string;
  mobile_number: string;
  date_of_birth: string;
  gender: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  emergency_contact: string;
  skills: string;
  experience: string;
  certifications: string;
  profile_photo: string;
};

type ProfileHistoryJob = {
  id: number;
  status?: string | null;
  service_type?: string | null;
  location?: string | null;
  site_address?: string | null;
  customer_name?: string | null;
  completed_at?: string | null;
  rejected_at?: string | null;
};

type ProfileTab = "personal" | "skills" | "history" | "documents";

const emptyProfileForm: TechnicianProfileForm = {
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
};

const profileTabs: {
  id: ProfileTab;
  label: string;
  icon: typeof User;
}[] = [
  { id: "personal", label: "Personal Details", icon: User },
  { id: "skills", label: "Skills & Certifications", icon: Award },
  { id: "history", label: "Job History", icon: Briefcase },
  { id: "documents", label: "Documents", icon: FileText },
];

const DetailField = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <div style={{ minWidth: 0 }}>
    <div style={{ color: "#718096", fontSize: 12, marginBottom: 4 }}>
      {label}
    </div>
    <div style={{ color: "#243B53", fontSize: 14, fontWeight: 500, overflowWrap: "anywhere" }}>
      {value || "Not provided"}
    </div>
  </div>
);

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

export default function TechnicianProfilePage({
  onNavigate,
}: {
  onNavigate?: (tab: string) => void;
}) {
  const { user } = useAuthStore();
  const [isNew, setIsNew] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState<TechnicianProfileForm>(emptyProfileForm);
  const [savedForm, setSavedForm] =
    useState<TechnicianProfileForm>(emptyProfileForm);
  const [age, setAge] = useState<number | null>(null);
  const [activeProfileTab, setActiveProfileTab] =
    useState<ProfileTab>("personal");
  const [historyJobs, setHistoryJobs] = useState<ProfileHistoryJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [profileMetadata, setProfileMetadata] = useState<{
    id: string;
    createdAt: string;
  } | null>(null);
  const [dashboardStats, setDashboardStats] = useState<{
    technicianStatus: string | null;
    totalCompleted: number;
  } | null>(null);

  useEffect(() => {
    getTechnicianDashboard()
      .then(({ data }) => {
        setDashboardStats({
          technicianStatus: data.technician_status || null,
          totalCompleted: data.total_completed ?? 0,
        });
      })
      .catch(() => {
        setDashboardStats(null);
      });
  }, []);

  useEffect(() => {
    if (activeProfileTab !== "history" || historyJobs.length > 0) return;

    setHistoryLoading(true);
    setHistoryError("");
    getTechnicianJobHistory()
      .then((response) => {
        setHistoryJobs(
          Array.isArray(response.data) ? response.data : [],
        );
      })
      .catch(() => {
        setHistoryError("Unable to load job history. Please try again later.");
      })
      .finally(() => setHistoryLoading(false));
  }, [activeProfileTab, historyJobs.length]);

  useEffect(() => {
    getTechnicianProfile()
      .then((res) => {
        const p = res.data;
        if (p.profile_completed) {
          setIsNew(false);
          setProfileMetadata({
            id: String(p.id || ""),
            createdAt: String(p.created_at || ""),
          });
          const profileForm = {
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
          };
          setForm(profileForm);
          setSavedForm(profileForm);
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
      setSavedForm(form);
      setIsEditing(false);
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

  if (!isNew && !isEditing) {
    const skills = form.skills.split(",").map((skill) => skill.trim()).filter(Boolean);
    const certifications = form.certifications
      .split(",")
      .map((certification) => certification.trim())
      .filter(Boolean);
    const fullName = form.full_name || "Technician";
    const initials = fullName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0].toUpperCase())
      .join("");
    const formattedDob = form.date_of_birth
      ? new Date(`${form.date_of_birth}T00:00:00`).toLocaleDateString()
      : "";
    const formattedJoinedDate = profileMetadata?.createdAt
      ? new Date(profileMetadata.createdAt).toLocaleDateString(undefined, {
          day: "numeric",
          month: "short",
          year: "numeric",
        })
      : "Not available";
    const normalizedStatus = dashboardStats?.technicianStatus?.replace(
      /_/g,
      " ",
    );
    const formattedStatus = normalizedStatus
      ? normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1)
      : "Status unavailable";
    const beginEditing = () => {
      setError("");
      setSuccess("");
      setIsEditing(true);
    };
    const formatJobDate = (value?: string | null) => {
      if (!value) return "Date unavailable";
      const date = new Date(value);
      return Number.isNaN(date.getTime())
        ? "Date unavailable"
        : date.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
          });
    };

    return (
      <div style={{ height: "100%", overflowY: "auto", background: "#F3F8FC", padding: 22, boxSizing: "border-box", fontFamily: "'Inter', sans-serif" }}>
        <style>{`
          .technician-profile-layout { display: grid; grid-template-columns: minmax(260px, 310px) minmax(0, 1fr); gap: 18px; max-width: 1440px; margin: 0 auto; align-items: start; }
          .technician-profile-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 24px; }
          @media (max-width: 760px) {
            .technician-profile-layout { grid-template-columns: minmax(0, 1fr); }
            .technician-profile-fields { grid-template-columns: minmax(0, 1fr); }
          }
        `}</style>
        {onNavigate && (
          <div style={{ maxWidth: 1440, margin: "0 auto 14px" }}>
            <button
              type="button"
              onClick={() => onNavigate("tech_dashboard")}
              style={{ display: "inline-flex", alignItems: "center", gap: 7, border: 0, padding: "4px 0", background: "transparent", color: "#078A72", fontSize: 13, fontWeight: 700, cursor: "pointer" }}
            >
              <ArrowLeft size={16} /> Back to Dashboard
            </button>
          </div>
        )}
        <div className="technician-profile-layout">
          <section style={{ background: "#FFFFFF", border: "1px solid #E5EDF3", borderRadius: 12, padding: 24, boxShadow: "0 2px 8px rgba(31, 65, 93, 0.05)", textAlign: "center" }}>
            <div style={{ display: "flex", justifyContent: "flex-end", margin: "-6px -4px 10px" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 999, background: dashboardStats?.technicianStatus ? "#E8F8F1" : "#F1F5F9", color: dashboardStats?.technicianStatus ? "#078A4D" : "#64748B", padding: "5px 10px", fontSize: 11, fontWeight: 700 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: dashboardStats?.technicianStatus ? "#10B981" : "#94A3B8" }} />
                {formattedStatus}
              </span>
            </div>
            <div style={{ width: 96, height: 96, margin: "0 auto 12px", borderRadius: "50%", background: "#DDF5EC", color: "#078A4D", display: "grid", placeItems: "center", fontSize: 30, fontWeight: 700, overflow: "hidden" }}>
              {initials || <User size={38} />}
              {form.profile_photo && (
                <img
                  src={form.profile_photo}
                  alt={`${fullName} profile`}
                  onError={(event) => {
                    event.currentTarget.style.display = "none";
                  }}
                  style={{ width: "100%", height: "100%", objectFit: "cover", gridArea: "1 / 1" }}
                />
              )}
            </div>
            <h1 style={{ margin: "0 0 4px", color: "#173B4A", fontSize: 22, fontWeight: 700 }}>{fullName}</h1>
            <div style={{ color: "#52627E", fontSize: 14 }}>Technician</div>

            <div style={{ display: "flex", justifyContent: "center", gap: 12, margin: "22px 0" }}>
              {[
                { icon: <Wrench size={18} />, value: skills[0] || "Skills not added", label: "Service skill" },
                { icon: <MapPin size={18} />, value: form.city || "Location not added", label: "Location" },
                { icon: <Award size={18} />, value: dashboardStats ? String(dashboardStats.totalCompleted) : "—", label: "Completed jobs" },
              ].map((item) => (
                <div key={item.label} style={{ flex: 1, minWidth: 0, color: "#078A4D", display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
                  <span style={{ width: 40, height: 40, borderRadius: "50%", background: "#E8F8F1", display: "grid", placeItems: "center" }}>{item.icon}</span>
                  <span style={{ color: "#24425A", fontSize: 13, fontWeight: 700, lineHeight: 1.35, overflowWrap: "anywhere" }}>{item.value}</span>
                  <span style={{ color: "#71819A", fontSize: 10, lineHeight: 1.25 }}>{item.label}</span>
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={beginEditing}
              style={{ width: "100%", minHeight: 42, border: 0, borderRadius: 8, background: "#078A4D", color: "#FFFFFF", fontSize: 14, fontWeight: 700, cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8 }}
            >
              <Pencil size={15} /> Edit Profile Information
            </button>

            <div style={{ borderTop: "1px solid #E8EEF3", marginTop: 20, paddingTop: 8, textAlign: "left", display: "grid", gap: 0 }}>
              {[
                { icon: <Phone size={17} />, value: form.mobile_number },
                { icon: <Mail size={17} />, value: user?.email || "" },
                { icon: <MapPin size={17} />, value: [form.city, form.state].filter(Boolean).join(", ") },
                { icon: <CalendarDays size={17} />, value: `Joined ${formattedJoinedDate}` },
              ].map((item, index) => (
                <div key={index} style={{ minHeight: 38, display: "flex", alignItems: "center", gap: 12, color: "#52627E", fontSize: 13, overflowWrap: "anywhere" }}>
                  <span style={{ color: "#3785A0", flexShrink: 0 }}>{item.icon}</span>
                  <span>{item.value || "Not provided"}</span>
                </div>
              ))}
            </div>
          </section>

          <section style={{ background: "#FFFFFF", border: "1px solid #E5EDF3", borderRadius: 12, overflow: "hidden", boxShadow: "0 2px 8px rgba(31, 65, 93, 0.04)", minWidth: 0 }}>
            <nav aria-label="Technician profile sections" style={{ display: "flex", overflowX: "auto", borderBottom: "1px solid #E8EEF3", padding: "0 14px" }}>
              {profileTabs.map((tab) => {
                const Icon = tab.icon;
                const selected = activeProfileTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    aria-current={selected ? "page" : undefined}
                    onClick={() => setActiveProfileTab(tab.id)}
                    style={{ flex: "0 0 auto", display: "inline-flex", alignItems: "center", gap: 9, padding: "16px 14px 13px", border: 0, borderBottom: selected ? "3px solid #078A72" : "3px solid transparent", background: "transparent", color: selected ? "#078A72" : "#71819A", fontWeight: selected ? 700 : 500, fontSize: 13, whiteSpace: "nowrap", cursor: "pointer" }}
                  >
                    <Icon size={17} /> {tab.label}
                  </button>
                );
              })}
            </nav>

            <div style={{ padding: 16, display: "grid", gap: 14 }}>
              {activeProfileTab === "personal" && (
                <>
                  <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, overflow: "hidden" }}>
                    <div style={{ padding: "14px 16px", borderBottom: "1px solid #E8EEF3", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                      <h2 style={{ margin: 0, color: "#24425A", fontSize: 15, display: "flex", alignItems: "center", gap: 10 }}>
                        <User size={18} color="#078A8A" /> Personal Details
                      </h2>
                      <button type="button" onClick={beginEditing} aria-label="Edit personal details" style={{ border: 0, padding: 4, background: "transparent", color: "#078A8A", cursor: "pointer", display: "flex" }}><Pencil size={16} /></button>
                    </div>
                    <div className="technician-profile-fields" style={{ padding: 18 }}>
                      <DetailField label="Full Name" value={form.full_name} />
                      <DetailField label="Email Address" value={user?.email || ""} />
                      <DetailField label="Mobile Number" value={form.mobile_number} />
                      <DetailField label="Gender" value={form.gender} />
                      <DetailField label="Date of Birth" value={formattedDob} />
                      {age !== null && <DetailField label="Age" value={`${age} years`} />}
                    </div>
                  </section>

                  <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, overflow: "hidden" }}>
                    <div style={{ padding: "14px 16px", borderBottom: "1px solid #E8EEF3", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                      <h2 style={{ margin: 0, color: "#24425A", fontSize: 15, display: "flex", alignItems: "center", gap: 10 }}>
                        <MapPin size={18} color="#078A8A" /> Address &amp; Location
                      </h2>
                      <button type="button" onClick={beginEditing} aria-label="Edit address and location" style={{ border: 0, padding: 4, background: "transparent", color: "#078A8A", cursor: "pointer", display: "flex" }}><Pencil size={16} /></button>
                    </div>
                    <div className="technician-profile-fields" style={{ padding: 18 }}>
                      <DetailField label="Street Address" value={form.address} />
                      <DetailField label="City" value={form.city} />
                      <DetailField label="State" value={form.state} />
                      <DetailField label="Pincode" value={form.pincode} />
                    </div>
                  </section>

                  <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, overflow: "hidden" }}>
                    <div style={{ padding: "14px 16px", borderBottom: "1px solid #E8EEF3", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                      <h2 style={{ margin: 0, color: "#24425A", fontSize: 15, display: "flex", alignItems: "center", gap: 10 }}>
                        <Briefcase size={18} color="#078A8A" /> Employment Details
                      </h2>
                      <button type="button" onClick={beginEditing} aria-label="Edit employment details" style={{ border: 0, padding: 4, background: "transparent", color: "#078A8A", cursor: "pointer", display: "flex" }}><Pencil size={16} /></button>
                    </div>
                    <div className="technician-profile-fields" style={{ padding: 18 }}>
                      <DetailField label="Service Skills" value={skills.join(", ")} />
                      <DetailField label="Experience" value={form.experience} />
                      <DetailField label="Joined" value={formattedJoinedDate} />
                      <DetailField label="Status" value={formattedStatus} />
                    </div>
                  </section>

                  <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, overflow: "hidden" }}>
                    <div style={{ padding: "14px 16px", borderBottom: "1px solid #E8EEF3", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                      <h2 style={{ margin: 0, color: "#24425A", fontSize: 15, display: "flex", alignItems: "center", gap: 10 }}>
                        <Phone size={18} color="#078A8A" /> Emergency Contact
                      </h2>
                      <button type="button" onClick={beginEditing} aria-label="Edit emergency contact" style={{ border: 0, padding: 4, background: "transparent", color: "#078A8A", cursor: "pointer", display: "flex" }}><Pencil size={16} /></button>
                    </div>
                    <div className="technician-profile-fields" style={{ padding: 18 }}>
                      <DetailField label="Contact Name" value="" />
                      <DetailField label="Contact Number" value={form.emergency_contact} />
                      <DetailField label="Relationship" value="" />
                    </div>
                  </section>
                </>
              )}

              {activeProfileTab === "skills" && (
                <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, overflow: "hidden" }}>
                  <h2 style={{ margin: 0, padding: "14px 16px", borderBottom: "1px solid #E8EEF3", color: "#24425A", fontSize: 15, display: "flex", alignItems: "center", gap: 10 }}>
                    <Award size={18} color="#078A8A" /> Skills &amp; Certifications
                  </h2>
                  <div style={{ padding: 18, display: "grid", gap: 22 }}>
                    <div>
                      <h3 style={{ margin: "0 0 12px", color: "#52627E", fontSize: 13 }}>Service Skills</h3>
                      {skills.length ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 9 }}>
                          {skills.map((skill) => (
                            <span key={skill} style={{ borderRadius: 999, background: "#E8F8F1", color: "#087A51", padding: "8px 13px", fontSize: 13, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 7 }}>
                              <Wrench size={14} /> {skill}
                            </span>
                          ))}
                        </div>
                      ) : <p style={{ margin: 0, color: "#71819A", fontSize: 13 }}>No skills have been added to your profile yet.</p>}
                    </div>
                    <div>
                      <h3 style={{ margin: "0 0 12px", color: "#52627E", fontSize: 13 }}>Certifications</h3>
                      {certifications.length ? (
                        <div style={{ display: "grid", gap: 10 }}>
                          {certifications.map((certification) => (
                            <div key={certification} style={{ display: "flex", alignItems: "center", gap: 10, color: "#243B53", fontSize: 14 }}>
                              <Award size={17} color="#078A8A" /> {certification}
                            </div>
                          ))}
                        </div>
                      ) : <p style={{ margin: 0, color: "#71819A", fontSize: 13 }}>No certifications have been added to your profile yet.</p>}
                    </div>
                    <DetailField label="Experience" value={form.experience} />
                  </div>
                </section>
              )}

              {activeProfileTab === "history" && (
                <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, overflow: "hidden" }}>
                  <h2 style={{ margin: 0, padding: "14px 16px", borderBottom: "1px solid #E8EEF3", color: "#24425A", fontSize: 15, display: "flex", alignItems: "center", gap: 10 }}>
                    <History size={18} color="#078A8A" /> Job History
                  </h2>
                  {historyLoading ? (
                    <p role="status" style={{ margin: 0, padding: 24, color: "#71819A", fontSize: 13 }}>Loading job history...</p>
                  ) : historyError ? (
                    <p role="alert" style={{ margin: 0, padding: 24, color: "#B42318", fontSize: 13 }}>{historyError}</p>
                  ) : historyJobs.length === 0 ? (
                    <p style={{ margin: 0, padding: 24, color: "#71819A", fontSize: 13 }}>No job history is available yet.</p>
                  ) : (
                    <div style={{ display: "grid" }}>
                      {historyJobs.map((job) => (
                        <article key={job.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "15px 18px", borderBottom: "1px solid #EEF2F6" }}>
                          <div style={{ minWidth: 0 }}>
                            <strong style={{ display: "block", color: "#243B53", fontSize: 14 }}>#{job.id} — {job.service_type || "Service job"}</strong>
                            <span style={{ display: "block", color: "#71819A", fontSize: 12, marginTop: 5, overflowWrap: "anywhere" }}>{job.location || job.site_address || job.customer_name || "Location not provided"}</span>
                          </div>
                          <div style={{ flexShrink: 0, textAlign: "right" }}>
                            <span style={{ display: "block", color: "#52627E", fontSize: 12 }}>{String(job.status || "Completed").replaceAll("_", " ")}</span>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "#71819A", fontSize: 11, marginTop: 5 }}>
                              <Clock3 size={12} /> {formatJobDate(job.rejected_at || job.completed_at)}
                            </span>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {activeProfileTab === "documents" && (
                <section style={{ border: "1px solid #E5EDF3", borderRadius: 10, padding: 34, textAlign: "center", color: "#71819A" }}>
                  <FileText size={30} color="#078A8A" style={{ marginBottom: 10 }} />
                  <h2 style={{ margin: "0 0 7px", color: "#24425A", fontSize: 16 }}>Documents</h2>
                  <p style={{ margin: 0, fontSize: 13 }}>No documents have been added to your profile yet.</p>
                </section>
              )}
            </div>
          </section>
        </div>
      </div>
    );
  }

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
            justifyContent: "space-between",
          }}
        >
          {!isNew && (
            <button
              type="button"
              style={{ ...s.btn, background: "#EEF4F1", color: "#52627E" }}
              onClick={() => {
                setForm(savedForm);
                setError("");
                setSuccess("");
                setIsEditing(false);
              }}
            >
              Cancel
            </button>
          )}
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
