import React, { useEffect, useState } from "react";
import api from "../services/api";
import { Eye, Pencil, Trash2, ExternalLink, Copy, Check, Share2, Loader2, CheckCircle2 } from "lucide-react";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import EmptyState from "../components/ui/EmptyState";
import JobStatusTimeline from "../components/customer-tracking/JobStatusTimeline";
import useAuthStore from "../store/authStore";
import { getJobClosure } from "../services/planningService";
import { JobClosureModal } from "../components/jobs/JobClosureModal";

const JOBS_PAGE_SIZE = 8;

interface JobFormData {
  customer_name: string;
  location: string;
  issue_description: string;
  priority: string;
  service_type: string;
  contact_number: string;
  preferred_service_date: string;
  status: string;
  required_skill?: string;
  tenant_id: string;
  sla_deadline?: string;
  attempt_count?: number;
}

const getActiveTenantId = () => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("tenant_id") || "tenant-1";
  }
  return "tenant-1";
};

const initialFormData: JobFormData = {
  customer_name: "",
  location: "",
  issue_description: "",
  priority: "",
  service_type: "",
  contact_number: "",
  preferred_service_date: "",
  status: "active",
  required_skill: "",
  tenant_id: getActiveTenantId(),
  sla_deadline: "",
  attempt_count: 0,
};

interface Job {
  id: string | number;
  customer_name: string;
  location: string;
  issue_description?: string;
  priority: string;
  service_type: string;
  contact_number?: string;
  preferred_service_date?: string;
  status: string;
  required_skill?: string;
  completed_at?: string;
  completed_by?: string;
}


const priorities = [
  { label: "Critical", value: "CRITICAL" },
  { label: "High", value: "HIGH" },
  { label: "Medium", value: "MEDIUM" },
  { label: "Low", value: "LOW" },
];

const serviceTypes = [
  { label: "HVAC Repair", value: "HVAC_REPAIR" },
  { label: "Electrical Service", value: "ELECTRICAL_SERVICE" },
  { label: "Plumbing Service", value: "PLUMBING_SERVICE" },
  { label: "Network Support", value: "NETWORK_SUPPORT" },
  { label: "General Maintenance", value: "GENERAL_MAINTENANCE" },
];

const priorityMap: Record<string, string> = { P1: "CRITICAL", P2: "HIGH", P3: "MEDIUM", P4: "LOW", P5: "LOW" };

function normalizeP(p: string): string {
  const up = (p || "").toUpperCase();
  return priorityMap[up] || up;
}

const formatServiceType = (type: string) => {
  if (!type) return "";
  return type
    .replace(/_/g, " ")
    .toLowerCase()
    .split(" ")
    .map(word => {
      const uppercaseAcronyms = ["hvac", "cctv", "ac", "sla", "ip", "it"];
      if (uppercaseAcronyms.includes(word)) {
        return word.toUpperCase();
      }
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
};

const getPriorityStyle = (priority: string): React.CSSProperties => {
  const p = (priority || "").toUpperCase();
  const base = {
    fontSize: "9px",
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: "20px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    display: "inline-block",
  } as React.CSSProperties;
  if (p === "CRITICAL" || p === "P1") return { ...base, background: "#FAE5E5", color: "#7A2020" };
  if (p === "HIGH" || p === "P2") return { ...base, background: "#FEF0D6", color: "#7A5120" };
  if (p === "MEDIUM" || p === "P3") return { ...base, background: "#FDFBDC", color: "#706020" };
  if (p === "LOW" || p === "P4" || p === "P5") return { ...base, background: "#DDEEE5", color: "#2F4F3E" };
  return { ...base, background: "#F0F4F2", color: "#6B7280" };
};

interface PopupState {
  show: boolean;
  title: string;
  message: string;
  jobId?: string;
}

const CopyJobIdButton = ({ jobId }: { jobId: string | number }) => {
  const [copied, setCopied] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(String(jobId)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1000);
    });
  };

  return (
    <button
      onClick={handleCopy}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={copied ? "Copied!" : "Copy Job ID"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "22px",
        height: "22px",
        borderRadius: "4px",
        border: "none",
        cursor: "pointer",
        transition: "all 0.2s",
        backgroundColor: isHovered ? "#DDEEE5" : "transparent",
        color: copied ? "#10B981" : (isHovered ? "#2F4F3E" : "#9CA3AF"),
      }}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
};



