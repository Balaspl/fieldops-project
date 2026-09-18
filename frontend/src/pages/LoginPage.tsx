/**
 * LoginPage — Enterprise authentication page for FieldOps Commander.
 *
 * Authentication methods:
 * - Email/password login
 * - Forgot password
 * - Enterprise OIDC SSO
 * - MFA verification
 * - MFA recovery code
 * - Trust this device for 30 days
 * - Password visibility toggle
 * - Loading states and error handling
 * - Backend-enforced account lockout
 * - Backend-enforced rate limiting
 */

import { useState, useEffect } from "react";
import {
  Eye,
  EyeOff,
  Lock,
  Mail,
  Shield,
  ArrowRight,
  AlertCircle,
  Building2,
  KeyRound,
  CheckCircle,
  Smartphone,
} from "lucide-react";

import useAuthStore from "../store/authStore";
import api from "../services/api";
import logo from "../assets/logo.png";

const styles = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background:
      "linear-gradient(135deg, #0a1a12 0%, #0d2818 25%, #143d24 50%, #1a5032 75%, #0d2818 100%)",
    fontFamily: "'Inter', sans-serif",
    position: "relative" as const,
    overflow: "hidden",
  },

  bgPattern: {
    position: "absolute" as const,
    inset: 0,
    backgroundImage: `
      radial-gradient(
        circle at 20% 30%,
        rgba(34, 197, 94, 0.08) 0%,
        transparent 50%
      ),
      radial-gradient(
        circle at 80% 70%,
        rgba(16, 185, 129, 0.06) 0%,
        transparent 50%
      ),
      radial-gradient(
        circle at 50% 50%,
        rgba(5, 150, 105, 0.04) 0%,
        transparent 60%
      )
    `,
    pointerEvents: "none" as const,
  },

  card: {
    width: "100%",
    maxWidth: "440px",
    margin: "0 20px",
    background: "rgba(15, 35, 23, 0.85)",
    backdropFilter: "blur(20px)",
    border: "1px solid rgba(34, 197, 94, 0.15)",
    borderRadius: "20px",
    padding: "48px 40px",
    boxShadow:
      "0 25px 60px rgba(0, 0, 0, 0.4), 0 0 80px rgba(34, 197, 94, 0.05)",
    position: "relative" as const,
    zIndex: 1,
  },

  logoSection: {
    textAlign: "center" as const,
    marginBottom: "36px",
  },

  logo: {
    height: "48px",
    marginBottom: "16px",
    filter: "brightness(1.1)",
  },

  title: {
    fontSize: "24px",
    fontWeight: 700,
    color: "#e8f5ee",
    margin: 0,
    letterSpacing: "-0.5px",
  },

  subtitle: {
    fontSize: "14px",
    color: "rgba(167, 199, 183, 0.7)",
    marginTop: "8px",
  },

  form: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "20px",
  },

  fieldGroup: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "6px",
  },

  label: {
    fontSize: "13px",
    fontWeight: 500,
    color: "rgba(167, 199, 183, 0.8)",
    letterSpacing: "0.3px",
  },

  inputWrapper: {
    position: "relative" as const,
    display: "flex",
    alignItems: "center",
  },

  inputIcon: {
    position: "absolute" as const,
    left: "14px",
    color: "rgba(34, 197, 94, 0.5)",
    pointerEvents: "none" as const,
  },

  input: {
    width: "100%",
    padding: "14px 14px 14px 44px",
    background: "rgba(10, 26, 18, 0.6)",
    border: "1px solid rgba(34, 197, 94, 0.2)",
    borderRadius: "12px",
    color: "#e8f5ee",
    fontSize: "15px",
    fontFamily: "'Inter', sans-serif",
    outline: "none",
    transition: "border-color 0.2s, box-shadow 0.2s",
    boxSizing: "border-box" as const,
  },

  inputFocus: {
    borderColor: "rgba(34, 197, 94, 0.5)",
    boxShadow: "0 0 0 3px rgba(34, 197, 94, 0.1)",
  },

  togglePassword: {
    position: "absolute" as const,
    right: "14px",
    background: "none",
    border: "none",
    color: "rgba(167, 199, 183, 0.5)",
    cursor: "pointer",
    padding: "4px",
    display: "flex",
    alignItems: "center",
  },

  button: {
    padding: "14px",
    background: "linear-gradient(135deg, #16a34a, #15803d)",
    border: "none",
    borderRadius: "12px",
    color: "#fff",
    fontSize: "15px",
    fontWeight: 600,
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    transition: "transform 0.15s, box-shadow 0.2s, opacity 0.2s",
    boxShadow: "0 4px 15px rgba(22, 163, 74, 0.3)",
    marginTop: "4px",
  },

  buttonDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
  },

  ssoButton: {
    padding: "14px",
    background: "rgba(10, 26, 18, 0.6)",
    border: "1px solid rgba(34, 197, 94, 0.3)",
    borderRadius: "12px",
    color: "#e8f5ee",
    fontSize: "15px",
    fontWeight: 600,
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "10px",
    width: "100%",
  },

  error: {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
    padding: "12px 16px",
    background: "rgba(220, 38, 38, 0.1)",
    border: "1px solid rgba(220, 38, 38, 0.25)",
    borderRadius: "10px",
    color: "#fca5a5",
    fontSize: "13px",
    lineHeight: 1.5,
  },

  success: {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
    padding: "12px 16px",
    background: "rgba(34, 197, 94, 0.1)",
    border: "1px solid rgba(34, 197, 94, 0.25)",
    borderRadius: "10px",
    color: "#86efac",
    fontSize: "13px",
    lineHeight: 1.5,
  },

  forgotLinkContainer: {
    display: "flex",
    justifyContent: "flex-end",
    marginTop: "-10px",
  },

  forgotLink: {
    background: "none",
    border: "none",
    padding: 0,
    color: "#86efac",
    fontSize: "13px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
  },

  backButton: {
    padding: "12px",
    background: "transparent",
    border: "1px solid rgba(34, 197, 94, 0.25)",
    borderRadius: "12px",
    color: "#86efac",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    width: "100%",
  },

  secondaryButton: {
    padding: "12px",
    background: "transparent",
    border: "none",
    color: "#86efac",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    width: "100%",
  },

  securityBadge: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    marginTop: "24px",
    fontSize: "12px",
    color: "rgba(167, 199, 183, 0.4)",
  },

  trustDevice: {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
    padding: "12px 14px",
    background: "rgba(34, 197, 94, 0.05)",
    border: "1px solid rgba(34, 197, 94, 0.15)",
    borderRadius: "10px",
    cursor: "pointer",
  },

  trustCheckbox: {
    width: "17px",
    height: "17px",
    marginTop: "2px",
    accentColor: "#16a34a",
    cursor: "pointer",
  },

  trustTitle: {
    color: "#d1fae5",
    fontSize: "13px",
    fontWeight: 600,
    margin: 0,
  },

  trustDescription: {
    color: "rgba(167, 199, 183, 0.6)",
    fontSize: "11px",
    lineHeight: 1.4,
    margin: "3px 0 0",
  },
};

