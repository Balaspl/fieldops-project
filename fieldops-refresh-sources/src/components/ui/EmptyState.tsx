import React, { useState } from "react";
import { LucideIcon, Inbox } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string | React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className = "",
}) => {
  const [isHovered, setIsHovered] = useState(false);

  const keyframes = `
    @keyframes empty-state-fade-in {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    @keyframes empty-state-float {
      0% {
        transform: translateY(0px);
      }
      50% {
        transform: translateY(-8px);
      }
      100% {
        transform: translateY(0px);
      }
    }
  `;

  const containerStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "64px 24px",
    margin: "auto",
    textAlign: "center",
    width: "100%",
    minHeight: "320px",
    flex: 1,
    boxSizing: "border-box",
    animation: "empty-state-fade-in 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards",
  };

  const imageContainerStyle: React.CSSProperties = {
    width: "160px",
    height: "130px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: "16px",
    animation: "empty-state-float 3.5s ease-in-out infinite",
    transition: "transform 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
    transform: isHovered ? "scale(1.05)" : "scale(1)",
  };

  const imageStyle: React.CSSProperties = {
    maxWidth: "100%",
    maxHeight: "100%",
    objectFit: "contain",
    pointerEvents: "none",
  };

  const iconWrapStyle: React.CSSProperties = {
    width: "64px",
    height: "64px",
    borderRadius: "50%",
    background: "#EEF4F1",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: "16px",
    transition: "transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
    flexShrink: 0,
    transform: isHovered ? "scale(1.08)" : "scale(1)",
  };

  const titleStyle: React.CSSProperties = {
    fontSize: "14px",
    fontWeight: 700,
    color: "#2F4F3E",
    margin: "0 0 6px",
    fontFamily: "'Inter', sans-serif",
    lineHeight: 1.2,
  };

  const descriptionStyle: React.CSSProperties = {
    fontSize: "12px",
    color: "#6B7280",
    margin: 0,
    fontFamily: "'Inter', sans-serif",
    maxWidth: "340px",
    lineHeight: 1.5,
  };

  const actionStyle: React.CSSProperties = {
    marginTop: "16px",
    display: "flex",
    justifyContent: "center",
    gap: "8px",
  };

  // If the icon is the default Inbox, show the sweeping illustration image.
  // If a custom icon is explicitly passed (not Inbox), respect it and show the custom icon.
  const isDefaultIcon = Icon === Inbox;

  return (
    <div
      style={containerStyle}
      className={`empty-state-container ${className}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <style>{keyframes}</style>
      {isDefaultIcon ? (
        <div style={imageContainerStyle} className="empty-state-image-wrap">
          <img
            src="/empty-state.png?v=3"
            alt="No data available"
            style={imageStyle}
          />
        </div>
      ) : (
        <div style={iconWrapStyle} className="empty-state-icon-wrap">
          <Icon size={28} style={{ color: "#7AAE8A" }} />
        </div>
      )}
      <h3 style={titleStyle} className="empty-state-title">{title}</h3>
      {description && <p style={descriptionStyle} className="empty-state-description">{description}</p>}
      {action && <div style={actionStyle} className="empty-state-action">{action}</div>}
    </div>
  );
};

export default EmptyState;

