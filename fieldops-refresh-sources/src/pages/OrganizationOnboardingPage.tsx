import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  X,
  Building2,
  CheckCircle,
  Eye,
  EyeOff,
  Lock,
  Mail,
  ShieldCheck,
  User,
  AlertCircle,
  MapPin,
} from "lucide-react";
import api from "../services/api";
import useAuthStore from "../store/authStore";
import logo from "../assets/logo.png";

type Step = "details" | "otp" | "password" | "success";

interface OrganizationOnboardingPageProps {
  onBackToLogin: () => void;
}

export default function OrganizationOnboardingPage({
  onBackToLogin,
}: OrganizationOnboardingPageProps) {
  const authenticateWithTokens = useAuthStore(
    (state) => state.authenticateWithTokens,
  );
  const [step, setStep] = useState<Step>("details");
  const [organizationName, setOrganizationName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");

  const [address, setAddress] = useState("");
  const [siteLatitude, setSiteLatitude] = useState<number | null>(null);
  const [siteLongitude, setSiteLongitude] = useState<number | null>(null);
  const [isGettingLocation, setIsGettingLocation] = useState(false);

  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [onboardingId, setOnboardingId] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const clearError = () => setError("");

  const startOnboarding = async () => {
    clearError();

    if (!organizationName.trim()) {
      setError("Please enter your organization name.");
      return;
    }

    if (!firstName.trim()) {
      setError("Please enter the admin first name.");
      return;
    }

    if (!lastName.trim()) {
      setError("Please enter the admin last name.");
      return;
    }

    if (!email.trim()) {
      setError("Please enter the admin email.");
      return;
    }

    if (!address.trim() || siteLatitude === null || siteLongitude === null) {
      setError("Please select the organization location.");
      return;
    }

    // if (!locationVerified || siteLatitude === null || siteLongitude === null) {
    //   setError("Please verify the organization location.");
    //   return;
    // }
    // Location is optional during onboarding.
    // If an address is provided, resolve its coordinates silently.
    // The user is not asked to verify the location.

    const latitude = siteLatitude;
    const longitude = siteLongitude;

    setLoading(true);

    try {
      const response = await api.post("/organizations/onboarding/start", {
        organization_name: organizationName.trim(),
        admin_first_name: firstName.trim(),
        admin_last_name: lastName.trim(),
        admin_email: email.trim(),
        address: address.trim(),
        site_latitude: latitude,
        site_longitude: longitude,
      });

      setOnboardingId(response.data.onboarding_id);
      setStep("otp");
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          "Unable to start organization onboarding.",
      );
    } finally {
      setLoading(false);
    }
  };

  const verifyOtp = async () => {
    clearError();

    if (!/^\d{6}$/.test(otp)) {
      setError("Please enter the 6-digit verification code.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/organizations/onboarding/verify-otp", {
        onboarding_id: onboardingId,
        otp,
      });

      setStep("password");
    } catch (err: any) {
      setError(
        err.response?.data?.detail || "Invalid or expired verification code.",
      );
    } finally {
      setLoading(false);
    }
  };

  const completeOnboarding = async () => {
    clearError();

    if (password.length < 8) {
      setError("Password must contain at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      // 1. Create organization + Super Admin
      const response = await api.post("/organizations/onboarding/complete", {
        onboarding_id: onboardingId,
        password,
        confirm_password: confirmPassword,
      });

      const { access_token, refresh_token, user } = response.data;

      authenticateWithTokens(access_token, refresh_token, user);
    } catch (err: any) {
      const detail = err.response?.data?.detail;

      if (typeof detail === "string") {
        setError(detail);
      } else if (detail?.errors && Array.isArray(detail.errors)) {
        setError(detail.errors.join(" "));
      } else if (detail?.error) {
        setError(String(detail.error));
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unable to complete organization registration.");
      }
    } finally {
      setLoading(false);
    }
  };

  const goBack = () => {
    clearError();

    if (step === "otp") {
      setStep("details");
    } else if (step === "password") {
      setStep("otp");
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.background} />

      <div style={styles.card}>
        <button
          type="button"
          onClick={onBackToLogin}
          aria-label="Back to login"
          style={styles.closeButton}
        >
          <X size={20} />
        </button>

      <div style={styles.header}>
          <img
            src={logo}
            alt="FieldOps Commander"
            style={styles.logo}
          />

          <h1 style={styles.title}>Create Your Organization</h1>

          <p style={styles.subtitle}>
            Set up your FieldOps organization and Super Admin account.
          </p>
        </div>

        {step !== "success" && (
          <div style={styles.steps}>
            <StepIndicator
              number="1"
              label="Organization"
              active={step === "details"}
              completed={step !== "details"}
            />

            <div style={styles.stepLine} />

            <StepIndicator
              number="2"
              label="Verification"
              active={step === "otp"}
              completed={step === "password"}
            />

            <div style={styles.stepLine} />

            <StepIndicator
              number="3"
              label="Password"
              active={step === "password"}
              completed={false}
            />
          </div>
        )}

        {error && (
          <div style={styles.error}>
            <AlertCircle size={17} />
            <span>{error}</span>
          </div>
        )}

        {/* STEP 1 */}

        {step === "details" && (
          <div style={styles.form}>
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Organization Name</label>

              <div style={styles.inputWrapper}>
                <Building2 size={18} style={styles.icon} />

                <input
                  type="text"
                  placeholder="Enter organization name"
                  value={organizationName}
                  onChange={(e) => setOrganizationName(e.target.value)}
                  style={styles.input}
                />
              </div>
            </div>

            <div style={styles.row}>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Admin First Name</label>

                <div style={styles.inputWrapper}>
                  <User size={18} style={styles.icon} />

                  <input
                    type="text"
                    placeholder="First name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    style={styles.input}
                  />
                </div>
              </div>

              <div style={styles.fieldGroup}>
                <label style={styles.label}>Admin Last Name</label>

                <div style={styles.inputWrapper}>
                  <User size={18} style={styles.icon} />

                  <input
                    type="text"
                    placeholder="Last name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    style={styles.input}
                  />
                </div>
              </div>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Admin Email</label>

              <div style={styles.inputWrapper}>
                <Mail size={18} style={styles.icon} />

                <input
                  type="email"
                  placeholder="admin@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={styles.input}
                />
              </div>

              <span style={styles.helpText}>
                A verification code will be sent to this email.
              </span>
            </div>
            {/* ORGANIZATION LOCATION */}
            <div style={styles.fieldGroup}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <label style={styles.label}>Organization Location *</label>

                <span
                  onClick={() => {
                    if (!navigator.geolocation) {
                      setError("Geolocation is not supported by this browser.");
                      return;
                    }

                    setError("");
                    setIsGettingLocation(true);

                    navigator.geolocation.getCurrentPosition(
                      async (position) => {
                        const { latitude, longitude } = position.coords;

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

                          if (response.data?.verified) {
                            setAddress(response.data.address);
                            setSiteLatitude(latitude);
                            setSiteLongitude(longitude);
                          } else {
                            setError(
                              response.data?.message ||
                                "Unable to determine address from this location.",
                            );
                          }
                        } catch {
                          setError(
                            "Unable to determine address from this location.",
                          );
                        } finally {
                          setIsGettingLocation(false);
                        }
                      },
                      () => {
                        setIsGettingLocation(false);
                        setError("Unable to get your current location.");
                      },
                      {
                        enableHighAccuracy: true,
                        timeout: 30000,
                        maximumAge: 0,
                      },
                    );
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    color: "#5C9470",
                    fontSize: "12px",
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
                </span>
              </div>

              <div style={styles.inputWrapper}>
                <MapPin size={18} style={styles.icon} />

                <input
                  type="text"
                  placeholder="Enter organization address"
                  value={address}
                  onChange={(e) => {
                    setAddress(e.target.value);
                    setSiteLatitude(null);
                    setSiteLongitude(null);
                  }}
                  style={styles.input}
                />
              </div>
            </div>
            <button
              type="button"
              onClick={startOnboarding}
              disabled={loading}
              style={{
                ...styles.primaryButton,
                ...(loading ? styles.disabled : {}),
              }}
            >
              {loading ? (
                "Sending verification code..."
              ) : (
                <>
                  Continue
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </div>
        )}

        {/* STEP 2 */}

        {step === "otp" && (
          <div style={styles.form}>
            <div style={styles.otpIcon}>
              <Mail size={30} />
            </div>

            <div style={styles.centerText}>
              <h2 style={styles.sectionTitle}>Check Your Email</h2>

              <p style={styles.description}>
                We sent a 6-digit verification code to
              </p>

              <strong style={styles.emailText}>{email}</strong>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Verification Code</label>

              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="000000"
                value={otp}
                onChange={(e) =>
                  setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                style={styles.otpInput}
              />

              <span style={styles.helpText}>
                The verification code expires in 10 minutes.
              </span>
            </div>

            <button
              type="button"
              onClick={verifyOtp}
              disabled={loading}
              style={{
                ...styles.primaryButton,
                ...(loading ? styles.disabled : {}),
              }}
            >
              {loading ? (
                "Verifying..."
              ) : (
                <>
                  Verify Email
                  <ArrowRight size={18} />
                </>
              )}
            </button>

            <button type="button" onClick={goBack} style={styles.backButton}>
              <ArrowLeft size={17} />
              Back
            </button>
          </div>
        )}

        {/* STEP 3 */}

        {step === "password" && (
          <div style={styles.form}>
            <div style={styles.centerText}>
              <div style={styles.passwordIcon}>
                <Lock size={28} />
              </div>

              <h2 style={styles.sectionTitle}>Create Your Password</h2>

              <p style={styles.description}>
                This password will be used by the Super Admin to sign in to
                FieldOps.
              </p>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Password</label>

              <div style={styles.inputWrapper}>
                <Lock size={18} style={styles.icon} />

                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{
                    ...styles.input,
                    paddingRight: "45px",
                  }}
                />

                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={styles.passwordToggle}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Confirm Password</label>

              <div style={styles.inputWrapper}>
                <Lock size={18} style={styles.icon} />

                <input
                  type={showConfirmPassword ? "text" : "password"}
                  placeholder="Confirm password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  style={{
                    ...styles.input,
                    paddingRight: "45px",
                  }}
                />

                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  style={styles.passwordToggle}
                >
                  {showConfirmPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </div>

            <button
              type="button"
              onClick={completeOnboarding}
              disabled={loading}
              style={{
                ...styles.primaryButton,
                ...(loading ? styles.disabled : {}),
              }}
            >
              {loading ? (
                "Creating Organization..."
              ) : (
                <>
                  Create Organization
                  <CheckCircle size={18} />
                </>
              )}
            </button>

            <button type="button" onClick={goBack} style={styles.backButton}>
              <ArrowLeft size={17} />
              Back
            </button>
          </div>
        )}

        {/* SUCCESS */}

        {step === "success" && (
          <div style={styles.success}>
            <div style={styles.successIcon}>
              <CheckCircle size={42} />
            </div>

            <h2 style={styles.sectionTitle}>Organization Created!</h2>

            <p style={styles.description}>
              Your organization and Super Admin account have been created
              successfully.
            </p>

            <div style={styles.successBox}>
              <strong>{organizationName}</strong>

              <span>
                Super Admin: {firstName} {lastName}
              </span>

              <span>{email}</span>
            </div>

            <button
              type="button"
              onClick={() => {
                window.location.href = "/";
              }}
              style={styles.primaryButton}
            >
              Go to Login
              <ArrowRight size={18} />
            </button>
          </div>
        )}

        <div style={styles.security}>
          <ShieldCheck size={15} />
          <span>Your organization data is securely protected.</span>
        </div>
      </div>
    </div>
  );
}

function StepIndicator({
  number,
  label,
  active,
  completed,
}: {
  number: string;
  label: string;
  active: boolean;
  completed: boolean;
}) {
  return (
    <div style={styles.step}>
      <div
        style={{
          ...styles.stepCircle,
          ...(active ? styles.stepActive : {}),
          ...(completed ? styles.stepCompleted : {}),
        }}
      >
        {completed ? <CheckCircle size={16} /> : number}
      </div>

      <span
        style={{
          ...styles.stepLabel,
          ...(active ? styles.stepLabelActive : {}),
        }}
      >
        {label}
      </span>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, #0a1a12, #0d2818, #143d24, #1a5032)",
    fontFamily: "'Inter', sans-serif",
    padding: "30px 20px",
    position: "relative",
    boxSizing: "border-box",
  },

  background: {
    position: "absolute",
    inset: 0,
    background:
      "radial-gradient(circle at 20% 30%, rgba(34,197,94,.08), transparent 45%), radial-gradient(circle at 80% 70%, rgba(16,185,129,.06), transparent 45%)",
    pointerEvents: "none",
  },

  card: {
    width: "100%",
    maxWidth: "620px",
    background: "rgba(15,35,23,.9)",
    backdropFilter: "blur(20px)",
    border: "1px solid rgba(34,197,94,.15)",
    borderRadius: "20px",
    padding: "40px",
    boxShadow: "0 25px 60px rgba(0,0,0,.4)",
    position: "relative",
    zIndex: 1,
    boxSizing: "border-box",
  },
  
  closeButton: {
  position: "absolute",
  top: "18px",
  right: "18px",
  width: "36px",
  height: "36px",
  borderRadius: "8px",
  border: "1px solid rgba(167,199,183,.2)",
  background: "rgba(10,26,18,.5)",
  color: "rgba(167,199,183,.7)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
},

  header: {
    textAlign: "center",
    marginBottom: "30px",
  },

  logo: {
    height: "45px",
    marginBottom: "12px",
  },

  title: {
    margin: 0,
    color: "#e8f5ee",
    fontSize: "24px",
    fontWeight: 700,
  },

  subtitle: {
    color: "rgba(167,199,183,.7)",
    fontSize: "14px",
    marginTop: "8px",
  },

  steps: {
    display: "flex",
    alignItems: "center",
    marginBottom: "30px",
  },

  step: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "6px",
    minWidth: "90px",
  },

  stepCircle: {
    width: "30px",
    height: "30px",
    borderRadius: "50%",
    border: "1px solid rgba(167,199,183,.3)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "rgba(167,199,183,.5)",
    fontSize: "12px",
  },

  stepActive: {
    background: "#16a34a",
    borderColor: "#16a34a",
    color: "#fff",
  },

  stepCompleted: {
    background: "#15803d",
    borderColor: "#15803d",
    color: "#fff",
  },

  stepLabel: {
    fontSize: "11px",
    color: "rgba(167,199,183,.45)",
  },

  stepLabelActive: {
    color: "#a7c7b7",
  },

  stepLine: {
    flex: 1,
    height: "1px",
    background: "rgba(167,199,183,.2)",
    marginBottom: "17px",
  },

  form: {
    display: "flex",
    flexDirection: "column",
    gap: "18px",
  },

  fieldGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "7px",
    flex: 1,
  },

  row: {
    display: "flex",
    gap: "15px",
  },

  label: {
    color: "rgba(167,199,183,.85)",
    fontSize: "13px",
    fontWeight: 500,
  },

  inputWrapper: {
    position: "relative",
    display: "flex",
    alignItems: "center",
  },

  icon: {
    position: "absolute",
    left: "14px",
    color: "rgba(34,197,94,.55)",
    pointerEvents: "none",
  },

  input: {
    width: "100%",
    padding: "13px 14px 13px 43px",
    background: "rgba(10,26,18,.7)",
    border: "1px solid rgba(34,197,94,.2)",
    borderRadius: "10px",
    color: "#e8f5ee",
    fontSize: "14px",
    outline: "none",
    boxSizing: "border-box",
  },

  helpText: {
    fontSize: "11px",
    color: "rgba(167,199,183,.5)",
  },

  locationButton: {
    alignSelf: "flex-start",
    marginTop: "2px",
    padding: "10px 16px",
    border: "1px solid rgba(34,197,94,.2)",
    borderRadius: "8px",
    background: "rgba(10,26,18,.7)",
    color: "rgba(167,199,183,.85)",
    fontSize: "13px",
    fontWeight: 500,
    cursor: "pointer",
  },

  primaryButton: {
    marginTop: "5px",
    padding: "14px",
    border: "none",
    borderRadius: "10px",
    background: "linear-gradient(135deg,#16a34a,#15803d)",
    color: "#fff",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: "8px",
  },

  disabled: {
    opacity: 0.6,
    cursor: "not-allowed",
  },

  error: {
    display: "flex",
    alignItems: "center",
    gap: "9px",
    padding: "12px",
    background: "rgba(220,38,38,.1)",
    border: "1px solid rgba(220,38,38,.25)",
    borderRadius: "9px",
    color: "#fca5a5",
    fontSize: "13px",
    marginBottom: "15px",
  },

  otpIcon: {
    width: "60px",
    height: "60px",
    borderRadius: "50%",
    background: "rgba(34,197,94,.1)",
    color: "#4ade80",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    margin: "0 auto",
  },

  centerText: {
    textAlign: "center",
  },

  sectionTitle: {
    color: "#e8f5ee",
    fontSize: "20px",
    margin: "8px 0",
  },

  description: {
    color: "rgba(167,199,183,.65)",
    fontSize: "13px",
    lineHeight: 1.6,
    margin: 0,
  },

  emailText: {
    display: "block",
    color: "#4ade80",
    fontSize: "14px",
    marginTop: "5px",
  },

  otpInput: {
    width: "100%",
    padding: "15px",
    background: "rgba(10,26,18,.7)",
    border: "1px solid rgba(34,197,94,.25)",
    borderRadius: "10px",
    color: "#e8f5ee",
    fontSize: "24px",
    textAlign: "center",
    letterSpacing: "8px",
    outline: "none",
    boxSizing: "border-box",
  },

  passwordIcon: {
    width: "56px",
    height: "56px",
    borderRadius: "50%",
    background: "rgba(34,197,94,.1)",
    color: "#4ade80",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    margin: "0 auto 10px",
  },

  passwordToggle: {
    position: "absolute",
    right: "12px",
    background: "none",
    border: "none",
    color: "rgba(167,199,183,.55)",
    cursor: "pointer",
  },

  backButton: {
    background: "none",
    border: "none",
    color: "rgba(167,199,183,.65)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    fontSize: "13px",
  },

  success: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
    gap: "14px",
  },

  successIcon: {
    width: "75px",
    height: "75px",
    borderRadius: "50%",
    background: "rgba(34,197,94,.12)",
    color: "#4ade80",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  successBox: {
    width: "100%",
    display: "flex",
    flexDirection: "column",
    gap: "5px",
    padding: "16px",
    background: "rgba(10,26,18,.5)",
    border: "1px solid rgba(34,197,94,.15)",
    borderRadius: "10px",
    color: "rgba(167,199,183,.7)",
    fontSize: "13px",
    boxSizing: "border-box",
  },

  security: {
    marginTop: "25px",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: "6px",
    color: "rgba(167,199,183,.4)",
    fontSize: "11px",
  },
};
