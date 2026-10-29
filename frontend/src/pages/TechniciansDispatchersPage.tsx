import React, { useEffect, useState } from "react";
import { Users } from "lucide-react";
import TechnicianListPage from "./TechDashboardPage";
import DispatcherPage from "./dispatcher/DispatcherPage";

export type StaffView = "technicians" | "dispatchers";

interface TechniciansDispatchersPageProps {
  activeView?: StaffView;
  allowDispatcherToggle?: boolean;
  onViewChange?: (view: StaffView) => void;
}

export default function TechniciansDispatchersPage({
  activeView: requestedView,
  allowDispatcherToggle = true,
  onViewChange,
}: TechniciansDispatchersPageProps) {
  const [activeView, setActiveView] = useState<StaffView>(
    requestedView ?? "technicians",
  );

  // Keep the displayed page synchronized with App.tsx navigation.
  useEffect(() => {
    setActiveView(requestedView ?? "technicians");
  }, [requestedView]);

  const changeView = (view: StaffView) => {
    setActiveView(view);
    onViewChange?.(view);
  };

  const tabStyle = (selected: boolean): React.CSSProperties => ({
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    minHeight: "40px",
    padding: "0 18px",
    border: selected
      ? "1px solid #168653"
      : "1px solid #E3ECE7",
    borderRadius: "9px",
    background: selected ? "#168653" : "#FFFFFF",
    color: selected ? "#FFFFFF" : "#334155",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap",
  });

  return (
    <div
      style={{
        height: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        padding: "14px",
        boxSizing: "border-box",
        background: "#EEF4F1",
        overflow: "hidden",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <style>{`
        .staff-switch-body {
          flex: 1;
          min-height: 0;
          overflow: auto;
        }

        .staff-switch-body .tld-header-responsive > div:first-child,
        .staff-switch-body .dispatcher-header > div:first-child {
          display: none !important;
        }

        .staff-switch-body .tld-header-responsive,
        .staff-switch-body .dispatcher-header {
          justify-content: flex-end !important;
        }

        @media (max-width: 600px) {
          .staff-switch-heading {
            flex-direction: column !important;
            align-items: flex-start !important;
          }

          .staff-switch-buttons {
            width: 100%;
          }

          .staff-switch-buttons button {
            flex: 1;
          }
        }
      `}</style>

      <div
        className="staff-switch-heading"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
          flexWrap: "wrap",
          padding: "16px 20px",
          background: "#FFFFFF",
          border: "1px solid #E3ECE7",
          borderRadius: "12px",
          boxShadow: "0 1px 4px rgba(47,79,62,.05)",
          boxSizing: "border-box",
        }}
      >
        <div>
          <h1
            style={{
              margin: 0,
              fontSize: "20px",
              fontWeight: 750,
              color: "#172B24",
            }}
          >
            {allowDispatcherToggle
              ? "Technicians & Dispatchers"
              : activeView === "dispatchers"
                ? "Dispatchers"
                : "Technicians"}
          </h1>

          <p
            style={{
              margin: "6px 0 0",
              fontSize: "12px",
              color: "#64748B",
            }}
          >
            Manage your organization's staff
          </p>
        </div>

        {allowDispatcherToggle && (
          <div
            className="staff-switch-buttons"
            role="tablist"
            aria-label="Choose staff type"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <button
              type="button"
              role="tab"
              aria-selected={activeView === "technicians"}
              style={tabStyle(activeView === "technicians")}
              onClick={() => changeView("technicians")}
            >
              <Users size={16} />
              Technicians
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={activeView === "dispatchers"}
              style={tabStyle(activeView === "dispatchers")}
              onClick={() => changeView("dispatchers")}
            >
              <Users size={16} />
              Dispatchers
            </button>
          </div>
        )}
      </div>

      <div className="staff-switch-body">
        {activeView === "technicians" ? (
          <TechnicianListPage />
        ) : (
          <DispatcherPage />
        )}
      </div>
    </div>
  );
}