import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Building2,
  CalendarDays,
  ChevronDown,
  Clock3,
  Eye,
  IdCard,
  Mail,
  MapPin,
  Phone,
  RefreshCw,
  UsersRound,
} from "lucide-react";
import dispatcherService, { Dispatcher } from "../../services/dispatcherService";
import dispatcherBanner from "../../assets/dispatcher-banner.png";

const REFRESH_MS = 30000;

const localCss = `
  .dispatcher-page {
    width: 100%;
    min-height: 100%;
    padding: 18px 22px 28px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 20px;
    color: #172b24;
    font-family: 'Inter', sans-serif;
  }

  .dispatcher-profile-card {
    width: 100%;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    background: #ffffff;
    border: 1px solid #e0ebe5;
    border-radius: 20px;
    box-shadow: 0 5px 20px rgba(21, 73, 49, .06);
    box-sizing: border-box;
  }

  .dispatcher-banner {
    min-height: 200px;
    position: relative;
    display: flex;
    align-items: center;
    gap: 30px;
    padding: 26px 38px;
    overflow: hidden;
    border-radius: 20px;
    color: #ffffff;
    background: linear-gradient(112deg, #075632 0%, #087746 46%, #087c49 70%, #034b31 100%);
    box-sizing: border-box;
  }

  .dispatcher-banner::before,
  .dispatcher-banner::after {
    content: "";
    position: absolute;
    pointer-events: none;
    border: 1px solid rgba(164, 245, 191, .18);
    border-radius: 50%;
    transform: rotate(-8deg);
  }

  .dispatcher-banner.has-custom-art::before,
  .dispatcher-banner.has-custom-art::after {
    display: none;
  }

  .dispatcher-banner::before {
    width: 72%;
    height: 170px;
    left: 24%;
    bottom: -113px;
    box-shadow: 0 -18px 0 rgba(81, 203, 125, .08), 0 -36px 0 rgba(81, 203, 125, .05);
  }

  .dispatcher-banner::after {
    width: 42%;
    height: 135px;
    left: 40%;
    bottom: -104px;
    border-color: rgba(197, 255, 214, .15);
  }

  .dispatcher-avatar-large {
    z-index: 1;
    width: 132px;
    height: 132px;
    flex: 0 0 132px;
    display: grid;
    place-items: center;
    border: 5px solid rgba(255,255,255,.95);
    border-radius: 28px;
    background: linear-gradient(145deg, #75c66c, #16864d);
    color: #ffffff;
    font-size: 40px;
    font-weight: 800;
    box-shadow: 0 9px 22px rgba(0, 38, 22, .2), inset 0 1px 0 rgba(255,255,255,.35);
    box-sizing: border-box;
  }

  .dispatcher-banner-copy {
    z-index: 1;
    min-width: 0;
  }

  .dispatcher-banner-copy h2 {
    margin: 0 0 10px;
    color: #ffffff;
    font-size: clamp(24px, 2vw, 34px);
    line-height: 1.1;
    font-weight: 800;
    overflow-wrap: anywhere;
  }

  .dispatcher-role {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-bottom: 16px;
    color: rgba(255,255,255,.95);
    font-size: 16px;
    font-weight: 600;
  }

  .dispatcher-active-pill {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    padding: 9px 16px;
    border-radius: 999px;
    color: #075b32;
    background: #f7fff9;
    font-size: 14px;
    font-weight: 800;
  }

  .dispatcher-active-dot {
    width: 11px;
    height: 11px;
    border-radius: 50%;
    background: #16b341;
    box-shadow: 0 0 0 4px rgba(22,179,65,.12);
  }

  .dispatcher-banner-art {
    position: absolute;
    top: 0;
    right: 2%;
    bottom: 0;
    width: min(43%, 600px);
    display: flex;
    align-items: center;
    justify-content: center;
    color: rgba(245,255,248,.9);
    pointer-events: none;
  }

  .dispatcher-banner-art svg {
    filter: drop-shadow(0 4px 5px rgba(0, 30, 16, .12));
  }

  .dispatcher-details-card {
    padding: 20px 26px 24px;
    border: 1px solid #e1eaf0;
    border-radius: 18px;
    background: linear-gradient(145deg, #fbfdff, #f7fafc);
    box-shadow: 0 2px 7px rgba(30, 58, 77, .04);
    box-sizing: border-box;
  }

  .dispatcher-details-heading {
    min-height: 58px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 0 0 14px;
    border-bottom: 1px solid #dfe7ed;
  }

  .dispatcher-details-heading-title {
    display: flex;
    align-items: center;
    gap: 14px;
    color: #0c6b32;
  }

  .dispatcher-details-heading-title h3 {
    margin: 0;
    color: #172b30;
    font-size: 18px;
    font-weight: 800;
  }

  .dispatcher-actions-wrap {
    position: relative;
    z-index: 3;
  }

  .dispatcher-actions-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    min-height: 48px;
    padding: 0 18px;
    border: 1px solid #b8dfc8;
    border-radius: 12px;
    background: #ffffff;
    color: #087234;
    font-size: 14px;
    font-weight: 750;
    cursor: pointer;
    box-shadow: 0 3px 9px rgba(18, 95, 51, .08);
  }

  .dispatcher-actions-button:hover {
    background: #f3fbf6;
  }

  .dispatcher-actions-menu {
    position: absolute;
    top: calc(100% + 7px);
    right: 0;
    min-width: 205px;
    padding: 6px;
    border: 1px solid #dce9e2;
    border-radius: 12px;
    background: #ffffff;
    box-shadow: 0 12px 28px rgba(20, 54, 37, .16);
  }

  .dispatcher-actions-menu button {
    width: 100%;
    min-height: 40px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 10px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: #34483d;
    font: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }

  .dispatcher-actions-menu button:hover {
    background: #f0f8f3;
    color: #087234;
  }

  .dispatcher-details-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(0, .95fr);
    margin-top: 10px;
  }

  .dispatcher-info-list {
    padding: 4px 30px 0 0;
  }

  .dispatcher-info-row {
    min-height: 52px;
    display: grid;
    grid-template-columns: 38px minmax(120px, .75fr) minmax(0, 1.25fr);
    align-items: center;
    gap: 12px;
    border-bottom: 1px solid #e4ebef;
  }

  .dispatcher-info-icon {
    width: 36px;
    height: 36px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background: #eaf6ee;
    color: #087234;
  }

  .dispatcher-info-label {
    color: #425267;
    font-size: 14px;
    font-weight: 550;
  }

  .dispatcher-info-value {
    color: #182536;
    font-size: 14px;
    font-weight: 700;
    overflow-wrap: anywhere;
  }

  .dispatcher-status-column {
    padding: 8px 0 0 34px;
    border-left: 1px solid #dfe7ed;
  }

  .dispatcher-status-heading {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
    color: #087234;
  }

  .dispatcher-status-heading h4 {
    margin: 0;
    color: #172b30;
    font-size: 17px;
    font-weight: 800;
  }

  .dispatcher-duty-card {
    min-height: 88px;
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 20px;
    padding: 0 28px;
    border: 1px solid #d6efe0;
    border-radius: 17px;
    background: linear-gradient(110deg, #edf9f1, #e0f3e7);
    color: #0b6834;
    font-size: 25px;
    font-weight: 800;
    box-sizing: border-box;
  }

  .dispatcher-duty-card.is-off-duty {
    border-color: #eadfe0;
    background: linear-gradient(110deg, #fbf4f4, #f4eaea);
    color: #8c3939;
  }

  .dispatcher-duty-dot {
    width: 17px;
    height: 17px;
    flex: 0 0 17px;
    border-radius: 50%;
    background: #13a63b;
  }

  .is-off-duty .dispatcher-duty-dot {
    background: #b44949;
  }

  .dispatcher-timestamp-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
  }

  .dispatcher-timestamp-card {
    min-height: 92px;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 16px;
    border: 1px solid #dfe8ee;
    border-radius: 15px;
    background: linear-gradient(145deg, #f7fafc, #ffffff);
    box-sizing: border-box;
  }

  .dispatcher-timestamp-icon {
    width: 54px;
    height: 54px;
    flex: 0 0 54px;
    display: grid;
    place-items: center;
    border-radius: 15px;
    background: #e9f5ec;
    color: #087234;
  }

  .dispatcher-timestamp-label {
    margin-bottom: 5px;
    color: #526174;
    font-size: 13px;
    font-weight: 600;
  }

  .dispatcher-timestamp-value {
    color: #172536;
    font-size: 14px;
    font-weight: 750;
  }

  .dispatcher-state {
    min-height: 250px;
    display: grid;
    place-items: center;
    padding: 24px;
    border: 1px solid #e0ebe5;
    border-radius: 18px;
    background: #ffffff;
    color: #617268;
    text-align: center;
  }

  .dispatcher-state button {
    margin-top: 12px;
    padding: 10px 15px;
    border: 1px solid #b8dfc8;
    border-radius: 9px;
    background: #f3fbf6;
    color: #087234;
    font-weight: 700;
    cursor: pointer;
  }

  @media (max-width: 1000px) {
    .dispatcher-details-grid {
      grid-template-columns: minmax(0, 1fr);
    }
    .dispatcher-info-list {
      padding-right: 0;
    }
    .dispatcher-status-column {
      margin-top: 18px;
      padding: 20px 0 0;
      border-left: 0;
      border-top: 1px solid #dfe7ed;
    }
  }

  @media (max-width: 640px) {
    .dispatcher-page {
      padding: 12px;
      gap: 14px;
    }
    .dispatcher-profile-card {
      padding: 10px;
      gap: 12px;
      border-radius: 15px;
    }
    .dispatcher-banner {
      min-height: 160px;
      padding: 20px 16px;
      gap: 14px;
      border-radius: 14px;
    }
    .dispatcher-avatar-large {
      width: 74px;
      height: 74px;
      flex-basis: 74px;
      border-width: 3px;
      border-radius: 18px;
      font-size: 24px;
    }
    .dispatcher-role {
      margin-bottom: 9px;
      font-size: 12px;
    }
    .dispatcher-active-pill {
      padding: 6px 10px;
      font-size: 11px;
    }
    .dispatcher-banner-art {
      width: 34%;
      right: -8%;
      opacity: .5;
    }
    .dispatcher-details-card {
      padding: 14px;
      border-radius: 14px;
    }
    .dispatcher-details-heading-title h3 {
      font-size: 15px;
    }
    .dispatcher-actions-button {
      min-height: 40px;
      padding: 0 11px;
      font-size: 12px;
    }
    .dispatcher-info-row {
      grid-template-columns: 34px minmax(86px, .75fr) minmax(0, 1.15fr);
      gap: 8px;
      min-height: 48px;
    }
    .dispatcher-info-label,
    .dispatcher-info-value {
      font-size: 11px;
    }
    .dispatcher-info-icon {
      width: 32px;
      height: 32px;
    }
    .dispatcher-duty-card {
      min-height: 68px;
      margin-bottom: 12px;
      padding: 0 16px;
      font-size: 20px;
    }
    .dispatcher-timestamp-grid {
      grid-template-columns: minmax(0, 1fr);
      gap: 9px;
    }
    .dispatcher-timestamp-card {
      min-height: 76px;
      padding: 10px;
    }
    .dispatcher-timestamp-icon {
      width: 44px;
      height: 44px;
      flex-basis: 44px;
    }
    .dispatcher-timestamp-label,
    .dispatcher-timestamp-value {
      font-size: 12px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .dispatcher-actions-button,
    .dispatcher-actions-menu button {
      transition: none !important;
    }
  }
`;

