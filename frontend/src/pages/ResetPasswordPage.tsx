import { useState } from "react";
import {
  Lock,
  Eye,
  EyeOff,
  Shield,
  ArrowRight,
  AlertCircle,
  CheckCircle,
} from "lucide-react";

import api from "../services/api";
import logo from "../assets/logo.png";

interface ResetPasswordPageProps {
  token: string;
  onBackToLogin: () => void;
}

export default function ResetPasswordPage({
  token,
  onBackToLogin,
}: ResetPasswordPageProps) {
  const [newPassword, setNewPassword] =
    useState("");

  const [confirmPassword, setConfirmPassword] =
    useState("");

  const [showNewPassword, setShowNewPassword] =
    useState(false);

  const [
    showConfirmPassword,
    setShowConfirmPassword,
  ] = useState(false);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const [success, setSuccess] =
    useState(false);

  const validatePassword = (
    password: string,
  ) => {
    if (password.length < 8) {
      return "Password must be at least 8 characters.";
    }

    if (password.length > 128) {
      return "Password must not exceed 128 characters.";
    }

    if (!/[A-Z]/.test(password)) {
      return "Password must contain at least one uppercase letter.";
    }

    if (!/[a-z]/.test(password)) {
      return "Password must contain at least one lowercase letter.";
    }

    if (!/[0-9]/.test(password)) {
      return "Password must contain at least one number.";
    }

    if (!/[^A-Za-z0-9]/.test(password)) {
      return "Password must contain at least one special character.";
    }

    return null;
  };

  const handleSubmit = async (
    e: React.FormEvent,
  ) => {
    e.preventDefault();

    setError("");

    if (!token) {
      setError(
        "This password reset link is invalid.",
      );
      return;
    }

    const passwordError =
      validatePassword(newPassword);

    if (passwordError) {
      setError(passwordError);
      return;
    }

    if (
      newPassword !== confirmPassword
    ) {
      setError(
        "Passwords do not match.",
      );
      return;
    }

    setLoading(true);

    try {
      await api.post(
        "/auth/reset-password",
        {
          token,
          new_password: newPassword,
        },
      );

      setSuccess(true);
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.response?.data?.message;

      setError(
        typeof detail === "string"
          ? detail
          : "Unable to reset your password. The link may be expired or already used.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background:
          "linear-gradient(135deg, #0a1a12 0%, #0d2818 25%, #143d24 50%, #1a5032 75%, #0d2818 100%)",
        fontFamily: "'Inter', sans-serif",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
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
            )
          `,
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          width: "100%",
          maxWidth: "440px",
          margin: "0 20px",
          background: "rgba(15, 35, 23, 0.85)",
          backdropFilter: "blur(20px)",
          border:
            "1px solid rgba(34, 197, 94, 0.15)",
          borderRadius: "20px",
          padding: "48px 40px",
          boxShadow:
            "0 25px 60px rgba(0, 0, 0, 0.4)",
          position: "relative",
          zIndex: 1,
          boxSizing: "border-box",
        }}
      >
        {/* LOGO */}

        <div
          style={{
            textAlign: "center",
            marginBottom: "32px",
          }}
        >
          <img
            src={logo}
            alt="FieldOps Commander"
            style={{
              height: "48px",
              marginBottom: "16px",
            }}
          />

          <h1
            style={{
              fontSize: "24px",
              fontWeight: 700,
              color: "#e8f5ee",
              margin: 0,
            }}
          >
            Reset Password
          </h1>

          <p
            style={{
              fontSize: "14px",
              color:
                "rgba(167, 199, 183, 0.7)",
              marginTop: "8px",
            }}
          >
            Create a new password for your
            FieldOps account.
          </p>
        </div>

        {/* SUCCESS */}

        {success ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              textAlign: "center",
              gap: "16px",
            }}
          >
            <div
              style={{
                width: "60px",
                height: "60px",
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background:
                  "rgba(34, 197, 94, 0.1)",
                border:
                  "1px solid rgba(34, 197, 94, 0.25)",
              }}
            >
              <CheckCircle
                size={30}
                color="#86efac"
              />
            </div>

            <h2
              style={{
                color: "#e8f5ee",
                fontSize: "20px",
                margin: 0,
              }}
            >
              Password Reset Successful
            </h2>

            <p
              style={{
                color:
                  "rgba(167, 199, 183, 0.7)",
                fontSize: "14px",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              Your password has been changed
              successfully. You can now log in
              using your new password.
            </p>

            <button
              type="button"
              onClick={onBackToLogin}
              style={{
                width: "100%",
                padding: "14px",
                background:
                  "linear-gradient(135deg, #16a34a, #15803d)",
                border: "none",
                borderRadius: "12px",
                color: "#fff",
                fontSize: "15px",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
              }}
            >
              Back to Login
              <ArrowRight size={18} />
            </button>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "20px",
            }}
          >
            {/* ERROR */}

            {error && (
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "10px",
                  padding: "12px 16px",
                  background:
                    "rgba(220, 38, 38, 0.1)",
                  border:
                    "1px solid rgba(220, 38, 38, 0.25)",
                  borderRadius: "10px",
                  color: "#fca5a5",
                  fontSize: "13px",
                  lineHeight: 1.5,
                }}
              >
                <AlertCircle
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />

                <span>{error}</span>
              </div>
            )}

            {/* NEW PASSWORD */}

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "6px",
              }}
            >
              <label
                style={{
                  fontSize: "13px",
                  fontWeight: 500,
                  color:
                    "rgba(167, 199, 183, 0.8)",
                }}
              >
                New Password
              </label>

              <div
                style={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <Lock
                  size={18}
                  style={{
                    position: "absolute",
                    left: "14px",
                    color:
                      "rgba(34, 197, 94, 0.5)",
                  }}
                />

                <input
                  type={
                    showNewPassword
                      ? "text"
                      : "password"
                  }
                  value={newPassword}
                  onChange={(e) => {
                    setNewPassword(
                      e.target.value,
                    );
                    setError("");
                  }}
                  placeholder="Enter new password"
                  autoComplete="new-password"
                  required
                  style={{
                    width: "100%",
                    padding:
                      "14px 44px 14px 44px",
                    background:
                      "rgba(10, 26, 18, 0.6)",
                    border:
                      "1px solid rgba(34, 197, 94, 0.2)",
                    borderRadius: "12px",
                    color: "#e8f5ee",
                    fontSize: "15px",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />

                <button
                  type="button"
                  onClick={() =>
                    setShowNewPassword(
                      !showNewPassword,
                    )
                  }
                  style={{
                    position: "absolute",
                    right: "12px",
                    background: "none",
                    border: "none",
                    color:
                      "rgba(167, 199, 183, 0.5)",
                    cursor: "pointer",
                    display: "flex",
                  }}
                >
                  {showNewPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </div>

            {/* CONFIRM PASSWORD */}

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "6px",
              }}
            >
              <label
                style={{
                  fontSize: "13px",
                  fontWeight: 500,
                  color:
                    "rgba(167, 199, 183, 0.8)",
                }}
              >
                Confirm Password
              </label>

              <div
                style={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <Lock
                  size={18}
                  style={{
                    position: "absolute",
                    left: "14px",
                    color:
                      "rgba(34, 197, 94, 0.5)",
                  }}
                />

                <input
                  type={
                    showConfirmPassword
                      ? "text"
                      : "password"
                  }
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(
                      e.target.value,
                    );
                    setError("");
                  }}
                  placeholder="Confirm new password"
                  autoComplete="new-password"
                  required
                  style={{
                    width: "100%",
                    padding:
                      "14px 44px 14px 44px",
                    background:
                      "rgba(10, 26, 18, 0.6)",
                    border:
                      "1px solid rgba(34, 197, 94, 0.2)",
                    borderRadius: "12px",
                    color: "#e8f5ee",
                    fontSize: "15px",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />

                <button
                  type="button"
                  onClick={() =>
                    setShowConfirmPassword(
                      !showConfirmPassword,
                    )
                  }
                  style={{
                    position: "absolute",
                    right: "12px",
                    background: "none",
                    border: "none",
                    color:
                      "rgba(167, 199, 183, 0.5)",
                    cursor: "pointer",
                    display: "flex",
                  }}
                >
                  {showConfirmPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </div>

            {/* PASSWORD REQUIREMENTS */}

            <div
              style={{
                padding: "12px 14px",
                background:
                  "rgba(34, 197, 94, 0.05)",
                border:
                  "1px solid rgba(34, 197, 94, 0.12)",
                borderRadius: "10px",
                color:
                  "rgba(167, 199, 183, 0.65)",
                fontSize: "12px",
                lineHeight: 1.7,
              }}
            >
              Password must contain:
              <br />
              • 8–128 characters
              <br />
              • One uppercase letter
              <br />
              • One lowercase letter
              <br />
              • One number
              <br />
              • One special character
            </div>

            {/* SUBMIT */}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                padding: "14px",
                background:
                  "linear-gradient(135deg, #16a34a, #15803d)",
                border: "none",
                borderRadius: "12px",
                color: "#fff",
                fontSize: "15px",
                fontWeight: 600,
                cursor: loading
                  ? "not-allowed"
                  : "pointer",
                opacity: loading ? 0.6 : 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
              }}
            >
              {loading ? (
                "Resetting Password..."
              ) : (
                <>
                  Reset Password
                  <ArrowRight size={18} />
                </>
              )}
            </button>

            {/* BACK */}

            <button
              type="button"
              onClick={onBackToLogin}
              disabled={loading}
              style={{
                width: "100%",
                padding: "12px",
                background: "transparent",
                border:
                  "1px solid rgba(34, 197, 94, 0.25)",
                borderRadius: "12px",
                color: "#86efac",
                fontSize: "14px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Back to Login
            </button>
          </form>
        )}

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px",
            marginTop: "24px",
            fontSize: "12px",
            color:
              "rgba(167, 199, 183, 0.4)",
          }}
        >
          <Shield size={14} />
          Your account is protected
        </div>
      </div>
    </div>
  );
}