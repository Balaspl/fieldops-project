
/**
 * LoginPage — Enterprise authentication page for FieldOps Commander.
 *
 * Features:
 * - Email/password login with validation
 * - Google OIDC login
 * - Account lockout feedback
 * - Password visibility toggle
 * - Loading states and error handling
 * - Responsive design with glassmorphism
 */

import { useState, useEffect, useRef } from "react";
import {
  Eye,
  EyeOff,
  Lock,
  Mail,
  Shield,
  ArrowRight,
  AlertCircle,
} from "lucide-react";
import useAuthStore from "../store/authStore";
import api from "../services/api";
import logo from "../assets/logo.png";

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

  const [googleLoading, setGoogleLoading] = useState(false);
  const [googleError, setGoogleError] = useState("");

  const googleButtonRef = useRef<HTMLDivElement | null>(null);

  const {
    login,
    isLoading,
    error,
    clearError,
    authenticateWithTokens,
  } = useAuthStore();

  useEffect(() => {
    clearError();
  }, [clearError]);

  /**
   * Handle Google ID token returned by Google Identity Services.
   */
  const handleGoogleCredential = async (
    response: { credential: string }
  ) => {
    setGoogleError("");

    if (!response.credential) {
      setGoogleError("Google did not return an ID token.");
      return;
    }

    setGoogleLoading(true);

    try {
      const result = await api.post("/auth/oidc/google", {
        id_token: response.credential,
      });

      const {
        access_token,
        refresh_token,
        user,
      } = result.data;

      if (!access_token || !refresh_token || !user) {
        throw new Error(
          "Google login response is missing authentication data."
        );
      }

      authenticateWithTokens(
        access_token,
        refresh_token,
        user
      );
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 401) {
        setGoogleError(
          typeof detail === "string"
            ? detail
            : "This Google account is not linked to a FieldOps account."
        );
      } else if (status === 403) {
        setGoogleError(
          typeof detail === "string"
            ? detail
            : "Google login is not allowed for this account."
        );
      } else {
        setGoogleError(
          typeof detail === "string"
            ? detail
            : "Google sign-in failed. Please try again."
        );
      }
    } finally {
      setGoogleLoading(false);
    }
  };

  /**
   * Initialize Google Identity Services.
   */
  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

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
  }, []);

  const handleSubmit = async (
    e: React.FormEvent
  ) => {
    e.preventDefault();

    if (!email || !password) return;

    try {
      await login(email, password);
    } catch {
      // Error is already set in the store
    }
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

          {googleError && (
            <div style={styles.error}>
              <AlertCircle
                size={16}
                style={{
                  flexShrink: 0,
                  marginTop: 2,
                }}
              />

              <span>{googleError}</span>
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
                e.target as HTMLElement
              ).style.transform =
                "translateY(0)";

              (
                e.target as HTMLElement
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

          {/* Google Sign-In */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <div
              ref={googleButtonRef}
              style={{
                minHeight: "40px",
              }}
            />

            {googleLoading && (
              <div
                style={{
                  fontSize: "12px",
                  color:
                    "rgba(167, 199, 183, 0.6)",
                }}
              >
                Signing in with Google...
              </div>
            )}
          </div>

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

