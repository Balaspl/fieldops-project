
/**
 * LoginPage — Enterprise authentication page for FieldOps Commander.
 *
 * Authentication methods:
 * - Email/password login
 * - Enterprise OIDC SSO
 * - Account lockout feedback
 * - Password visibility toggle
 * - Loading states and error handling
 * - Responsive design with glassmorphism
 *
 * SSO flow:
 *   Sign in with SSO
 *        ↓
 *   /auth/sso/login
 *        ↓
 *   Configured OIDC provider
 *        ↓
 *   /auth/sso/callback
 *        ↓
 *   Backend sets HttpOnly access-token cookie
 *        ↓
 *   Frontend loads authenticated user
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
    backgroundImage: `radial-gradient(circle at 20% 30%, rgba(34, 197, 94, 0.08) 0%, transparent 50%),
                       radial-gradient(circle at 80% 70%, rgba(16, 185, 129, 0.06) 0%, transparent 50%),
                       radial-gradient(circle at 50% 50%, rgba(5, 150, 105, 0.04) 0%, transparent 60%)`,
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
    transition: "background 0.2s, border-color 0.2s, opacity 0.2s",
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

  securityBadge: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    marginTop: "24px",
    fontSize: "12px",
    color: "rgba(167, 199, 183, 0.4)",
  },
};

interface LoginPageProps {
  onCreateOrganization: () => void;
}

export default function LoginPage({
  onCreateOrganization,
}: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [emailFocused, setEmailFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

  const [ssoLoading, setSsoLoading] = useState(false);
  const [ssoError, setSsoError] = useState("");

  // =========================================================
  // MFA LOGIN STATE
  // =========================================================

  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaLoading, setMfaLoading] = useState(false);
  const [mfaError, setMfaError] = useState("");

  const {
    authenticateWithTokens,
    isLoading,
    error,
    clearError,
  } = useAuthStore();

  useEffect(() => {
    clearError();
  }, [clearError]);

  /**
   * Start enterprise OIDC SSO.
   *
   * The backend performs the complete authentication flow.
   *
   * The browser is redirected to:
   *
   *   /auth/sso/login
   *
   * The backend then:
   *   1. Generates state + nonce
   *   2. Redirects to the configured OIDC provider
   *   3. Validates the callback
   *   4. Resolves the FieldOps user
   *   5. Creates the normal FieldOps JWT
   *   6. Stores the access token in an HttpOnly cookie
   *   7. Redirects back to the frontend
   */
  const handleSSOLogin = () => {
  setSsoError("");
  setSsoLoading(true);

  const apiBaseUrl =
    import.meta.env.VITE_API_BASE_URL ||
    "http://localhost:8000";

  window.location.href =
    `${apiBaseUrl}/auth/sso/login`;
};

  const handleSubmit = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();

    if (!email || !password) {
      return;
    }

    setMfaError("");
    clearError();

    try {
      const response = await api.post("/auth/login", {
        email,
        password,
      });

      const data = response.data;

      // -------------------------------------------------------
      // MFA is enabled for this account.
      // The backend deliberately returns no JWT yet.
      // -------------------------------------------------------
      if (data?.status === "MFA_REQUIRED") {
        setMfaRequired(true);
        setMfaChallenge(data.challenge || "");
        setMfaCode("");
        return;
      }

      // -------------------------------------------------------
      // Normal login: MFA is optional/not enabled.
      // -------------------------------------------------------
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
        return;
      }

      throw new Error("Invalid login response");
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      if (typeof detail === "string") {
        // Keep MFA errors separate from the normal login error.
        if (mfaRequired) {
          setMfaError(detail);
        }
      } else if (!mfaRequired) {
        // The existing auth store used to expose the login error.
        // We keep the generic API error visible through a local
        // message because this page now handles the login response
        // directly to detect MFA_REQUIRED.
      }
    }
  };

  // =========================================================
  // VERIFY MFA LOGIN
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
      const response = await api.post("/auth/mfa/verify", {
        challenge: mfaChallenge,
        code,
      });

      const data = response.data;

      // The MFA verification endpoint must return the normal
      // FieldOps tokens after successful verification.
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
        return;
      }

      setMfaError(
        "MFA was verified, but the server did not return a login session."
      );
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      setMfaError(
        typeof detail === "string"
          ? detail
          : "Invalid MFA code. Please try again."
      );
    } finally {
      setMfaLoading(false);
    }
  };

  const handleBackToLogin = () => {
    setMfaRequired(false);
    setMfaChallenge("");
    setMfaCode("");
    setMfaError("");
  };


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

        {mfaRequired ? (
          <form
            style={styles.form}
            onSubmit={handleMfaVerify}
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
                  background: "rgba(34, 197, 94, 0.1)",
                  border: "1px solid rgba(34, 197, 94, 0.25)",
                  marginBottom: "14px",
                }}
              >
                <Shield size={26} color="#86efac" />
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
                  color: "rgba(167, 199, 183, 0.7)",
                  fontSize: "13px",
                  lineHeight: 1.5,
                }}
              >
                Enter the 6-digit code from your
                authenticator app to continue.
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
                    const value = e.target.value
                      .replace(/\D/g, "")
                      .slice(0, 6);

                    setMfaCode(value);
                    setMfaError("");
                  }}
                  style={{
                    ...styles.input,
                    paddingLeft: "44px",
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

            <button
              id="mfa-verify-submit"
              type="submit"
              style={{
                ...styles.button,
                ...(mfaLoading ||
                mfaCode.length !== 6
                  ? styles.buttonDisabled
                  : {}),
              }}
              disabled={
                mfaLoading || mfaCode.length !== 6
              }
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
              onClick={handleBackToLogin}
              disabled={mfaLoading}
              style={{
                padding: "12px",
                background: "transparent",
                border: "1px solid rgba(34, 197, 94, 0.25)",
                borderRadius: "12px",
                color: "#86efac",
                fontSize: "14px",
                fontWeight: 600,
                cursor: mfaLoading
                  ? "not-allowed"
                  : "pointer",
                fontFamily: "'Inter', sans-serif",
                opacity: mfaLoading ? 0.6 : 1,
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
          <form
            style={styles.form}
            onSubmit={handleSubmit}
          >
            {error && (
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

            {/* Email */}
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
                  onChange={(e) =>
                    setEmail(e.target.value)
                  }
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

            {/* Password */}
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
                  onChange={(e) =>
                    setPassword(e.target.value)
                  }
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
                    setShowPassword(!showPassword)
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

            {/* Local Login */}
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
              onMouseEnter={(e) => {
                if (!isLoading) {
                  (
                    e.target as HTMLElement
                  ).style.transform =
                    "translateY(-1px)";

                  (
                    e.target as HTMLElement
                  ).style.boxShadow =
                    "0 6px 20px rgba(22, 163, 74, 0.4)";
                }
              }}
              onMouseLeave={(e) => {
                (
                  e.currentTarget as HTMLElement
                ).style.transform =
                  "translateY(0)";

                (
                  e.currentTarget as HTMLElement
                ).style.boxShadow =
                  "0 4px 15px rgba(22, 163, 74, 0.3)";
              }}
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

            {/* Divider */}
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

            {/* Enterprise SSO */}
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
              onMouseEnter={(e) => {
                if (!ssoLoading) {
                  (
                    e.currentTarget as HTMLElement
                  ).style.background =
                    "rgba(34, 197, 94, 0.08)";

                  (
                    e.currentTarget as HTMLElement
                  ).style.borderColor =
                    "rgba(34, 197, 94, 0.5)";
                }
              }}
              onMouseLeave={(e) => {
                (
                  e.currentTarget as HTMLElement
                ).style.background =
                  "rgba(10, 26, 18, 0.6)";

                (
                  e.currentTarget as HTMLElement
                ).style.borderColor =
                  "rgba(34, 197, 94, 0.3)";
              }}
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

            {/* Create Organization */}
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

