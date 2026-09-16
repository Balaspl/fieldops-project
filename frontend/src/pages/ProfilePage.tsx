import { useState, useEffect, useRef } from "react";
import {
  User,
  Building2,
  UserPlus,
  Shield,
  Mail,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Server,
  X,
  Edit3,
  Key,
  Save,
  Lock,
} from "lucide-react";
import useAuthStore from "../store/authStore";
import api from "../services/api";

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

interface OrganizationItem {
  id: string;
  name: string;
  slug: string;
  status: string;
  subscription_plan: string;
  max_users: number;
  max_technicians: number;
  contact_email: string | null;
  user_count?: number;
  created_at: string;
}

interface ToastNotice {
  id: string;
  type: "success" | "error";
  message: string;
}

export default function ProfilePage() {
  const { user, updateUser } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"profile" | "orgs" | "users">(
    "profile",
  );

  // Toast notifications state
  const [toasts, setToasts] = useState<ToastNotice[]>([]);

  const addPopToast = (type: "success" | "error", message: string) => {
    const id = Math.random().toString(36).slice(2, 9);
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // State for Name Edit
  const [firstName, setFirstName] = useState(user?.first_name || "");
  const [lastName, setLastName] = useState(user?.last_name || "");
  const [isUpdatingName, setIsUpdatingName] = useState(false);

  // State for Password Change
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  // Google OIDC Account Linking
  const googleButtonRef = useRef<HTMLDivElement | null>(null);
  const [linkingGoogle, setLinkingGoogle] = useState(false);

  // Multi-Factor Authentication (MFA)
  const [mfaStatus, setMfaStatus] = useState<{
    status: string;
    mfa_required: boolean;
    enrolled: boolean;
    enabled: boolean;
  } | null>(null);
  const [mfaSetup, setMfaSetup] = useState<{
    provisioning_uri: string;
    secret: string;
  } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [isEnablingMfa, setIsEnablingMfa] = useState(false);
  const [isVerifyingMfa, setIsVerifyingMfa] = useState(false);

  // State for Organization Creation
  const [orgName, setOrgName] = useState("");
  const [orgEmail, setOrgEmail] = useState("");
  const [orgPlan, setOrgPlan] = useState("PROFESSIONAL");
  const [maxUsers, setMaxUsers] = useState(25);
  const [maxTechs, setMaxTechs] = useState(100);
  const [isSubmittingOrg, setIsSubmittingOrg] = useState(false);

  // State for User Creation
  const [selectedOrgId, setSelectedOrgId] = useState(
    user?.tenant_id || "tenant-1",
  );
  const [userEmail, setUserEmail] = useState("");
  const [userPassword, setUserPassword] = useState("");
  const [userFirstName, setUserFirstName] = useState("");
  const [userLastName, setUserLastName] = useState("");
  const [userRole, setUserRole] = useState("dispatcher");
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);

  // Organizations list
  const [orgs, setOrgs] = useState<OrganizationItem[]>([]);
  const [isLoadingOrgs, setIsLoadingOrgs] = useState(false);
  const [organizationName, setOrganizationName] = useState("");

  const isSuperAdmin = user?.role === "super_admin";
  const isAdmin = user?.role === "admin" || isSuperAdmin;
  const isDispatcher = user?.role === "dispatcher";
  const mfaSupportedRoles = ["technician", "dispatcher", "admin", "super_admin"];
  const canUseMFA = mfaSupportedRoles.includes((user?.role || "").toLowerCase());

  useEffect(() => {
    if (user) {
      setFirstName(user.first_name || "");
      setLastName(user.last_name || "");
    }
  }, [user]);

  const fetchOrganizations = async () => {
    if (!isAdmin) return;
    setIsLoadingOrgs(true);
    try {
      const response = await api.get("/organizations");
      setOrgs(response.data?.data || []);
      if (response.data?.data?.length > 0 && !selectedOrgId) {
        setSelectedOrgId(response.data.data[0].id);
      }
    } catch {
      // Fallback
    } finally {
      setIsLoadingOrgs(false);
    }
  };
  const fetchCurrentOrganization = async () => {
    if (!user?.tenant_id || user.tenant_id === "__platform__") return;

    try {
      const response = await api.get("/organizations/current");
      setOrganizationName(response.data?.name || "");
    } catch {
      setOrganizationName("");
    }
  };

  useEffect(() => {
    if (isAdmin) {
      fetchOrganizations();
    }

    fetchCurrentOrganization();
  }, [isAdmin, user?.tenant_id]);

  const handleUpdateName = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firstName.trim() || !lastName.trim()) {
      addPopToast("error", "First name and last name cannot be empty.");
      return;
    }

    setIsUpdatingName(true);
    try {
      const response = await api.put("/auth/profile", {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });

      updateUser({
        first_name: response.data.first_name,
        last_name: response.data.last_name,
      });

      addPopToast("success", "Profile name updated successfully!");
    } catch (err: any) {
      addPopToast(
        "error",
        err.response?.data?.detail || "Failed to update profile name.",
      );
    } finally {
      setIsUpdatingName(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      addPopToast("error", "New password and confirm password do not match.");
      return;
    }

    setIsChangingPassword(true);
    try {
      await api.put("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });

      addPopToast("success", "Password changed successfully!");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : detail?.errors
            ? detail.errors.join(", ")
            : "Failed to change password.";
      addPopToast("error", msg);
    } finally {
      setIsChangingPassword(false);
    }
  };
  const handleGoogleCredential = async (
  response: { credential: string }
) => {
  if (!response.credential) {
    addPopToast(
      "error",
      "Google did not return an ID token."
    );
    return;
  }

  setLinkingGoogle(true);

  try {
    const result = await api.post(
      "/auth/oidc/google/link",
      {
        id_token: response.credential,
      }
    );

    if (result.data.status === "ALREADY_LINKED") {
      addPopToast(
        "success",
        "Google account is already linked."
      );
    } else {
      addPopToast(
        "success",
        "Google account linked successfully."
      );
    }
  } catch (err: any) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;

    if (status === 409) {
      addPopToast(
        "error",
        typeof detail === "string"
          ? detail
          : "This Google account is already linked to another FieldOps account."
      );
    } else if (status === 401) {
      addPopToast(
        "error",
        typeof detail === "string"
          ? detail
          : "Invalid Google identity. Please try again."
      );
    } else {
      addPopToast(
        "error",
        typeof detail === "string"
          ? detail
          : "Failed to link Google account."
      );
    }
  } finally {
    setLinkingGoogle(false);
  }
};
  useEffect(() => {
  if (activeTab !== "profile") {
    return;
  }

  const clientId =
    import.meta.env.VITE_GOOGLE_CLIENT_ID;

  if (!clientId) {
    addPopToast(
      "error",
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

  const fetchMfaStatus = async () => {
    if (!canUseMFA) return;

    try {
      const response = await api.get("/auth/mfa/status");
      setMfaStatus(response.data);
    } catch (err) {
      console.error("Failed to fetch MFA status", err);
    }
  };

  const handleEnableMfa = async () => {
    setIsEnablingMfa(true);

    try {
      const response = await api.post("/auth/mfa/enroll");

      setMfaSetup({
        provisioning_uri: response.data.provisioning_uri,
        secret: response.data.secret,
      });
      setMfaCode("");

      addPopToast(
        "success",
        "MFA setup started. Scan the QR code with your authenticator app.",
      );
    } catch (err: any) {
      addPopToast(
        "error",
        err.response?.data?.detail || "Failed to start MFA setup.",
      );
    } finally {
      setIsEnablingMfa(false);
    }
  };

  const handleVerifyMfaEnrollment = async () => {
    if (!/^\d{6}$/.test(mfaCode)) {
      addPopToast("error", "Enter a valid 6-digit authentication code.");
      return;
    }

    setIsVerifyingMfa(true);

    try {
      const response = await api.post("/auth/mfa/enroll/verify", {
        code: mfaCode,
      });

      setRecoveryCodes(response.data.recovery_codes || []);
      setMfaSetup(null);
      setMfaCode("");

      await fetchMfaStatus();

      addPopToast(
        "success",
        "MFA enabled successfully. It cannot be disabled by the user.",
      );
    } catch (err: any) {
      addPopToast(
        "error",
        err.response?.data?.detail || "Invalid MFA code.",
      );
    } finally {
      setIsVerifyingMfa(false);
    }
  };

  useEffect(() => {
    if (activeTab === "profile" && canUseMFA) {
      fetchMfaStatus();
    }
  }, [activeTab, user?.role]);

  const handleCreateOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmittingOrg(true);

    try {
      const response = await api.post("/organizations", {
        name: orgName,
        contact_email: orgEmail || undefined,
        subscription_plan: orgPlan,
        max_users: Number(maxUsers),
        max_technicians: Number(maxTechs),
      });

      addPopToast(
        "success",
        `Organization "${response.data.name}" created successfully! (ID: ${response.data.id})`,
      );
      setOrgName("");
      setOrgEmail("");
      fetchOrganizations();
    } catch (err: any) {
      addPopToast(
        "error",
        err.response?.data?.detail || "Failed to create organization.",
      );
    } finally {
      setIsSubmittingOrg(false);
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmittingUser(true);

    const targetOrgId = selectedOrgId || user?.tenant_id || "tenant-1";

    try {
      const response = await api.post(`/organizations/${targetOrgId}/admin`, {
        email: userEmail,
        password: userPassword,
        first_name: userFirstName,
        last_name: userLastName,
        role: userRole,
      });

      addPopToast(
        "success",
        `User "${response.data.email}" provisioned as ${userRole.toUpperCase()} under organization ${targetOrgId}`,
      );
      setUserEmail("");
      setUserPassword("");
      setUserFirstName("");
      setUserLastName("");
      fetchOrganizations();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : detail?.errors
            ? detail.errors.join(", ")
            : "Failed to provision user account.";
      addPopToast("error", msg);
    } finally {
      setIsSubmittingUser(false);
    }
  };

  return (
    <div
      style={{
        height: "100%",
        maxHeight: "100%",
        width: "100%",
        overflow: "hidden",
        background: "#EEF4F1",
        padding: "16px 24px",
        boxSizing: "border-box",
        fontFamily: "'Inter', sans-serif",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
        position: "relative",
      }}
    >
      {/* Floating Pop-up Toast Container */}
      <div
        style={{
          position: "fixed",
          top: "20px",
          right: "20px",
          zIndex: 99999,
          display: "flex",
          flexDirection: "column",
          gap: "8px",
          maxWidth: "400px",
          pointerEvents: "none",
        }}
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            style={{
              pointerEvents: "auto",
              padding: "12px 16px",
              borderRadius: "10px",
              background: toast.type === "success" ? "#F0FDF4" : "#FEF2F2",
              border: `1px solid ${toast.type === "success" ? "#86EFAC" : "#FCA5A5"}`,
              color: toast.type === "success" ? "#166534" : "#991B1B",
              boxShadow: "0 8px 20px rgba(0, 0, 0, 0.08)",
              display: "flex",
              alignItems: "flex-start",
              gap: "10px",
              fontSize: "12px",
              lineHeight: "1.4",
              fontWeight: 500,
              animation: "slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          >
            {toast.type === "success" ? (
              <CheckCircle
                size={16}
                color="#166534"
                style={{ flexShrink: 0, marginTop: 1 }}
              />
            ) : (
              <AlertCircle
                size={16}
                color="#991B1B"
                style={{ flexShrink: 0, marginTop: 1 }}
              />
            )}
            <div style={{ flex: 1 }}>{toast.message}</div>
            <button
              onClick={() => removeToast(toast.id)}
              style={{
                background: "none",
                border: "none",
                color: "inherit",
                cursor: "pointer",
                padding: "2px",
                opacity: 0.6,
                display: "flex",
                alignItems: "center",
              }}
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>

      <style>{`
        @keyframes slideInRight {
          from {
            opacity: 0;
            transform: translateX(40px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
      `}</style>

      {/* 1. Top Header Banner */}
      <div
        style={{
          background: "#FFFFFF",
          borderRadius: "12px",
          padding: "12px 20px",
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
              width: "42px",
              height: "42px",
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
            {user?.first_name ? user.first_name[0].toUpperCase() : "U"}
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
                {user?.first_name} {user?.last_name}
              </h1>
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 700,
                  padding: "2px 6px",
                  borderRadius: "4px",
                  background: "#EAF4EE",
                  color: "#2F4F3E",
                  textTransform: "uppercase",
                }}
              >
                {user?.role?.replace("_", " ")}
              </span>
            </div>
            <span
              style={{ fontSize: "12px", color: "#5C9470", fontWeight: 500 }}
            >
              {user?.email}
            </span>
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <span
            style={{ fontSize: "11px", color: "#5C9470", display: "block" }}
          >
            Organization
          </span>

          <span style={{ fontSize: "13px", fontWeight: 700, color: "#2F4F3E" }}>
            {organizationName}
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
            padding: "6px 14px",
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
          <User size={14} /> Profile & Edit
        </button>

        {isAdmin && (
          <button
            onClick={() => setActiveTab("orgs")}
            style={{
              padding: "6px 14px",
              borderRadius: "7px",
              fontSize: "12px",
              fontWeight: 600,
              border: "none",
              background: activeTab === "orgs" ? "#2F4F3E" : "transparent",
              color: activeTab === "orgs" ? "#FFFFFF" : "#5C9470",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              transition: "all 0.2s ease",
            }}
          >
            <Building2 size={14} /> Organizations ({orgs.length})
          </button>
        )}

        {(isAdmin || isDispatcher) && (
          <button
            onClick={() => setActiveTab("users")}
            style={{
              padding: "6px 14px",
              borderRadius: "7px",
              fontSize: "12px",
              fontWeight: 600,
              border: "none",
              background: activeTab === "users" ? "#2F4F3E" : "transparent",
              color: activeTab === "users" ? "#FFFFFF" : "#5C9470",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              transition: "all 0.2s ease",
            }}
          >
            <UserPlus size={14} /> User Provisioning
          </button>
        )}
      </div>

      {/* 3. Main Content View Area (Fits 100% height, No outer page scrollbar) */}
      {activeTab === "profile" && (
        <div
          style={{
            flex: 1,
            display: "grid",
            gridTemplateColumns: "1.1fr 1fr",
            gap: "16px",
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {/* Left Column: Account Attributes & Edit Name */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "14px",
              minHeight: 0,
            }}
          >
            {/* Account Attributes */}
            <div
              style={{
                background: "#FFFFFF",
                borderRadius: "12px",
                border: "1px solid #E3ECE7",
                padding: "16px 20px",
                boxShadow: "0 1px 4px rgba(47, 79, 62, 0.02)",
              }}
            >
              <h2
                style={{
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  margin: "0 0 12px",
                }}
              >
                Account Attributes
              </h2>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "10px",
                }}
              >
                <div
                  style={{
                    padding: "10px 12px",
                    background: "#F3F8F5",
                    borderRadius: "8px",
                    border: "1px solid #E3ECE7",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      color: "#5C9470",
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                    }}
                  >
                    <Mail size={12} /> Registered Email
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      display: "block",
                      marginTop: "2px",
                      wordBreak: "break-all",
                    }}
                  >
                    {user?.email}
                  </span>
                </div>

                <div
                  style={{
                    padding: "10px 12px",
                    background: "#F3F8F5",
                    borderRadius: "8px",
                    border: "1px solid #E3ECE7",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      color: "#5C9470",
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                    }}
                  >
                    <Building2 size={12} /> Organization
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      display: "block",
                      marginTop: "2px",
                      wordBreak: "break-all",
                    }}
                  >
                    {organizationName}
                  </span>
                </div>

                <div
                  style={{
                    padding: "10px 12px",
                    background: "#F3F8F5",
                    borderRadius: "8px",
                    border: "1px solid #E3ECE7",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      color: "#5C9470",
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                    }}
                  >
                    <Shield size={12} /> Assigned Role
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      display: "block",
                      marginTop: "2px",
                      textTransform: "capitalize",
                    }}
                  >
                    {user?.role?.replace("_", " ")}
                  </span>
                </div>

                <div
                  style={{
                    padding: "10px 12px",
                    background: "#F3F8F5",
                    borderRadius: "8px",
                    border: "1px solid #E3ECE7",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      color: "#5C9470",
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                    }}
                  >
                    <Server size={12} /> Status
                  </span>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      marginTop: "2px",
                    }}
                  >
                    <CheckCircle size={12} color="#2F4F3E" /> Signed in (JWT)
                  </span>
                </div>
              </div>
            </div>

            {/* Edit Profile Name */}
            <div
              style={{
                background: "#FFFFFF",
                borderRadius: "12px",
                border: "1px solid #E3ECE7",
                padding: "16px 20px",
                boxShadow: "0 1px 4px rgba(47, 79, 62, 0.02)",
              }}
            >
              <h2
                style={{
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  margin: "0 0 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <Edit3 size={15} /> Edit Profile Name
              </h2>

              <form
                onSubmit={handleUpdateName}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "10px",
                }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "10px",
                  }}
                >
                  <div>
                    <label
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        color: "#2F4F3E",
                        display: "block",
                        marginBottom: "3px",
                      }}
                    >
                      First Name *
                    </label>
                    <input
                      type="text"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      required
                      style={{
                        width: "100%",
                        padding: "7px 10px",
                        border: "1px solid #E3ECE7",
                        borderRadius: "7px",
                        fontSize: "12px",
                        background: "#F9FAF9",
                        color: "#2F4F3E",
                        outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        color: "#2F4F3E",
                        display: "block",
                        marginBottom: "3px",
                      }}
                    >
                      Last Name *
                    </label>
                    <input
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      required
                      style={{
                        width: "100%",
                        padding: "7px 10px",
                        border: "1px solid #E3ECE7",
                        borderRadius: "7px",
                        fontSize: "12px",
                        background: "#F9FAF9",
                        color: "#2F4F3E",
                        outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isUpdatingName}
                  style={{
                    padding: "8px 14px",
                    background: "#2F4F3E",
                    color: "#FFFFFF",
                    border: "none",
                    borderRadius: "7px",
                    fontSize: "12px",
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    width: "fit-content",
                    boxShadow: "0 2px 5px rgba(47, 79, 62, 0.12)",
                    marginTop: "2px",
                  }}
                >
                  <Save size={13} />
                  {isUpdatingName ? "Saving..." : "Save Profile Name"}
                </button>
              </form>
            </div>
          </div>

          {/* Right Column: Change Password */}
<div
  style={{
    background: "#FFFFFF",
    borderRadius: "12px",
    border: "1px solid #E3ECE7",
    padding: "12px 20px",
    boxShadow: "0 1px 4px rgba(47, 79, 62, 0.02)",
    display: "flex",
    flexDirection: "column",
    height: "fit-content",
    maxHeight: "100%",
    overflowY: "auto",
    boxSizing: "border-box",
  }}
>
  {/* Change Password Heading */}
  <h2
    style={{
      fontSize: "14px",
      fontWeight: 700,
      color: "#2F4F3E",
      margin: "0 0 8px",
      display: "flex",
      alignItems: "center",
      gap: "6px",
    }}
  >
    <Lock size={15} /> Change Password
  </h2>

  {/* Change Password Form */}
  <form
    onSubmit={handleChangePassword}
    style={{
      display: "flex",
      flexDirection: "column",
      gap: "6px",
    }}
  >
    {/* Current Password */}
    <div>
      <label
        style={{
          fontSize: "11px",
          fontWeight: 700,
          color: "#2F4F3E",
          display: "block",
          marginBottom: "3px",
        }}
      >
        Current Password *
      </label>

      <input
        type="password"
        placeholder="Enter current password"
        value={currentPassword}
        onChange={(e) => setCurrentPassword(e.target.value)}
        required
        style={{
          width: "100%",
          padding: "6px 10px",
          border: "1px solid #E3ECE7",
          borderRadius: "7px",
          fontSize: "12px",
          background: "#F9FAF9",
          color: "#2F4F3E",
          outline: "none",
          boxSizing: "border-box",
        }}
      />
    </div>

    {/* New Password */}
    <div>
      <label
        style={{
          fontSize: "11px",
          fontWeight: 700,
          color: "#2F4F3E",
          display: "block",
          marginBottom: "3px",
        }}
      >
        New Password * (min 8 chars, 1 upper, 1 lower, 1 digit, 1
        special)
      </label>

      <input
        type="password"
        placeholder="Enter new password"
        value={newPassword}
        onChange={(e) => setNewPassword(e.target.value)}
        required
        style={{
          width: "100%",
          padding: "6px 10px",
          border: "1px solid #E3ECE7",
          borderRadius: "7px",
          fontSize: "12px",
          background: "#F9FAF9",
          color: "#2F4F3E",
          outline: "none",
          boxSizing: "border-box",
        }}
      />
    </div>

    {/* Confirm New Password */}
    <div>
      <label
        style={{
          fontSize: "11px",
          fontWeight: 700,
          color: "#2F4F3E",
          display: "block",
          marginBottom: "3px",
        }}
      >
        Confirm New Password *
      </label>

      <input
        type="password"
        placeholder="Confirm new password"
        value={confirmPassword}
        onChange={(e) => setConfirmPassword(e.target.value)}
        required
        style={{
          width: "100%",
          padding: "6px 10px",
          border: "1px solid #E3ECE7",
          borderRadius: "7px",
          fontSize: "12px",
          background: "#F9FAF9",
          color: "#2F4F3E",
          outline: "none",
          boxSizing: "border-box",
        }}
      />
    </div>

    {/* Update Password Button */}
    <button
      type="submit"
      disabled={isChangingPassword}
      style={{
        padding: "8px 16px",
        background: "#2F4F3E",
        color: "#FFFFFF",
        border: "none",
        borderRadius: "7px",
        fontSize: "12px",
        fontWeight: 700,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "6px",
        marginTop: "3px",
        boxShadow: "0 2px 5px rgba(47, 79, 62, 0.12)",
      }}
    >
      <Key size={14} />

      {isChangingPassword
        ? "Updating Password..."
        : "Update Password"}
    </button>
  </form>

  {/* Google Account */}
  <div
    style={{
      marginTop: "10px",
      paddingTop: "10px",
      borderTop: "1px solid #E3ECE7",
    }}
  >
    <h2
      style={{
        fontSize: "14px",
        fontWeight: 700,
        color: "#2F4F3E",
        margin: "0 0 6px",
        display: "flex",
        alignItems: "center",
        gap: "6px",
      }}
    >
      <Shield size={15} />
      Google Account
    </h2>

    <p
      style={{
        fontSize: "12px",
        color: "#6B7280",
        margin: "0 0 8px",
        lineHeight: 1.4,
      }}
    >
      Link your Google account to this existing FieldOps account.
      After linking, you can use Google to sign in.
    </p>

    <div
      ref={googleButtonRef}
      style={{
        minHeight: "40px",
      }}
    />

    {linkingGoogle && (
      <div
        style={{
          marginTop: "6px",
          fontSize: "12px",
          color: "#5C9470",
          fontWeight: 600,
        }}
      >
        Linking Google account...
      </div>
    )}
  </div>

  {/* Multi-Factor Authentication */}
  {canUseMFA && (
    <div
      style={{
        marginTop: "10px",
        paddingTop: "10px",
        borderTop: "1px solid #E3ECE7",
      }}
    >
      <h2
        style={{
          fontSize: "14px",
          fontWeight: 700,
          color: "#2F4F3E",
          margin: "0 0 6px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <Shield size={15} /> Multi-Factor Authentication
      </h2>

      <p
        style={{
          fontSize: "12px",
          color: "#6B7280",
          margin: "0 0 10px",
          lineHeight: 1.4,
        }}
      >
        Add an authenticator app as an additional security step when signing in.
      </p>

      {/* MFA OFF */}
      {mfaStatus && !mfaStatus.enabled && !mfaSetup && (
        <div
          style={{
            padding: "11px",
            background: "#F3F8F5",
            border: "1px solid #E3ECE7",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              fontWeight: 700,
              color: "#2F4F3E",
              marginBottom: "4px",
            }}
          >
            MFA is OFF
          </div>

          <div
            style={{
              fontSize: "11px",
              color: "#6B7280",
              marginBottom: "9px",
              lineHeight: 1.4,
            }}
          >
            Normal email/password login is allowed. Enable MFA to require a
            6-digit authenticator code during future logins.
          </div>

          <button
            type="button"
            onClick={handleEnableMfa}
            disabled={isEnablingMfa}
            style={{
              padding: "8px 14px",
              background: "#2F4F3E",
              color: "#FFFFFF",
              border: "none",
              borderRadius: "7px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: isEnablingMfa ? "not-allowed" : "pointer",
            }}
          >
            {isEnablingMfa ? "Starting..." : "Enable MFA"}
          </button>
        </div>
      )}

      {/* MFA SETUP */}
      {mfaSetup && (
        <div
          style={{
            padding: "11px",
            background: "#F3F8F5",
            border: "1px solid #E3ECE7",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              fontWeight: 700,
              color: "#2F4F3E",
              marginBottom: "5px",
            }}
          >
            Set up your authenticator
          </div>

          <p
            style={{
              fontSize: "11px",
              color: "#6B7280",
              lineHeight: 1.4,
              margin: "0 0 8px",
            }}
          >
            Scan this QR code with Google Authenticator, Microsoft Authenticator,
            or another compatible TOTP app.
          </p>

          <div
            style={{
              display: "flex",
              justifyContent: "center",
              margin: "10px 0",
            }}
          >
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(mfaSetup.provisioning_uri)}`}
              alt="MFA QR Code"
              width={180}
              height={180}
              style={{ borderRadius: "6px" }}
            />
          </div>

          <div
            style={{
              fontSize: "10px",
              color: "#6B7280",
              marginBottom: "8px",
              wordBreak: "break-all",
            }}
          >
            Manual setup key: {mfaSetup.secret}
          </div>

          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="Enter 6-digit code"
            value={mfaCode}
            onChange={(e) =>
              setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            style={{
              width: "100%",
              padding: "8px 10px",
              border: "1px solid #E3ECE7",
              borderRadius: "7px",
              fontSize: "13px",
              boxSizing: "border-box",
              marginBottom: "8px",
              background: "#FFFFFF",
              color: "#2F4F3E",
              outline: "none",
            }}
          />

          <button
            type="button"
            onClick={handleVerifyMfaEnrollment}
            disabled={isVerifyingMfa || mfaCode.length !== 6}
            style={{
              width: "100%",
              padding: "9px",
              background: mfaCode.length === 6 ? "#2F4F3E" : "#A7B9AE",
              color: "#FFFFFF",
              border: "none",
              borderRadius: "7px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: isVerifyingMfa || mfaCode.length !== 6 ? "not-allowed" : "pointer",
            }}
          >
            {isVerifyingMfa ? "Verifying..." : "Verify & Enable MFA"}
          </button>
        </div>
      )}

      {/* MFA ON / LOCKED */}
      {mfaStatus?.enabled && !mfaSetup && (
        <div
          style={{
            padding: "11px",
            background: "#F0FDF4",
            border: "1px solid #86EFAC",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "7px",
              fontSize: "12px",
              fontWeight: 700,
              color: "#166534",
            }}
          >
            <CheckCircle size={15} /> MFA is ON
          </div>

          <div
            style={{
              fontSize: "11px",
              color: "#166534",
              marginTop: "5px",
              lineHeight: 1.4,
            }}
          >
            Future logins will require a 6-digit code from your authenticator app.
          </div>

          <div
            style={{
              marginTop: "8px",
              padding: "7px 9px",
              background: "#DCFCE7",
              borderRadius: "6px",
              fontSize: "10px",
              fontWeight: 600,
              color: "#166534",
            }}
          >
            🔒 MFA is locked after enrollment and cannot be disabled by the user.
          </div>
        </div>
      )}

      {/* Recovery Codes */}
      {recoveryCodes.length > 0 && (
        <div
          style={{
            marginTop: "9px",
            padding: "11px",
            background: "#FFF7ED",
            border: "1px solid #FED7AA",
            borderRadius: "8px",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              fontWeight: 700,
              color: "#9A3412",
              marginBottom: "4px",
            }}
          >
            Save your recovery codes
          </div>

          <div
            style={{
              fontSize: "11px",
              color: "#7C2D12",
              marginBottom: "8px",
              lineHeight: 1.4,
            }}
          >
            These codes are shown after enrollment. Store them somewhere secure.
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "5px",
            }}
          >
            {recoveryCodes.map((code) => (
              <code
                key={code}
                style={{
                  padding: "5px 7px",
                  background: "#FFFFFF",
                  border: "1px solid #FED7AA",
                  borderRadius: "5px",
                  fontSize: "11px",
                  color: "#7C2D12",
                }}
              >
                {code}
              </code>
            ))}
          </div>
        </div>
      )}
    </div>
  )}
</div>
          
        </div>
      )}

      {/* Tab 2: Organizations Creation & List */}
      {activeTab === "orgs" && isAdmin && (
        <div
          style={{
            flex: 1,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "16px",
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {/* Create Form */}
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "12px",
              border: "1px solid #E3ECE7",
              padding: "16px 20px",
              boxShadow: "0 1px 4px rgba(47, 79, 62, 0.02)",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <h2
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: "#2F4F3E",
                margin: "0 0 12px",
              }}
            >
              Provision New Organization
            </h2>

            <form
              onSubmit={handleCreateOrg}
              style={{ display: "flex", flexDirection: "column", gap: "10px" }}
            >
              <div>
                <label
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                    display: "block",
                    marginBottom: "3px",
                  }}
                >
                  Organization Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Acme Field Solutions"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  required
                  style={{
                    width: "100%",
                    padding: "7px 10px",
                    border: "1px solid #E3ECE7",
                    borderRadius: "7px",
                    fontSize: "12px",
                    background: "#F9FAF9",
                    color: "#2F4F3E",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              <div>
                <label
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                    display: "block",
                    marginBottom: "3px",
                  }}
                >
                  Contact Email
                </label>
                <input
                  type="email"
                  placeholder="contact@acme.com"
                  value={orgEmail}
                  onChange={(e) => setOrgEmail(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "7px 10px",
                    border: "1px solid #E3ECE7",
                    borderRadius: "7px",
                    fontSize: "12px",
                    background: "#F9FAF9",
                    color: "#2F4F3E",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "10px",
                }}
              >
                <div>
                  <label
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      display: "block",
                      marginBottom: "3px",
                    }}
                  >
                    Subscription Plan
                  </label>
                  <select
                    value={orgPlan}
                    onChange={(e) => setOrgPlan(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      border: "1px solid #E3ECE7",
                      borderRadius: "7px",
                      fontSize: "12px",
                      background: "#F9FAF9",
                      color: "#2F4F3E",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  >
                    <option value="FREE">FREE</option>
                    <option value="STARTER">STARTER</option>
                    <option value="PROFESSIONAL">PROFESSIONAL</option>
                    <option value="ENTERPRISE">ENTERPRISE</option>
                  </select>
                </div>

                <div>
                  <label
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      color: "#2F4F3E",
                      display: "block",
                      marginBottom: "3px",
                    }}
                  >
                    Max Users
                  </label>
                  <input
                    type="number"
                    value={maxUsers}
                    onChange={(e) => setMaxUsers(Number(e.target.value))}
                    min={1}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      border: "1px solid #E3ECE7",
                      borderRadius: "7px",
                      fontSize: "12px",
                      background: "#F9FAF9",
                      color: "#2F4F3E",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmittingOrg}
                style={{
                  padding: "9px",
                  background: "#2F4F3E",
                  color: "#FFFFFF",
                  border: "none",
                  borderRadius: "7px",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: "pointer",
                  marginTop: "4px",
                  boxShadow: "0 2px 5px rgba(47, 79, 62, 0.15)",
                }}
              >
                {isSubmittingOrg ? "Provisioning..." : "Provision Organization"}
              </button>
            </form>
          </div>

          {/* Org List */}
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "12px",
              border: "1px solid #E3ECE7",
              padding: "16px 20px",
              boxShadow: "0 1px 4px rgba(47, 79, 62, 0.02)",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "12px",
              }}
            >
              <h2
                style={{
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  margin: 0,
                }}
              >
                Organizations ({orgs.length})
              </h2>
              <button
                onClick={fetchOrganizations}
                style={{
                  background: "none",
                  border: "none",
                  color: "#5C9470",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  fontSize: "11px",
                }}
              >
                <RefreshCw size={13} /> Refresh
              </button>
            </div>

            {isLoadingOrgs ? (
              <p style={{ color: "#5C9470", fontSize: "12px" }}>
                Loading organizations...
              </p>
            ) : orgs.length === 0 ? (
              <p style={{ color: "#5C9470", fontSize: "12px" }}>
                No organizations registered.
              </p>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  overflowY: "auto",
                  flex: 1,
                  paddingRight: "4px",
                }}
              >
                {orgs.map((o) => (
                  <div
                    key={o.id}
                    style={{
                      padding: "10px 12px",
                      borderRadius: "8px",
                      border: "1px solid #E3ECE7",
                      background: "#F3F8F5",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontWeight: 700,
                          fontSize: "12px",
                          color: "#2F4F3E",
                        }}
                      >
                        {o.name}
                      </div>
                      <div
                        style={{
                          fontSize: "10px",
                          color: "#5C9470",
                          marginTop: "1px",
                        }}
                      >
                        ID: {o.id} | Slug: {o.slug}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: "2px 6px",
                        borderRadius: "5px",
                        background: "#EAF4EE",
                        color: "#2F4F3E",
                        fontSize: "10px",
                        fontWeight: 700,
                      }}
                    >
                      {o.subscription_plan}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: User Provisioning Form */}
      {activeTab === "users" && (isAdmin || isDispatcher) && (
        <div
          style={{
            background: "#FFFFFF",
            borderRadius: "12px",
            border: "1px solid #E3ECE7",
            padding: "16px 20px",
            boxShadow: "0 1px 4px rgba(47, 79, 62, 0.02)",
            maxWidth: "580px",
          }}
        >
          <h2
            style={{
              fontSize: "14px",
              fontWeight: 700,
              color: "#2F4F3E",
              margin: "0 0 12px",
            }}
          >
            {isDispatcher
            ? "Provision Technician Account"
              : "Provision User or Admin Account"}
          </h2>

          <form
            onSubmit={handleCreateUser}
            style={{ display: "flex", flexDirection: "column", gap: "10px" }}
          >
            <div>
              <label
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                Target Organization *
              </label>
              <select
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  border: "1px solid #E3ECE7",
                  borderRadius: "7px",
                  fontSize: "12px",
                  background: "#F9FAF9",
                  color: "#2F4F3E",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              >
                {orgs.length > 0 ? (
                  orgs.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name} ({o.id})
                    </option>
                  ))
                ) : (
                  <option value={user?.tenant_id || "tenant-1"}>
                    {user?.tenant_id || "tenant-1"}
                  </option>
                )}
              </select>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "10px",
              }}
            >
              <div>
                <label
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                    display: "block",
                    marginBottom: "3px",
                  }}
                >
                  First Name *
                </label>
                <input
                  type="text"
                  placeholder="John"
                  value={userFirstName}
                  onChange={(e) => setUserFirstName(e.target.value)}
                  required
                  style={{
                    width: "100%",
                    padding: "7px 10px",
                    border: "1px solid #E3ECE7",
                    borderRadius: "7px",
                    fontSize: "12px",
                    background: "#F9FAF9",
                    color: "#2F4F3E",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              <div>
                <label
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#2F4F3E",
                    display: "block",
                    marginBottom: "3px",
                  }}
                >
                  Last Name *
                </label>
                <input
                  type="text"
                  placeholder="Doe"
                  value={userLastName}
                  onChange={(e) => setUserLastName(e.target.value)}
                  required
                  style={{
                    width: "100%",
                    padding: "7px 10px",
                    border: "1px solid #E3ECE7",
                    borderRadius: "7px",
                    fontSize: "12px",
                    background: "#F9FAF9",
                    color: "#2F4F3E",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>

            <div>
              <label
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                Email Address *
              </label>
              <input
                type="email"
                placeholder="newadmin@organization.com"
                value={userEmail}
                onChange={(e) => setUserEmail(e.target.value)}
                required
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  border: "1px solid #E3ECE7",
                  borderRadius: "7px",
                  fontSize: "12px",
                  background: "#F9FAF9",
                  color: "#2F4F3E",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div>
              <label
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                Password * (min 8 chars, upper, lower, digit, special)
              </label>
              <input
                type="password"
                placeholder="SecurePass@123"
                value={userPassword}
                onChange={(e) => setUserPassword(e.target.value)}
                required
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  border: "1px solid #E3ECE7",
                  borderRadius: "7px",
                  fontSize: "12px",
                  background: "#F9FAF9",
                  color: "#2F4F3E",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div>
              <label
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  color: "#2F4F3E",
                  display: "block",
                  marginBottom: "3px",
                }}
              >
                Assigned Role *
              </label>
              {isDispatcher ? (
              <input
                type="text"
                value="Technician"
                readOnly
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  border: "1px solid #E3ECE7",
                  borderRadius: "7px",
                  fontSize: "12px",
                  background: "#F3F8F5",
                  color: "#2F4F3E",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            ) : (
              <select
                value={userRole}
                onChange={(e) => setUserRole(e.target.value)}
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  border: "1px solid #E3ECE7",
                  borderRadius: "7px",
                  fontSize: "12px",
                  background: "#F9FAF9",
                  color: "#2F4F3E",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              >
                <option value="dispatcher">Dispatcher</option>
                <option value="technician">Technician</option>
              </select>
            )}
            </div>

            <button
              type="submit"
              disabled={isSubmittingUser}
              style={{
                padding: "9px",
                background: "#2F4F3E",
                color: "#FFFFFF",
                border: "none",
                borderRadius: "7px",
                fontSize: "12px",
                fontWeight: 700,
                cursor: "pointer",
                marginTop: "4px",
                boxShadow: "0 2px 5px rgba(47, 79, 62, 0.15)",
              }}
            >
              {isSubmittingUser ? "Provisioning..." : "Provision User Account"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
