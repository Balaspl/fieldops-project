import { useEffect } from "react";
import { useCustomerTrackingStore } from "../../store/customerTrackingStore";

export default function PublicTrackingPage({ token }: { token: string }) {
  const { job, technician, latestGps, eta, expired, loading, error, fetchTrackingInfo } = useCustomerTrackingStore();

  useEffect(() => {
    let active = true;
    const refresh = () => { if (active) void fetchTrackingInfo(token); };
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [token, fetchTrackingInfo]);

  if (loading && !job) return <main style={layout}><h1>Loading tracking details…</h1></main>;
  if (expired || error || !job) return <main style={layout}><h1>Tracking link unavailable</h1><p>{error || "This tracking link has expired or could not be found."}</p></main>;

  return <main style={layout}>
    <section style={card}>
      <h1>Service tracking</h1>
      <p>Job #{job.id} · {job.service_type || "Service visit"}</p>
      <p><b>Status:</b> {job.status}</p>
      <p><b>Location:</b> {job.site_address || "Not available"}</p>
      <p><b>Appointment:</b> {job.scheduled_window || "Not specified"}</p>
      {job.issue_description && <p>{job.issue_description}</p>}
      {technician && <p><b>Technician:</b> {technician.name}</p>}
      {eta != null && <p><b>Estimated arrival:</b> about {eta} minutes</p>}
      {latestGps && <p>
        Technician location updated {latestGps.timestamp ? new Date(latestGps.timestamp).toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }) : "recently"}.{" "}
        <a href={`https://www.google.com/maps/search/?api=1&query=${latestGps.latitude},${latestGps.longitude}`} target="_blank" rel="noreferrer">View current location</a>
      </p>}
      {!technician && <p>Technician details will appear here when assigned.</p>}
    </section>
  </main>;
}

const layout: React.CSSProperties = { minHeight: "100vh", padding: 24, background: "#EEF4F1", fontFamily: "Inter, sans-serif", color: "#1F2933" };
const card: React.CSSProperties = { maxWidth: 640, margin: "8vh auto", padding: 28, background: "white", border: "1px solid #E3ECE7", borderRadius: 14, boxShadow: "0 4px 14px rgba(15,23,42,.06)" };
