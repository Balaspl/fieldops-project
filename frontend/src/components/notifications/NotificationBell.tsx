import React, { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { motion } from "framer-motion";
import { NotificationBellProps } from "../../types/notifications.ts";

const playBeep = () => {
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;
    const audioCtx = new AudioContextClass();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
    gainNode.gain.setValueAtTime(0.08, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.15);

    oscillator.start();
    oscillator.stop(audioCtx.currentTime + 0.15);
  } catch (e) {
    console.warn("Web Audio Context blocked or unsupported:", e);
  }
};

const styles = {
  container: {
    boxSizing: "border-box",
  } as React.CSSProperties,

  bell: {
    position: "relative",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    cursor: "pointer",
    outline: "none",
    transition: "all 0.2s ease-in-out",
    padding: "0",
  } as React.CSSProperties,

  badge: {
    position: "absolute",
    top: "-5px",
    right: "-5px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: "16px",
    height: "16px",
    padding: "0 3px",
    fontSize: "9px",
    fontWeight: 700,
    borderRadius: "8px",
    border: "2px solid #ffffff",
    transition: "background-color 0.2s ease",
  } as React.CSSProperties,
};

export const NotificationBell: React.FC<NotificationBellProps> = ({
  unreadCount,
  onClick,
  isAnimated = true,
  showSound = true,
  className = ""
}) => {
  const prevCount = useRef(unreadCount);
  const [bounce, setBounce] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    if (unreadCount > prevCount.current) {
      if (isAnimated) {
        setBounce(true);
        const timer = setTimeout(() => setBounce(false), 500);
        return () => clearTimeout(timer);
      }
      if (showSound) {
        playBeep();
      }
    }
    prevCount.current = unreadCount;
  }, [unreadCount, isAnimated, showSound]);

  // Clean trigger for manual animation props
  useEffect(() => {
    if (isAnimated && unreadCount > 0) {
      setBounce(true);
      const timer = setTimeout(() => setBounce(false), 500);
      return () => clearTimeout(timer);
    }
  }, [isAnimated]);

  const displayCount = unreadCount > 99 ? "99+" : unreadCount;
  const hasUnread = unreadCount > 0;
  const ariaLabel = `Notifications, ${unreadCount} unread`;

  const bellStyle: React.CSSProperties = {
    ...styles.bell,
    backgroundColor: isHovered ? "#f8fafc" : "#ffffff",
    color: hasUnread ? "#dc2626" : "#16a34a",
    borderColor: isHovered ? "#cbd5e1" : "#e2e8f0",
    borderStyle: "solid",
    borderWidth: "1px",
  };

  const badgeStyle: React.CSSProperties = {
    ...styles.badge,
    backgroundColor: hasUnread ? "#dc2626" : "#16a34a",
    color: "#ffffff",
  };

  return (
    <div style={styles.container} className={`noc-module ${className}`}>
      <button
        type="button"
        style={bellStyle}
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-label={ariaLabel}
        title={ariaLabel}
      >
        <motion.div
          animate={bounce ? { rotate: [0, -15, 15, -15, 15, 0] } : {}}
          transition={{ duration: 0.5 }}
          style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <Bell size={16} fill="currentColor" strokeWidth={2.5} />
        </motion.div>
        
        <span
          style={badgeStyle}
          aria-hidden="true"
        >
          {displayCount}
        </span>
      </button>
    </div>
  );
};

export default NotificationBell;