interface LoginPageProps {
  onCreateOrganization: () => void;
}

export default function LoginPage({
  onCreateOrganization,
}: LoginPageProps) {
  // =========================================================
  // LOGIN STATE
  // =========================================================

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);

  const [emailFocused, setEmailFocused] = useState(false);

  const [passwordFocused, setPasswordFocused] = useState(false);

  // =========================================================
  // LOGIN ERROR
  // =========================================================

  /*
   * Backend remains the source of truth for:
   *
   * - authentication
   * - account lockout
   * - rate limiting
   *
   * Frontend does not maintain failed-attempt counters.
   */

  const [loginError, setLoginError] = useState("");

  // =========================================================
  // FORGOT PASSWORD STATE
  // =========================================================

  const [showForgotPassword, setShowForgotPassword] =
    useState(false);

  const [forgotEmail, setForgotEmail] = useState("");

  const [forgotLoading, setForgotLoading] = useState(false);

  const [forgotError, setForgotError] = useState("");

  const [forgotSuccess, setForgotSuccess] = useState("");

  // =========================================================
  // SSO STATE
  // =========================================================

  const [ssoLoading, setSsoLoading] = useState(false);

  const [ssoError, setSsoError] = useState("");

  // =========================================================
  // MFA STATE
  // =========================================================

  const [mfaRequired, setMfaRequired] = useState(false);

  const [mfaChallenge, setMfaChallenge] = useState("");

  const [mfaCode, setMfaCode] = useState("");

  const [recoveryCode, setRecoveryCode] = useState("");

  const [useRecoveryCode, setUseRecoveryCode] = useState(false);

  const [mfaLoading, setMfaLoading] = useState(false);

  const [mfaError, setMfaError] = useState("");

  // =========================================================
  // TRUST DEVICE STATE
  // =========================================================

  const [trustDevice, setTrustDevice] = useState(false);

  const {
    authenticateWithTokens,
    isLoading,
    error,
    clearError,
  } = useAuthStore();

  useEffect(() => {
    clearError();
  }, [clearError]);

  // =========================================================
  // ENTERPRISE SSO
  // =========================================================

  const handleSSOLogin = () => {
  setSsoError("");
  setSsoLoading(true);

  // Tell the application that the upcoming
  // authentication flow is SSO.
  localStorage.setItem("auth_mode", "sso");

  const apiBaseUrl =
    import.meta.env.VITE_API_BASE_URL ||
    "http://localhost:8000";

  window.location.href =
    `${apiBaseUrl}/auth/sso/login`;
};

  // =========================================================
  // NORMAL LOGIN
  // =========================================================

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim() || !password) {
      return;
    }

    setLoginError("");
    setMfaError("");
    clearError();

    const normalizedEmail = email.trim().toLowerCase();

    try {
      /*
       * If the browser already has a trusted-device token,
       * send it to the backend.
       *
       * Backend will:
       *
       * 1. Verify email/password.
       * 2. Validate trusted device.
       * 3. Skip MFA if trusted device is valid.
       * 4. Otherwise return MFA_REQUIRED.
       * 5. Enforce account lockout.
       * 6. Enforce rate limiting.
       */

      const trustedDeviceToken =
        localStorage.getItem(`trusted_device_token_${normalizedEmail}`);

      const response = await api.post("/auth/login", {
        email: normalizedEmail,
        password,
        trusted_device_token:
          trustedDeviceToken || undefined,
      });

      const data = response.data;

      // =====================================================
      // MFA REQUIRED
      // =====================================================

      if (data?.status === "MFA_REQUIRED") {
        setMfaRequired(true);

        setMfaChallenge(data.challenge || "");

        setMfaCode("");
        setRecoveryCode("");
        setUseRecoveryCode(false);
        setTrustDevice(false);
        setMfaError("");
        setLoginError("");

        return;
      }

      // =====================================================
      // NORMAL LOGIN
      // =====================================================

      if (
        data?.access_token &&
        data?.refresh_token &&
        data?.user
      ) {
        authenticateWithTokens(
          data.access_token,
          data.refresh_token,
          data.user
        );

        setLoginError("");

        return;
      }

      throw new Error("Invalid login response");
    } catch (err: any) {
      const status = err.response?.status;

      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      // =====================================================
      // ACCOUNT LOCKOUT
      // HTTP 423
      // =====================================================

      if (
        status === 423 ||
        (typeof detail === "string" &&
          detail.toLowerCase().includes("account is locked"))
      ) {
        setLoginError(
          "Your account is locked. Please try again later."
        );

        return;
      }

      // =====================================================
      // RATE LIMIT
      // HTTP 429
      // =====================================================

      if (status === 429) {
        setLoginError(
          "Too many login attempts. Please wait a moment and try again."
        );

        return;
      }

      // =====================================================
      // TRUSTED DEVICE TOKEN
      // =====================================================

      if (status === 401 || status === 403) {
        const message =
          typeof detail === "string"
            ? detail.toLowerCase()
            : "";

        if (
          message.includes("trusted") ||
          message.includes("device")
        ) {
          localStorage.removeItem(
            `trusted_device_token_${normalizedEmail}`
          );
        }
      }

      // =====================================================
      // GENERAL LOGIN ERROR
      // =====================================================

      if (typeof detail === "string") {
        setLoginError(detail);
      } else {
        setLoginError(
          "Unable to sign in. Please try again."
        );
      }
    }
  };

  // =========================================================
  // FORGOT PASSWORD
  // =========================================================

  const handleForgotPassword = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();

    const normalizedEmail =
      forgotEmail.trim().toLowerCase();

    if (!normalizedEmail) {
      setForgotError(
        "Please enter your email address."
      );
      return;
    }

    setForgotLoading(true);
    setForgotError("");
    setForgotSuccess("");

    try {
      const response = await api.post(
        "/auth/forgot-password",
        {
          email: normalizedEmail,
        }
      );

      const message =
        response.data?.message ||
        "If an account with that email exists, a password reset link has been sent.";

      setForgotSuccess(message);
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      setForgotError(
        typeof detail === "string"
          ? detail
          : "Unable to process the password reset request. Please try again."
      );
    } finally {
      setForgotLoading(false);
    }
  };

  // =========================================================
  // BACK TO LOGIN FROM FORGOT PASSWORD
  // =========================================================

  const handleBackToLogin = () => {
    setShowForgotPassword(false);
    setForgotEmail("");
    setForgotError("");
    setForgotSuccess("");
    setLoginError("");
  };

  // =========================================================
  // VERIFY MFA
  // =========================================================

  const handleMfaVerify = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();

    const code = mfaCode.trim();

    if (!mfaChallenge) {
      setMfaError(
        "Your MFA session is missing or expired. Please log in again."
      );
      return;
    }

    if (!/^\d{6}$/.test(code)) {
      setMfaError(
        "Enter the 6-digit code from your authenticator app."
      );
      return;
    }

    setMfaLoading(true);
    setMfaError("");

    try {
      const response = await api.post(
        "/auth/mfa/verify",
        {
          challenge: mfaChallenge,
          code,
          trust_device: trustDevice,
        }
      );

      const data = response.data;

      if (
        data?.status === "VERIFIED" &&
        data?.access_token &&
        data?.refresh_token &&
        data?.user
      ) {
        /*
         * Backend returns the raw trusted-device token
         * only when trust_device=true.
         */

        if (
          trustDevice &&
          data?.trusted_device_token &&
          data?.user?.email
        ) {
          const normalizedEmail =
            data.user.email.trim().toLowerCase();

          localStorage.setItem(
            `trusted_device_token_${normalizedEmail}`,
            data.trusted_device_token
          );
        }

        authenticateWithTokens(
          data.access_token,
          data.refresh_token,
          data.user
        );

        setMfaRequired(false);
        setMfaChallenge("");
        setMfaCode("");
        setRecoveryCode("");
        setUseRecoveryCode(false);
        setTrustDevice(false);

        return;
      }

      setMfaError(
        "MFA was verified, but the server did not return a login session."
      );
    } catch (err: any) {
      const status = err.response?.status;

      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      // Account lockout during MFA
      if (
        status === 423 ||
        (typeof detail === "string" &&
          detail.toLowerCase().includes("account is locked"))
      ) {
        setMfaError(
          "Your account is locked. Please try again later."
        );
        return;
      }

      // Rate limit during MFA
      if (status === 429) {
        setMfaError(
          "Too many verification attempts. Please wait a moment and try again."
        );
        return;
      }

      setMfaError(
        typeof detail === "string"
          ? detail
          : "Invalid MFA code. Please try again."
      );
    } finally {
      setMfaLoading(false);
    }
  };

  // =========================================================
  // VERIFY MFA RECOVERY CODE
  // =========================================================

  const handleMfaRecovery = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();

    const code = recoveryCode.trim();

    if (!mfaChallenge) {
      setMfaError(
        "Your MFA session is missing or expired. Please log in again."
      );
      return;
    }

    if (!code) {
      setMfaError(
        "Enter one of your recovery codes."
      );
      return;
    }

    setMfaLoading(true);
    setMfaError("");

    try {
      const response = await api.post(
        "/auth/mfa/recovery",
        {
          challenge: mfaChallenge,
          recovery_code: code,
        }
      );

      const data = response.data;

      if (
        data?.status === "VERIFIED" &&
        data?.access_token &&
        data?.refresh_token &&
        data?.user
      ) {
        authenticateWithTokens(
          data.access_token,
          data.refresh_token,
          data.user
        );

        setMfaRequired(false);
        setMfaChallenge("");
        setMfaCode("");
        setRecoveryCode("");
        setUseRecoveryCode(false);
        setTrustDevice(false);

        return;
      }

      setMfaError(
        "Recovery code was verified, but the server did not return a login session."
      );
    } catch (err: any) {
      const status = err.response?.status;

      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      if (
        status === 423 ||
        (typeof detail === "string" &&
          detail.toLowerCase().includes("account is locked"))
      ) {
        setMfaError(
          "Your account is locked. Please try again later."
        );
        return;
      }

      if (status === 429) {
        setMfaError(
          "Too many verification attempts. Please wait a moment and try again."
        );
        return;
      }

      setMfaError(
        typeof detail === "string"
          ? detail
          : "Invalid recovery code. Please try again."
      );
    } finally {
      setMfaLoading(false);
    }
  };

  // =========================================================
  // BACK FROM MFA
  // =========================================================

  const handleBackFromMfa = () => {
    if (mfaLoading) {
      return;
    }

    setMfaRequired(false);
    setMfaChallenge("");
    setMfaCode("");
    setRecoveryCode("");
    setUseRecoveryCode(false);
    setTrustDevice(false);
    setMfaError("");
    setLoginError("");
  };

  // =========================================================
  // FORGOT PASSWORD PAGE
  // =========================================================

  if (showForgotPassword) {
    return (
      <div style={styles.page}>
        <div style={styles.bgPattern} />

        <div style={styles.card}>
          <div style={styles.logoSection}>
            <img
              src={logo}
              alt="FieldOps Commander"
              style={styles.logo}
            />

            <h1 style={styles.title}>
              Forgot Password?
            </h1>

            <p style={styles.subtitle}>
              Enter your email address and we'll send you
              a password reset link.
            </p>
          </div>

          <form
            style={styles.form}
            onSubmit={handleForgotPassword}
          >
            {forgotError && (
              <div style={styles.error}>
                <AlertCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>{forgotError}</span>
              </div>
            )}

            {forgotSuccess && (
              <div style={styles.success}>
                <CheckCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>{forgotSuccess}</span>
              </div>
            )}

            <div style={styles.fieldGroup}>
              <label style={styles.label}>
                Email Address
              </label>

              <div style={styles.inputWrapper}>
                <Mail
                  size={18}
                  style={styles.inputIcon}
                />

                <input
                  id="forgot-password-email"
                  type="email"
                  placeholder="you@company.com"
                  value={forgotEmail}
                  onChange={(e) => {
                    setForgotEmail(e.target.value);
                    setForgotError("");
                    setForgotSuccess("");
                  }}
                  style={styles.input}
                  autoComplete="email"
                  autoFocus
                  required
                />
              </div>
            </div>

            <button
              id="forgot-password-submit"
              type="submit"
              disabled={forgotLoading}
              style={{
                ...styles.button,
                ...(forgotLoading
                  ? styles.buttonDisabled
                  : {}),
              }}
            >
              {forgotLoading ? (
                <>
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      border:
                        "2px solid rgba(255,255,255,0.3)",
                      borderTopColor: "#fff",
                      borderRadius: "50%",
                      animation:
                        "spin 0.8s linear infinite",
                    }}
                  />

                  Sending...
                </>
              ) : (
                <>
                  <KeyRound size={18} />
                  Send Reset Link
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleBackToLogin}
              disabled={forgotLoading}
              style={{
                ...styles.backButton,
                opacity: forgotLoading ? 0.6 : 1,
                cursor: forgotLoading
                  ? "not-allowed"
                  : "pointer",
              }}
            >
              Back to Login
            </button>
          </form>

          <div style={styles.securityBadge}>
            <Shield size={14} />

            <span>
              Your account information is protected
            </span>
          </div>
        </div>

        <style>{`
          @keyframes spin {
            from {
              transform: rotate(0deg);
            }

            to {
              transform: rotate(360deg);
            }
          }

          input::placeholder {
            color: rgba(167, 199, 183, 0.35);
          }
        `}</style>
      </div>
    );
  }

  // =========================================================
  // MAIN LOGIN PAGE
  // =========================================================

  return (
    <div style={styles.page}>
      <div style={styles.bgPattern} />

      <div style={styles.card}>
        <div style={styles.logoSection}>
          <img
            src={logo}
            alt="FieldOps Commander"
            style={styles.logo}
          />

          <h1 style={styles.title}>
            FieldOps Commander
          </h1>

          <p style={styles.subtitle}>
            Enterprise Field Operations Platform
          </p>
        </div>

        {/* =====================================================
            MFA SCREEN
        ====================================================== */}

        {mfaRequired ? (
          <form
            style={styles.form}
            onSubmit={
              useRecoveryCode
                ? handleMfaRecovery
                : handleMfaVerify
            }
          >
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                textAlign: "center",
                marginBottom: "4px",
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background:
                    "rgba(34, 197, 94, 0.1)",
                  border:
                    "1px solid rgba(34, 197, 94, 0.25)",
                  marginBottom: "14px",
                }}
              >
                <Shield
                  size={26}
                  color="#86efac"
                />
              </div>

              <h2
                style={{
                  margin: 0,
                  color: "#e8f5ee",
                  fontSize: "20px",
                  fontWeight: 700,
                }}
              >
                Multi-Factor Authentication
              </h2>

              <p
                style={{
                  margin: "8px 0 0",
                  color:
                    "rgba(167, 199, 183, 0.7)",
                  fontSize: "13px",
                  lineHeight: 1.5,
                }}
              >
                {useRecoveryCode
                  ? "Enter one of your saved recovery codes."
                  : "Enter the 6-digit code from your authenticator app to continue."}
              </p>
            </div>

            {mfaError && (
              <div style={styles.error}>
                <AlertCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>{mfaError}</span>
              </div>
            )}

            {/* =================================================
                AUTHENTICATOR CODE
            ================================================== */}

            {!useRecoveryCode ? (
              <>
                <div style={styles.fieldGroup}>
                  <label style={styles.label}>
                    Authenticator Code
                  </label>

                  <div style={styles.inputWrapper}>
                    <Shield
                      size={18}
                      style={styles.inputIcon}
                    />

                    <input
                      id="mfa-login-code"
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="Enter 6-digit code"
                      value={mfaCode}
                      onChange={(e) => {
                        const value =
                          e.target.value
                            .replace(/\D/g, "")
                            .slice(0, 6);

                        setMfaCode(value);
                        setMfaError("");
                      }}
                      style={{
                        ...styles.input,
                        textAlign: "center",
                        letterSpacing: "0.3em",
                        fontWeight: 700,
                      }}
                      maxLength={6}
                      autoFocus
                      required
                    />
                  </div>
                </div>

                {/* =================================================
                    TRUST THIS DEVICE
                ================================================== */}

                <label
                  htmlFor="trust-device"
                  style={styles.trustDevice}
                >
                  <input
                    id="trust-device"
                    type="checkbox"
                    checked={trustDevice}
                    onChange={(e) =>
                      setTrustDevice(
                        e.target.checked
                      )
                    }
                    disabled={mfaLoading}
                    style={styles.trustCheckbox}
                  />

                  <Smartphone
                    size={18}
                    color="#86efac"
                    style={{
                      flexShrink: 0,
                      marginTop: 1,
                    }}
                  />

                  <div>
                    <p style={styles.trustTitle}>
                      Trust this device
                    </p>

                    <p
                      style={
                        styles.trustDescription
                      }
                    >
                      Skip MFA verification on this
                      browser for 30 days.
                    </p>
                  </div>
                </label>

                <button
                  id="mfa-verify-submit"
                  type="submit"
                  disabled={
                    mfaLoading ||
                    mfaCode.length !== 6
                  }
                  style={{
                    ...styles.button,
                    ...(mfaLoading ||
                    mfaCode.length !== 6
                      ? styles.buttonDisabled
                      : {}),
                  }}
                >
                  {mfaLoading ? (
                    <>
                      <div
                        style={{
                          width: 18,
                          height: 18,
                          border:
                            "2px solid rgba(255,255,255,0.3)",
                          borderTopColor: "#fff",
                          borderRadius: "50%",
                          animation:
                            "spin 0.8s linear infinite",
                        }}
                      />

                      Verifying...
                    </>
                  ) : (
                    <>
                      Verify & Continue
                      <ArrowRight size={18} />
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setUseRecoveryCode(true);
                    setMfaCode("");
                    setTrustDevice(false);
                    setMfaError("");
                  }}
                  disabled={mfaLoading}
                  style={{
                    ...styles.secondaryButton,
                    opacity: mfaLoading ? 0.6 : 1,
                    cursor: mfaLoading
                      ? "not-allowed"
                      : "pointer",
                  }}
                >
                  Use a recovery code
                </button>
              </>
            ) : (
              <>
                {/* =================================================
                    RECOVERY CODE
                ================================================== */}

                <div style={styles.fieldGroup}>
                  <label style={styles.label}>
                    Recovery Code
                  </label>

                  <div style={styles.inputWrapper}>
                    <KeyRound
                      size={18}
                      style={styles.inputIcon}
                    />

                    <input
                      id="mfa-recovery-code"
                      type="text"
                      inputMode="text"
                      placeholder="Enter recovery code"
                      value={recoveryCode}
                      onChange={(e) => {
                        setRecoveryCode(
                          e.target.value
                        );
                        setMfaError("");
                      }}
                      style={{
                        ...styles.input,
                        textAlign: "center",
                        letterSpacing: "0.08em",
                        fontWeight: 700,
                      }}
                      autoFocus
                      required
                    />
                  </div>
                </div>

                <button
                  id="mfa-recovery-submit"
                  type="submit"
                  disabled={
                    mfaLoading ||
                    !recoveryCode.trim()
                  }
                  style={{
                    ...styles.button,
                    ...(mfaLoading ||
                    !recoveryCode.trim()
                      ? styles.buttonDisabled
                      : {}),
                  }}
                >
                  {mfaLoading ? (
                    <>
                      <div
                        style={{
                          width: 18,
                          height: 18,
                          border:
                            "2px solid rgba(255,255,255,0.3)",
                          borderTopColor: "#fff",
                          borderRadius: "50%",
                          animation:
                            "spin 0.8s linear infinite",
                        }}
                      />

                      Verifying...
                    </>
                  ) : (
                    <>
                      Verify Recovery Code
                      <ArrowRight size={18} />
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setUseRecoveryCode(false);
                    setRecoveryCode("");
                    setMfaError("");
                  }}
                  disabled={mfaLoading}
                  style={{
                    ...styles.secondaryButton,
                    opacity: mfaLoading ? 0.6 : 1,
                    cursor: mfaLoading
                      ? "not-allowed"
                      : "pointer",
                  }}
                >
                  Use authenticator code instead
                </button>
              </>
            )}

            {/* =================================================
                BACK TO LOGIN
            ================================================== */}

            <button
              type="button"
              onClick={handleBackFromMfa}
              disabled={mfaLoading}
              style={{
                ...styles.backButton,
                opacity: mfaLoading ? 0.6 : 1,
                cursor: mfaLoading
                  ? "not-allowed"
                  : "pointer",
              }}
            >
              Back to Login
            </button>

            <div style={styles.securityBadge}>
              <Shield size={14} />

              <span>
                MFA protects your FieldOps account
              </span>
            </div>
          </form>
        ) : (
          /* =====================================================
             LOGIN FORM
          ====================================================== */

          <form
            style={styles.form}
            onSubmit={handleSubmit}
          >
            {/* =================================================
                ACCOUNT LOCKOUT / LOGIN ERROR
            ================================================== */}

            {loginError && (
              <div style={styles.error}>
                <AlertCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>{loginError}</span>
              </div>
            )}

            {!loginError && error && (
              <div style={styles.error}>
                <AlertCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>
                  {typeof error === "string"
                    ? error
                    : "An error occurred"}
                </span>
              </div>
            )}

            {ssoError && (
              <div style={styles.error}>
                <AlertCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>{ssoError}</span>
              </div>
            )}

            {/* =================================================
                EMAIL
            ================================================== */}

            <div style={styles.fieldGroup}>
              <label style={styles.label}>
                Email Address
              </label>

              <div style={styles.inputWrapper}>
                <Mail
                  size={18}
                  style={styles.inputIcon}
                />

                <input
                  id="login-email"
                  type="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setLoginError("");
                  }}
                  onFocus={() =>
                    setEmailFocused(true)
                  }
                  onBlur={() =>
                    setEmailFocused(false)
                  }
                  style={{
                    ...styles.input,
                    ...(emailFocused
                      ? styles.inputFocus
                      : {}),
                  }}
                  autoComplete="email"
                  required
                />
              </div>
            </div>

            {/* =================================================
                PASSWORD
            ================================================== */}

            <div style={styles.fieldGroup}>
              <label style={styles.label}>
                Password
              </label>

              <div style={styles.inputWrapper}>
                <Lock
                  size={18}
                  style={styles.inputIcon}
                />

                <input
                  id="login-password"
                  type={
                    showPassword
                      ? "text"
                      : "password"
                  }
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setLoginError("");
                  }}
                  onFocus={() =>
                    setPasswordFocused(true)
                  }
                  onBlur={() =>
                    setPasswordFocused(false)
                  }
                  style={{
                    ...styles.input,
                    paddingRight: "44px",
                    ...(passwordFocused
                      ? styles.inputFocus
                      : {}),
                  }}
                  autoComplete="current-password"
                  required
                />

                <button
                  type="button"
                  style={styles.togglePassword}
                  onClick={() =>
                    setShowPassword(
                      !showPassword
                    )
                  }
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </div>

            {/* =================================================
                FORGOT PASSWORD
            ================================================== */}

            <div
              style={
                styles.forgotLinkContainer
              }
            >
              <button
                type="button"
                onClick={() => {
                  setForgotEmail(email);
                  setForgotError("");
                  setForgotSuccess("");
                  setLoginError("");
                  setShowForgotPassword(true);
                }}
                style={styles.forgotLink}
              >
                Forgot Password?
              </button>
            </div>

            {/* =================================================
                SIGN IN
            ================================================== */}

            <button
              id="login-submit"
              type="submit"
              style={{
                ...styles.button,
                ...(isLoading
                  ? styles.buttonDisabled
                  : {}),
              }}
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      border:
                        "2px solid rgba(255,255,255,0.3)",
                      borderTopColor: "#fff",
                      borderRadius: "50%",
                      animation:
                        "spin 0.8s linear infinite",
                    }}
                  />

                  Signing in...
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight size={18} />
                </>
              )}
            </button>

            {/* =================================================
                DIVIDER
            ================================================== */}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                margin: "4px 0",
              }}
            >
              <div
                style={{
                  flex: 1,
                  height: "1px",
                  background:
                    "rgba(167, 199, 183, 0.15)",
                }}
              />

              <span
                style={{
                  color:
                    "rgba(167, 199, 183, 0.45)",
                  fontSize: "12px",
                  fontWeight: 500,
                }}
              >
                OR
              </span>

              <div
                style={{
                  flex: 1,
                  height: "1px",
                  background:
                    "rgba(167, 199, 183, 0.15)",
                }}
              />
            </div>

            {/* =================================================
                ENTERPRISE SSO
            ================================================== */}

            <button
              id="sso-login"
              type="button"
              style={{
                ...styles.ssoButton,
                ...(ssoLoading
                  ? styles.buttonDisabled
                  : {}),
              }}
              disabled={ssoLoading}
              onClick={handleSSOLogin}
            >
              {ssoLoading ? (
                <>
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      border:
                        "2px solid rgba(255,255,255,0.3)",
                      borderTopColor: "#fff",
                      borderRadius: "50%",
                      animation:
                        "spin 0.8s linear infinite",
                    }}
                  />

                  Redirecting to SSO...
                </>
              ) : (
                <>
                  <Building2 size={18} />
                  Sign in with Enterprise SSO
                </>
              )}
            </button>

            {/* =================================================
                CREATE ORGANIZATION
            ================================================== */}

            <button
              type="button"
              onClick={onCreateOrganization}
              style={{
                marginTop: "12px",
                padding: "12px",
                width: "100%",
                background: "transparent",
                border:
                  "1px solid rgba(34, 197, 94, 0.3)",
                borderRadius: "12px",
                color: "#86efac",
                fontSize: "14px",
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "'Inter', sans-serif",
              }}
            >
              Create Organization
            </button>
          </form>
        )}

        <div style={styles.securityBadge}>
          <Shield size={14} />

          <span>
            Secured with enterprise-grade encryption
          </span>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from {
            transform: rotate(0deg);
          }

          to {
            transform: rotate(360deg);
          }
        }

        input::placeholder {
          color: rgba(167, 199, 183, 0.35);
        }
      `}</style>
    </div>
  );
}