function JobCreationForm() {
  const [formData, setFormData] = useState<JobFormData>(initialFormData);
  const [errors, setErrors] = useState<Partial<Record<keyof JobFormData, string>>>({});
  const [apiError, setApiError] = useState("");
  const [loading, setLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);

  // States for styling hover/focus effects
  const [hoveredBtn, setHoveredBtn] = useState<string | null>(null);
  const [hoveredRow, setHoveredRow] = useState<string | number | null>(null);
  const [focusedInput, setFocusedInput] = useState<string | null>(null);

  const getInputStyle = (name: string, hasError = false) => {
    let style = { ...styles.formInput };
    if (hasError) {
      style = { ...style, ...styles.inputError };
    } else if (focusedInput === name) {
      style = { ...style, ...styles.formInputFocus };
    }
    return style;
  };

  // State variables for list rendering and filtering
  const [jobs, setJobs] = useState<Job[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [debSearchTerm, setDebSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [priorityFilter, setPriorityFilter] = useState("ALL");
  const [serviceFilter, setServiceFilter] = useState("ALL");
  const [serviceTypesList, setServiceTypesList] = useState<Array<{ value: string; label: string }>>([]);
  const [jobsPage, setJobsPage] = useState(1);
  const [totalJobsCount, setTotalJobsCount] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    setJobsPage(1);
  }, [debSearchTerm, statusFilter, priorityFilter, serviceFilter]);



  const getFormServiceTypes = () => {
    const list = [...serviceTypes];
    if (formData.service_type) {
      const seenNormal = new Set<string>(list.map(s => (s.value || "").toUpperCase().replace(/_/g, " ").replace(/\s+/g, " ").trim()));
      const val = formData.service_type;
      const normalized = val.toUpperCase().replace(/_/g, " ").replace(/\s+/g, " ").trim();
      if (!seenNormal.has(normalized)) {
        const label = val.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
        list.push({ label, value: val });
      }
    }
    return list;
  };

  const { user } = useAuthStore();
  const userRole = (user?.role || localStorage.getItem("user_role") || "").toLowerCase();
  const isTechnician = userRole === "technician";

  const [isEditing, setIsEditing] = useState(false);
  const [editingJobId, setEditingJobId] = useState<string | number | null>(null);

  const [popup, setPopup] = useState<PopupState>({ show: false, title: "", message: "", jobId: "" });
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [viewJob, setViewJob] = useState<Job | null>(null);

  const [isClosureModalOpen, setIsClosureModalOpen] = useState(false);
  const [closureDetails, setClosureDetails] = useState<any>(null);

  useEffect(() => {
    if (viewJob) {
      if (viewJob.status?.toUpperCase() === "COMPLETED") {
        getJobClosure(viewJob.id)
          .then((data) => setClosureDetails(data))
          .catch(() => setClosureDetails(null));
      } else {
        setClosureDetails(null);
      }
    } else {
      setClosureDetails(null);
    }
  }, [viewJob]);

  const handleClosureSuccess = () => {
    if (viewJob) {
      const updatedJob = { ...viewJob, status: "COMPLETED" };
      setViewJob(updatedJob);
      getJobClosure(viewJob.id).then((data) => setClosureDetails(data)).catch(() => {});
    }
    fetchJobs();
  };


  const fetchServiceTypes = async () => {
    try {
      const response = await api.get("/jobs/service-types");
      const mapped = response.data.map((st: string) => {
        const predefined = serviceTypes.find(s => (s.value || "").toUpperCase().replace(/_/g, " ").replace(/\s+/g, " ").trim() === st.toUpperCase().replace(/_/g, " ").replace(/\s+/g, " ").trim());
        return {
          value: predefined ? predefined.value : st,
          label: predefined ? predefined.label : st.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
        };
      });
      setServiceTypesList(mapped);
    } catch (error) {
      console.error("Failed to fetch unique service types:", error);
    }
  };

  const fetchJobs = async () => {
    try {
      setJobsLoading(true);
      const params: any = {
        page: jobsPage,
        limit: JOBS_PAGE_SIZE
      };
      if (debSearchTerm) params.search = debSearchTerm;
      if (statusFilter && statusFilter !== "ALL") params.status = statusFilter;
      if (priorityFilter && priorityFilter !== "ALL") params.priority = priorityFilter;
      if (serviceFilter && serviceFilter !== "ALL") params.service_type = serviceFilter;

      const [response] = await Promise.all([
        api.get("/jobs", { params }),
        new Promise(resolve => setTimeout(resolve, 1000))
      ]);
      setJobs(response.data);
      const totalHeader = response.headers["x-total-count"] || response.headers["X-Total-Count"];
      setTotalJobsCount(totalHeader ? parseInt(totalHeader, 10) : response.data.length);
    } catch (error) {
      console.error(error);
      setApiError("Unable to fetch jobs. Please check backend API.");
    } finally {
      setJobsLoading(false);
    }
  };

  useEffect(() => {
    fetchServiceTypes();
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [debSearchTerm, statusFilter, priorityFilter, serviceFilter, jobsPage]);

  const validateForm = () => {
    const newErrors: Partial<Record<keyof JobFormData, string>> = {};
    if (!formData.customer_name.trim()) newErrors.customer_name = "Customer name is required";
    if (!formData.location.trim()) newErrors.location = "Location is required";
    if (!formData.issue_description.trim()) newErrors.issue_description = "Issue description is required";
    if (!formData.priority) newErrors.priority = "Priority is required";
    if (!formData.service_type) newErrors.service_type = "Service type is required";
    if (!formData.contact_number.trim()) {
      newErrors.contact_number = "Contact number is required";
    } else if (!/^[6-9]\d{9}$/.test(formData.contact_number)) {
      newErrors.contact_number = "Enter a valid 10-digit Indian mobile number";
    }
    if (!formData.preferred_service_date) newErrors.preferred_service_date = "Preferred service date is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const resetForm = () => {
    setFormData(initialFormData);
    setErrors({});
    setIsEditing(false);
    setEditingJobId(null);
    setIsFormOpen(false);
  };

  const handleChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = event.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setErrors(prev => ({ ...prev, [name]: "" }));
    setApiError("");
  };

  const handleEdit = (job: Job) => {
    setIsEditing(true);
    setEditingJobId(job.id);
    setApiError("");
    let jobStatus = job.status || "active";
    const statusLower = jobStatus.toLowerCase().trim();
    if (statusLower === "inprogress") {
      jobStatus = "in progress";
    } else if (statusLower === "canceled") {
      jobStatus = "cancelled";
    }
    setFormData({
      customer_name: job.customer_name || "",
      location: job.location || "",
      issue_description: job.issue_description || "",
      priority: job.priority || "",
      service_type: job.service_type || "",
      contact_number: job.contact_number || "",
      preferred_service_date: job.preferred_service_date || "",
      status: jobStatus,
      required_skill: job.required_skill || "",
      tenant_id: (job as any).tenant_id || "tenant-1",
      sla_deadline: (job as any).sla_deadline ? new Date((job as any).sla_deadline).toISOString().slice(0, 16) : "",
      attempt_count: (job as any).attempt_count !== undefined ? (job as any).attempt_count : 0,
    });
    setIsFormOpen(true);
  };

  const handleCancelEdit = () => { resetForm(); setApiError(""); };
  const closePopup = () => setPopup({ show: false, title: "", message: "", jobId: "" });

  const handleCreateNew = () => {
    setFormData(initialFormData);
    setErrors({});
    setIsEditing(false);
    setEditingJobId(null);
    setApiError("");
    setIsFormOpen(true);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!validateForm()) return;
    try {
      setLoading(true);
      const payload = {
        ...formData,
        sla_deadline: formData.sla_deadline && formData.sla_deadline.trim() ? formData.sla_deadline : null,
        required_skill: formData.required_skill && formData.required_skill.trim() ? formData.required_skill : null,
        attempt_count: formData.attempt_count !== undefined ? Number(formData.attempt_count) : 0,
      };

      if (isEditing && editingJobId !== null) {
        const response = await api.put(`/jobs/${editingJobId}`, payload);
        setPopup({ show: true, title: "Job Updated Successfully", message: "The job details have been updated successfully.", jobId: response.data?.id ?? editingJobId });
        resetForm();
        fetchJobs();
      } else {
        const response = await api.post("/jobs", payload);
        setPopup({ show: true, title: "Job Created Successfully", message: "Your job request has been submitted successfully.", jobId: response.data?.id ?? "" });
        resetForm();
        setJobsPage(1);
        setSearchTerm("");
        setDebSearchTerm("");
        setStatusFilter("ALL");
        setPriorityFilter("ALL");
        setServiceFilter("ALL");
        if (debSearchTerm === "" && statusFilter === "ALL" && priorityFilter === "ALL" && serviceFilter === "ALL") {
          fetchJobs();
        }
      }
      fetchServiceTypes();
    } catch (error: any) {
      console.error(error);
      let errorMsg = "Unable to save job. Please check backend API.";
      if (error.response?.data) {
        const data = error.response.data;
        if (data.error && data.error !== "Bad request") {
          errorMsg = data.error;
        } else if (data.detail && Array.isArray(data.detail)) {
          errorMsg = data.detail.map((d: any) => {
            const field = d.loc && d.loc.length > 0 ? d.loc[d.loc.length - 1] : "field";
            const formattedField = String(field).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
            return `${formattedField}: ${d.msg}`;
          }).join(", ");
        } else if (data.detail) {
          errorMsg = data.detail;
        }
      }
      setApiError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string | number) => {
    const job = jobs.find(j => j.id === id);
    const name = job?.customer_name || `Job #${id}`;
    if (!window.confirm(`Are you sure you want to delete "${name}"?`)) return;
    try {
      setJobsLoading(true);
      await api.delete(`/jobs/${id}`);
      setPopup({ show: true, title: "Job Deleted", message: "The job has been removed successfully.", jobId: id });
      fetchJobs();
      fetchServiceTypes();
    } catch (error) {
      console.error(error);
      setApiError("Unable to delete job. Please check backend API.");
    } finally {
      setJobsLoading(false);
    }
  };

  const filteredJobs = jobs;

  const jobsTotalPages = Math.max(1, Math.ceil(totalJobsCount / JOBS_PAGE_SIZE));
  const safeJobsPage = Math.min(jobsPage, jobsTotalPages);
  const paginatedJobs = jobs;

  useEffect(() => {
    const total = Math.max(1, Math.ceil(totalJobsCount / JOBS_PAGE_SIZE));
    if (jobsPage > total) {
      setJobsPage(total);
    }
  }, [totalJobsCount, jobsPage]);

  const getJobsPageNums = () => {
    const nums: number[] = [];
    const delta = 2;
    for (let i = Math.max(1, safeJobsPage - delta); i <= Math.min(jobsTotalPages, safeJobsPage + delta); i++) {
      nums.push(i);
    }
    return nums;
  };

  const formatStatus = (status: string) => {
    const s = (status || "active").toLowerCase().trim();
    if (s === "inprogress" || s === "in progress") return "In Progress";
    if (s === "canceled" || s === "cancelled") return "Cancelled";
    return s.charAt(0).toUpperCase() + s.slice(1);
  };

  const getStatusStyle = (status: string): React.CSSProperties => {
    const s = (status || "").toLowerCase().trim();
    const base = {
      fontSize: "10px",
      fontWeight: 600,
      padding: "2px 9px",
      borderRadius: "20px",
      textTransform: "capitalize",
      display: "inline-block",
      whiteSpace: "nowrap",
    } as React.CSSProperties;
    if (s === "inprogress" || s === "in progress") return { ...base, background: "#FEF3DC", color: "#7A5120" };
    if (s === "completed") return { ...base, background: "#E8F0FE", color: "#2F5090" };
    if (s === "canceled" || s === "cancelled") return { ...base, background: "#FAE5E5", color: "#7A2020" };
    return { ...base, background: "#DDEEE5", color: "#2F4F3E" };
  };

  return (
    <div style={styles.jobsPage}>
      <style>{`
        @keyframes jobsFadeInRow {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .jobs-table-body tr {
          animation: jobsFadeInRow 0.25s ease-out forwards;
        }
      `}</style>
      {/* Success Popup */}
      {popup.show && (
        <div style={styles.popupOverlay}>
          <div style={styles.successPopup}>
            <div style={styles.successIcon}>✓</div>
            <h3>{popup.title}</h3>
            {popup.jobId && <div style={styles.jobIdBox}>Job ID: <strong>#{popup.jobId}</strong></div>}
            <p>{popup.message}</p>
            <button
              type="button"
              style={hoveredBtn === 'popupClose' ? { ...styles.popupCloseBtn, background: '#5C9470' } : styles.popupCloseBtn}
              onMouseEnter={() => setHoveredBtn('popupClose')}
              onMouseLeave={() => setHoveredBtn(null)}
              onClick={closePopup}
            >
              OK
            </button>
          </div>
        </div>
      )}


      {/* Main Content: List Only (Form moved to Sidebar) */}
      <div style={styles.mainContentRow}>
        {/* Job Management List */}
        <div style={styles.contentCard}>
          <div style={styles.cardHeader}>
            <div>
              <p style={styles.cardSubtitle}>View and manage all submitted job requests</p>
            </div>
            <div style={styles.headerActionsRow}>
              <button
                style={hoveredBtn === 'refresh' ? { ...styles.refreshIconBtn, background: "#F6FAF8", borderColor: "#7AAE8A" } : styles.refreshIconBtn}
                onMouseEnter={() => setHoveredBtn('refresh')}
                onMouseLeave={() => setHoveredBtn(null)}
                onClick={fetchJobs}
                title="Refresh"
              >
                ⟳ Refresh
              </button>
              <button
                style={hoveredBtn === 'add' ? { ...styles.addJobBtn, background: "#5C9470" } : styles.addJobBtn}
                onMouseEnter={() => setHoveredBtn('add')}
                onMouseLeave={() => setHoveredBtn(null)}
                onClick={handleCreateNew}
              >
                + Create Job
              </button>
            </div>
          </div>

          {/* Filters */}
          <div style={styles.filtersRow}>
            <div style={styles.filterGroup}>
              <label style={styles.filterLabel}>Search</label>
              <input
                type="text"
                placeholder="Search name, location..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                onFocus={() => setFocusedInput('search')}
                onBlur={() => setFocusedInput(null)}
                style={focusedInput === 'search' ? { ...styles.filterInput, ...styles.filterInputFocus } : styles.filterInput}
              />
            </div>
            <div style={styles.filterGroup}>
              <label style={styles.filterLabel}>Priority</label>
              <select
                value={priorityFilter}
                onChange={e => setPriorityFilter(e.target.value)}
                onFocus={() => setFocusedInput('priorityFilter')}
                onBlur={() => setFocusedInput(null)}
                style={focusedInput === 'priorityFilter' ? { ...styles.filterInput, ...styles.filterInputFocus } : styles.filterInput}
              >
                <option value="ALL">All Priorities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
              </select>
            </div>
            <div style={styles.filterGroup}>
              <label style={styles.filterLabel}>Service</label>
              <select
                value={serviceFilter}
                onChange={e => setServiceFilter(e.target.value)}
                onFocus={() => setFocusedInput('serviceFilter')}
                onBlur={() => setFocusedInput(null)}
                style={focusedInput === 'serviceFilter' ? { ...styles.filterInput, ...styles.filterInputFocus } : styles.filterInput}
              >
                <option value="ALL">All Services</option>
                {serviceTypesList.map(st => (
                  <option key={st.value} value={st.value}>
                    {st.label}
                  </option>
                ))}
              </select>
            </div>
            <div style={styles.filterGroup}>
              <label style={styles.filterLabel}>Status</label>
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
                onFocus={() => setFocusedInput('statusFilter')}
                onBlur={() => setFocusedInput(null)}
                style={focusedInput === 'statusFilter' ? { ...styles.filterInput, ...styles.filterInputFocus } : styles.filterInput}
              >
                <option value="ALL">All Statuses</option>
                <option value="active">Active (Unassigned)</option>
                <option value="QUEUED">Queued</option>
                <option value="ASSIGNED">Assigned</option>
                <option value="EN_ROUTE">En Route</option>
                <option value="ON_SITE">On Site</option>
                <option value="in progress">In Progress</option>
                <option value="ESCALATED">Escalated</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>

          {/* Jobs Count */}
          <p style={styles.resultsCount}>
            Showing <strong>{totalJobsCount === 0 ? 0 : (safeJobsPage - 1) * JOBS_PAGE_SIZE + 1}–{Math.min(safeJobsPage * JOBS_PAGE_SIZE, totalJobsCount)}</strong> of <strong>{totalJobsCount}</strong> job{totalJobsCount !== 1 ? "s" : ""} found
          </p>

          {/* Job Table */}
          <div style={{
            ...styles.tableContainer,
            display: "flex",
            flexDirection: "column",
            ...(jobsLoading ? { justifyContent: "center", alignItems: "center", minHeight: "350px", flex: 1 } : {})
          }}>
            {jobsLoading ? (
              <LoadingSpinner message="Loading jobs..." />
            ) : filteredJobs.length === 0 ? (
              <EmptyState
                title={
                  (searchTerm && searchTerm.trim()) ||
                    statusFilter !== "ALL" ||
                    priorityFilter !== "ALL" ||
                    serviceFilter !== "ALL"
                    ? "No jobs match your filters"
                    : "No jobs found"
                }
                description={
                  (searchTerm && searchTerm.trim()) ||
                    statusFilter !== "ALL" ||
                    priorityFilter !== "ALL" ||
                    serviceFilter !== "ALL"
                    ? "Try adjusting your search terms or filters."
                    : "Get started by creating your first job request."
                }
                action={
                  ((searchTerm && searchTerm.trim()) ||
                    statusFilter !== "ALL" ||
                    priorityFilter !== "ALL" ||
                    serviceFilter !== "ALL") ? (
                    <button
                      style={hoveredBtn === 'clearFilters' ? { ...styles.refreshIconBtn, background: '#F6FAF8', borderColor: '#7AAE8A' } : styles.refreshIconBtn}
                      onMouseEnter={() => setHoveredBtn('clearFilters')}
                      onMouseLeave={() => setHoveredBtn(null)}
                      onClick={() => {
                        setSearchTerm("");
                        setStatusFilter("ALL");
                        setPriorityFilter("ALL");
                        setServiceFilter("ALL");
                      }}
                    >
                      Clear Filters
                    </button>
                  ) : (
                    <button
                      style={hoveredBtn === 'emptyAdd' ? { ...styles.addJobBtn, background: '#5C9470' } : styles.addJobBtn}
                      onMouseEnter={() => setHoveredBtn('emptyAdd')}
                      onMouseLeave={() => setHoveredBtn(null)}
                      onClick={handleCreateNew}
                    >
                      + Create Job
                    </button>
                  )
                }
              />
            ) : (
              <table style={styles.dashboardTable}>
                <thead>
                  <tr>
                    <th style={{ ...styles.th, width: "8%" }}>Job ID</th>
                    <th style={{ ...styles.th, width: "20%" }}>Customer</th>
                    <th style={{ ...styles.th, width: "13%" }}>Location</th>
                    <th style={{ ...styles.th, width: "8%" }}>Priority</th>
                    <th style={{ ...styles.th, width: "15%" }}>Service Type</th>
                    <th style={{ ...styles.th, width: "11%" }}>Preferred Date</th>
                    <th style={{ ...styles.th, width: "10%" }}>Status</th>
                    <th style={{ ...styles.th, width: "15%" }}>Actions</th>
                  </tr>
                </thead>
                <tbody key={safeJobsPage} className="jobs-table-body">
                  {paginatedJobs.map(job => (
                    <tr
                      key={job.id}
                      style={hoveredRow === job.id ? { background: "#F8FBF9" } : undefined}
                      onMouseEnter={() => setHoveredRow(job.id)}
                      onMouseLeave={() => setHoveredRow(null)}
                    >
                      <td style={{ ...styles.td, ...styles.jobIdCell, width: "8%" }}>
                        <span style={{ fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace", color: "#5C9470", fontWeight: 700 }}>
                          {job.id}
                        </span>
                        <CopyJobIdButton jobId={job.id} />
                      </td>
                      <td style={{ ...styles.td, ...styles.customerCell, width: "20%", maxWidth: 0 }}>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={job.customer_name}>
                          <strong>{job.customer_name}</strong>
                        </div>
                        {job.issue_description && (
                          <div style={styles.issueSub} title={job.issue_description}>{job.issue_description}</div>
                        )}
                      </td>
                      <td style={{ ...styles.td, width: "13%", maxWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px", width: "100%", overflow: "hidden" }}>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }} title={job.location}>
                            {job.location}
                          </span>
                          <a
                            href={`https://maps.google.com/?q=${encodeURIComponent(job.location)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: "#9CA3AF",
                              display: "flex",
                              alignItems: "center",
                              transition: "color 0.2s",
                              flexShrink: 0
                            }}
                            title="Open in Maps"
                            onClick={(e) => e.stopPropagation()}
                            onMouseEnter={(e) => e.currentTarget.style.color = "#5C9470"}
                            onMouseLeave={(e) => e.currentTarget.style.color = "#9CA3AF"}
                          >
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      </td>
                      <td style={{ ...styles.td, width: "8%" }}>
                        <span style={getPriorityStyle(job.priority)}>
                          {normalizeP(job.priority)}
                        </span>
                      </td>
                      <td style={{ ...styles.td, width: "15%", maxWidth: 0 }}>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={formatServiceType(job.service_type)}>
                          {formatServiceType(job.service_type)}
                        </div>
                      </td>
                      <td style={{ ...styles.td, width: "11%", maxWidth: 0 }}>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={job.preferred_service_date}>
                          {job.preferred_service_date}
                        </div>
                      </td>
                      <td style={{ ...styles.td, width: "10%" }}>
                        <span style={getStatusStyle(job.status)}>{formatStatus(job.status)}</span>
                      </td>
                      <td style={styles.td}>
                        <div style={{ display: "flex", gap: "12px" }}>
                          <button
                            style={{ ...styles.iconActionBtn, color: "#16a34a" }}
                            onClick={() => setViewJob(job)}
                            title="View job details"
                            aria-label="View job"
                          >
                            <Eye size={15} />
                          </button>
                          <button
                            style={{ ...styles.iconActionBtn, color: "#ca8a04" }}
                            onClick={() => handleEdit(job)}
                            title="Edit job"
                            aria-label="Edit job"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            style={{ ...styles.iconActionBtn, color: "#dc2626" }}
                            onClick={() => handleDelete(job.id)}
                            title="Delete job"
                            aria-label="Delete job"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {/* Pagination */}
          {!jobsLoading && (
            <div style={styles.jobsPagination}>
              <span style={styles.jobsPageInfo}>
                Page <strong style={{ color: "#2F4F3E" }}>{safeJobsPage}</strong> of <strong style={{ color: "#2F4F3E" }}>{jobsTotalPages}</strong> · {totalJobsCount} results
              </span>
              <div style={styles.jobsPageControls}>
                <button
                  style={safeJobsPage === 1 ? { ...styles.jobsPageBtn, opacity: 0.4, cursor: "not-allowed" } : styles.jobsPageBtn}
                  type="button"
                  onClick={() => setJobsPage(1)}
                  disabled={safeJobsPage === 1}
                >
                  «
                </button>
                <button
                  style={safeJobsPage === 1 ? { ...styles.jobsPageBtn, opacity: 0.4, cursor: "not-allowed" } : styles.jobsPageBtn}
                  type="button"
                  onClick={() => setJobsPage(p => Math.max(1, p - 1))}
                  disabled={safeJobsPage === 1}
                >
                  ‹ Prev
                </button>
                <div style={styles.jobsPageNumbers}>
                  {getJobsPageNums().map(n => (
                    <button
                      key={n}
                      type="button"
                      style={
                        n === safeJobsPage
                          ? { ...styles.jobsPageNum, background: "#7AAE8A", borderColor: "#7AAE8A", color: "#fff" }
                          : styles.jobsPageNum
                      }
                      onClick={() => setJobsPage(n)}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <button
                  style={safeJobsPage === jobsTotalPages ? { ...styles.jobsPageBtn, opacity: 0.4, cursor: "not-allowed" } : styles.jobsPageBtn}
                  type="button"
                  onClick={() => setJobsPage(p => Math.min(jobsTotalPages, p + 1))}
                  disabled={safeJobsPage === jobsTotalPages}
                >
                  Next ›
                </button>
                <button
                  style={safeJobsPage === jobsTotalPages ? { ...styles.jobsPageBtn, opacity: 0.4, cursor: "not-allowed" } : styles.jobsPageBtn}
                  type="button"
                  onClick={() => setJobsPage(jobsTotalPages)}
                  disabled={safeJobsPage === jobsTotalPages}
                >
                  »
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* View Job Modal */}
      {viewJob && (
        <div style={styles.popupOverlay} onClick={() => setViewJob(null)}>
          <div style={{ ...styles.viewJobModal, maxWidth: "850px" }} onClick={e => e.stopPropagation()}>
            <div style={styles.viewModalHeader}>
              <h3 style={styles.viewModalHeaderTitle}>Job Details & Status History</h3>
              <button onClick={() => setViewJob(null)} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: '#6b7280' }}>×</button>
            </div>
            <div style={{ display: "flex", flexDirection: "row", flexWrap: "wrap", width: "100%" }}>
              {/* Left Column: Details */}
              <div style={{ flex: 1, minWidth: "300px", padding: "18px 22px 22px", display: "flex", flexDirection: "column", gap: "10px", borderRight: "1px solid #E3ECE7" }}>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Job ID</span><span style={styles.viewValue}>#{viewJob.id}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Customer</span><span style={styles.viewValue}>{viewJob.customer_name}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Location</span><span style={styles.viewValue}>{viewJob.location}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Priority</span><span style={getPriorityStyle(viewJob.priority)}>{normalizeP(viewJob.priority)}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Service Type</span><span style={styles.viewValue}>{viewJob.service_type?.replace(/_/g, ' ')}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Contact</span><span style={styles.viewValue}>{viewJob.contact_number}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Preferred Date</span><span style={styles.viewValue}>{viewJob.preferred_service_date}</span></div>
                <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Status</span><span style={getStatusStyle(viewJob.status)}>{formatStatus(viewJob.status)}</span></div>
                {viewJob.issue_description && (
                  <div style={{ ...styles.viewDetailRow, flexDirection: "column", gap: "4px" }}>
                    <span style={styles.viewLabel}>Issue</span>
                    <span style={styles.viewValue}>{viewJob.issue_description}</span>
                  </div>
                )}

                {/* Complete Job Button (Visible if status !== COMPLETED and logged user is Technician) */}
                {viewJob.status?.toUpperCase() !== "COMPLETED" && (
                  <button
                    type="button"
                    onClick={() => setIsClosureModalOpen(true)}
                    disabled={!isTechnician}
                    style={{
                      marginTop: "12px",
                      padding: "10px 16px",
                      backgroundColor: isTechnician ? "#166534" : "#94a3b8",
                      color: "#ffffff",
                      border: "none",
                      borderRadius: "8px",
                      fontWeight: 600,
                      fontSize: "14px",
                      cursor: isTechnician ? "pointer" : "not-allowed",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "6px"
                    }}
                    title={!isTechnician ? "Only logged-in technicians can complete jobs" : "Complete Job"}
                  >
                    <CheckCircle2 size={16} /> Complete Job
                  </button>
                )}

                {/* Closure Summary Details */}
                {(viewJob.status?.toUpperCase() === "COMPLETED" || closureDetails) && (
                  <div style={{ marginTop: "14px", padding: "12px", backgroundColor: "#f0fdf4", borderRadius: "8px", border: "1px solid #bbf7d0" }}>
                    <h4 style={{ fontSize: "13px", fontWeight: 700, color: "#166534", marginBottom: "6px" }}>Closure Summary</h4>
                    <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Completed By</span><span style={styles.viewValue}>{closureDetails?.technician_id || viewJob.completed_by || "Technician"}</span></div>
                    <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Completed Time</span><span style={styles.viewValue}>{closureDetails?.completed_at ? new Date(closureDetails.completed_at).toLocaleString() : (viewJob.completed_at ? new Date(viewJob.completed_at).toLocaleString() : "N/A")}</span></div>
                    {closureDetails?.work_summary && (
                      <div style={{ ...styles.viewDetailRow, flexDirection: "column", gap: "2px", marginTop: "4px" }}>
                        <span style={styles.viewLabel}>Work Summary</span>
                        <span style={styles.viewValue}>{closureDetails.work_summary}</span>
                      </div>
                    )}
                    {closureDetails?.before_images && closureDetails.before_images.length > 0 && (
                      <div style={{ marginTop: "6px" }}>
                        <span style={styles.viewLabel}>Before Images</span>
                        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "2px" }}>
                          {closureDetails.before_images.map((img: string, i: number) => (
                            <span key={i} style={{ fontSize: "11px", background: "#e2e8f0", padding: "2px 6px", borderRadius: "4px" }}>{img}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {closureDetails?.after_images && closureDetails.after_images.length > 0 && (
                      <div style={{ marginTop: "6px" }}>
                        <span style={styles.viewLabel}>After Images</span>
                        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "2px" }}>
                          {closureDetails.after_images.map((img: string, i: number) => (
                            <span key={i} style={{ fontSize: "11px", background: "#dcfce7", color: "#166534", padding: "2px 6px", borderRadius: "4px" }}>{img}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    <div style={{ display: "flex", gap: "8px", marginTop: "8px", paddingTop: "6px", borderTop: "1px dashed #cbd5e1", fontSize: "12px" }}>
                      <div><span style={styles.viewLabel}>Labour: </span><strong>${closureDetails?.labour_cost ?? 0}</strong></div>
                      <div><span style={styles.viewLabel}>Material: </span><strong>${closureDetails?.material_cost ?? 0}</strong></div>
                      <div><span style={styles.viewLabel}>Subtotal: </span><strong style={{ color: "#166534" }}>${closureDetails?.subtotal ?? 0}</strong></div>
                    </div>
                  </div>
                )}
              </div>
              
              {/* Right Column: Interactive vertical Timeline */}
              <div style={{ flex: 1, minWidth: "300px", padding: "18px 22px 22px" }} className="flex flex-col">
                <JobStatusTimeline jobId={viewJob.id} currentStatus={viewJob.status} />
              </div>
            </div>

            {/* Job Closure Modal */}
            <JobClosureModal
              jobId={viewJob.id}
              isOpen={isClosureModalOpen}
              onClose={() => setIsClosureModalOpen(false)}
              onSuccess={handleClosureSuccess}
            />
          </div>
        </div>
      )}


      {/* Sliding Sidebar for Job Form — rendered outside main div to avoid overflow:hidden clipping */}
      <div style={{
        ...styles.jobFormSidebar,
        right: isFormOpen ? 0 : "-420px",
      }}>
        <div style={styles.sidebarHeader}>
          <h3 style={{ fontSize: "16px", fontWeight: 700, color: "#2F4F3E" }}>{isEditing ? "Edit Job" : "Create New Job"}</h3>
          <button style={styles.closeSidebar} onClick={() => setIsFormOpen(false)}>×</button>
        </div>
        <div style={styles.sidebarBody}>
          {apiError && <div style={styles.alertError}>{apiError}</div>}
          <form onSubmit={handleSubmit} style={styles.jobForm}>
            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Customer Name <span style={styles.req}>*</span></label>
              <input
                type="text"
                name="customer_name"
                value={formData.customer_name}
                onChange={handleChange}
                onFocus={() => setFocusedInput('customer_name')}
                onBlur={() => setFocusedInput(null)}
                placeholder="Enter customer name"
                style={getInputStyle('customer_name', !!errors.customer_name)}
              />
              {errors.customer_name && <span style={styles.fieldError}>{errors.customer_name}</span>}
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Location <span style={styles.req}>*</span></label>
              <input
                type="text"
                name="location"
                value={formData.location}
                onChange={handleChange}
                onFocus={() => setFocusedInput('location')}
                onBlur={() => setFocusedInput(null)}
                placeholder="Enter location"
                style={getInputStyle('location', !!errors.location)}
              />
              {errors.location && <span style={styles.fieldError}>{errors.location}</span>}
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Priority <span style={styles.req}>*</span></label>
              <select
                name="priority"
                value={formData.priority}
                onChange={handleChange}
                onFocus={() => setFocusedInput('priority')}
                onBlur={() => setFocusedInput(null)}
                style={getInputStyle('priority', !!errors.priority)}
              >
                <option value="">Select priority</option>
                {priorities.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
              {errors.priority && <span style={styles.fieldError}>{errors.priority}</span>}
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Service Type <span style={styles.req}>*</span></label>
              <select
                name="service_type"
                value={formData.service_type}
                onChange={handleChange}
                onFocus={() => setFocusedInput('service_type')}
                onBlur={() => setFocusedInput(null)}
                style={getInputStyle('service_type', !!errors.service_type)}
              >
                <option value="">Select service type</option>
                {getFormServiceTypes().map(st => (
                  <option key={st.value} value={st.value}>{st.label}</option>
                ))}
              </select>
              {errors.service_type && <span style={styles.fieldError}>{errors.service_type}</span>}
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Contact Number <span style={styles.req}>*</span></label>
              <input
                type="text"
                name="contact_number"
                value={formData.contact_number}
                onChange={handleChange}
                onFocus={() => setFocusedInput('contact_number')}
                onBlur={() => setFocusedInput(null)}
                placeholder="9876543210"
                maxLength={10}
                style={getInputStyle('contact_number', !!errors.contact_number)}
              />
              {errors.contact_number && <span style={styles.fieldError}>{errors.contact_number}</span>}
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Preferred Service Date <span style={styles.req}>*</span></label>
              <input
                type="date"
                name="preferred_service_date"
                value={formData.preferred_service_date}
                onChange={handleChange}
                onFocus={() => setFocusedInput('preferred_service_date')}
                onBlur={() => setFocusedInput(null)}
                style={getInputStyle('preferred_service_date', !!errors.preferred_service_date)}
              />
              {errors.preferred_service_date && <span style={styles.fieldError}>{errors.preferred_service_date}</span>}
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Status <span style={styles.req}>*</span></label>
              <select
                name="status"
                value={formData.status}
                onChange={handleChange}
                onFocus={() => setFocusedInput('status')}
                onBlur={() => setFocusedInput(null)}
                style={getInputStyle('status')}
              >
                <option value="active">Active</option>
                <option value="QUEUED">Queued (Dispatch Queue)</option>
                <option value="ESCALATED">Escalated (SLA Escalations)</option>
                <option value="in progress">In Progress</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>
                Tenant ID <span style={styles.req}>*</span>{" "}
                <span style={{ fontSize: "11px", color: "#6B7280", fontWeight: 400 }}>(Active Session)</span>
              </label>
              <input
                type="text"
                name="tenant_id"
                value={formData.tenant_id}
                readOnly
                style={{ ...getInputStyle('tenant_id'), background: "#EEF2F6", cursor: "not-allowed" }}
              />
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>SLA Deadline (Optional)</label>
              <input
                type="datetime-local"
                name="sla_deadline"
                value={formData.sla_deadline || ""}
                onChange={handleChange}
                onFocus={() => setFocusedInput('sla_deadline')}
                onBlur={() => setFocusedInput(null)}
                style={getInputStyle('sla_deadline')}
              />
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Attempt Count (Optional)</label>
              <input
                type="number"
                name="attempt_count"
                value={formData.attempt_count ?? 0}
                onChange={handleChange}
                onFocus={() => setFocusedInput('attempt_count')}
                onBlur={() => setFocusedInput(null)}
                min={0}
                placeholder="0"
                style={getInputStyle('attempt_count')}
              />
            </div>

            <div style={styles.formGroup}>
              <label style={styles.formLabel}>Issue Description <span style={styles.req}>*</span></label>
              <textarea
                name="issue_description"
                value={formData.issue_description}
                onChange={handleChange}
                onFocus={() => setFocusedInput('issue_description')}
                onBlur={() => setFocusedInput(null)}
                placeholder="Describe the issue in detail..."
                rows={4}
                style={getInputStyle('issue_description', !!errors.issue_description)}
              />
              {errors.issue_description && <span style={styles.fieldError}>{errors.issue_description}</span>}
            </div>

            <div style={styles.formActions}>
              <button
                type="submit"
                style={
                  loading
                    ? { ...styles.btnPrimary, background: '#A8CDB5', cursor: 'not-allowed', boxShadow: 'none' }
                    : hoveredBtn === 'submit'
                      ? { ...styles.btnPrimary, background: '#5C9470' }
                      : styles.btnPrimary
                }
                disabled={loading}
                onMouseEnter={() => setHoveredBtn('submit')}
                onMouseLeave={() => setHoveredBtn(null)}
              >
                {loading ? "Submitting..." : isEditing ? "Update Job" : "Create Job"}
              </button>
              <button
                type="button"
                style={hoveredBtn === 'cancel' ? { ...styles.btnSecondary, background: '#EAF4EE', borderColor: '#7AAE8A' } : styles.btnSecondary}
                onClick={handleCancelEdit}
                onMouseEnter={() => setHoveredBtn('cancel')}
                onMouseLeave={() => setHoveredBtn(null)}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>
      {isFormOpen && <div style={styles.sidebarOverlay} onClick={() => setIsFormOpen(false)}></div>}
    </div>
  );
}

const styles = {
  jobsPage: {
    fontFamily: "'Inter', sans-serif",
    background: "#EEF4F1",
    height: "100%",
    maxHeight: "100%",
    padding: "10px 14px",
    color: "#1F2933",
    display: "flex",
    flexDirection: "column",
    boxSizing: "border-box",
    overflow: "hidden",
  } as React.CSSProperties,
  popupOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(31, 41, 51, 0.4)",
    zIndex: 2000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,
  successPopup: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: "32px",
    maxWidth: "380px",
    width: "90%",
    textAlign: "center",
    boxShadow: "0 20px 50px rgba(47, 79, 62, 0.15)",
  } as React.CSSProperties,
  successIcon: {
    width: "52px",
    height: "52px",
    background: "#DDEEE5",
    color: "#2F4F3E",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "24px",
    fontWeight: 800,
    margin: "0 auto 14px",
  } as React.CSSProperties,
  jobIdCell: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,
  jobIdBox: {
    background: "#F6FAF8",
    borderRadius: "6px",
    padding: "6px 14px",
    fontSize: "13px",
    color: "#2F4F3E",
    marginBottom: "10px",
    display: "inline-block",
    border: "1px solid #E3ECE7",
  } as React.CSSProperties,
  popupCloseBtn: {
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    padding: "10px 28px",
    borderRadius: "8px",
    fontWeight: 700,
    fontSize: "13px",
    cursor: "pointer",
    transition: "background .2s",
  } as React.CSSProperties,
  mainContentRow: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    overflow: "hidden",
    boxSizing: "border-box",
  } as React.CSSProperties,
  contentCard: {
    background: "#FFFFFF",
    borderRadius: "12px",
    padding: "8px 16px",
    boxShadow: "0 1px 4px rgba(47, 79, 62, 0.07)",
    border: "1px solid #E3ECE7",
    display: "flex",
    flexDirection: "column",
    flex: 1,
    overflow: "hidden",
    boxSizing: "border-box",
  } as React.CSSProperties,
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "8px",
    marginBottom: "6px",
    paddingBottom: "6px",
    borderBottom: "1px solid #E3ECE7",
  } as React.CSSProperties,
  cardSubtitle: {
    fontSize: "12px",
    color: "#6B7280",
    margin: "1px 0 0 0",
  } as React.CSSProperties,
  headerActionsRow: {
    display: "flex",
    gap: "8px",
  } as React.CSSProperties,
  refreshIconBtn: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    color: "#2F4F3E",
    padding: "7px 14px",
    borderRadius: "8px",
    fontWeight: 600,
    fontSize: "12px",
    cursor: "pointer",
    transition: "all .2s",
    boxShadow: "0 1px 3px rgba(47,79,62,.06)",
  } as React.CSSProperties,
  addJobBtn: {
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    padding: "7px 16px",
    borderRadius: "8px",
    fontWeight: 700,
    fontSize: "12px",
    cursor: "pointer",
    transition: "background .2s",
    boxShadow: "0 2px 6px rgba(122, 174, 138, 0.3)",
  } as React.CSSProperties,
  filtersRow: {
    display: "grid",
    gridTemplateColumns: "2fr 1fr 1fr 1fr",
    gap: "8px",
    marginBottom: "4px",
  } as React.CSSProperties,
  filterGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  } as React.CSSProperties,
  filterLabel: {
    fontSize: "10px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".05em",
  } as React.CSSProperties,
  filterInput: {
    padding: "5px 8px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "12px",
    color: "#1F2933",
    outline: "none",
    transition: "border-color .2s",
    background: "#FFFFFF",
  } as React.CSSProperties,
  filterInputFocus: {
    borderColor: "#7AAE8A",
    boxShadow: "0 0 0 2px rgba(122,174,138,.12)",
  } as React.CSSProperties,
  resultsCount: {
    fontSize: "11px",
    color: "#6B7280",
    fontWeight: 500,
    marginBottom: "4px",
  } as React.CSSProperties,
  tableContainer: {
    overflowX: "hidden",
    overflowY: "hidden",
    flex: 1,
    minHeight: 0,
    boxSizing: "border-box",
  } as React.CSSProperties,
  dashboardTable: {
    width: "100%",
    borderCollapse: "collapse",
    tableLayout: "fixed",
  } as React.CSSProperties,
  th: {
    background: "#F6FAF8",
    padding: "0 10px",
    height: "32px",
    textAlign: "left",
    fontSize: "9.5px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    borderBottom: "1px solid #E3ECE7",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  } as React.CSSProperties,
  td: {
    padding: "4px 10px",
    fontSize: "11.5px",
    color: "#1F2933",
    borderBottom: "1px solid #F0F6F2",
    verticalAlign: "middle",
  } as React.CSSProperties,
  jobIdCell: {
    fontWeight: 700,
    color: "#5C9470",
  } as React.CSSProperties,
  customerCell: {
    fontWeight: 600,
    color: "#2F4F3E",
  } as React.CSSProperties,
  issueSub: {
    display: "block",
    fontSize: "11.5px",
    color: "#6B7280",
    fontWeight: 400,
    marginTop: "2px",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  } as React.CSSProperties,
  viewJobModal: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: 0,
    maxWidth: "460px",
    width: "94%",
    boxShadow: "0 20px 50px rgba(47,79,62,.18)",
    overflow: "hidden",
  } as React.CSSProperties,
  viewModalHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "18px 22px 14px",
    borderBottom: "1px solid #E3ECE7",
    background: "#F6FAF8",
  } as React.CSSProperties,
  viewModalHeaderTitle: {
    fontSize: "15px",
    fontWeight: 700,
    color: "#2F4F3E",
    margin: 0,
  } as React.CSSProperties,
  viewModalBody: {
    padding: "18px 22px 22px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  } as React.CSSProperties,
  viewDetailRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
  } as React.CSSProperties,
  viewLabel: {
    minWidth: "110px",
    fontSize: "11px",
    fontWeight: 600,
    color: "#9CA3AF",
    textTransform: "uppercase",
    letterSpacing: ".03em",
    paddingTop: "2px",
  } as React.CSSProperties,
  viewValue: {
    fontSize: "13px",
    color: "#1F2937",
    fontWeight: 500,
    flex: 1,
  } as React.CSSProperties,
  jobFormSidebar: {
    position: "fixed",
    top: 0,
    width: "420px",
    height: "100vh",
    background: "#FFFFFF",
    zIndex: 2000,
    boxShadow: "-4px 0 24px rgba(47,79,62,.1)",
    display: "flex",
    flexDirection: "column",
    transition: "right .3s cubic-bezier(0.4, 0, 0.2, 1)",
  } as React.CSSProperties,
  sidebarHeader: {
    padding: "20px 24px",
    borderBottom: "1px solid #E3ECE7",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "#F8FBF9",
  } as React.CSSProperties,
  closeSidebar: {
    background: "none",
    border: "none",
    fontSize: "22px",
    color: "#6B7280",
    cursor: "pointer",
    width: "32px",
    height: "32px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background .15s",
  } as React.CSSProperties,
  sidebarBody: {
    flex: 1,
    overflowY: "auto",
    padding: "24px",
  } as React.CSSProperties,
  sidebarOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(31,41,51,.35)",
    zIndex: 1999,
    backdropFilter: "blur(2px)",
  } as React.CSSProperties,
  jobForm: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  } as React.CSSProperties,
  formGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  } as React.CSSProperties,
  formLabel: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#2F4F3E",
    marginBottom: "4px",
  } as React.CSSProperties,
  req: {
    color: "#D96C6C",
  } as React.CSSProperties,
  formInput: {
    padding: "9px 12px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "13px",
    fontFamily: "'Inter', sans-serif",
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    width: "100%",
    transition: "border-color .2s, box-shadow .2s",
  } as React.CSSProperties,
  formInputFocus: {
    borderColor: "#7AAE8A",
    boxShadow: "0 0 0 3px rgba(122, 174, 138, 0.15)",
  } as React.CSSProperties,
  inputError: {
    borderColor: "#D96C6C",
    boxShadow: "0 0 0 2px rgba(217,108,108,.1)",
  } as React.CSSProperties,
  fieldError: {
    fontSize: "11px",
    color: "#D96C6C",
    marginTop: "2px",
  } as React.CSSProperties,
  alertError: {
    background: "#FDF2F2",
    color: "#9B3A3A",
    border: "1px solid #F5C6C6",
    borderRadius: "8px",
    padding: "10px 14px",
    fontSize: "12px",
    fontWeight: 500,
    marginBottom: "14px",
  } as React.CSSProperties,
  formActions: {
    display: "flex",
    gap: "10px",
    marginTop: "10px",
  } as React.CSSProperties,
  btnPrimary: {
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    padding: "10px 20px",
    borderRadius: "8px",
    fontWeight: 700,
    fontSize: "13px",
    cursor: "pointer",
    transition: "background .2s",
    flex: 1,
    boxShadow: "0 2px 6px rgba(122,174,138,.25)",
  } as React.CSSProperties,
  btnSecondary: {
    background: "#F6FAF8",
    color: "#2F4F3E",
    border: "1.5px solid #E3ECE7",
    padding: "10px 16px",
    borderRadius: "8px",
    fontWeight: 600,
    fontSize: "13px",
    cursor: "pointer",
    transition: "all .2s",
  } as React.CSSProperties,
  jobsPagination: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 0 0 0",
    borderTop: "1px solid #E3ECE7",
    flexWrap: "wrap",
    gap: "6px",
    marginTop: "6px",
  } as React.CSSProperties,
  jobsPageInfo: {
    fontSize: "11px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,
  jobsPageControls: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,
  jobsPageBtn: {
    padding: "3px 8px",
    background: "#FFFFFF",
    border: "1.5px solid #E3ECE7",
    borderRadius: "6px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#2F4F3E",
    cursor: "pointer",
    transition: "all .2s",
  } as React.CSSProperties,
  jobsPageNumbers: {
    display: "flex",
    gap: "4px",
  } as React.CSSProperties,
  jobsPageNum: {
    width: "22px",
    height: "22px",
    borderRadius: "6px",
    border: "1.5px solid #E3ECE7",
    background: "#FFFFFF",
    fontSize: "10px",
    fontWeight: 600,
    color: "#6B7280",
    cursor: "pointer",
    padding: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all .2s",
  } as React.CSSProperties,
  iconActionBtn: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "28px",
    height: "28px",
    border: "none",
    background: "none",
    padding: 0,
    cursor: "pointer",
    transition: "transform .15s, opacity .15s",
    outline: "none",
  } as React.CSSProperties,
};

export default JobCreationForm;