function getInitials(name = "") {
  return name
    .trim()
    .split(/\s+/)
    .map((word) => word[0]?.toUpperCase() || "")
    .slice(0, 2)
    .join("");
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function DispatcherPage() {
  const [dispatchers, setDispatchers] = useState<Dispatcher[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Dispatcher | null>(null);
  const [openActionsId, setOpenActionsId] = useState<string | null>(null);

  const fetchDispatchers = useCallback(async (silent = false) => {
    try {
      if (silent) setRefreshing(true);
      else setLoading(true);
      setError("");
      const data = await dispatcherService.getDispatchers();
      setDispatchers(data);
    } catch (err: any) {
      console.error("Failed to load dispatchers:", err);
      setError(
        err?.response?.data?.detail ||
          err?.response?.data?.error ||
          "Failed to load dispatchers",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void fetchDispatchers();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && document.hasFocus()) {
        void fetchDispatchers(true);
      }
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [fetchDispatchers]);

  const openDetails = (dispatcher: Dispatcher) => {
    setSelected(dispatcher);
    setOpenActionsId(null);
  };

  const infoRows = (dispatcher: Dispatcher) => [
    { label: "Email", value: dispatcher.email || "—", Icon: Mail },
    { label: "Phone", value: dispatcher.phone_number || "—", Icon: Phone },
    { label: "Organization", value: dispatcher.organization_name || "—", Icon: Building2 },
    { label: "Tenant ID", value: dispatcher.tenant_id || "—", Icon: UsersRound },
    { label: "Dispatcher ID", value: dispatcher.id || "—", Icon: IdCard },
    { label: "Last Login", value: formatDateTime(dispatcher.last_login), Icon: CalendarDays },
  ];

  return (
    <div className="dispatcher-page">
      <style>{localCss}</style>

      {loading && (
        <div className="dispatcher-state" role="status">Loading dispatchers…</div>
      )}

      {!loading && error && (
        <div className="dispatcher-state" role="alert">
          <div>
            <div>{error}</div>
            <button type="button" onClick={() => void fetchDispatchers()}>
              Try again
            </button>
          </div>
        </div>
      )}

      {!loading && !error && dispatchers.length === 0 && (
        <div className="dispatcher-state">No dispatcher found.</div>
      )}

      {!loading && !error && dispatchers.map((dispatcher) => (
        <article className="dispatcher-profile-card" key={dispatcher.id}>
          <header
            className="dispatcher-banner has-custom-art"
            style={{
              backgroundImage: `url(${dispatcherBanner})`,
              backgroundSize: "cover",
              backgroundPosition: "center center",
            }}
          >
            <div className="dispatcher-avatar-large" aria-hidden="true">
              {getInitials(dispatcher.name)}
            </div>

            <div className="dispatcher-banner-copy">
              <h2>{dispatcher.name || "Dispatcher"}</h2>
              <div className="dispatcher-role">
                <UsersRound size={20} />
                Dispatcher
              </div>
              <span className="dispatcher-active-pill">
                <span
                  className="dispatcher-active-dot"
                  style={!dispatcher.is_active ? { background: "#89969a" } : undefined}
                />
                {dispatcher.is_active ? "Active" : "Inactive"}
              </span>
            </div>

          </header>

          <section className="dispatcher-details-card" aria-label={`Details for ${dispatcher.name}`}>
            <div className="dispatcher-details-heading">
              <div className="dispatcher-details-heading-title">
                <UsersRound size={30} strokeWidth={2.5} />
                <h3>Dispatcher Details</h3>
              </div>

              <div className="dispatcher-actions-wrap">
                <button
                  type="button"
                  className="dispatcher-actions-button"
                  aria-expanded={openActionsId === dispatcher.id}
                  aria-haspopup="menu"
                  onClick={() => setOpenActionsId((current) => current === dispatcher.id ? null : dispatcher.id)}
                >
                  Actions <ChevronDown size={17} />
                </button>
                {openActionsId === dispatcher.id && (
                  <div className="dispatcher-actions-menu" role="menu">
                    <button type="button" role="menuitem" onClick={() => openDetails(dispatcher)}>
                      <Eye size={16} /> View full details
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setOpenActionsId(null);
                        void fetchDispatchers(true);
                      }}
                    >
                      <RefreshCw size={16} /> {refreshing ? "Refreshing…" : "Refresh dispatcher"}
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="dispatcher-details-grid">
              <div className="dispatcher-info-list">
                {infoRows(dispatcher).map(({ label, value, Icon }) => (
                  <div className="dispatcher-info-row" key={label}>
                    <span className="dispatcher-info-icon"><Icon size={21} strokeWidth={2.3} /></span>
                    <span className="dispatcher-info-label">{label}</span>
                    <span className="dispatcher-info-value">{value}</span>
                  </div>
                ))}
              </div>

              <aside className="dispatcher-status-column">
                <div className="dispatcher-status-heading">
                  <Activity size={27} strokeWidth={2.5} />
                  <h4>Status</h4>
                </div>

                <div className={`dispatcher-duty-card${dispatcher.is_on_duty ? "" : " is-off-duty"}`}>
                  <span className="dispatcher-duty-dot" />
                  {dispatcher.is_on_duty ? "On Duty" : "Off Duty"}
                </div>

                <div className="dispatcher-timestamp-grid">
                  <div className="dispatcher-timestamp-card">
                    <span className="dispatcher-timestamp-icon"><CalendarDays size={34} /></span>
                    <span>
                      <div className="dispatcher-timestamp-label">Account Created</div>
                      <div className="dispatcher-timestamp-value">{formatDate(dispatcher.created_at)}</div>
                    </span>
                  </div>
                  <div className="dispatcher-timestamp-card">
                    <span className="dispatcher-timestamp-icon"><Clock3 size={34} /></span>
                    <span>
                      <div className="dispatcher-timestamp-label">Last Updated</div>
                      <div className="dispatcher-timestamp-value">{formatDateTime(dispatcher.updated_at)}</div>
                    </span>
                  </div>
                </div>
              </aside>
            </div>
          </section>
        </article>
      ))}

      {selected && (
        <>
          <div
            onClick={() => setSelected(null)}
            style={{ position: "fixed", inset: 0, zIndex: 999, background: "rgba(20,40,30,.28)" }}
          />
          <aside
            className="dispatcher-sidebar"
            style={{
              position: "fixed", top: 0, right: 0, zIndex: 1000, width: "min(440px, 100vw)", height: "100vh",
              padding: 24, boxSizing: "border-box", overflowY: "auto", background: "#fff",
              boxShadow: "-8px 0 30px rgba(20,54,37,.16)", fontFamily: "'Inter', sans-serif",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
              <h3 style={{ margin: 0, color: "#0b6834", fontSize: 18 }}>Dispatcher Details</h3>
              <button type="button" onClick={() => setSelected(null)} aria-label="Close dispatcher details" style={{ border: 0, background: "transparent", color: "#526174", fontSize: 28, cursor: "pointer" }}>×</button>
            </div>
            <div style={{ display: "grid", gap: 14 }}>
              {[
                ["Name", selected.name],
                ["Role", "Dispatcher"],
                ["Email", selected.email],
                ["Phone", selected.phone_number || "—"],
                ["Organization", selected.organization_name || "—"],
                ["Tenant ID", selected.tenant_id || "—"],
                ["Dispatcher ID", selected.id],
                ["Account Status", selected.is_active ? "Active" : "Inactive"],
                ["Duty Status", selected.is_on_duty ? "On Duty" : "Off Duty"],
                ["Last Login", formatDateTime(selected.last_login)],
                ["Account Created", formatDateTime(selected.created_at)],
                ["Last Updated", formatDateTime(selected.updated_at)],
              ].map(([label, value]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 18, paddingBottom: 10, borderBottom: "1px solid #edf2ef", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>{label}</span>
                  <strong style={{ maxWidth: "62%", color: "#172b24", textAlign: "right", overflowWrap: "anywhere" }}>{value}</strong>
                </div>
              ))}
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
