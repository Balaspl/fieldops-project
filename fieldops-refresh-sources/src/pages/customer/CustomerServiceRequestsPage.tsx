import { useState, useEffect, useRef } from "react";
import {
  FileText,
  PlusCircle,
  XCircle,
  AlertCircle,
  CheckCircle,
  CheckCircle2,
  X,
  Clock,
  Send,
  MapPin,
  UserCheck,
  Users,
  Briefcase,
  Navigation,
  Phone,
  User,
  Receipt,
  Printer,
  Download,
  ExternalLink,
  ShieldCheck,
  MessageSquare,
} from "lucide-react";

import {
  getServiceRequests,
  createServiceRequest,
  cancelServiceRequest,
  getCustomerInvoice,
  updateServiceRequest,
  type CustomerInvoiceResponse,
} from "../../services/customerPortalService";

import api from "../../services/api";
import { OlaMaps } from "olamaps-web-sdk";
import AnimatedJobProgress from "../../components/customer-tracking/AnimatedJobProgress";
import JobLiveTrackingMap from "../../components/customer-tracking/JobLiveTrackingMap";
import CustomerNewRequestMarketplace from "../../components/customer/CustomerNewRequestMarketplace";
import JobMessagePanel from "../../components/customer-tracking/JobMessagePanel";
import { useTrackingStore } from "../../store/trackingStore";

const OLA_STYLE =
  "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

const getDisplayStatusText = (status: string) => {
  const s = String(status || "").trim().toUpperCase();
  switch (s) {
    case "CREATED":
    case "PENDING":
    case "UNASSIGNED":
      return "UNASSIGNED";
    case "ASSIGNED":
      return "AWAITING ACCEPTANCE";
    case "ACCEPTED":
      return "ASSIGNED";
    case "EN_ROUTE":
      return "EN ROUTE";
    case "ON_SITE":
    case "IN_PROGRESS":
      return "IN PROGRESS";
    case "COMPLETED":
    case "CLOSED":
      return "COMPLETED";
    case "CANCELLED":
      return "CANCELLED";
    case "QUEUED":
      return "UNASSIGNED";
    case "REJECTED_BY_TECHNICIAN":
      return "REJECTED";
    default:
      return s;
  }
};

const badge = (status: string) => {
  const displayStatus = getDisplayStatusText(status);

  const colors: Record<string, { bg: string; color: string; border: string }> = {
    UNASSIGNED: { bg: "#FEF3C7", color: "#B45309", border: "#FDE68A" },
    "AWAITING ACCEPTANCE": { bg: "#FFF7ED", color: "#C2410C", border: "#FFEDD5" },
    ASSIGNED: { bg: "#EFF6FF", color: "#1D4ED8", border: "#DBEAFE" },
    "EN ROUTE": { bg: "#F0F9FF", color: "#0284C7", border: "#BAE6FD" },
    "IN PROGRESS": { bg: "#F5F3FF", color: "#7C3AED", border: "#DDD6FE" },
    COMPLETED: { bg: "#ECFDF5", color: "#059669", border: "#A7F3D0" },
    CANCELLED: { bg: "#FEF2F2", color: "#DC2626", border: "#FECACA" },
    REJECTED: { bg: "#FFF1F2", color: "#BE123C", border: "#FECDD3" },
  };

  const style = colors[displayStatus] || { bg: "#F1F5F9", color: "#64748B", border: "#E2E8F0" };

  return {
    fontSize: "11px",
    fontWeight: 700,
    padding: "3px 10px",
    borderRadius: "20px",
    background: style.bg,
    color: style.color,
    border: `1px solid ${style.border}`,
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.3px",
  };
};

interface CustomerServiceRequestsPageProps {
  createOnly?: boolean;
  onNavigate?: (tab: string) => void;
}

