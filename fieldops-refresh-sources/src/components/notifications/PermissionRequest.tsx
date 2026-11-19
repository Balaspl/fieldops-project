import React, { useEffect, useState } from "react";
import { Bell, BellOff, Check, MessageSquare, Info, Settings, ShieldAlert, ArrowRight, RefreshCw, X } from "lucide-react";
import { PermissionRequestProps } from "../../types/notifications.ts";

const COOLDOWN_DAYS = 7;

const styles = {
  container: {
    width: "100%",
    fontFamily: "'Inter', sans-serif",
    boxSizing: "border-box",
  } as React.CSSProperties,

  permissionCard: {
    background: "linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)",
    border: "1px solid #e2e8f0",
    borderRadius: "16px",
    padding: "24px",
    boxShadow: "0 10px 25px -5px rgba(51, 65, 85, 0.08), 0 8px 10px -6px rgba(51, 65, 85, 0.04)",
    maxWidth: "480px",
    marginLeft: "auto",
    marginRight: "auto",
    boxSizing: "border-box",
    position: "relative",
    overflow: "hidden",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
  } as React.CSSProperties,

  cardHeader: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    fontSize: "18px",
    fontWeight: 800,
    color: "#0f172a",
    marginBottom: "12px",
  } as React.CSSProperties,

  cardDescription: {
    fontSize: "14px",
    color: "#475569",
    lineHeight: 1.5,
    margin: "0 0 20px 0",
    fontWeight: 500,
  } as React.CSSProperties,

  fallbackList: {
    margin: "12px 0 20px 12px",
    padding: 0,
    listStyleType: "none",
    fontSize: "13.5px",
    color: "#475569",
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  } as React.CSSProperties,

  fallbackItem: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontWeight: 600,
  } as React.CSSProperties,

  actions: {
    display: "flex",
    gap: "12px",
    flexWrap: "wrap",
    justifyContent: "flex-end",
  } as React.CSSProperties,

  btnPrimary: {
    height: "40px",
    padding: "0 18px",
    fontSize: "13.5px",
    fontWeight: 700,
    color: "#ffffff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    boxShadow: "0 4px 12px rgba(37, 99, 235, 0.2)",
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    transition: "all 0.2s ease",
  } as React.CSSProperties,

  btnSecondary: {
    height: "40px",
    padding: "0 16px",
    fontSize: "13.5px",
    fontWeight: 600,
    color: "#64748b",
    backgroundColor: "#f1f5f9",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    transition: "all 0.2s ease",
  } as React.CSSProperties,

  compactPill: {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    height: "32px",
    padding: "0 10px",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: 700,
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.03)",
    transition: "all 0.25s ease",
    border: "1px solid transparent",
    boxSizing: "border-box",
  } as React.CSSProperties,

  compactBtn: {
    border: "none",
    borderRadius: "6px",
    height: "22px",
    padding: "0 8px",
    fontSize: "10.5px",
    fontWeight: 800,
    cursor: "pointer",
    transition: "all 0.2s ease",
    marginLeft: "4px",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  smsForm: {
    marginTop: "20px",
    paddingTop: "16px",
    borderTop: "1px dashed #cbd5e1",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  infoBox: {
    marginTop: "12px",
    padding: "10px 14px",
    borderRadius: "8px",
    backgroundColor: "#f8fafc",
    border: "1px solid #e2e8f0",
    fontSize: "12px",
    color: "#64748b",
    lineHeight: 1.4,
    display: "flex",
    gap: "8px",
    alignItems: "flex-start",
  } as React.CSSProperties,
};

const localCss = `
  .pr-btn-primary-default {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  }
  .pr-btn-primary-default:hover {
    background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(37, 99, 235, 0.3) !important;
  }
  .pr-btn-primary-default:active {
    transform: translateY(0);
  }

  .pr-btn-primary-danger {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important;
  }
  .pr-btn-primary-danger:hover {
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%) !important;
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3) !important;
  }

  .pr-btn-secondary:hover {
    background-color: #e2e8f0 !important;
    color: #0f172a !important;
  }

  .pr-compact-pill-default {
    background-color: #eff6ff;
    border-color: #bfdbfe;
    color: #1e3a8a;
  }
  .pr-compact-pill-granted {
    background-color: #f0fdf4;
    border-color: #bbf7d0;
    color: #166534;
  }
  .pr-compact-pill-denied {
    background-color: #fef2f2;
    border-color: #fecaca;
    color: #991b1b;
  }

  .pr-compact-btn-enable {
    background-color: #2563eb;
    color: #ffffff;
  }
  .pr-compact-btn-enable:hover {
    background-color: #1d4ed8;
  }
  .pr-compact-btn-disable {
    background-color: #fee2e2;
    color: #991b1b;
  }
  .pr-compact-btn-disable:hover {
    background-color: #fecaca;
  }
  .pr-compact-btn-settings {
    background-color: #f1f5f9;
    color: #475569;
    border: 1px solid #cbd5e1;
  }
  .pr-compact-btn-settings:hover {
    background-color: #e2e8f0;
  }

  .pr-icon-pulse {
    animation: pr-pulse 2s infinite ease-in-out;
  }
  @keyframes pr-pulse {
    0% { transform: scale(1); opacity: 0.9; }
    50% { transform: scale(1.15); opacity: 1; }
    100% { transform: scale(1); opacity: 0.9; }
  }

  @keyframes pr-fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .pr-animate-in {
    animation: pr-fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
`;

export const PermissionRequest: React.FC<PermissionRequestProps> = ({
  onPermissionChange,
  className = "",
  compact = false
}) => {
  const [permission, setPermission] = useState<string>("default");
  const [isSupported, setIsSupported] = useState<boolean>(true);
  const [isIOSDevice, setIsIOSDevice] = useState<boolean>(false);
  const [isAppStandalone, setIsAppStandalone] = useState<boolean>(false);
  const [inCooldown, setInCooldown] = useState<boolean>(false);
  const [showSMSForm, setShowSMSForm] = useState<boolean>(false);
  const [phoneNumber, setPhoneNumber] = useState<string>("");
  const [smsRegistered, setSmsRegistered] = useState<boolean>(false);
  const [dismissed, setDismissed] = useState<boolean>(false);
  const [showSettingsInfo, setShowSettingsInfo] = useState<boolean>(false);

  const checkAvailabilityAndCooldowns = () => {
    if (typeof window === "undefined") return;

    const hasNotificationSupport = "Notification" in window;
    setIsSupported(hasNotificationSupport);

    // Initial check of Notification.permission
    let currentPermission = hasNotificationSupport ? Notification.permission : "unsupported";

    // Read stored override status if present
    const savedStatus = localStorage.getItem("push_permission_status");
    if (savedStatus) {
      currentPermission = savedStatus;
    }

    // 7-day cooldown checks for denied status
    let cooldownActive = false;
    const deniedAt = localStorage.getItem("push_permission_denied_at");
    if (deniedAt && currentPermission === "denied") {
      const diffTime = Math.abs(Date.now() - new Date(deniedAt).getTime());
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      
      if (diffDays > COOLDOWN_DAYS) {
        // Cooldown passed: Allow re-request (revert state back to default in UI representation)
        currentPermission = "default";
        localStorage.setItem("push_permission_status", "default");
        localStorage.removeItem("push_permission_denied_at");
      } else {
        cooldownActive = true;
      }
    }

    // Dismiss duration (24-hour check for 'maybe later')
    const maybeLaterAt = localStorage.getItem("push_permission_maybe_later_at");
    if (maybeLaterAt) {
      const diffTime = Math.abs(Date.now() - new Date(maybeLaterAt).getTime());
      const diffHours = Math.ceil(diffTime / (1000 * 60 * 60));
      if (diffHours < 24 && currentPermission === "default") {
        setDismissed(true);
      }
    }

    setPermission(currentPermission);
    setInCooldown(cooldownActive);

    // iOS and PWA Standalone Detection
    const userAgent = window.navigator.userAgent;
    const isIOS = /iPad|iPhone|iPod/.test(userAgent) && !(window as any).MSStream;
    setIsIOSDevice(isIOS);

    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || (window.navigator as any).standalone;
    setIsAppStandalone(!!isStandalone);
  };

  useEffect(() => {
    checkAvailabilityAndCooldowns();
  }, []);

  const requestPermission = async () => {
    if (typeof window === "undefined" || !isSupported) return;

    try {
      const result = await Notification.requestPermission();
      setPermission(result);
      localStorage.setItem("push_permission_status", result);

      if (result === "granted") {
        localStorage.removeItem("push_permission_denied_at");
        localStorage.removeItem("push_permission_maybe_later_at");
        const mockToken = "mock_fcm_token_" + Math.random().toString(36).substring(7);
        localStorage.setItem("push_fcm_token", mockToken);
        if (onPermissionChange) onPermissionChange("granted");
      } else if (result === "denied") {
        localStorage.setItem("push_permission_denied_at", new Date().toISOString());
        setInCooldown(true);
        if (onPermissionChange) onPermissionChange("denied");
      }
    } catch (error) {
      // Fallback for browsers returning promise vs callback
      console.warn("Notification requestPermission error: falling back", error);
      Notification.requestPermission((result) => {
        setPermission(result);
        localStorage.setItem("push_permission_status", result);
        if (result === "granted") {
          localStorage.removeItem("push_permission_denied_at");
          localStorage.removeItem("push_permission_maybe_later_at");
          const mockToken = "mock_fcm_token_" + Math.random().toString(36).substring(7);
          localStorage.setItem("push_fcm_token", mockToken);
          if (onPermissionChange) onPermissionChange("granted");
        } else if (result === "denied") {
          localStorage.setItem("push_permission_denied_at", new Date().toISOString());
          setInCooldown(true);
          if (onPermissionChange) onPermissionChange("denied");
        }
      });
    }
  };

  const handleDisable = () => {
    localStorage.removeItem("push_permission_status");
    localStorage.removeItem("push_fcm_token");
    localStorage.removeItem("push_permission_denied_at");
    localStorage.removeItem("push_permission_maybe_later_at");
    setPermission("default");
    setInCooldown(false);
    setDismissed(false);
    if (onPermissionChange) onPermissionChange("default");
  };

  const handleMaybeLater = () => {
    localStorage.setItem("push_permission_maybe_later_at", new Date().toISOString());
    setDismissed(true);
  };

  const handleRegisterSMS = (e: React.FormEvent) => {
    e.preventDefault();
    if (phoneNumber.trim()) {
      localStorage.setItem("sms_notification_phone", phoneNumber.trim());
      setSmsRegistered(true);
      setTimeout(() => {
        setShowSMSForm(false);
        setSmsRegistered(false);
        setPhoneNumber("");
      }, 2000);
    }
  };

  const handleSettingsClick = () => {
    setShowSettingsInfo(!showSettingsInfo);
  };

  // Helper for manual demo resets
  const handleResetDemo = () => {
    handleDisable();
  };

  if (dismissed && permission === "default") {
    return (
      <div style={styles.container} className={`noc-module ${className} pr-animate-in`} style={{ display: "flex", justifyContent: "flex-end" }}>
        <style>{localCss}</style>
        <button
          type="button"
          className="pr-btn-secondary"
          style={{ ...styles.btnSecondary, fontSize: "11px", height: "26px", padding: "0 8px", color: "#64748b" }}
          onClick={handleResetDemo}
        >
          Reset Demo Prompt
        </button>
      </div>
    );
  }

  // 1. Unsupported Device/Browser state
  if (!isSupported || permission === "unsupported") {
    if (compact) return null;
    return (
      <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
        <style>{localCss}</style>
        <div style={styles.permissionCard}>
          <div style={styles.cardHeader}>
            <BellOff className="text-rose-500" size={20} />
            <span>Push Unsupported</span>
          </div>
          <p style={styles.cardDescription}>
            Notifications are not supported on this browser. You can register for SMS fallback notifications.
          </p>
          <div style={styles.actions}>
            <button
              type="button"
              className="pr-btn-secondary"
              style={styles.btnSecondary}
              onClick={() => setShowSMSForm(!showSMSForm)}
            >
              Use SMS Instead
            </button>
          </div>
          {showSMSForm && renderSMSForm()}
        </div>
      </div>
    );
  }

  // 2. iOS Safari standalone requirements banner
  if (isIOSDevice && !isAppStandalone && permission === "default") {
    if (compact) {
      return (
        <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
          <style>{localCss}</style>
          <div className="pr-compact-pill-default" style={styles.compactPill} title="Add app to Home Screen to allow push alerts">
            <Info size={14} className="pr-icon-pulse" />
            <span>iOS Safari: Add to Home Screen</span>
            <button type="button" className="pr-compact-btn-settings" style={styles.compactBtn} onClick={handleMaybeLater}>Later</button>
          </div>
        </div>
      );
    }

    return (
      <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
        <style>{localCss}</style>
        <div style={styles.permissionCard}>
          <div style={styles.cardHeader}>
            <Info className="text-amber-500" size={20} />
            <span>📱 iOS Notification Requirements</span>
          </div>
          <p style={styles.cardDescription}>
            To receive job alerts on iOS Safari, tap the Share button and select <strong>"Add to Home Screen"</strong>, then open the app from your home screen.
          </p>
          <div style={styles.actions}>
            <button type="button" className="pr-btn-secondary" style={styles.btnSecondary} onClick={handleMaybeLater}>
              Maybe Later
            </button>
            <button
              type="button"
              className="pr-btn-primary-default"
              style={styles.btnPrimary}
              onClick={() => setShowSMSForm(!showSMSForm)}
            >
              Use SMS Fallback
            </button>
          </div>
          {showSMSForm && renderSMSForm()}
        </div>
      </div>
    );
  }

  // 3. Granted State
  if (permission === "granted") {
    if (compact) {
      return (
        <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
          <style>{localCss}</style>
          <div className="pr-compact-pill-granted" style={styles.compactPill}>
            <Check size={14} />
            <span>Active</span>
            <button type="button" className="pr-compact-btn-disable" style={styles.compactBtn} onClick={handleDisable}>Disable</button>
          </div>
        </div>
      );
    }

    return (
      <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
        <style>{localCss}</style>
        <div style={styles.permissionCard}>
          <div style={styles.cardHeader}>
            <Check className="text-emerald-500" size={20} />
            <span>✅ Push Notifications Enabled</span>
          </div>
          <p style={styles.cardDescription}>
            You'll receive instant alerts. Never miss an assignment.
          </p>
          <div style={styles.actions}>
            <button
              type="button"
              className="pr-btn-secondary"
              style={styles.btnSecondary}
              onClick={handleDisable}
            >
              Disable
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 4. Denied State (within cooldown check)
  if (permission === "denied") {
    if (compact) {
      return (
        <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
          <style>{localCss}</style>
          <div className="pr-compact-pill-denied" style={styles.compactPill}>
            <BellOff size={14} />
            <span>Blocked</span>
            <button type="button" className="pr-compact-btn-settings" style={styles.compactBtn} onClick={handleSettingsClick}>Settings</button>
            <button type="button" className="pr-compact-btn-disable" style={{ ...styles.compactBtn, backgroundColor: "#fff" }} onClick={handleResetDemo}>Reset</button>
          </div>
          {showSettingsInfo && (
            <div style={{ ...styles.infoBox, marginTop: "8px", maxWidth: "250px" }}>
              To unblock notifications, open browser site settings and set Notifications to "Allow", then refresh.
            </div>
          )}
        </div>
      );
    }

    return (
      <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
        <style>{localCss}</style>
        <div style={styles.permissionCard}>
          <div style={styles.cardHeader}>
            <BellOff className="text-rose-500" size={20} />
            <span>❌ Push Notifications Blocked</span>
          </div>
          <div style={styles.cardDescription}>
            You can still receive:
            <ul style={styles.fallbackList}>
              <li style={styles.fallbackItem}><MessageSquare size={13} className="text-blue-500" /> SMS notifications</li>
              <li style={styles.fallbackItem}><Check size={13} className="text-emerald-500" /> In-app notifications</li>
            </ul>
          </div>
          <div style={styles.actions}>
            <button
              type="button"
              className="pr-btn-secondary"
              style={styles.btnSecondary}
              onClick={() => setShowSMSForm(!showSMSForm)}
            >
              Use SMS Instead
            </button>
            <button
              type="button"
              className="pr-btn-primary-danger"
              style={styles.btnPrimary}
              onClick={handleSettingsClick}
            >
              <Settings size={14} />
              <span>Enable in Settings</span>
            </button>
          </div>
          {showSettingsInfo && (
            <div style={styles.infoBox}>
              <Info size={16} className="text-slate-500 shrink-0" />
              <span>
                To unblock notifications: Click the lock or settings icon next to the URL in your browser's address bar, change Notifications to <strong>"Allow"</strong>, and refresh the page.
              </span>
            </div>
          )}
          {showSMSForm && renderSMSForm()}
        </div>
      </div>
    );
  }

  // 5. Default State (Prompt State)
  if (compact) {
    return (
      <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
        <style>{localCss}</style>
        <div className="pr-compact-pill-default" style={styles.compactPill}>
          <Bell size={14} className="pr-icon-pulse" />
          <span>Enable Push Alerts?</span>
          <button type="button" className="pr-compact-btn-enable" style={styles.compactBtn} onClick={requestPermission}>Enable</button>
          <button type="button" className="pr-compact-btn-settings" style={styles.compactBtn} onClick={handleMaybeLater}>Later</button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container} className={`noc-module ${className} pr-animate-in`}>
      <style>{localCss}</style>
      <div style={styles.permissionCard}>
        <div style={styles.cardHeader}>
          <Bell className="text-blue-500 pr-icon-pulse" size={20} />
          <span>📱 Enable Push Notifications</span>
        </div>
        <p style={styles.cardDescription}>
          Get instant alerts for new jobs. Never miss an assignment.
        </p>
        <div style={styles.actions}>
          <button
            type="button"
            className="pr-btn-secondary"
            style={styles.btnSecondary}
            onClick={handleMaybeLater}
          >
            Maybe Later
          </button>
          <button
            type="button"
            className="pr-btn-primary-default"
            style={styles.btnPrimary}
            onClick={requestPermission}
          >
            Enable Notifications
          </button>
        </div>
      </div>
    </div>
  );

  function renderSMSForm() {
    return (
      <div style={styles.smsForm} className="pr-animate-in">
        <p style={{ fontSize: "13px", fontWeight: 700, color: "#334155", margin: "0 0 6px 0" }}>
          SMS Alerts Subscription
        </p>
        {smsRegistered ? (
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "#166534", fontSize: "13px", fontWeight: 600 }}>
            <Check size={14} /> SMS number registered successfully!
          </div>
        ) : (
          <form onSubmit={handleRegisterSMS} style={{ display: "flex", gap: "8px" }}>
            <input
              type="tel"
              placeholder="+91 98765-43210"
              style={{
                height: "38px",
                padding: "8px 12px",
                border: "1px solid #cbd5e1",
                borderRadius: "8px",
                fontFamily: "inherit",
                fontSize: "13.5px",
                boxSizing: "border-box",
                flex: 1,
                outline: "none",
              }}
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              required
            />
            <button
              type="submit"
              className="pr-btn-primary-default"
              style={{ ...styles.btnPrimary, height: "38px" }}
            >
              <MessageSquare size={14} /> Subscribe
            </button>
          </form>
        )}
      </div>
    );
  }
};

export default PermissionRequest;