export default function CustomerServiceRequestsPage({
  createOnly = false,
  onNavigate,
}: CustomerServiceRequestsPageProps) {
  const [requests, setRequests] = useState<any[]>([]);
  const [activeCardFilter, setActiveCardFilter] = useState<string>("ALL");
  const [chatRequest, setChatRequest] = useState<any | null>(null);

  const normalizeStatus = (status: any) => {
    if (!status) return "";
    return String(status).trim().toUpperCase();
  };

  const isUnassigned = (s: string) =>
    ["CREATED", "PENDING", "UNASSIGNED", "ASSIGNED", "QUEUED"].includes(s);

  const isAssigned = (s: string) =>
    s === "ACCEPTED";

  const isActiveJob = (s: string) =>
    ["EN_ROUTE", "ON_SITE", "IN_PROGRESS"].includes(s);

  const isCompleted = (s: string) =>
    ["COMPLETED", "CLOSED"].includes(s);

  const isCancelled = (s: string) =>
    s === "CANCELLED";

  const totalRequestsCount = requests.length;
  const unassignedCount = requests.filter((r) => isUnassigned(normalizeStatus(r.status))).length;
  const assignedCount = requests.filter((r) => isAssigned(normalizeStatus(r.status))).length;
  const activeJobsCount = requests.filter((r) => isActiveJob(normalizeStatus(r.status))).length;
  const completedJobsCount = requests.filter((r) => isCompleted(normalizeStatus(r.status))).length;
  const cancelledJobsCount = requests.filter((r) => isCancelled(normalizeStatus(r.status))).length;

  const statsCards = [
    {
      key: "ALL",
      label: "Total Requests",
      value: totalRequestsCount,
      icon: <FileText size={18} strokeWidth={2.2} />,
      iconBg: "#DCFCE7",
      color: "#10B981",
      valueColor: "#0F172A",
      gradStart: "rgba(167, 243, 208, 0.45)",
      gradEnd: "rgba(110, 231, 183, 0.85)",
    },
    {
      key: "UNASSIGNED",
      label: "Unassigned Jobs",
      value: unassignedCount,
      icon: <Clock size={18} strokeWidth={2.2} />,
      iconBg: "#FEF3C7",
      color: "#F59E0B",
      valueColor: "#92400E",
      gradStart: "rgba(254, 215, 170, 0.45)",
      gradEnd: "rgba(253, 224, 71, 0.85)",
    },
    {
      key: "ASSIGNED",
      label: "Assigned Jobs",
      value: assignedCount,
      icon: <Users size={18} strokeWidth={2.2} />,
      iconBg: "#DBEAFE",
      color: "#2563EB",
      valueColor: "#1E40AF",
      gradStart: "rgba(191, 219, 254, 0.45)",
      gradEnd: "rgba(147, 197, 253, 0.85)",
    },
    {
      key: "ACTIVE",
      label: "Active Jobs",
      value: activeJobsCount,
      icon: <Briefcase size={18} strokeWidth={2.2} />,
      iconBg: "#F3E8FF",
      color: "#9333EA",
      valueColor: "#581C87",
      gradStart: "rgba(233, 213, 255, 0.45)",
      gradEnd: "rgba(196, 181, 253, 0.85)",
    },
    {
      key: "COMPLETED",
      label: "Completed Jobs",
      value: completedJobsCount,
      icon: <CheckCircle2 size={18} strokeWidth={2.2} />,
      iconBg: "#DCFCE7",
      color: "#10B981",
      valueColor: "#065F46",
      gradStart: "rgba(167, 243, 208, 0.45)",
      gradEnd: "rgba(110, 231, 183, 0.85)",
    },
    {
      key: "CANCELLED",
      label: "Cancelled Jobs",
      value: cancelledJobsCount,
      icon: <XCircle size={18} strokeWidth={2.2} />,
      iconBg: "#FEE2E2",
      color: "#EF4444",
      valueColor: "#991B1B",
      gradStart: "rgba(254, 202, 202, 0.5)",
      gradEnd: "rgba(248, 113, 113, 0.85)",
    },
  ];

  const displayedRequests = requests.filter((sr) => {
    const s = normalizeStatus(sr.status);
    if (activeCardFilter === "UNASSIGNED") return isUnassigned(s);
    if (activeCardFilter === "ASSIGNED") return isAssigned(s);
    if (activeCardFilter === "ACTIVE") return isActiveJob(s);
    if (activeCardFilter === "COMPLETED") return isCompleted(s);
    if (activeCardFilter === "CANCELLED") return isCancelled(s);
    return true;
  });
  const [loading, setLoading] = useState(!createOnly);

  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  // Job Tracking & Invoice Modal State
  const [trackingModalRequest, setTrackingModalRequest] = useState<any | null>(null);
  const [trackingJobDetails, setTrackingJobDetails] = useState<any | null>(null);
  const [trackingInvoiceDetails, setTrackingInvoiceDetails] = useState<CustomerInvoiceResponse | null>(null);
  const [trackingLoading, setTrackingLoading] = useState<boolean>(false);

  // Dedicated Standalone Live Map Modal State
  const [liveMapModalRequest, setLiveMapModalRequest] = useState<any | null>(null);
  const [liveMapJobDetails, setLiveMapJobDetails] = useState<any | null>(null);
  const [liveMapLoading, setLiveMapLoading] = useState<boolean>(false);

  const handleOpenDedicatedLiveMap = async (sr: any, existingJobDetails?: any) => {
    if (!sr) return;
    setLiveMapModalRequest(sr);

    if (existingJobDetails) {
      setLiveMapJobDetails(existingJobDetails);
      setLiveMapLoading(false);
    } else {
      setLiveMapJobDetails({
        id: sr.linked_job_id || sr.id,
        site_latitude: sr.site_latitude || 13.0495,
        site_longitude: sr.site_longitude || 80.2282,
        status: sr.status,
        location: sr.location,
        assigned_technician_id: sr.assigned_technician_id,
        assigned_technician_name: sr.assigned_technician_name,
        technician_latitude: sr.technician_latitude || null,
        technician_longitude: sr.technician_longitude || null,
      });
      setLiveMapLoading(false);
    }

    const targetJobId = sr.linked_job_id || sr.id;
    if (targetJobId) {
      try {
        const res = await api.get(`/api/customer/jobs/${targetJobId}`);
        if (res.data) {
          setLiveMapJobDetails(res.data);
        }
      } catch (err) {
        console.error("Error fetching live map details:", err);
      }
    }
  };

  const handleOpenTracking = async (sr: any) => {
    setTrackingModalRequest(sr);
    setTrackingJobDetails(null);
    setTrackingInvoiceDetails(null);
    setTrackingLoading(true);

    try {
      if (sr.linked_job_id) {
        let fetchedJobStatus = sr.status;
        try {
          const res = await api.get(`/api/customer/jobs/${sr.linked_job_id}`);
          if (res.data) {
            setTrackingJobDetails(res.data);
            fetchedJobStatus = res.data.status || sr.status;
            useTrackingStore.getState().setJobTrackingSnapshot(String(sr.linked_job_id), {
              status: fetchedJobStatus,
              eta: res.data.estimated_arrival ?? null,
              duration_minutes: res.data.eta_duration_minutes ?? null,
            });
            if (res.data.status && res.data.status !== sr.status) {
              setRequests((prev) =>
                prev.map((r) => (r.id === sr.id ? { ...r, status: res.data.status } : r))
              );
            }
          }
        } catch (err) {
          console.error("Error fetching job tracking details:", err);
        }

        const s = normalizeStatus(fetchedJobStatus);
        if (["COMPLETED", "CLOSED"].includes(s)) {
          try {
            const invRes = await getCustomerInvoice(sr.linked_job_id);
            if (invRes.data) {
              setTrackingInvoiceDetails(invRes.data);
            }
          } catch (invErr) {
            console.error("Error fetching invoice:", invErr);
          }
        }
      }
    } finally {
      setTrackingLoading(false);
    }
  };

  // Real-time polling while Track Job modal is open
  useEffect(() => {
    const linkedJobId = trackingModalRequest?.linked_job_id;
    if (!linkedJobId) return;

    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/customer/jobs/${linkedJobId}`);
        if (!isMounted || !res.data) return;

        setTrackingJobDetails(res.data);

        useTrackingStore.getState().setJobTrackingSnapshot(String(linkedJobId), {
          status: res.data.status,
          eta: res.data.estimated_arrival ?? null,
          duration_minutes: res.data.eta_duration_minutes ?? null,
        });

        const normSt = normalizeStatus(res.data.status);
        if (["COMPLETED", "CLOSED"].includes(normSt) && !trackingInvoiceDetails) {
          try {
            const invRes = await getCustomerInvoice(linkedJobId);
            if (isMounted && invRes.data) {
              setTrackingInvoiceDetails(invRes.data);
            }
          } catch (invErr) {
            console.error("Error polling invoice:", invErr);
          }
        }

        setRequests((prev) =>
          prev.map((r) =>
            r.linked_job_id === linkedJobId || r.id === trackingModalRequest.id
              ? { ...r, status: res.data.status }
              : r
          )
        );
      } catch (err) {
        console.error("Error polling tracking job details:", err);
      }
    }, 3000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [trackingModalRequest?.linked_job_id, trackingModalRequest?.id, trackingInvoiceDetails]);

  const handlePrintInvoice = (inv: CustomerInvoiceResponse, req: any) => {
    const printWindow = window.open("", "_blank");
    if (!printWindow) return;

    const orgName = inv.organization_name || "FieldOps Certified Service";
    const techName = inv.technician_name || "Assigned Technician";
    const dateStr = inv.completed_at ? new Date(inv.completed_at).toLocaleDateString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
    }) : new Date().toLocaleDateString("en-IN");

    const html = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Invoice #${inv.id} - ${orgName}</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; color: #1e293b; line-height: 1.5; }
          .header { border-bottom: 2px solid #069660; padding-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-start; }
          .org-name { font-size: 26px; font-weight: 800; color: #069660; margin: 0; }
          .invoice-badge { background: #dcfce7; color: #065f46; font-weight: 700; font-size: 14px; padding: 6px 14px; border-radius: 20px; text-transform: uppercase; }
          .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px; }
          .meta-label { font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; }
          .meta-val { font-size: 15px; font-weight: 600; color: #0f172a; }
          table { width: 100%; border-collapse: collapse; margin-top: 24px; }
          th { background: #f8fafc; text-align: left; padding: 12px; font-size: 12px; color: #475569; text-transform: uppercase; border-bottom: 1px solid #e2e8f0; }
          td { padding: 14px 12px; border-bottom: 1px solid #f1f5f9; font-size: 14px; }
          .amount-col { text-align: right; }
          .total-row td { font-size: 18px; font-weight: 800; color: #069660; border-top: 2px solid #069660; }
          .footer { margin-top: 50px; text-align: center; font-size: 13px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 20px; }
          @media print {
            body { margin: 20px; }
          }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <h1 class="org-name">${orgName}</h1>
            <p style="margin: 4px 0 0; color: #64748b; font-size: 14px;">Official Service Receipt & Tax Invoice</p>
          </div>
          <div style="text-align: right;">
            <span class="invoice-badge">PAID</span>
            <p style="margin: 8px 0 0; font-size: 14px; font-weight: 700; color: #334155;">Invoice #${inv.id}</p>
            <p style="margin: 2px 0 0; font-size: 12px; color: #64748b;">${dateStr}</p>
          </div>
        </div>

        <div class="grid">
          <div>
            <div class="meta-label">Customer Details</div>
            <div class="meta-val">${inv.customer_name || req.contact_number || "Valued Customer"}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">${inv.location || req.location || "Service Location"}</div>
          </div>
          <div style="text-align: right;">
            <div class="meta-label">Service Organization</div>
            <div class="meta-val">${orgName}</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 4px;">Technician: <strong>${techName}</strong></div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Job ID: #${inv.job_id}</div>
          </div>
        </div>

        <div style="margin-top: 20px;">
          <div class="meta-label">Service Summary</div>
          <div style="font-size: 14px; color: #334155; background: #f8fafc; padding: 12px 16px; border-radius: 8px; border: 1px solid #e2e8f0;">
            <strong>${inv.service_type || req.service_type || "Service"}</strong>: ${inv.work_summary || req.description || "Work completed successfully as per specifications."}
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>Description</th>
              <th class="amount-col">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Labour Charges</td>
              <td class="amount-col">₹${inv.labour_cost.toFixed(2)}</td>
            </tr>
            <tr>
              <td>Material / Spares Charges</td>
              <td class="amount-col">₹${inv.material_cost.toFixed(2)}</td>
            </tr>
            <tr>
              <td style="font-weight: 600;">Subtotal</td>
              <td class="amount-col" style="font-weight: 600;">₹${inv.subtotal.toFixed(2)}</td>
            </tr>
            <tr>
              <td>GST (${((inv.gst_rate || 0.18) * 100).toFixed(0)}%)</td>
              <td class="amount-col">₹${inv.gst_amount.toFixed(2)}</td>
            </tr>
            <tr class="total-row">
              <td>Total Paid</td>
              <td class="amount-col">₹${inv.total_amount.toFixed(2)}</td>
            </tr>
          </tbody>
        </table>

        <div class="footer">
          Thank you for choosing ${orgName}. Official digital record for completed service job #${inv.job_id}.
        </div>

        <script>
          window.onload = function() { window.print(); }
        </script>
      </body>
      </html>
    `;

    printWindow.document.write(html);
    printWindow.document.close();
  };

  const [form, setForm] = useState({
    title: "",
    description: "",
    service_type: "",
    priority: "select priority",
    preferred_visit_date: "",
    location: "",
    contact_number: "",
  });

  const [siteLatitude, setSiteLatitude] =
    useState<number | null>(null);

  const [siteLongitude, setSiteLongitude] =
    useState<number | null>(null);

  const [isGettingLocation, setIsGettingLocation] =
    useState(false);

  const [locationSearch, setLocationSearch] =
    useState("");

  const [locationResults, setLocationResults] =
    useState<any[]>([]);

  const [isSearchingLocations, setIsSearchingLocations] =
    useState(false);

  const [locationSearchError, setLocationSearchError] =
    useState("");

  const [selectedLocationName, setSelectedLocationName] =
    useState("");

  const [locationConfirmed, setLocationConfirmed] =
    useState(false);

  const [mapVisible, setMapVisible] =
    useState(false);

  const [mapError, setMapError] =
    useState(false);

  const [mapTarget, setMapTarget] =
    useState<{
      latitude: number;
      longitude: number;
    } | null>(null);

  const [isResolvingMapCenter, setIsResolvingMapCenter] =
    useState(false);

  const mapContainerRef =
    useRef<HTMLDivElement | null>(null);

  const olaMapRef =
    useRef<any>(null);

  const programmaticMapMove =
    useRef(false);

  const reverseGeocodeSequence =
    useRef(0);

  const mapRequestId =
    useRef(0);

  const selectedLocationSearch =
    useRef("");

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  const [loadError, setLoadError] =
    useState("");

  const [success, setSuccess] =
    useState("");

  useEffect(() => {
    const query = locationSearch.trim();

    if (
      query ===
      selectedLocationSearch.current
    ) {
      selectedLocationSearch.current =
        "";
      setLocationResults([]);
      setIsSearchingLocations(false);
      setLocationSearchError("");
      return;
    }

    if (query.length < 2) {
      setLocationResults([]);
      setIsSearchingLocations(false);
      setLocationSearchError("");
      return;
    }

    let active = true;

    const timer = window.setTimeout(
      async () => {
        const requestId =
          ++mapRequestId.current;

        setIsSearchingLocations(true);
        setLocationSearchError("");

        try {
          const apiKey =
            import.meta.env.VITE_OLA_MAPS_API_KEY;

          if (!apiKey) {
            if (
              active &&
              requestId === mapRequestId.current
            ) {
              setLocationResults([]);
              setLocationSearchError(
                "Map search is not configured."
              );
            }
            return;
          }

          const params = new URLSearchParams({
            input: query,
            api_key: apiKey,
          });

          const response = await fetch(
            `https://api.olamaps.io/places/v1/autocomplete?${params.toString()}`
          );

          if (!response.ok) {
            throw new Error(
              `Autocomplete request failed with status ${response.status}`
            );
          }

          const data = await response.json();

          if (
            active &&
            requestId === mapRequestId.current
          ) {
            const results =
              data?.predictions ||
              data?.results ||
              [];

            setLocationResults(
              Array.isArray(results)
                ? results
                : []
            );
          }
        } catch {
          if (
            active &&
            requestId === mapRequestId.current
          ) {
            setLocationResults([]);
            setLocationSearchError(
              "Unable to search locations."
            );
          }
        } finally {
          if (
            active &&
            requestId === mapRequestId.current
          ) {
            setIsSearchingLocations(false);
          }
        }
      },
      350
    );

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [locationSearch]);

  const reverseGeocodeAddress = async (
    latitude: number,
    longitude: number
  ): Promise<string> => {
    // First use the application's Ola Maps reverse-geocoding endpoint.
    try {
      const response = await api.get(
        "/organizations/location-reverse",
        {
          params: {
            latitude,
            longitude,
          },
        }
      );

      const data = response?.data;

      if (typeof data?.address === "string" && data.address.trim()) {
        return data.address.trim();
      }

      if (
        typeof data?.display_name === "string" &&
        data.display_name.trim()
      ) {
        return data.display_name.trim();
      }

      if (typeof data?.name === "string" && data.name.trim()) {
        return data.name.trim();
      }

      // Some reverse-geocoders return address as an object.
      if (data?.address && typeof data.address === "object") {
        const addressParts = [
          data.address.road,
          data.address.neighbourhood,
          data.address.suburb,
          data.address.city ||
            data.address.town ||
            data.address.village,
          data.address.district,
          data.address.state,
          data.address.postcode,
          data.address.country,
        ].filter(
          (value): value is string =>
            typeof value === "string" && value.trim().length > 0
        );

        if (addressParts.length > 0) {
          return addressParts.join(", ");
        }
      }
    } catch {
      // Continue with the public reverse-geocoder.
    }

    // Fallback: resolve the exact clicked coordinates to the nearest
    // mapped road/address using OpenStreetMap.
    try {
      const params = new URLSearchParams({
        format: "jsonv2",
        lat: String(latitude),
        lon: String(longitude),
        zoom: "18",
        addressdetails: "1",
        "accept-language": "en",
      });

      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?${params.toString()}`,
        {
          headers: {
            Accept: "application/json",
          },
        }
      );

      if (response.ok) {
        const data = await response.json();

        if (
          typeof data?.display_name === "string" &&
          data.display_name.trim()
        ) {
          return data.display_name.trim();
        }

        const addressParts = [
          data?.address?.house_number &&
            data?.address?.road
            ? `${data.address.house_number} ${data.address.road}`
            : data?.address?.road,
          data?.address?.neighbourhood,
          data?.address?.suburb,
          data?.address?.city ||
            data?.address?.town ||
            data?.address?.village,
          data?.address?.district,
          data?.address?.state,
          data?.address?.postcode,
          data?.address?.country,
        ].filter(
          (value): value is string =>
            typeof value === "string" && value.trim().length > 0
        );

        if (addressParts.length > 0) {
          return addressParts.join(", ");
        }
      }
    } catch {
      // Both providers failed.
    }

    return "";
  };

  useEffect(() => {
    if (
      !mapVisible ||
      !mapContainerRef.current ||
      mapTarget === null
    ) {
      return;
    }

    let disposed = false;

    const initialiseMap = async () => {
      try {
        const apiKey =
          import.meta.env.VITE_OLA_MAPS_API_KEY;

        if (!apiKey) {
          setMapError(true);
          return;
        }

        const olaMaps = new OlaMaps({
          apiKey,
        });

        if (disposed) {
          return;
        }

        const instance = await olaMaps.init({
          style: OLA_STYLE,
          container: mapContainerRef.current,
          center: [
            mapTarget.longitude,
            mapTarget.latitude,
          ],
          zoom: 16,
        });

        if (disposed) {
          instance?.remove?.();
          return;
        }

        olaMapRef.current =
          instance;

        const addCustomerLocationPoint =
          () => {
            try {
              if (
                !instance.getSource(
                  "customer-location"
                )
              ) {
                instance.addSource(
                  "customer-location",
                  {
                    type: "geojson",
                    data: {
                      type: "Feature",
                      properties: {},
                      geometry: {
                        type: "Point",
                        coordinates: [
                          mapTarget.longitude,
                          mapTarget.latitude,
                        ],
                      },
                    },
                  }
                );
              }

              if (
                !instance.getLayer(
                  "customer-location-point"
                )
              ) {
                instance.addLayer({
                  id:
                    "customer-location-point",
                  type: "circle",
                  source:
                    "customer-location",
                  paint: {
                    "circle-radius": 9,
                    "circle-color":
                      "#DC2626",
                    "circle-stroke-width":
                      3,
                    "circle-stroke-color":
                      "#FFFFFF",
                  },
                });
              }

              setMapError(false);
            } catch {
              setMapError(false);
            }
          };

        if (
          instance.isStyleLoaded?.()
        ) {
          addCustomerLocationPoint();
        } else {
          instance.once(
            "load",
            addCustomerLocationPoint
          );
        }

        instance.on(
          "click",
          async (event: any) => {
            const longitude =
              event?.lngLat?.lng;

            const latitude =
              event?.lngLat?.lat;

            if (
              typeof longitude !== "number" ||
              typeof latitude !== "number"
            ) {
              return;
            }

            setSiteLatitude(latitude);
            setSiteLongitude(longitude);

            setMapTarget({
              latitude,
              longitude,
            });

            // A map click is a manual location selection.
            // Resolve the exact clicked point to a human-readable address.
            setLocationConfirmed(false);
            setLocationSearchError(
              "Finding the address at the selected point..."
            );

            const requestId =
              ++reverseGeocodeSequence.current;

            setIsResolvingMapCenter(true);

            try {
              const name = await reverseGeocodeAddress(
                latitude,
                longitude
              );

              if (
                requestId !==
                reverseGeocodeSequence.current
              ) {
                return;
              }

              if (!name) {
                setLocationConfirmed(false);
                setLocationSearchError(
                  "No address is mapped at this point. Please select a nearby road or address on the map."
                );
                return;
              }

              setSelectedLocationName(name);
              selectedLocationSearch.current = name;

              setLocationSearch(name);

              setForm((current) => ({
                ...current,
                location: name,
              }));

              setLocationConfirmed(true);
              setLocationSearchError("");
            } catch {
              if (
                requestId ===
                reverseGeocodeSequence.current
              ) {
                setLocationConfirmed(false);
                setLocationSearchError(
                  "Unable to find the address at the selected point. Please try another point."
                );
              }
            } finally {
              if (
                requestId ===
                reverseGeocodeSequence.current
              ) {
                setIsResolvingMapCenter(false);
              }
            }
          }
        );

        setMapError(false);
      } catch {
        if (!disposed) {
          setMapError(true);
        }
      }
    };

    void initialiseMap();

    return () => {
      disposed = true;

      try {
        olaMapRef.current?.remove?.();
      } catch {
        // Ignore map cleanup errors.
      }

      olaMapRef.current = null;
    };
  }, [mapVisible, mapTarget]);

  const MAX_LOCATION_ACCURACY_METERS = 250;
  const LOCATION_WAIT_TIMEOUT_MS = 30000;

  const getCurrentLocation = () => {
    if (!navigator.geolocation) {
      setIsGettingLocation(false);
      setLocationConfirmed(false);
      setLocationSearchError(
        "Your browser does not support location services."
      );
      return;
    }

    setIsGettingLocation(true);
    setMapError(false);
    setLocationConfirmed(false);
    setLocationSearchError(
      `Waiting for an accurate location (within ${MAX_LOCATION_ACCURACY_METERS} m)...`
    );
    setLocationResults([]);

    let watchId: number | null = null;
    let timeoutId: number | null = null;
    let finished = false;
    let bestPosition: GeolocationPosition | null = null;

    const cleanup = () => {
      if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
        watchId = null;
      }

      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
    };

    const failForAccuracy = () => {
      if (finished) {
        return;
      }

      finished = true;
      cleanup();

      setIsGettingLocation(false);
      setIsResolvingMapCenter(false);
      setLocationConfirmed(false);

      const bestAccuracy =
        bestPosition?.coords.accuracy;

      if (typeof bestAccuracy === "number") {
        setLocationSearchError(
          `Could not get an accurate location within ${MAX_LOCATION_ACCURACY_METERS} m. Best available accuracy was ±${Math.round(bestAccuracy)} m. Please enable precise location/GPS and try again.`
        );
      } else {
        setLocationSearchError(
          `Could not get an accurate location within ${MAX_LOCATION_ACCURACY_METERS} m. Please enable precise location/GPS and try again.`
        );
      }
    };

    const finishWithPosition = async (
      position: GeolocationPosition
    ) => {
      if (finished) {
        return;
      }

      const accuracy = position.coords.accuracy;

      if (
        !Number.isFinite(accuracy) ||
        accuracy > MAX_LOCATION_ACCURACY_METERS
      ) {
        return;
      }

      finished = true;
      cleanup();

      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;

      setSiteLatitude(latitude);
      setSiteLongitude(longitude);
      setMapTarget({ latitude, longitude });
      setMapVisible(true);
      setIsGettingLocation(false);
      setIsResolvingMapCenter(true);
      setLocationSearchError("");

      const requestId =
        ++reverseGeocodeSequence.current;

      try {
        const name = await reverseGeocodeAddress(
          latitude,
          longitude
        );

        if (
          requestId !==
          reverseGeocodeSequence.current
        ) {
          return;
        }

        if (!name) {
          setLocationConfirmed(false);
          setLocationSearchError(
            `Your location is accurate to ±${Math.round(accuracy)} m, but no nearby address could be determined. Please try again.`
          );
          return;
        }

        setSelectedLocationName(name);
        selectedLocationSearch.current = name;
        setLocationSearch(name);

        setForm((current) => ({
          ...current,
          location: name,
        }));

        setLocationConfirmed(true);
        setLocationSearchError(
          `Location found within ±${Math.round(accuracy)} m.`
        );
      } catch {
        if (
          requestId ===
          reverseGeocodeSequence.current
        ) {
          setLocationConfirmed(false);
          setLocationSearchError(
            `Your location is accurate to ±${Math.round(accuracy)} m, but the nearby address could not be determined. Please try again.`
          );
        }
      } finally {
        if (
          requestId ===
          reverseGeocodeSequence.current
        ) {
          setIsResolvingMapCenter(false);
        }
      }
    };

    const handlePosition = (
      position: GeolocationPosition
    ) => {
      if (finished) {
        return;
      }

      const accuracy = position.coords.accuracy;

      if (
        !bestPosition ||
        accuracy < bestPosition.coords.accuracy
      ) {
        bestPosition = position;
      }

      console.log(
        "[CustomerLocation] Location reading:",
        {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracyMeters: accuracy,
        }
      );

      if (
        Number.isFinite(accuracy) &&
        accuracy <= MAX_LOCATION_ACCURACY_METERS
      ) {
        setLocationSearchError(
          `Accurate location found: ±${Math.round(accuracy)} m. Confirming address...`
        );
        void finishWithPosition(position);
        return;
      }

      setLocationSearchError(
        `Waiting for better accuracy... Current accuracy ±${Math.round(accuracy)} m (need ≤${MAX_LOCATION_ACCURACY_METERS} m).`
      );
    };

    const handleError = (
      error: GeolocationPositionError
    ) => {
      if (finished) {
        return;
      }

      console.warn(
        "[CustomerLocation] Geolocation error:",
        error.code,
        error.message
      );

      if (
        bestPosition &&
        bestPosition.coords.accuracy <=
          MAX_LOCATION_ACCURACY_METERS
      ) {
        void finishWithPosition(bestPosition);
        return;
      }

      if (error.code === error.PERMISSION_DENIED) {
        finished = true;
        cleanup();
        setIsGettingLocation(false);
        setLocationConfirmed(false);
        setLocationSearchError(
          "Location permission was denied. Please allow location access and try again."
        );
      }
    };

    watchId = navigator.geolocation.watchPosition(
      handlePosition,
      handleError,
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 10000,
      }
    );

    timeoutId = window.setTimeout(
      failForAccuracy,
      LOCATION_WAIT_TIMEOUT_MS
    );
  };

  const selectLocation =
    async (result: any) => {
      let latitude =
        Number(
          result?.latitude ??
          result?.geometry?.location?.lat ??
          result?.geometry?.coordinates?.[1]
        );

      let longitude =
        Number(
          result?.longitude ??
          result?.geometry?.location?.lng ??
          result?.geometry?.coordinates?.[0]
        );

      let name =
        result?.description ||
        result?.display_name ||
        result?.name ||
        result?.place_name ||
        result?.formatted_address ||
        locationSearch;

      const placeId =
        result?.place_id;

      const apiKey =
        import.meta.env.VITE_OLA_MAPS_API_KEY;

      if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude)
      ) {
        if (
          !placeId ||
          !apiKey
        ) {
          setLocationSearchError(
            "Unable to determine the selected location."
          );
          return;
        }

        try {
          const params =
            new URLSearchParams({
              place_id: placeId,
              api_key: apiKey,
            });

          const response =
            await fetch(
              `https://api.olamaps.io/places/v1/details?${params.toString()}`
            );

          if (!response.ok) {
            throw new Error(
              `Place details request failed with status ${response.status}`
            );
          }

          const data =
            await response.json();

          const place =
            data?.result ||
            data;

          latitude =
            Number(
              place?.geometry?.location?.lat ??
              place?.geometry?.coordinates?.[1]
            );

          longitude =
            Number(
              place?.geometry?.location?.lng ??
              place?.geometry?.coordinates?.[0]
            );

          name =
            place?.name ||
            place?.display_name ||
            place?.formatted_address ||
            name;
        } catch {
          setLocationSearchError(
            "Unable to load the selected location."
          );
          return;
        }
      }

      if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude)
      ) {
        setLocationSearchError(
          "Unable to determine the selected location."
        );
        return;
      }

      selectedLocationSearch.current =
        name;

      setSiteLatitude(latitude);
      setSiteLongitude(longitude);

      setSelectedLocationName(name);
      setLocationConfirmed(true);

      setForm((current) => ({
        ...current,
        location: name,
      }));

      setMapTarget({
        latitude,
        longitude,
      });

      setLocationSearch(name);
      setLocationResults([]);
      setLocationSearchError("");
      setMapError(false);
      setMapVisible(true);
    };

  const load = () => {
    setLoading(true);
    setLoadError("");

    getServiceRequests()
      .then((r) => {
        setRequests(
          Array.isArray(r.data)
            ? r.data
            : []
        );

        setLoadError("");
      })
      .catch((e: any) => {
        const status =
          e?.response?.status;

        if (status === 401) {
          setLoadError(
            "Your session has expired. Please sign in again."
          );
        } else if (status === 403) {
          setLoadError(
            "You do not have permission to view your service requests."
          );
        } else {
          setLoadError(
            "We couldn't load your service requests. Please try again."
          );
        }

        /*
         * Do not leave stale customer data visible
         * after a failed reload.
         *
         * The backend remains authoritative for
         * customer/tenant/object access.
         */
        setRequests([]);
      })
      .finally(() =>
        setLoading(false)
      );
  };

  useEffect(() => {
    if (!createOnly) {
      load();
    }
  }, [createOnly]);

  // Auto-refresh requests list in background so status updates appear without manual refresh
  useEffect(() => {
    if (createOnly) return;

    let isMounted = true;
    const interval = setInterval(async () => {
      if (document.hidden) return;
      try {
        const r = await getServiceRequests();
        if (isMounted && Array.isArray(r.data)) {
          setRequests(r.data);
        }
      } catch (err) {
        // Silent background failure
      }
    }, 4000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [createOnly]);

  const reset = () => {
    setForm({
      title: "",
      description: "",
      service_type: "",
      priority: "select priority",
      preferred_visit_date: "",
      location: "",
      contact_number: "",
    });

    setShowCreate(false);
    setEditId(null);

    setSiteLatitude(null);
    setSiteLongitude(null);

    setLocationSearch("");
    setLocationResults([]);
    setLocationSearchError("");

    setSelectedLocationName("");
    setLocationConfirmed(false);

    setMapVisible(false);
    setMapError(false);
    setMapTarget(null);

    setError("");
    setSuccess("");
    setLoadError("");
  };

  const validate =
    () => {
      const title =
        form.title.trim();

      const description =
        form.description.trim();

      const serviceType =
        form.service_type.trim();

      const priority =
        form.priority.trim();

      const location =
        form.location.trim();

      const contactNumber =
        form.contact_number.trim();

      if (!title) {
        setError(
          "Please enter a title."
        );
        return false;
      }

      if (!description) {
        setError(
          "Please enter a description."
        );
        return false;
      }

      if (!serviceType) {
        setError(
          "Please select a service type."
        );
        return false;
      }

      if (
        !priority ||
        priority ===
          "select priority"
      ) {
        setError(
          "Please select a priority."
        );
        return false;
      }

      if (!location) {
        setError(
          "Please enter or select a location."
        );
        return false;
      }

      if (
        !locationConfirmed ||
        siteLatitude === null ||
        siteLongitude === null
      ) {
        setError(
          "Please confirm the service location on the map."
        );
        return false;
      }

      if (!/^\d{10}$/.test(contactNumber)) {
        setError(
          "Contact number must be exactly 10 digits."
        );
        return false;
      }

      setError("");
      return true;
    };

  const handleSubmit =
    async (
      event?: React.FormEvent
    ) => {
      event?.preventDefault();

      if (saving) {
        return;
      }

      if (!validate()) {
        return;
      }

      setSaving(true);
      setError("");
      setSuccess("");

      try {
        const title =
          form.title.trim();

        const description =
          form.description.trim();

        const location =
          form.location.trim();

        const contactNumber =
          form.contact_number.trim();

        const payload = {
          ...form,
          title,
          description,
          location,
          contact_number:
            contactNumber,
          preferred_visit_date:
            form.preferred_visit_date ||
            null,
          site_latitude:
            siteLatitude,
          site_longitude:
            siteLongitude,
        };

        if (editId) {
          await updateServiceRequest(
            editId,
            payload
          );

          setSuccess(
            "Request updated!"
          );

          setShowCreate(false);
          setEditId(null);

          setForm({
            title: "",
            description: "",
            service_type: "",
            priority:
              "select priority",
            preferred_visit_date:
              "",
            location: "",
            contact_number: "",
          });

          load();
        } else {
          await createServiceRequest(
            payload
          );

          if (createOnly) {
            onNavigate?.(
              "cust_requests"
            );
            return;
          }

          setSuccess(
            "Request created!"
          );

          reset();
          load();
        }
      } catch (e: any) {
        const status =
          e?.response?.status;

        if (status === 401) {
          setError(
            "Your session has expired. Please sign in again."
          );
        } else if (
          status === 403
        ) {
          setError(
            "You do not have permission to update this service request."
          );
        } else {
          const detail =
            e?.response?.data?.detail;

          if (typeof detail === "string") {
            setError(detail);
          } else if (detail?.message) {
            setError(detail.message);
          } else if (Array.isArray(detail) && detail[0]?.msg) {
            setError(detail[0].msg);
          } else {
            setError("Failed to save service request.");
          }
        }
      } finally {
        setSaving(false);
      }
    };

  const handleCancel =
    async (
      id: number
    ) => {
      if (
        !confirm(
          "Cancel this service request?"
        )
      ) {
        return;
      }

      try {
        await cancelServiceRequest(
          id
        );

        load();
      } catch (e: any) {
        const status =
          e?.response?.status;

        if (status === 401) {
          alert(
            "Your session has expired. Please sign in again."
          );
        } else if (
          status === 403
        ) {
          alert(
            "You do not have permission to cancel this service request."
          );
        } else {
          const detail =
            e?.response?.data?.detail;

          alert(
            typeof detail ===
              "string"
              ? detail
              : "Failed to cancel service request."
          );
        }
      }
    };

  const startEdit =
    (sr: any) => {
      setForm({
        title:
          sr.title || "",
        description:
          sr.description || "",
        service_type:
          sr.service_type || "",
        priority:
          sr.priority ||
          "select priority",
        preferred_visit_date:
          sr.preferred_visit_date
            ? String(
                sr.preferred_visit_date
              ).slice(0, 10)
            : "",
        location:
          sr.location || "",
        contact_number:
          sr.contact_number ||
          "",
      });

      setSiteLatitude(
        sr.site_latitude ??
          null
      );

      setSiteLongitude(
        sr.site_longitude ??
          null
      );

      setSelectedLocationName(
        sr.location || ""
      );

      setEditId(sr.id);

      setLocationConfirmed(
        Boolean(
          sr.site_latitude !=
            null &&
          sr.site_longitude !=
            null
        )
      );

      setShowCreate(true);
      setError("");
      setSuccess("");
    };

  const upd = (
    k: string,
    v: string
  ) => {
    setForm((f) => ({
      ...f,
      [k]: v,
    }));
  };

  const inputStyle = {
    width: "100%",
    padding: "10px 12px",
    border:
      "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    boxSizing:
      "border-box" as const,
    outline: "none",
    fontFamily:
      "'Inter', sans-serif",
  };

  const labelStyle = {
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "4px",
    display:
      "block" as const,
  };

  const requiredStar = {
    color: "#DC2626",
  };

  if (createOnly) {
    return <CustomerNewRequestMarketplace onNavigate={onNavigate} />;
  }

  return (
    <div
      style={{
        padding: "24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily:
          "'Inter', sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent:
            "space-between",
          alignItems: "center",
          marginBottom:
            "20px",
        }}
      >
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#1F2933",
            display: "flex",
            alignItems:
              "center",
            gap: "8px",
          }}
        >
          <FileText
            size={22}
            color="#7AAE8A"
          />
          My Requests
        </h2>

        <button
          onClick={() => {
            onNavigate?.(
              "cust_create_request"
            );
          }}
          style={{
            padding:
              "10px 20px",
            border: "none",
            borderRadius:
              "10px",
            background:
              "linear-gradient(180deg, #069660 0%, #058353 100%)",
            boxShadow:
              "0 2px 6px rgba(5, 131, 83, 0.28)",
            color: "#fff",
            fontSize:
              "13px",
            fontWeight: 700,
            cursor:
              "pointer",
            display:
              "flex",
            alignItems:
              "center",
            gap:
              "6px",
          }}
        >
          <PlusCircle
            size={16}
          />
          New Request
        </button>
      </div>

      {/* 6 Stats Cards */}
      <style>{`
        .kpi-cards-grid {
          display: grid;
          grid-template-columns: repeat(6, minmax(0, 1fr));
          gap: 12px;
          margin-bottom: 24px;
        }
        @media (max-width: 1024px) {
          .kpi-cards-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
        @media (max-width: 640px) {
          .kpi-cards-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
      `}</style>
      <div className="kpi-cards-grid">
        {statsCards.map((c) => {
          const isSelected = activeCardFilter === c.key;
          return (
            <div
              key={c.key}
              onClick={() => {
                setActiveCardFilter((prev) => (prev === c.key ? "ALL" : c.key));
              }}
              title={`Click to filter by ${c.label}`}
              style={{
                position: "relative",
                background: "#ffffff",
                borderRadius: "22px",
                padding: "16px 16px 14px 16px",
                overflow: "hidden",
                boxShadow: isSelected
                  ? `0 8px 24px ${c.color}25`
                  : "0 1px 3px rgba(0,0,0,0.03)",
                border: isSelected
                  ? `2px solid ${c.color}`
                  : "1px solid #E5E7EB",
                cursor: "pointer",
                transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                userSelect: "none",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                minHeight: "135px",
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = c.color;
                  e.currentTarget.style.transform = "translateY(-3px)";
                  e.currentTarget.style.boxShadow = `0 8px 20px ${c.color}18`;
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = "#E5E7EB";
                  e.currentTarget.style.transform = "translateY(0)";
                  e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.03)";
                }
              }}
            >
              {/* Bottom-Right Organic Layered Waves */}
              <svg
                style={{
                  position: "absolute",
                  right: 0,
                  bottom: 0,
                  width: "145px",
                  height: "110px",
                  pointerEvents: "none",
                  zIndex: 0,
                }}
                viewBox="0 0 145 110"
                fill="none"
                preserveAspectRatio="none"
              >
                <defs>
                  <linearGradient
                    id={`wave-front-${c.key}`}
                    x1="0%"
                    y1="100%"
                    x2="100%"
                    y2="0%"
                  >
                    <stop offset="0%" stopColor={c.gradStart} stopOpacity="0.5" />
                    <stop offset="100%" stopColor={c.gradEnd} stopOpacity="0.9" />
                  </linearGradient>
                  <linearGradient
                    id={`wave-back-${c.key}`}
                    x1="0%"
                    y1="100%"
                    x2="100%"
                    y2="0%"
                  >
                    <stop offset="0%" stopColor={c.gradStart} stopOpacity="0.25" />
                    <stop offset="100%" stopColor={c.gradEnd} stopOpacity="0.45" />
                  </linearGradient>
                </defs>

                {/* Back undulating wave */}
                <path
                  d="M10,110 C32,104 42,78 68,82 C94,86 112,56 132,38 C138,32 142,28 145,24 L145,110 Z"
                  fill={`url(#wave-back-${c.key})`}
                />

                {/* Front undulating wave with crests and ripples */}
                <path
                  d="M25,110 C46,108 58,90 82,93 C106,96 120,68 136,52 C140,46 143,42 145,38 L145,110 Z"
                  fill={`url(#wave-front-${c.key})`}
                />
              </svg>

              {/* Top-Left Squircle Icon Container */}
              <div style={{ position: "relative", zIndex: 2 }}>
                <div
                  style={{
                    width: "40px",
                    height: "40px",
                    borderRadius: "14px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: c.iconBg,
                    color: c.color,
                  }}
                >
                  {c.icon}
                </div>
              </div>

              {/* Middle & Bottom: Label + Count */}
              <div
                style={{
                  position: "relative",
                  zIndex: 2,
                  marginTop: "12px",
                }}
              >
                <div
                  style={{
                    fontSize: "13px",
                    color: "#374151",
                    fontWeight: 500,
                    marginBottom: "4px",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {c.label}
                </div>
                <div
                  style={{
                    fontSize: "30px",
                    fontWeight: 800,
                    color: c.valueColor,
                    lineHeight: 1,
                    letterSpacing: "-0.02em",
                  }}
                >
                  {c.value}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Success */}
      {success && (
        <div
          style={{
            background:
              "#F0FFF4",
            border:
              "1px solid #C6F6D5",
            borderRadius:
              "8px",
            padding:
              "10px 14px",
            color:
              "#22543D",
            fontSize:
              "13px",
            marginBottom:
              "16px",
            display:
              "flex",
            alignItems:
              "center",
            gap:
              "8px",
          }}
        >
          <CheckCircle
            size={16}
          />
          {success}
        </div>
      )}

      {/* Request Cards */}
      {loading ? (
        <div
          style={{
            textAlign:
              "center",
            padding:
              "48px",
            color:
              "#9CA3AF",
          }}
          role="status"
          aria-live="polite"
        >
          Loading...
        </div>
      ) : loadError ? (
        <div
          style={{
            textAlign:
              "center",
            padding:
              "36px",
            background:
              "#fff",
            borderRadius:
              "14px",
            border:
              "1px solid #E3ECE7",
          }}
          role="alert"
        >
          <div
            style={{
              fontSize:
                "14px",
              fontWeight:
                600,
              color:
                "#374151",
              marginBottom:
                "14px",
            }}
          >
            {loadError}
          </div>

          <button
            type="button"
            onClick={load}
            style={{
              border:
                "none",
              borderRadius:
                "8px",
              background:
                "#7AAE8A",
              color:
                "#fff",
              padding:
                "9px 16px",
              fontSize:
                "12px",
              fontWeight:
                700,
              cursor:
                "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      ) : requests.length ===
        0 ? (
        <div
          style={{
            textAlign:
              "center",
            padding:
              "48px",
            color:
              "#9CA3AF",
          }}
        >
          No service requests yet.
          Create your first one!
        </div>
      ) : displayedRequests.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            background: "#fff",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
            color: "#64748B",
          }}
        >
          <div style={{ fontSize: "15px", fontWeight: 600, marginBottom: "8px", color: "#1F2933" }}>
            No {activeCardFilter.toLowerCase().replace("_", " ")} requests found.
          </div>
          <button
            type="button"
            onClick={() => setActiveCardFilter("ALL")}
            style={{
              padding: "8px 16px",
              background: "#7AAE8A",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Show All Requests
          </button>
        </div>
      ) : (
        <div
          style={{
            display:
              "grid",
            gridTemplateColumns:
              "repeat(auto-fill, minmax(300px, 1fr))",
            gap:
              "14px",
          }}
        >
          {displayedRequests.map((sr) => {
            const rawStatus = normalizeStatus(sr.status);
            const displayStatus = getDisplayStatusText(sr.status);
            const canCancel = ["CREATED", "PENDING", "UNASSIGNED", "ASSIGNED"].includes(rawStatus);

            return (
              <div
                key={sr.id}
                style={{
                  background: "#FFFFFF",
                  borderRadius: "16px",
                  padding: "20px",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.04)",
                  border: "1px solid #E2E8F0",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  transition: "transform 0.2s ease, box-shadow 0.2s ease",
                }}
              >
                <div>
                  {/* Card Header: Job ID + Status Badge */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "12px",
                      gap: "8px",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "12px",
                        fontWeight: 700,
                        color: "#64748B",
                        background: "#F1F5F9",
                        padding: "3px 8px",
                        borderRadius: "6px",
                      }}
                    >
                      Job #{sr.linked_job_id || sr.id}
                    </span>

                    <span style={badge(sr.status)}>
                      {displayStatus}
                    </span>
                  </div>

                  {/* Title */}
                  <h3
                    style={{
                      fontSize: "16px",
                      fontWeight: 700,
                      color: "#0F172A",
                      margin: "0 0 10px 0",
                      lineHeight: 1.35,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={sr.title}
                  >
                    {sr.title}
                  </h3>

                  {/* Preferred Date */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      fontSize: "13px",
                      color: "#64748B",
                      marginBottom: "16px",
                    }}
                  >
                    <Clock size={14} color="#94A3B8" />
                    <span>
                      Preferred Date:{" "}
                      <strong style={{ color: "#334155" }}>
                        {sr.preferred_visit_date
                          ? new Date(sr.preferred_visit_date).toLocaleDateString()
                          : "Flexible"}
                      </strong>
                    </span>
                  </div>
                </div>

                {/* Card Actions: Cancel (if before start) + Track Job */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    alignItems: "center",
                    gap: "8px",
                    paddingTop: "14px",
                    borderTop: "1px solid #F1F5F9",
                  }}
                >
                  {sr.linked_job_id && ["ACCEPTED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS"].includes(rawStatus) && (
                    <button
                      type="button"
                      onClick={() => setChatRequest(sr)}
                      style={{
                        border: "1px solid #DDD6FE",
                        background: "#F5F3FF",
                        borderRadius: "8px",
                        padding: "7px 12px",
                        fontSize: "12px",
                        fontWeight: 700,
                        color: "#7C3AED",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                      }}
                    >
                      <MessageSquare size={13} />
                      Chat
                    </button>
                  )}
                  {canCancel && (
                    <button
                      type="button"
                      onClick={() => void handleCancel(sr.id)}
                      style={{
                        border: "1px solid #FECACA",
                        background: "#FEF2F2",
                        borderRadius: "8px",
                        padding: "7px 12px",
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#DC2626",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        transition: "background 0.15s ease",
                      }}
                    >
                      <XCircle size={13} />
                      Cancel
                    </button>
                  )}

                  {rawStatus === "EN_ROUTE" && (
                    <button
                      type="button"
                      onClick={() => void handleOpenDedicatedLiveMap(sr)}
                      style={{
                        border: "none",
                        background: "linear-gradient(135deg, #1D4ED8 0%, #2563EB 100%)",
                        borderRadius: "8px",
                        padding: "7px 14px",
                        fontSize: "12px",
                        fontWeight: 700,
                        color: "#FFFFFF",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        boxShadow: "0 2px 6px rgba(37, 99, 235, 0.3)",
                        transition: "transform 0.15s ease, box-shadow 0.15s ease",
                      }}
                    >
                      <MapPin size={13} />
                      Live Map
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => void handleOpenTracking(sr)}
                    style={{
                      border: "none",
                      background: "linear-gradient(135deg, #058353 0%, #069660 100%)",
                      borderRadius: "8px",
                      padding: "7px 14px",
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#FFFFFF",
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      boxShadow: "0 2px 6px rgba(6, 150, 96, 0.25)",
                      transition: "transform 0.15s ease, box-shadow 0.15s ease",
                    }}
                  >
                    <Navigation size={13} />
                    Track Job
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {chatRequest?.linked_job_id && (
        <JobMessagePanel
          key={Number(chatRequest.linked_job_id)}
          jobId={Number(chatRequest.linked_job_id)}
          initialTechnicianName={chatRequest.assigned_technician_name}
          onClose={() => setChatRequest(null)}
        />
      )}

      {/* Edit/Create Modal */}
      {showCreate && (
        <div
          style={{
            position:
              "fixed",
            inset: 0,
            background:
              "rgba(15,23,42,0.45)",
            display:
              "flex",
            alignItems:
              "center",
            justifyContent:
              "center",
            padding:
              "20px",
            zIndex:
              1000,
          }}
        >
          <div
            style={{
              width:
                "100%",
              maxWidth:
                "760px",
              maxHeight:
                "90vh",
              overflowY:
                "auto",
              background:
                "#FFFFFF",
              borderRadius:
                "16px",
              boxShadow:
                "0 20px 40px rgba(0,0,0,0.18)",
            }}
          >
            <div
              style={{
                display:
                  "flex",
                justifyContent:
                  "space-between",
                alignItems:
                  "center",
                padding:
                  "18px 20px",
                borderBottom:
                  "1px solid #E5E7EB",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize:
                      "17px",
                    fontWeight:
                      700,
                    color:
                      "#1F2933",
                  }}
                >
                  {editId
                    ? "Edit Service Request"
                    : "Create Service Request"}
                </div>

                <div
                  style={{
                    fontSize:
                      "12px",
                    color:
                      "#6B7280",
                    marginTop:
                      "4px",
                  }}
                >
                  Update the
                  request
                  details below.
                </div>
              </div>

              <button
                type="button"
                onClick={
                  reset
                }
                disabled={
                  saving
                }
                style={{
                  border:
                    "none",
                  background:
                    "transparent",
                  padding:
                    "6px",
                  cursor:
                    saving
                      ? "not-allowed"
                      : "pointer",
                  color:
                    "#6B7280",
                }}
                aria-label="Close"
              >
                <X
                  size={
                    20
                  }
                />
              </button>
            </div>

            <form
              onSubmit={(event) =>
                void handleSubmit(
                  event
                )
              }
              style={{
                padding:
                  "20px",
              }}
            >
              {error && (
                <div
                  style={{
                    background:
                      "#FEF2F2",
                    border:
                      "1px solid #FECACA",
                    borderRadius:
                      "8px",
                    padding:
                      "10px",
                    color:
                      "#991B1B",
                    fontSize:
                      "13px",
                    marginBottom:
                      "14px",
                    display:
                      "flex",
                    alignItems:
                      "center",
                    gap:
                      "6px",
                  }}
                >
                  <AlertCircle
                    size={
                      14
                    }
                  />
                  {error}
                </div>
              )}

              <div
                style={{
                  display:
                    "flex",
                  flexDirection:
                    "column",
                  gap:
                    "18px",
                }}
              >
                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Title{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <input
                    style={
                      inputStyle
                    }
                    value={
                      form.title
                    }
                    onChange={(
                      e
                    ) =>
                      upd(
                        "title",
                        e.target
                          .value
                      )
                    }
                    placeholder="Brief title for your request"
                  />
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Description{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <textarea
                    style={{
                      ...inputStyle,
                      minHeight:
                        "120px",
                      resize:
                        "vertical",
                    }}
                    value={
                      form.description
                    }
                    onChange={(
                      e
                    ) =>
                      upd(
                        "description",
                        e.target
                          .value
                      )
                    }
                    placeholder="Describe the issue in detail..."
                  />
                </div>

                <div
                  style={{
                    display:
                      "grid",
                    gridTemplateColumns:
                      "1fr 1fr",
                    gap:
                      "16px",
                  }}
                >
                  <div>
                    <label
                      style={
                        labelStyle
                      }
                    >
                      Service Type{" "}
                      <span
                        style={{
                          color:
                            "red",
                        }}
                      >
                        *
                      </span>
                    </label>

                    <select
                      required
                      style={{
                        ...inputStyle,
                        color:
                          form.service_type
                            ? "#111827"
                            : "#9CA3AF",
                      }}
                      value={
                        form.service_type
                      }
                      onChange={(
                        e
                      ) =>
                        upd(
                          "service_type",
                          e.target
                            .value
                        )
                      }
                    >
                      <option value="">
                        select service
                      </option>

                      <option value="HVAC Repair">
                        HVAC Repair
                      </option>

                      <option value="Electrical">
                        Electrical
                      </option>

                      <option value="Plumbing">
                        Plumbing
                      </option>

                      <option value="General Maintenance">
                        General Maintenance
                      </option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={
                        labelStyle
                      }
                    >
                      Priority{" "}
                      <span
                        style={{
                          color:
                            "red",
                        }}
                      >
                        *
                      </span>
                    </label>

                    <select
                      required
                      style={{
                        ...inputStyle,
                        color:
                          form.priority !==
                          "select priority"
                            ? "#111827"
                            : "#9CA3AF",
                      }}
                      value={
                        form.priority
                      }
                      onChange={(
                        e
                      ) =>
                        upd(
                          "priority",
                          e.target
                            .value
                        )
                      }
                    >
                      <option value="select priority">
                        select priority
                      </option>

                      <option value="LOW">
                        LOW
                      </option>

                      <option value="MEDIUM">
                        MEDIUM
                      </option>

                      <option value="HIGH">
                        HIGH
                      </option>

                      <option value="URGENT">
                        URGENT
                      </option>
                    </select>
                  </div>
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Preferred Visit Date
                  </label>

                  <input
                    type="date"
                    style={
                      inputStyle
                    }
                    value={
                      form.preferred_visit_date
                    }
                    onChange={(
                      e
                    ) =>
                      upd(
                        "preferred_visit_date",
                        e.target
                          .value
                      )
                    }
                  />
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Contact Number{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <input
                    type="tel"
                    style={
                      inputStyle
                    }
                    value={
                      form.contact_number
                    }
                    onChange={(e) =>
                      upd(
                        "contact_number",
                        e.target.value
                          .replace(/\D/g, "")
                          .slice(0, 10)
                      )
                    }
                    maxLength={10}
                    placeholder="Enter contact number"
                  />
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Service Location{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <div
                    style={{
                      display:
                        "flex",
                      gap:
                        "8px",
                      marginBottom:
                        "8px",
                    }}
                  >
                    <input
                      style={{
                        ...inputStyle,
                        flex: 1,
                      }}
                      value={
                        locationSearch
                      }
                      onChange={(
                        e
                      ) => {
                        setLocationSearch(
                          e.target.value
                        );
                        setLocationConfirmed(
                          false
                        );
                        setSelectedLocationName(
                          ""
                        );
                        setSiteLatitude(
                          null
                        );
                        setSiteLongitude(
                          null
                        );
                      }}
                      placeholder="Search service location"
                    />

                    <button
                      type="button"
                      onClick={
                        getCurrentLocation
                      }
                      disabled={
                        isGettingLocation
                      }
                      style={{
                        border:
                          "1px solid #D1D5DB",
                        background:
                          "#FFFFFF",
                        borderRadius:
                          "8px",
                        padding:
                          "0 12px",
                        cursor:
                          isGettingLocation
                            ? "not-allowed"
                            : "pointer",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        gap:
                          "6px",
                        whiteSpace:
                          "nowrap",
                      }}
                    >
                      <MapPin
                        size={
                          15
                        }
                      />

                      {isGettingLocation
                        ? "Waiting for ≤150 m..."
                        : "Use my location"}
                    </button>
                  </div>

                  {locationSearchError && (
                    <div
                      style={{
                        color:
                          "#991B1B",
                        fontSize:
                          "12px",
                        marginBottom:
                          "8px",
                      }}
                    >
                      {
                        locationSearchError
                      }
                    </div>
                  )}

                  {isSearchingLocations && (
                    <div
                      style={{
                        color:
                          "#6B7280",
                        fontSize:
                          "12px",
                        marginBottom:
                          "8px",
                      }}
                    >
                      Searching...
                    </div>
                  )}

                  {locationResults.length >
                    0 && (
                    <div
                      style={{
                        border:
                          "1px solid #E5E7EB",
                        borderRadius:
                          "8px",
                        background:
                          "#FFFFFF",
                        overflow:
                          "hidden",
                        marginBottom:
                          "8px",
                      }}
                    >
                      {locationResults.map(
                        (
                          result,
                          index
                        ) => (
                          <button
                            type="button"
                            key={
                              result.id ||
                              result.place_id ||
                              index
                            }
                            onClick={() =>
                              void selectLocation(
                                result
                              )
                            }
                            style={{
                              display:
                                "block",
                              width:
                                "100%",
                              border:
                                "none",
                              borderBottom:
                                index ===
                                locationResults.length -
                                  1
                                  ? "none"
                                  : "1px solid #F3F4F6",
                              background:
                                "#FFFFFF",
                              textAlign:
                                "left",
                              padding:
                                "10px 12px",
                              cursor:
                                "pointer",
                              fontSize:
                                "13px",
                              color:
                                "#374151",
                            }}
                          >
                            {result.display_name ||
                              result.name ||
                              "Location"}
                          </button>
                        )
                      )}
                    </div>
                  )}

                  <div
                    style={{
                      display:
                        "flex",
                      justifyContent:
                        "space-between",
                      alignItems:
                        "center",
                      marginBottom:
                        "8px",
                      gap:
                        "10px",
                    }}
                  >
                    <span
                      style={{
                        fontSize:
                          "12px",
                        color:
                          locationConfirmed
                            ? "#166534"
                            : "#6B7280",
                        fontWeight:
                          locationConfirmed
                            ? 600
                            : 400,
                      }}
                    >
                      {locationConfirmed
                        ? `Location confirmed${
                            form.location.trim()
                              ? `: ${form.location.trim()}`
                              : selectedLocationName
                              ? `: ${selectedLocationName}`
                              : ""
                          }`
                        : "Select a location and confirm it on the map."}
                    </span>

                    <button
                      type="button"
                      onClick={() =>
                        setMapVisible(
                          (value) =>
                            !value
                        )
                      }
                      style={{
                        border:
                          "1px solid #D1D5DB",
                        background:
                          "#FFFFFF",
                        borderRadius:
                          "8px",
                        padding:
                          "6px 10px",
                        fontSize:
                          "12px",
                        fontWeight:
                          600,
                        cursor:
                          "pointer",
                      }}
                    >
                      {mapVisible
                        ? "Hide Map"
                        : "Show Map"}
                    </button>
                  </div>

                  {mapVisible && (
                    <div>
                      {mapError && (
                        <div
                          style={{
                            background:
                              "#FEF2F2",
                            border:
                              "1px solid #FECACA",
                            color:
                              "#991B1B",
                            borderRadius:
                              "8px",
                            padding:
                              "8px 10px",
                            fontSize:
                              "12px",
                            marginBottom:
                              "8px",
                          }}
                        >
                          Map could not be loaded.
                          You can still enter the
                          location manually and
                          continue if coordinates
                          are already available.
                        </div>
                      )}

                      <div
                        ref={
                          mapContainerRef
                        }
                        style={{
                          height:
                            "280px",
                          border:
                            "1px solid #D1D5DB",
                          borderRadius:
                            "10px",
                          overflow:
                            "hidden",
                          background:
                            "#F3F4F6",
                        }}
                      />

                      {isResolvingMapCenter && (
                        <div
                          style={{
                            fontSize:
                              "12px",
                            color:
                              "#6B7280",
                            marginTop:
                              "6px",
                          }}
                        >
                          Resolving
                          selected
                          location...
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div
                  style={{
                    display:
                      "flex",
                    justifyContent:
                      "flex-end",
                    gap:
                      "10px",
                    marginTop:
                      "4px",
                  }}
                >
                  <button
                    type="button"
                    onClick={
                      reset
                    }
                    disabled={
                      saving
                    }
                    style={{
                      padding:
                        "10px 20px",
                      border:
                        "1px solid #D1D5DB",
                      borderRadius:
                        "8px",
                      background:
                        "#FFFFFF",
                      color:
                        "#374151",
                      fontSize:
                        "13px",
                      fontWeight:
                        700,
                      cursor:
                        saving
                          ? "not-allowed"
                          : "pointer",
                    }}
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={
                      saving
                    }
                    style={{
                      padding:
                        "10px 24px",
                      border:
                        "none",
                      borderRadius:
                        "8px",
                      background:
                        "#7AAE8A",
                      color:
                        "#fff",
                      fontSize:
                        "13px",
                      fontWeight:
                        700,
                      cursor:
                        saving
                          ? "not-allowed"
                          : "pointer",
                      display:
                        "flex",
                      alignItems:
                        "center",
                      gap:
                        "6px",
                      opacity:
                        saving
                          ? 0.7
                          : 1,
                    }}
                  >
                    <Send
                      size={
                        14
                      }
                    />

                    {saving
                      ? "Submitting..."
                      : editId
                      ? "Update"
                      : "Submit"}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Track Job Modal & Drawer */}
      {/* Dedicated Standalone Live Map Modal */}
      {liveMapModalRequest && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.65)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
            zIndex: 1200,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setLiveMapModalRequest(null);
            }
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "880px",
              height: "85vh",
              maxHeight: "650px",
              background: "#FFFFFF",
              borderRadius: "20px",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.35)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            {/* Header: Title, Live Status Badge, and Close Button */}
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid #E2E8F0",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "#F8FAFC",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "10px",
                    background: "#DBEAFE",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#1D4ED8",
                  }}
                >
                  <MapPin size={20} />
                </div>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "#0F172A" }}>
                      Live Technician Tracking
                    </h3>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: "2px 8px",
                        borderRadius: "12px",
                        fontSize: "11px",
                        fontWeight: 700,
                        background: "#DCFCE7",
                        color: "#059669",
                      }}
                    >
                      <span
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "50%",
                          background: "#10B981",
                          boxShadow: "0 0 0 2px rgba(16,185,129,0.3)",
                        }}
                      />
                      LIVE GPS
                    </span>
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748B", marginTop: "2px" }}>
                    Job #{liveMapModalRequest.linked_job_id || liveMapModalRequest.id} • {liveMapJobDetails?.assigned_technician_name ? `Technician: ${liveMapJobDetails.assigned_technician_name}` : "En route to your location"}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setLiveMapModalRequest(null)}
                style={{
                  border: "none",
                  background: "#F1F5F9",
                  borderRadius: "50%",
                  width: "34px",
                  height: "34px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  color: "#64748B",
                  transition: "background 0.15s ease",
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Map Body: Always display map instantly */}
            <div style={{ flex: 1, position: "relative", minHeight: "450px", width: "100%", height: "100%" }}>
              <div style={{ position: "relative", width: "100%", height: "100%" }}>
                  <JobLiveTrackingMap
                    jobId={liveMapJobDetails?.id || liveMapModalRequest.linked_job_id || liveMapModalRequest.id}
                    customerLatitude={liveMapJobDetails?.site_latitude ?? liveMapModalRequest.site_latitude ?? 13.0495}
                    customerLongitude={liveMapJobDetails?.site_longitude ?? liveMapModalRequest.site_longitude ?? 80.2282}
                    technicianLatitude={liveMapJobDetails?.technician_latitude ?? null}
                    technicianLongitude={liveMapJobDetails?.technician_longitude ?? null}
                    technicianId={liveMapJobDetails?.assigned_technician_id ?? null}
                    mode="customer"
                    tenantId={liveMapJobDetails?.tenant_id || localStorage.getItem("tenant_id") || "default"}
                    trackingTenantId={liveMapJobDetails?.tracking_tenant_id}
                    buildingAddress={liveMapModalRequest.location || liveMapJobDetails?.location}
                  />

                  {["ON_SITE", "IN_PROGRESS", "COMPLETED"].includes(
                    normalizeStatus(liveMapJobDetails?.status || liveMapModalRequest.status)
                  ) && (
                    <div
                      style={{
                        position: "absolute",
                        top: 16,
                        right: 16,
                        zIndex: 20,
                        background: "rgba(255, 255, 255, 0.95)",
                        backdropFilter: "blur(6px)",
                        border: "1px solid #E2E8F0",
                        borderRadius: "10px",
                        padding: "8px 14px",
                        boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                      }}
                    >
                      <CheckCircle2 size={16} color="#7C3AED" />
                      <span style={{ fontSize: "12px", fontWeight: 600, color: "#1E293B" }}>
                        Technician on site / Job active
                      </span>
                    </div>
                  )}
              </div>
            </div>
          </div>
        </div>
      )}

      {trackingModalRequest && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.55)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
            zIndex: 1100,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setTrackingModalRequest(null);
            }
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "800px",
              maxHeight: "90vh",
              overflowY: "auto",
              background: "#FFFFFF",
              borderRadius: "20px",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: "20px 24px",
                borderBottom: "1px solid #E2E8F0",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                background: "#F8FAFC",
                borderTopLeftRadius: "20px",
                borderTopRightRadius: "20px",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#64748B",
                      background: "#E2E8F0",
                      padding: "3px 9px",
                      borderRadius: "6px",
                    }}
                  >
                    Job #{trackingModalRequest.linked_job_id || trackingModalRequest.id}
                  </span>
                  <span style={{ fontSize: "12px", color: "#94A3B8" }}>
                    • {trackingModalRequest.request_number}
                  </span>
                </div>
                <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 800, color: "#0F172A" }}>
                  {trackingModalRequest.title}
                </h2>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={badge(trackingJobDetails?.status || trackingModalRequest.status)}>
                  {getDisplayStatusText(trackingJobDetails?.status || trackingModalRequest.status)}
                </span>
                <button
                  type="button"
                  onClick={() => setTrackingModalRequest(null)}
                  style={{
                    border: "none",
                    background: "#F1F5F9",
                    borderRadius: "50%",
                    width: "32px",
                    height: "32px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "pointer",
                    color: "#64748B",
                  }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* 6-Step Animated Progress Bar */}
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid #E2E8F0",
                background: "#FFFFFF",
              }}
            >
              <AnimatedJobProgress
                jobId={trackingModalRequest.linked_job_id || trackingModalRequest.id}
                status={trackingJobDetails?.status || trackingModalRequest.status}
                workStartedAt={trackingJobDetails?.work_started_at}
                arrivedAt={trackingJobDetails?.on_site_at}
                completedAt={trackingJobDetails?.completed_at}
              />
            </div>

            {/* Modal Content Body */}
            <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
              {trackingLoading ? (
                <div style={{ padding: "40px", textAlign: "center", color: "#64748B" }}>
                  <Clock size={24} style={{ animation: "spin 1s linear infinite", margin: "0 auto 10px" }} />
                  <div>Loading job and technician status...</div>
                </div>
              ) : (
                <>
                  {/* Job Details Card */}
                  <div
                    style={{
                      background: "#F8FAFC",
                      border: "1px solid #E2E8F0",
                      borderRadius: "14px",
                      padding: "18px",
                    }}
                  >
                    <h4 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 700, color: "#334155" }}>
                      Service Request Details
                    </h4>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                        gap: "12px",
                        fontSize: "13px",
                      }}
                    >
                      <div>
                        <span style={{ color: "#64748B", display: "block", fontSize: "11px", fontWeight: 600 }}>SERVICE TYPE</span>
                        <strong style={{ color: "#0F172A" }}>{trackingModalRequest.service_type || "General Service"}</strong>
                      </div>
                      <div>
                        <span style={{ color: "#64748B", display: "block", fontSize: "11px", fontWeight: 600 }}>PREFERRED DATE</span>
                        <strong style={{ color: "#0F172A" }}>
                          {trackingModalRequest.preferred_visit_date
                            ? new Date(trackingModalRequest.preferred_visit_date).toLocaleDateString()
                            : "Flexible"}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "#64748B", display: "block", fontSize: "11px", fontWeight: 600 }}>CONTACT NUMBER</span>
                        <strong style={{ color: "#0F172A" }}>{trackingModalRequest.contact_number || "N/A"}</strong>
                      </div>
                      <div>
                        <span style={{ color: "#64748B", display: "block", fontSize: "11px", fontWeight: 600 }}>LOCATION</span>
                        <div style={{ display: "flex", alignItems: "center", gap: "4px", color: "#0F172A", fontWeight: 600 }}>
                          <MapPin size={13} color="#069660" />
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {trackingModalRequest.location || "Service address"}
                          </span>
                        </div>
                      </div>
                    </div>

                    {trackingModalRequest.description && (
                      <div style={{ marginTop: "14px", paddingTop: "12px", borderTop: "1px solid #E2E8F0" }}>
                        <span style={{ color: "#64748B", display: "block", fontSize: "11px", fontWeight: 600, marginBottom: "4px" }}>
                          PROBLEM DESCRIPTION
                        </span>
                        <div style={{ fontSize: "13px", color: "#334155", lineHeight: 1.5 }}>
                          {trackingModalRequest.description}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Technician Card (Privacy Protected - Only after accepted) */}
                  {trackingJobDetails?.assigned_technician_name ? (
                    <div
                      style={{
                        background: "#FFFFFF",
                        border: "1px solid #CFE0D6",
                        borderRadius: "14px",
                        padding: "18px",
                        boxShadow: "0 2px 6px rgba(0,0,0,0.03)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                        <h4 style={{ margin: 0, fontSize: "14px", fontWeight: 700, color: "#065F46", display: "flex", alignItems: "center", gap: "6px" }}>
                          <ShieldCheck size={16} color="#069660" />
                          Assigned Field Technician
                        </h4>
                        <span style={{ fontSize: "11px", fontWeight: 700, color: "#059669", background: "#DCFCE7", padding: "2px 8px", borderRadius: "12px" }}>
                          ACCEPTED & ASSIGNED
                        </span>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "16px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                          {trackingJobDetails.assigned_technician_photo ? (
                            <img
                              src={trackingJobDetails.assigned_technician_photo}
                              alt={trackingJobDetails.assigned_technician_name}
                              style={{ width: "48px", height: "48px", borderRadius: "50%", objectFit: "cover", border: "2px solid #069660" }}
                            />
                          ) : (
                            <div
                              style={{
                                width: "48px",
                                height: "48px",
                                borderRadius: "50%",
                                background: "#DCFCE7",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                color: "#065F46",
                              }}
                            >
                              <User size={24} />
                            </div>
                          )}

                          <div>
                            <div style={{ fontSize: "15px", fontWeight: 700, color: "#0F172A" }}>
                              {trackingJobDetails.assigned_technician_name}
                            </div>
                            <div style={{ fontSize: "12px", color: "#64748B", marginTop: "2px" }}>
                              {trackingJobDetails.assigned_technician_skills?.[0] || "Certified Field Specialist"}
                            </div>
                          </div>
                        </div>

                        {trackingJobDetails.assigned_technician_phone && (
                          <a
                            href={`tel:${trackingJobDetails.assigned_technician_phone}`}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "6px",
                              padding: "8px 14px",
                              background: "#069660",
                              color: "#FFFFFF",
                              borderRadius: "8px",
                              fontSize: "13px",
                              fontWeight: 700,
                              textDecoration: "none",
                              boxShadow: "0 2px 4px rgba(6,150,96,0.2)",
                            }}
                          >
                            <Phone size={14} />
                            <span>Call {trackingJobDetails.assigned_technician_phone}</span>
                          </a>
                        )}
                      </div>
                    </div>
                  ) : normalizeStatus(trackingModalRequest.status) === "CANCELLED" ? (
                    <div
                      style={{
                        background: "#FEF2F2",
                        border: "1px solid #FECACA",
                        borderRadius: "14px",
                        padding: "16px",
                        color: "#991B1B",
                        fontSize: "13px",
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <XCircle size={18} color="#EF4444" />
                      <div>This job request is cancelled. If you need service, please submit a new request.</div>
                    </div>
                  ) : (
                    <div
                      style={{
                        background: "#FFFBEB",
                        border: "1px solid #FDE68A",
                        borderRadius: "14px",
                        padding: "16px",
                        color: "#92400E",
                        fontSize: "13px",
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <Clock size={18} color="#F59E0B" />
                      <div>
                        Finding and offering your job to the best ranked technician in your area. Technician contact details will appear here as soon as they accept.
                      </div>
                    </div>
                  )}

                  {/* En Route Notification Banner */}
                  {normalizeStatus(trackingJobDetails?.status || trackingModalRequest.status) === "EN_ROUTE" && (
                    <div
                      style={{
                        background: "#EFF6FF",
                        border: "1px solid #BFDBFE",
                        borderRadius: "14px",
                        padding: "16px 18px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: "12px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <span
                          style={{
                            width: "10px",
                            height: "10px",
                            borderRadius: "50%",
                            background: "#2563EB",
                            display: "inline-block",
                            boxShadow: "0 0 0 4px rgba(37, 99, 235, 0.2)",
                          }}
                        />
                        <div>
                          <strong style={{ fontSize: "14px", color: "#1E40AF", display: "block" }}>
                            Technician is En Route
                          </strong>
                          <span style={{ fontSize: "12px", color: "#3B82F6" }}>
                            Live GPS telemetry is active for this trip.
                          </span>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          const details = trackingJobDetails;
                          const req = trackingModalRequest;
                          setTrackingModalRequest(null);
                          void handleOpenDedicatedLiveMap(req, details);
                        }}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "8px 16px",
                          background: "linear-gradient(135deg, #1D4ED8 0%, #2563EB 100%)",
                          color: "#FFFFFF",
                          border: "none",
                          borderRadius: "8px",
                          fontSize: "12px",
                          fontWeight: 700,
                          cursor: "pointer",
                          boxShadow: "0 2px 6px rgba(37, 99, 235, 0.3)",
                        }}
                      >
                        <MapPin size={13} />
                        View Live Map
                      </button>
                    </div>
                  )}

                  {/* Live Tracking Closed Banner (When ON_SITE or IN_PROGRESS) */}
                  {["ON_SITE", "IN_PROGRESS"].includes(normalizeStatus(trackingJobDetails?.status || trackingModalRequest.status)) && (
                    <div
                      style={{
                        background: "#F5F3FF",
                        border: "1px solid #DDD6FE",
                        borderRadius: "14px",
                        padding: "14px 18px",
                        color: "#5B21B6",
                        fontSize: "13px",
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <CheckCircle2 size={18} color="#7C3AED" />
                      <div>
                        <strong>Technician Arrived On Site:</strong> The technician is currently carrying out service at your premises. Live GPS tracking has concluded.
                      </div>
                    </div>
                  )}

                  {/* Completed Job & Invoice Section */}
                  {["COMPLETED", "CLOSED"].includes(normalizeStatus(trackingJobDetails?.status || trackingModalRequest.status)) && (
                    <div
                      style={{
                        background: "#FFFFFF",
                        border: "2px solid #069660",
                        borderRadius: "14px",
                        padding: "20px",
                        boxShadow: "0 4px 12px rgba(6, 150, 96, 0.08)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          marginBottom: "16px",
                          flexWrap: "wrap",
                          gap: "10px",
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <Receipt size={20} color="#069660" />
                            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 800, color: "#065F46" }}>
                              Official Job Invoice
                            </h3>
                          </div>
                          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#64748B" }}>
                            Service Organization: <strong style={{ color: "#0F172A" }}>
                              {trackingInvoiceDetails?.organization_name || "FieldOps Certified Service"}
                            </strong>
                          </p>
                        </div>

                        {trackingInvoiceDetails && (
                          <button
                            type="button"
                            onClick={() => handlePrintInvoice(trackingInvoiceDetails, trackingModalRequest)}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "6px",
                              padding: "8px 16px",
                              background: "linear-gradient(135deg, #058353 0%, #069660 100%)",
                              color: "#FFFFFF",
                              border: "none",
                              borderRadius: "8px",
                              fontSize: "13px",
                              fontWeight: 700,
                              cursor: "pointer",
                              boxShadow: "0 2px 6px rgba(6, 150, 96, 0.25)",
                            }}
                          >
                            <Download size={14} />
                            Download Invoice
                          </button>
                        )}
                      </div>

                      {trackingInvoiceDetails ? (
                        <div style={{ background: "#F8FAFC", borderRadius: "10px", padding: "14px", fontSize: "13px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#475569" }}>
                            <span>Labour Charges:</span>
                            <strong>₹{trackingInvoiceDetails.labour_cost.toFixed(2)}</strong>
                          </div>
                          <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#475569" }}>
                            <span>Material & Spares:</span>
                            <strong>₹{trackingInvoiceDetails.material_cost.toFixed(2)}</strong>
                          </div>
                          <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#475569" }}>
                            <span>GST ({((trackingInvoiceDetails.gst_rate || 0.18) * 100).toFixed(0)}%):</span>
                            <strong>₹{trackingInvoiceDetails.gst_amount.toFixed(2)}</strong>
                          </div>
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              padding: "10px 0 4px",
                              marginTop: "6px",
                              borderTop: "1px solid #E2E8F0",
                              fontSize: "15px",
                              color: "#065F46",
                              fontWeight: 800,
                            }}
                          >
                            <span>Total Amount Paid:</span>
                            <span>₹{trackingInvoiceDetails.total_amount.toFixed(2)}</span>
                          </div>
                        </div>
                      ) : (
                        <div style={{ fontSize: "13px", color: "#64748B" }}>
                          Invoice processing complete. Click refresh if billing summary is taking a moment to load.
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
