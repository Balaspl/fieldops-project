import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import api from "../services/api";
import {
  Eye,
  Pencil,
  Trash2,
  ExternalLink,
  Copy,
  Check,
  Loader2,
  CheckCircle2,
  Star,
} from "lucide-react";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import EmptyState from "../components/ui/EmptyState";
import JobStatusTimeline from "../components/customer-tracking/JobStatusTimeline";
import useAuthStore from "../store/authStore";
import {
  getJobClosure,
  getJobs,
  getTechnicians,
  getJobAuditHistory,
  getJobInvoice,
  getJobInvoicePdf,
  getJobPaymentStatus,
  getJobCustomerFeedback,
  type CustomerFeedbackResponse,
  type JobAuditHistoryResponse,
  type JobAuditHistorySource,
  type JobInvoiceResponse,
  type JobPaymentStatusResponse,
} from "../services/planningService";
import { JobClosureModal } from "../components/jobs/JobClosureModal";

const JOBS_PAGE_SIZE = 25;
const AUDIT_HISTORY_PAGE_SIZE = 25;

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

type JobFilterKey =
  | "status"
  | "priority"
  | "service_type"
  | "sla"
  | "technician"
  | "location";

interface JobListFilters {
  status: string;
  priority: string;
  service_type: string;
  sla: string;
  technician: string;
  location: string;
}

const DEFAULT_JOB_LIST_FILTERS: JobListFilters = {
  status: "ALL",
  priority: "ALL",
  service_type: "ALL",
  sla: "ALL",
  technician: "ALL",
  location: "",
};

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

interface TechnicianOption {
  technician_id: number;
  technician_name: string;
}

interface PopupState {
  show: boolean;
  title: string;
  message: string;
  jobId?: string;
}

const PRIORITY_FILTER_OPTIONS = [
  { label: "All Priorities", value: "ALL" },
  { label: "Critical", value: "CRITICAL" },
  { label: "High", value: "HIGH" },
  { label: "Medium", value: "MEDIUM" },
  { label: "Low", value: "LOW" },
];

const priorities = PRIORITY_FILTER_OPTIONS.filter(
  (priority) => priority.value !== "ALL"
);

const serviceTypes = [
  { label: "HVAC Repair", value: "HVAC_REPAIR" },
  { label: "Electrical Service", value: "ELECTRICAL_SERVICE" },
  { label: "Plumbing Service", value: "PLUMBING_SERVICE" },
  { label: "Network Support", value: "NETWORK_SUPPORT" },
  { label: "General Maintenance", value: "GENERAL_MAINTENANCE" },
];

const priorityMap: Record<string, string> = {
  P1: "CRITICAL",
  P2: "HIGH",
  P3: "MEDIUM",
  P4: "LOW",
  P5: "LOW",
};

function normalizeP(priority: string): string {
  const up = (priority || "").toUpperCase();
  return priorityMap[up] || up;
}

const formatServiceType = (type: string) => {
  if (!type) {
    return "";
  }

  return type
    .replace(/_/g, " ")
    .toLowerCase()
    .split(" ")
    .map((word) => {
      const uppercaseAcronyms = [
        "hvac",
        "cctv",
        "ac",
        "sla",
        "ip",
        "it",
      ];

      if (uppercaseAcronyms.includes(word)) {
        return word.toUpperCase();
      }

      return (
        word.charAt(0).toUpperCase() +
        word.slice(1)
      );
    })
    .join(" ");
};

const getPriorityStyle = (
  priority: string
): React.CSSProperties => {
  const p = (priority || "").toUpperCase();

  const base: React.CSSProperties = {
    fontSize: "9px",
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: "20px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    display: "inline-block",
  };

  if (p === "CRITICAL" || p === "P1") {
    return {
      ...base,
      background: "#FAE5E5",
      color: "#7A2020",
    };
  }

  if (p === "HIGH" || p === "P2") {
    return {
      ...base,
      background: "#FEF0D6",
      color: "#7A5120",
    };
  }

  if (p === "MEDIUM" || p === "P3") {
    return {
      ...base,
      background: "#FDFBDC",
      color: "#706020",
    };
  }

  if (p === "LOW" || p === "P4" || p === "P5") {
    return {
      ...base,
      background: "#DDEEE5",
      color: "#2F4F3E",
    };
  }

  return {
    ...base,
    background: "#F0F4F2",
    color: "#6B7280",
  };
};

const CopyJobIdButton = ({
  jobId,
}: {
  jobId: string | number;
}) => {
  const [copied, setCopied] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleCopy = (
    event: React.MouseEvent
  ) => {
    event.stopPropagation();

    navigator.clipboard
      .writeText(String(jobId))
      .then(() => {
        setCopied(true);

        window.setTimeout(() => {
          setCopied(false);
        }, 1000);
      })
      .catch(() => {
        setCopied(false);
      });
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      onMouseEnter={() =>
        setIsHovered(true)
      }
      onMouseLeave={() =>
        setIsHovered(false)
      }
      title={
        copied
          ? "Copied!"
          : "Copy Job ID"
      }
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
        backgroundColor: isHovered
          ? "#DDEEE5"
          : "transparent",
        color: copied
          ? "#10B981"
          : isHovered
            ? "#2F4F3E"
            : "#9CA3AF",
      }}
    >
      {copied ? (
        <Check size={12} />
      ) : (
        <Copy size={12} />
      )}
    </button>
  );
};

function JobCreationForm() {
  const { user } = useAuthStore();

  const userRole = (
    user?.role ||
    localStorage.getItem("user_role") ||
    ""
  ).toLowerCase();

  const isTechnician =
    userRole === "technician";

  const [formData, setFormData] =
    useState<JobFormData>(
      initialFormData
    );

  const [errors, setErrors] =
    useState<
      Partial<
        Record<
          keyof JobFormData,
          string
        >
      >
    >({});

  const [apiError, setApiError] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [jobsLoading, setJobsLoading] =
    useState(false);

  const [hoveredBtn, setHoveredBtn] =
    useState<string | null>(null);

  const [hoveredRow, setHoveredRow] =
    useState<
      string | number | null
    >(null);

  const [focusedInput, setFocusedInput] =
    useState<string | null>(null);

  const [jobs, setJobs] =
    useState<Job[]>([]);

  const [technicians, setTechnicians] =
    useState<TechnicianOption[]>([]);

  const [techniciansLoading, setTechniciansLoading] =
    useState(false);

  const [techniciansError, setTechniciansError] =
    useState("");

  const [searchTerm, setSearchTerm] =
    useState("");

  const [debSearchTerm, setDebSearchTerm] =
    useState("");

  const [jobsError, setJobsError] =
    useState("");

  const jobsRequestIdRef =
    useRef(0);

  const [jobFilters, setJobFilters] =
    useState<JobListFilters>(
      DEFAULT_JOB_LIST_FILTERS
    );

  const [jobsPage, setJobsPage] =
    useState(1);

  const [totalJobsCount, setTotalJobsCount] =
    useState(0);

  const [isEditing, setIsEditing] =
    useState(false);

  const [editingJobId, setEditingJobId] =
    useState<
      string | number | null
    >(null);

  const [popup, setPopup] =
    useState<PopupState>({
      show: false,
      title: "",
      message: "",
      jobId: "",
    });

  const [isFormOpen, setIsFormOpen] =
    useState(false);

  const [viewJob, setViewJob] =
    useState<Job | null>(null);

  const [isClosureModalOpen, setIsClosureModalOpen] =
    useState(false);

  const [closureDetails, setClosureDetails] =
    useState<any>(null);

  const [closureDetailsLoading, setClosureDetailsLoading] =
    useState(false);

  const [closureDetailsError, setClosureDetailsError] =
    useState("");

  const [failedDocumentImages, setFailedDocumentImages] =
    useState<Record<string, boolean>>({});

  const [timelineRefreshKey, setTimelineRefreshKey] =
    useState(0);

  const [auditHistory, setAuditHistory] =
    useState<JobAuditHistoryResponse | null>(
      null
    );

  const [auditHistoryLoading, setAuditHistoryLoading] =
    useState(false);

  const [auditHistoryError, setAuditHistoryError] =
    useState("");

  const [auditHistoryPage, setAuditHistoryPage] =
    useState(1);

  const [auditHistoryEventType, setAuditHistoryEventType] = useState("");
  const [auditHistorySource, setAuditHistorySource] =
    useState<JobAuditHistorySource | "">("");

  const [auditHistoryExportLoading, setAuditHistoryExportLoading] =
    useState(false);
  const [auditHistoryExportError, setAuditHistoryExportError] =
    useState("");

  const auditHistoryExportInProgressRef =
    useRef(false);

  const auditHistoryRequestIdRef =
    useRef(0);

  const closureDetailsRequestIdRef =
    useRef(0);

  const [invoiceDetails, setInvoiceDetails] =
    useState<JobInvoiceResponse | null>(
      null
    );

  const [invoiceDetailsLoading, setInvoiceDetailsLoading] =
    useState(false);

  const [invoiceDetailsError, setInvoiceDetailsError] =
    useState("");

  const invoiceDetailsRequestIdRef =
    useRef(0);

  const [invoiceDownloadLoading, setInvoiceDownloadLoading] =
    useState(false);

  const [invoiceDownloadError, setInvoiceDownloadError] =
    useState("");

  const [paymentStatus, setPaymentStatus] =
    useState<JobPaymentStatusResponse | null>(
      null
    );

  const [paymentStatusLoading, setPaymentStatusLoading] =
    useState(false);

  const [paymentStatusError, setPaymentStatusError] =
    useState("");

  const paymentStatusRequestIdRef =
    useRef(0);

  const [customerFeedbackDetails, setCustomerFeedbackDetails] =
    useState<CustomerFeedbackResponse | null>(
      null
    );

  const [customerFeedbackLoading, setCustomerFeedbackLoading] =
    useState(false);

  const [customerFeedbackError, setCustomerFeedbackError] =
    useState("");

  const customerFeedbackRequestIdRef =
    useRef(0);

  const [selectedImage, setSelectedImage] =
    useState<string | null>(null);

  const [selectedImageName, setSelectedImageName] =
    useState("");

  const getInputStyle = (
    name: string,
    hasError = false
  ) => {
    let style = {
      ...styles.formInput,
    };

    if (hasError) {
      style = {
        ...style,
        ...styles.inputError,
      };
    } else if (
      focusedInput === name
    ) {
      style = {
        ...style,
        ...styles.formInputFocus,
      };
    }

    return style;
  };

  const updateJobFilter = (
    key: JobFilterKey,
    value: string
  ) => {
    setJobFilters((previous) => ({
      ...previous,
      [key]: value,
    }));
  };

  const clearJobFilters = () => {
    setJobFilters({
      ...DEFAULT_JOB_LIST_FILTERS,
    });
  };

  useEffect(() => {
    const timer =
      window.setTimeout(() => {
        setDebSearchTerm(
          searchTerm.trim()
        );
      }, 300);

    return () => {
      window.clearTimeout(timer);
    };
  }, [searchTerm]);

  useEffect(() => {
    setJobsPage(1);
  }, [
    debSearchTerm,
    jobFilters,
  ]);

  const getFormServiceTypes =
    () => {
      const list = [
        ...serviceTypes,
      ];

      if (formData.service_type) {
        const seenNormal =
          new Set<string>(
            list.map((item) =>
              (item.value || "")
                .toUpperCase()
                .replace(/_/g, " ")
                .replace(/\s+/g, " ")
                .trim()
            )
          );

        const value =
          formData.service_type;

        const normalized =
          value
            .toUpperCase()
            .replace(/_/g, " ")
            .replace(/\s+/g, " ")
            .trim();

        if (
          !seenNormal.has(
            normalized
          )
        ) {
          const label =
            value
              .replace(/_/g, " ")
              .replace(
                /\b\w/g,
                (char) =>
                  char.toUpperCase()
              );

          list.push({
            label,
            value,
          });
        }
      }

      return list;
    };

  const getImageExtension = (
    image: string
  ) => {
    const dataUrlMatch =
      image.match(
        /^data:image\/([a-zA-Z0-9.+-]+);base64,/i
      );

    if (dataUrlMatch?.[1]) {
      const extension =
        dataUrlMatch[1].toLowerCase();

      return extension === "jpeg"
        ? "jpg"
        : extension;
    }

    const cleanUrl =
      image
        .split("?")[0]
        .split("#")[0];

    const fileName =
      cleanUrl.split("/").pop() ||
      "";

    const extensionMatch =
      fileName.match(
        /\.([a-zA-Z0-9]+)$/
      );

    return (
      extensionMatch?.[1]?.toLowerCase() ||
      "jpg"
    );
  };

  const getImageName = (
    image: string,
    type: "before" | "after",
    index: number
  ) => {
    const cleanUrl =
      image
        .split("?")[0]
        .split("#")[0];

    const fileName =
      cleanUrl.split("/").pop() ||
      "";

    if (
      fileName &&
      !fileName.startsWith("data:") &&
      /\.[a-zA-Z0-9]+$/.test(
        fileName
      )
    ) {
      return fileName;
    }

    return `${type}-image-${index + 1}.${getImageExtension(
      image
    )}`;
  };

  const openImagePreview = (
    image: string,
    type: "before" | "after",
    index: number
  ) => {
    setSelectedImage(image);
    setSelectedImageName(
      getImageName(
        image,
        type,
        index
      )
    );
  };

  const markDocumentImageUnavailable =
    (imageKey: string) => {
      setFailedDocumentImages(
        (previous) => ({
          ...previous,
          [imageKey]: true,
        })
      );
    };

  useEffect(() => {
    const requestId =
      ++closureDetailsRequestIdRef.current;

    setFailedDocumentImages({});
    setClosureDetailsError("");

    if (
      viewJob?.status?.toUpperCase() ===
      "COMPLETED"
    ) {
      setClosureDetailsLoading(
        true
      );
      setClosureDetails(null);

      getJobClosure(viewJob.id)
        .then((data) => {
          if (
            requestId !==
            closureDetailsRequestIdRef.current
          ) {
            return;
          }

          setClosureDetails(data);
        })
        .catch((error: any) => {
          if (
            requestId !==
            closureDetailsRequestIdRef.current
          ) {
            return;
          }

          setClosureDetails(
            null
          );

          const status =
            error?.response?.status;

          if (status === 403) {
            setClosureDetailsError(
              "You are not authorized to view completion report and documents for this job."
            );
          } else if (
            status === 404
          ) {
            setClosureDetailsError(
              "Completion report and documents are not available for this job."
            );
          } else {
            setClosureDetailsError(
              "Completion report and documents are temporarily unavailable. Please try again."
            );
          }
        })
        .finally(() => {
          if (
            requestId ===
            closureDetailsRequestIdRef.current
          ) {
            setClosureDetailsLoading(
              false
            );
          }
        });
    } else {
      setClosureDetails(
        null
      );
      setClosureDetailsLoading(
        false
      );
    }
  }, [viewJob]);

  useEffect(() => {
    const requestId =
      ++invoiceDetailsRequestIdRef.current;

    if (
      !viewJob ||
      viewJob.status?.toUpperCase() !==
        "COMPLETED"
    ) {
      setInvoiceDetails(null);
      setInvoiceDetailsError("");
      setInvoiceDetailsLoading(
        false
      );
      setInvoiceDownloadError("");
      return;
    }

    setInvoiceDetails(null);
    setInvoiceDetailsError("");
    setInvoiceDownloadError("");
    setInvoiceDetailsLoading(
      true
    );

    getJobInvoice(viewJob.id)
      .then((response) => {
        if (
          requestId !==
          invoiceDetailsRequestIdRef.current
        ) {
          return;
        }

        setInvoiceDetails(
          response
        );
      })
      .catch((error: any) => {
        if (
          requestId !==
          invoiceDetailsRequestIdRef.current
        ) {
          return;
        }

        setInvoiceDetails(null);

        const status =
          error?.response?.status;

        if (status === 403) {
          setInvoiceDetailsError(
            "You are not authorized to view the invoice for this job."
          );
        } else if (
          status === 404
        ) {
          setInvoiceDetailsError(
            "Invoice data is not available for this job."
          );
        } else {
          setInvoiceDetailsError(
            "Invoice data is temporarily unavailable. Please try again."
          );
        }
      })
      .finally(() => {
        if (
          requestId ===
          invoiceDetailsRequestIdRef.current
        ) {
          setInvoiceDetailsLoading(
            false
          );
        }
      });
  }, [viewJob]);

  useEffect(() => {
    const requestId =
      ++paymentStatusRequestIdRef.current;

    if (
      !viewJob ||
      viewJob.status?.toUpperCase() !==
        "COMPLETED"
    ) {
      setPaymentStatus(null);
      setPaymentStatusError("");
      setPaymentStatusLoading(
        false
      );
      return;
    }

    setPaymentStatus(null);
    setPaymentStatusError("");
    setPaymentStatusLoading(
      true
    );

    getJobPaymentStatus(viewJob.id)
      .then((response) => {
        if (
          requestId !==
          paymentStatusRequestIdRef.current
        ) {
          return;
        }

        setPaymentStatus(
          response
        );
      })
      .catch((error: any) => {
        if (
          requestId !==
          paymentStatusRequestIdRef.current
        ) {
          return;
        }

        setPaymentStatus(null);

        const status =
          error?.response?.status;

        if (status === 403) {
          setPaymentStatusError(
            "You are not authorized to view the payment status for this job."
          );
        } else if (
          status === 404
        ) {
          setPaymentStatusError(
            "Payment status is not available for this job."
          );
        } else {
          setPaymentStatusError(
            "Payment status is temporarily unavailable. Please try again."
          );
        }
      })
      .finally(() => {
        if (
          requestId ===
          paymentStatusRequestIdRef.current
        ) {
          setPaymentStatusLoading(
            false
          );
        }
      });
  }, [viewJob]);

  useEffect(() => {
    const requestId =
      ++customerFeedbackRequestIdRef.current;

    if (
      !viewJob ||
      isTechnician ||
      viewJob.status?.toUpperCase() !==
        "COMPLETED"
    ) {
      setCustomerFeedbackDetails(
        null
      );
      setCustomerFeedbackError("");
      setCustomerFeedbackLoading(
        false
      );
      return;
    }

    setCustomerFeedbackDetails(
      null
    );
    setCustomerFeedbackError("");
    setCustomerFeedbackLoading(
      true
    );

    getJobCustomerFeedback(viewJob.id)
      .then((response) => {
        if (
          requestId !==
          customerFeedbackRequestIdRef.current
        ) {
          return;
        }

        setCustomerFeedbackDetails(
          response
        );
      })
      .catch((error: any) => {
        if (
          requestId !==
          customerFeedbackRequestIdRef.current
        ) {
          return;
        }

        setCustomerFeedbackDetails(
          null
        );

        const status =
          error?.response?.status;

        if (status === 403) {
          setCustomerFeedbackError(
            "You are not authorized to view customer feedback for this job."
          );
        } else if (
          status === 404
        ) {
          setCustomerFeedbackError(
            "Customer feedback is not available for this job."
          );
        } else {
          setCustomerFeedbackError(
            "Customer feedback is temporarily unavailable. Please try again."
          );
        }
      })
      .finally(() => {
        if (
          requestId ===
          customerFeedbackRequestIdRef.current
        ) {
          setCustomerFeedbackLoading(
            false
          );
        }
      });
  }, [
    viewJob,
    isTechnician,
  ]);

  const loadAuditHistory = useCallback(
    async (jobId: string | number, requestedPage: number) => {
      if (requestedPage < 1) {
        return;
      }

      const requestId = ++auditHistoryRequestIdRef.current;

      setAuditHistoryLoading(true);
      setAuditHistoryError("");

      try {
        const response = await getJobAuditHistory(jobId, {
          event_type: auditHistoryEventType.trim() || undefined,
          source: auditHistorySource || undefined,
          page: requestedPage,
          page_size: AUDIT_HISTORY_PAGE_SIZE,
        });

        // Ignore stale responses when a newer request has already started.
        if (requestId !== auditHistoryRequestIdRef.current) {
          return;
        }

        setAuditHistory(response);
        setAuditHistoryPage(response.page);
      } catch (error: any) {
        if (requestId !== auditHistoryRequestIdRef.current) {
          return;
        }

        const status = error?.response?.status;

        if (status === 403) {
          setAuditHistoryError(
            "You are not authorized to view this audit history."
          );
        } else if (status === 404) {
          setAuditHistoryError(
            "Job audit history was not found."
          );
        } else if (status === 400) {
          setAuditHistoryError(
            "The selected audit history filter is invalid."
          );
        } else {
          setAuditHistoryError(
            "Failed to load job audit history. Please try again."
          );
        }
      } finally {
        if (requestId === auditHistoryRequestIdRef.current) {
          setAuditHistoryLoading(false);
        }
      }
    },
    [auditHistoryEventType, auditHistorySource]
  );


  /*
   * Task 12 - Audit History Export
   *
   * Export only the currently loaded, backend-authorized and filtered
   * audit-history records. No client-side records outside the authoritative
   * response are introduced.
   */
  const handleExportAuditHistory = useCallback(() => {
    if (
      auditHistoryExportLoading ||
      auditHistoryExportInProgressRef.current ||
      !auditHistory ||
      auditHistory.events.length === 0
    ) {
      return;
    }

    auditHistoryExportInProgressRef.current = true;
    setAuditHistoryExportLoading(true);
    setAuditHistoryExportError("");

    try {
      const escapeCsvValue = (value: unknown): string => {
        const text = value === null || value === undefined
          ? ""
          : String(value);

        return `"${text.replace(/"/g, '""')}"`;
      };

      const headers = [
        "Job ID",
        "Event Type",
        "Category",
        "Title",
        "Description",
        "Timestamp",
        "Actor",
        "Actor Role",
        "Source",
        "From Status",
        "To Status",
        "Current",
      ];

      const rows = auditHistory.events.map((event) => [
        event.job_id,
        event.event_type,
        event.event_category,
        event.title,
        event.description,
        event.timestamp
          ? new Date(event.timestamp).toLocaleString()
          : "",
        event.actor_name,
        event.actor_role,
        event.source,
        event.from_status ?? "",
        event.to_status ?? "",
        event.is_current ? "Yes" : "No",
      ]);

      const csv = [
        headers.map(escapeCsvValue).join(","),
        ...rows.map((row) =>
          row.map(escapeCsvValue).join(",")
        ),
      ].join("\r\n");

      const blob = new Blob(
        ["\uFEFF", csv],
        {
          type: "text/csv;charset=utf-8;",
        }
      );

      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = `job-${auditHistory.job_id}-audit-history-page-${auditHistoryPage}.csv`;

      document.body.appendChild(link);
      link.click();
      link.remove();

      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error(
        "[JobsPage] Failed to export audit history:",
        error
      );

      setAuditHistoryExportError(
        "Failed to export audit history. Please try again."
      );
    } finally {
      auditHistoryExportInProgressRef.current = false;
      setAuditHistoryExportLoading(false);
    }
  }, [
    auditHistory,
    auditHistoryPage,
    auditHistoryExportLoading,
  ]);


  useEffect(() => {
    if (!viewJob) {
      auditHistoryRequestIdRef.current += 1;

      setAuditHistory(null);
      setAuditHistoryPage(1);
      setAuditHistoryError("");
      setAuditHistoryExportError("");
      setAuditHistoryLoading(false);
      return;
    }

    setAuditHistory(null);
    setAuditHistoryPage(1);
    setAuditHistoryError("");
    setAuditHistoryExportError("");

    void loadAuditHistory(viewJob.id, 1);
  }, [
    viewJob,
    auditHistoryEventType,
    auditHistorySource,
    loadAuditHistory,
  ]);

  const handleDownloadInvoice =
    async () => {
      if (
        !viewJob ||
        invoiceDownloadLoading
      ) {
        return;
      }

      setInvoiceDownloadLoading(
        true
      );
      setInvoiceDownloadError("");

      try {
        const blob =
          await getJobInvoicePdf(
            viewJob.id
          );

        if (
          !blob ||
          blob.size === 0
        ) {
          throw new Error(
            "Invoice PDF is empty"
          );
        }

        const url =
          window.URL.createObjectURL(
            blob
          );

        const link =
          document.createElement(
            "a"
          );

        link.href = url;
        link.download = `invoice-job-${viewJob.id}.pdf`;

        document.body.appendChild(
          link
        );

        link.click();
        link.remove();

        window.setTimeout(
          () =>
            window.URL.revokeObjectURL(
              url
            ),
          1000
        );
      } catch (error: any) {
        const status =
          error?.response?.status;

        if (status === 403) {
          setInvoiceDownloadError(
            "You are not authorized to download the invoice PDF."
          );
        } else if (
          status === 404
        ) {
          setInvoiceDownloadError(
            "Invoice PDF is not available for this job."
          );
        } else {
          setInvoiceDownloadError(
            "Failed to download the invoice PDF. Please try again."
          );
        }
      } finally {
        setInvoiceDownloadLoading(
          false
        );
      }
    };

  const fetchServiceTypes =
    async () => {
      try {
        await api.get(
          "/jobs/service-types"
        );
      } catch (error) {
        console.error(
          "Failed to refresh service types:",
          error
        );
      }
    };

  const fetchJobs =
    useCallback(
      async () => {
        const requestId =
          ++jobsRequestIdRef.current;

        setJobsLoading(true);
        setJobsError("");

        try {
          const response =
            await getJobs({
              page: jobsPage,
              limit: JOBS_PAGE_SIZE,
              search:
                debSearchTerm ||
                undefined,
              status:
                jobFilters.status !==
                "ALL"
                  ? jobFilters.status
                  : undefined,
              priority:
                jobFilters.priority !==
                "ALL"
                  ? jobFilters.priority
                  : undefined,
              service_type:
                jobFilters.service_type !==
                "ALL"
                  ? jobFilters.service_type
                  : undefined,
              sla:
                jobFilters.sla !==
                "ALL"
                  ? jobFilters.sla
                  : undefined,
              location:
                jobFilters.location.trim() ||
                undefined,
              technician_id:
                jobFilters.technician !==
                "ALL"
                  ? Number(
                      jobFilters.technician
                    )
                  : undefined,
            });

          if (
            requestId !==
            jobsRequestIdRef.current
          ) {
            return;
          }

          setJobs(
            response.data ?? []
          );

          const totalHeader =
            response.headers[
              "x-total-count"
            ] ??
            response.headers[
              "X-Total-Count"
            ];

          const parsedTotal =
            totalHeader
              ? Number.parseInt(
                  String(
                    totalHeader
                  ),
                  10
                )
              : NaN;

          setTotalJobsCount(
            Number.isFinite(
              parsedTotal
            )
              ? parsedTotal
              : (
                  response.data ?? []
                ).length
          );
        } catch (error) {
          if (
            requestId !==
            jobsRequestIdRef.current
          ) {
            return;
          }

          console.error(
            "Failed to fetch jobs:",
            error
          );

          setJobs([]);
          setTotalJobsCount(0);
          setJobsError(
            "Unable to load jobs. Please try again."
          );
        } finally {
          if (
            requestId ===
            jobsRequestIdRef.current
          ) {
            setJobsLoading(false);
          }
        }
      },
      [
        jobsPage,
        debSearchTerm,
        jobFilters,
      ]
    );

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    const loadTechnicians =
      async () => {
        setTechniciansLoading(
          true
        );
        setTechniciansError("");

        try {
          const response =
            await getTechnicians();

          setTechnicians(
            response.data ?? []
          );
        } catch (error) {
          console.error(
            "Failed to fetch technicians:",
            error
          );

          setTechnicians([]);
          setTechniciansError(
            "Unable to load technicians."
          );
        } finally {
          setTechniciansLoading(
            false
          );
        }
      };

    void loadTechnicians();
  }, []);

  const validateForm = () => {
    const newErrors:
      Partial<
        Record<
          keyof JobFormData,
          string
        >
      > = {};

    if (
      !formData.customer_name.trim()
    ) {
      newErrors.customer_name =
        "Customer name is required";
    }

    if (
      !formData.location.trim()
    ) {
      newErrors.location =
        "Location is required";
    }

    if (
      !formData.issue_description.trim()
    ) {
      newErrors.issue_description =
        "Issue description is required";
    }

    if (!formData.priority) {
      newErrors.priority =
        "Priority is required";
    }

    if (!formData.service_type) {
      newErrors.service_type =
        "Service type is required";
    }

    if (
      !formData.contact_number.trim()
    ) {
      newErrors.contact_number =
        "Contact number is required";
    } else if (
      !/^[6-9]\d{9}$/.test(
        formData.contact_number
      )
    ) {
      newErrors.contact_number =
        "Enter a valid 10-digit Indian mobile number";
    }

    if (
      !formData.preferred_service_date
    ) {
      newErrors.preferred_service_date =
        "Preferred service date is required";
    }

    setErrors(newErrors);

    return (
      Object.keys(newErrors)
        .length === 0
    );
  };

  const resetForm = () => {
    setFormData(
      initialFormData
    );
    setErrors({});
    setIsEditing(false);
    setEditingJobId(null);
    setIsFormOpen(false);
  };

  const handleChange = (
    event: React.ChangeEvent<
      HTMLInputElement |
        HTMLSelectElement |
        HTMLTextAreaElement
    >
  ) => {
    const {
      name,
      value,
    } = event.target;

    setFormData((previous) => ({
      ...previous,
      [name]: value,
    }));

    setErrors((previous) => ({
      ...previous,
      [name]: "",
    }));

    setApiError("");
  };

  const handleEdit = (
    job: Job
  ) => {
    setIsEditing(true);
    setEditingJobId(job.id);
    setApiError("");

    let jobStatus =
      job.status ||
      "active";

    const statusLower =
      jobStatus
        .toLowerCase()
        .trim();

    if (
      statusLower ===
      "inprogress"
    ) {
      jobStatus =
        "in progress";
    } else if (
      statusLower ===
      "canceled"
    ) {
      jobStatus =
        "cancelled";
    }

    setFormData({
      customer_name:
        job.customer_name ||
        "",
      location:
        job.location || "",
      issue_description:
        job.issue_description ||
        "",
      priority:
        job.priority || "",
      service_type:
        job.service_type ||
        "",
      contact_number:
        job.contact_number ||
        "",
      preferred_service_date:
        job.preferred_service_date ||
        "",
      status:
        jobStatus,
      required_skill:
        job.required_skill ||
        "",
      tenant_id:
        (job as any)
          .tenant_id ||
        "tenant-1",
      sla_deadline:
        (job as any)
          .sla_deadline
          ? new Date(
              (job as any)
                .sla_deadline
            )
              .toISOString()
              .slice(
                0,
                16
              )
          : "",
      attempt_count:
        (job as any)
          .attempt_count !==
        undefined
          ? (
              job as any
            ).attempt_count
          : 0,
    });

    setIsFormOpen(true);
  };

  const handleCancelEdit =
    () => {
      resetForm();
      setApiError("");
    };

  const closePopup = () => {
    setPopup({
      show: false,
      title: "",
      message: "",
      jobId: "",
    });
  };

  const handleCreateNew =
    () => {
      setFormData(
        initialFormData
      );
      setErrors({});
      setIsEditing(false);
      setEditingJobId(null);
      setApiError("");
      setIsFormOpen(true);
    };

  const handleSubmit =
    async (
      event: React.FormEvent
    ) => {
      event.preventDefault();

      if (!validateForm()) {
        return;
      }

      try {
        setLoading(true);

        const payload = {
          ...formData,
          sla_deadline:
            formData.sla_deadline &&
            formData.sla_deadline.trim()
              ? formData.sla_deadline
              : null,
          required_skill:
            formData.required_skill &&
            formData.required_skill.trim()
              ? formData.required_skill
              : null,
          attempt_count:
            formData.attempt_count !==
            undefined
              ? Number(
                  formData.attempt_count
                )
              : 0,
        };

        if (
          isEditing &&
          editingJobId !== null
        ) {
          const response =
            await api.put(
              `/jobs/${editingJobId}`,
              payload
            );

          setPopup({
            show: true,
            title:
              "Job Updated Successfully",
            message:
              "The job details have been updated successfully.",
            jobId:
              response.data?.id ??
              editingJobId,
          });

          resetForm();

          void fetchJobs();
        } else {
          const response =
            await api.post(
              "/jobs",
              payload
            );

          setPopup({
            show: true,
            title:
              "Job Created Successfully",
            message:
              "Your job request has been submitted successfully.",
            jobId:
              response.data?.id ??
              "",
          });

          resetForm();

          setJobsPage(1);
          setSearchTerm("");
          setDebSearchTerm("");

          setJobFilters({
            status: "ALL",
            priority: "ALL",
            service_type:
              "ALL",
            sla: "ALL",
            technician:
              "ALL",
            location: "",
          });

          void fetchJobs();
        }

        void fetchServiceTypes();
      } catch (error: any) {
        console.error(
          error
        );

        let errorMsg =
          "Unable to save job. Please check backend API.";

        if (
          error.response?.data
        ) {
          const data =
            error.response.data;

          if (
            data.error &&
            data.error !==
              "Bad request"
          ) {
            errorMsg =
              data.error;
          } else if (
            data.detail &&
            Array.isArray(
              data.detail
            )
          ) {
            errorMsg =
              data.detail
                .map(
                  (detail: any) => {
                    const field =
                      detail.loc &&
                      detail.loc
                        .length >
                        0
                        ? detail.loc[
                            detail.loc
                              .length -
                              1
                          ]
                        : "field";

                    const formattedField =
                      String(
                        field
                      )
                        .replace(
                          /_/g,
                          " "
                        )
                        .replace(
                          /\b\w/g,
                          (char) =>
                            char.toUpperCase()
                        );

                    return `${formattedField}: ${detail.msg}`;
                  }
                )
                .join(", ");
          } else if (
            data.detail
          ) {
            errorMsg =
              data.detail;
          }
        }

        setApiError(
          errorMsg
        );
      } finally {
        setLoading(false);
      }
    };

  const handleDelete =
    async (
      id: string | number
    ) => {
      const job =
        jobs.find(
          (item) =>
            item.id === id
        );

      const name =
        job?.customer_name ||
        `Job #${id}`;

      if (
        !window.confirm(
          `Are you sure you want to delete "${name}"?`
        )
      ) {
        return;
      }

      try {
        setJobsLoading(
          true
        );

        await api.delete(
          `/jobs/${id}`
        );

        setPopup({
          show: true,
          title: "Job Deleted",
          message:
            "The job has been removed successfully.",
          jobId: String(id),
        });

        void fetchJobs();
        void fetchServiceTypes();
      } catch (error) {
        console.error(
          error
        );

        setApiError(
          "Unable to delete job. Please check backend API."
        );
      } finally {
        setJobsLoading(
          false
        );
      }
    };

  const jobsTotalPages =
    Math.max(
      1,
      Math.ceil(
        totalJobsCount /
          JOBS_PAGE_SIZE
      )
    );

  const safeJobsPage =
    Math.min(
      jobsPage,
      jobsTotalPages
    );

  useEffect(() => {
    if (
      jobsPage >
      jobsTotalPages
    ) {
      setJobsPage(
        jobsTotalPages
      );
    }
  }, [
    jobsPage,
    jobsTotalPages,
  ]);

  const getJobsPageNums =
    () => {
      const numbers: number[] =
        [];

      const delta = 2;

      for (
        let index =
          Math.max(
            1,
            safeJobsPage -
              delta
          );
        index <=
        Math.min(
          jobsTotalPages,
          safeJobsPage +
            delta
        );
        index += 1
      ) {
        numbers.push(
          index
        );
      }

      return numbers;
    };

  const formatStatus = (
    status: string
  ) => {
    const value =
      (
        status ||
        "active"
      )
        .toLowerCase()
        .trim();

    if (
      value ===
        "inprogress" ||
      value ===
        "in progress"
    ) {
      return "In Progress";
    }

    if (
      value ===
        "canceled" ||
      value ===
        "cancelled"
    ) {
      return "Cancelled";
    }

    return (
      value.charAt(0)
        .toUpperCase() +
      value.slice(1)
    );
  };

  const getStatusStyle = (
    status: string
  ): React.CSSProperties => {
    const value =
      (
        status || ""
      )
        .toLowerCase()
        .trim();

    const base: React.CSSProperties =
      {
        fontSize: "10px",
        fontWeight: 600,
        padding:
          "2px 9px",
        borderRadius:
          "20px",
        textTransform:
          "capitalize",
        display:
          "inline-block",
        whiteSpace:
          "nowrap",
      };

    if (
      value ===
        "inprogress" ||
      value ===
        "in progress"
    ) {
      return {
        ...base,
        background:
          "#FEF3DC",
        color:
          "#7A5120",
      };
    }

    if (
      value ===
      "completed"
    ) {
      return {
        ...base,
        background:
          "#E8F0FE",
        color:
          "#2F5090",
      };
    }

    if (
      value ===
        "canceled" ||
      value ===
        "cancelled"
    ) {
      return {
        ...base,
        background:
          "#FAE5E5",
        color:
          "#7A2020",
      };
    }

    if (
      value ===
      "rejected_by_technician"
    ) {
      return {
        ...base,
        background:
          "#FEE2E2",
        color:
          "#DC2626",
      };
    }

    return {
      ...base,
      background:
        "#DDEEE5",
      color:
        "#2F4F3E",
    };
  };

  const handleClosureSuccess =
    () => {
      if (viewJob) {
        const updatedJob =
          {
            ...viewJob,
            status:
              "COMPLETED",
          };

        setViewJob(
          updatedJob
        );

        getJobClosure(
          viewJob.id
        )
          .then((data) => {
            setClosureDetails(
              data
            );
          })
          .catch(() => {});

        setTimelineRefreshKey(
          (value) =>
            value + 1
        );
      }

      void fetchJobs();
    };

  const closeViewJob =
    () => {
      setViewJob(null);
      setIsClosureModalOpen(
        false
      );
    };

  const auditTotalPages =
    auditHistory
      ? Math.max(
          1,
          Math.ceil(
            auditHistory.total /
              (auditHistory.page_size ||
                AUDIT_HISTORY_PAGE_SIZE)
          )
        )
      : 1;

  return (
    <div
      style={
        styles.jobsPage
      }
    >
      <style>{`
        @keyframes jobsFadeInRow {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .jobs-table-body tr {
          animation:
            jobsFadeInRow
            0.25s
            ease-out
            forwards;
        }

        .job-view-content {
          display: grid;
          grid-template-columns:
            minmax(0, 1.06fr)
            minmax(0, 0.94fr);
          gap: 0;
          flex: 1;
          min-height: 0;
          overflow: hidden;
          background: #F7FAF8;
        }

        .job-view-panel {
          min-width: 0;
          min-height: 0;
          overflow-y: auto;
          overflow-x: hidden;
          padding: 16px;
          box-sizing: border-box;
          scrollbar-width: thin;
          scrollbar-color: #B8CDBF transparent;
        }

        .job-view-panel-left {
          border-right: 1px solid #DDE7E1;
        }

        .job-view-panel-right {
          background: #F4F8F5;
        }

        .job-view-section {
          background: #FFFFFF;
          border: 1px solid #DCE7E0;
          border-radius: 12px;
          padding: 14px;
          box-shadow:
            0 4px 14px rgba(15, 23, 42, 0.035);
        }

        .job-view-section + .job-view-section {
          margin-top: 12px;
        }

        .job-view-section-title {
          margin: 0;
          font-size: 13px;
          font-weight: 750;
          color: #2F4F3E;
        }

        .job-view-section-subtitle {
          display: block;
          margin-top: 3px;
          font-size: 10px;
          color: #64748B;
          line-height: 1.4;
        }

        .job-view-detail-grid {
          display: grid;
          grid-template-columns:
            repeat(2, minmax(0, 1fr));
          gap: 8px;
          margin-top: 12px;
        }

        .job-view-detail-card {
          padding: 9px;
          border: 1px solid #E2E8F0;
          border-radius: 9px;
          background: #F8FAFC;
          min-width: 0;
        }

        .job-view-detail-card-wide {
          grid-column: 1 / -1;
        }

        .job-view-detail-label {
          display: block;
          font-size: 9px;
          font-weight: 700;
          color: #94A3B8;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .job-view-detail-value {
          margin-top: 4px;
          font-size: 12px;
          color: #1F2937;
          font-weight: 550;
          overflow-wrap: anywhere;
          line-height: 1.45;
        }

        .job-view-status-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          flex-wrap: wrap;
        }

        .job-view-timeline-wrap {
          width: 100%;
          min-width: 0;
        }

        .job-view-audit-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 360px;
          overflow-y: auto;
          padding-right: 2px;
          margin-top: 12px;
        }

        .job-view-audit-event {
          padding: 10px;
          border: 1px solid #E2E8F0;
          border-radius: 9px;
          background: #F8FAFC;
        }

        .job-view-audit-event-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 10px;
        }

        .job-view-audit-event-title {
          font-size: 11px;
          color: #334155;
          font-weight: 700;
        }

        .job-view-audit-event-time {
          font-size: 9px;
          color: #64748B;
          white-space: nowrap;
        }

        .job-view-audit-event-description {
          margin-top: 4px;
          font-size: 10px;
          color: #475569;
          line-height: 1.45;
          overflow-wrap: anywhere;
        }

        .job-view-meta-row {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 7px;
        }

        .job-view-meta-pill {
          font-size: 9px;
          padding: 2px 6px;
          border-radius: 999px;
          font-weight: 700;
        }

        .job-view-feedback-rating {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 10px;
          border: 1px solid #E2E8F0;
          border-radius: 9px;
          background: #F8FAFC;
        }

        .job-view-invoice-summary {
          display: grid;
          grid-template-columns:
            repeat(2, minmax(0, 1fr));
          gap: 8px;
          margin-top: 12px;
        }

        .job-view-invoice-card {
          padding: 9px;
          background: #F8FAFC;
          border: 1px solid #E2E8F0;
          border-radius: 9px;
          min-width: 0;
        }

        .job-view-invoice-card-wide {
          grid-column: 1 / -1;
        }

        .job-view-cost-lines {
          display: flex;
          flex-direction: column;
          gap: 7px;
          font-size: 12px;
          padding: 10px;
          background: #F8FAFC;
          border: 1px solid #E2E8F0;
          border-radius: 9px;
          margin-top: 8px;
        }

        .job-view-cost-line {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }

        .job-view-cost-total {
          padding-top: 9px;
          margin-top: 2px;
          border-top: 1px solid #DCE7E0;
        }

        .job-view-pagination {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          flex-wrap: wrap;
          margin-top: 10px;
          padding-top: 9px;
          border-top: 1px solid #E2E8F0;
        }

        .job-view-pagination-controls {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .job-view-pagination-button {
          min-height: 30px;
          padding: 0 10px;
          border: 1px solid #D7E2DB;
          background: #FFFFFF;
          color: #2F4F3E;
          border-radius: 7px;
          font-size: 10px;
          font-weight: 700;
        }

        .job-view-pagination-button:not(:disabled) {
          cursor: pointer;
        }

        .job-view-pagination-button:disabled {
          color: #94A3B8;
          background: #F1F5F9;
          cursor: not-allowed;
        }

        .job-view-page-number {
          min-width: 74px;
          text-align: center;
          font-size: 10px;
          color: #475569;
          font-weight: 700;
        }

        .job-view-image-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 6px;
        }

        .job-view-image-button {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 5px 8px 5px 5px;
          background: #F8FAFC;
          border: 1px solid #DCE7E0;
          border-radius: 8px;
          cursor: pointer;
          text-align: left;
          max-width: 100%;
        }

        .job-view-image-button:hover {
          background: #F0F7F3;
        }

        .job-view-image {
          width: 52px;
          height: 52px;
          object-fit: cover;
          border-radius: 6px;
          border: 1px solid #DCE7E0;
          flex-shrink: 0;
        }

        @media (max-width: 900px) {
          .job-view-content {
            grid-template-columns:
              minmax(0, 1fr);
            overflow-y: auto;
          }

          .job-view-panel {
            overflow-y: visible;
          }

          .job-view-panel-left {
            border-right: none;
            border-bottom:
              1px solid #DDE7E1;
          }
        }

        @media (max-width: 620px) {
          .job-view-detail-grid,
          .job-view-invoice-summary {
            grid-template-columns:
              minmax(0, 1fr);
          }

          .job-view-detail-card-wide,
          .job-view-invoice-card-wide {
            grid-column: auto;
          }
        }
      `}</style>

      {/* Success Popup */}
      {popup.show && (
        <div
          style={
            styles.popupOverlay
          }
        >
          <div
            style={
              styles.successPopup
            }
          >
            <div
              style={
                styles.successIcon
              }
            >
              ✓
            </div>

            <h3>
              {popup.title}
            </h3>

            {popup.jobId && (
              <div
                style={
                  styles.jobIdBox
                }
              >
                Job ID:{" "}
                <strong>
                  #{popup.jobId}
                </strong>
              </div>
            )}

            <p>
              {popup.message}
            </p>

            <button
              type="button"
              style={
                hoveredBtn ===
                "popupClose"
                  ? {
                      ...styles.popupCloseBtn,
                      background:
                        "#5C9470",
                    }
                  : styles.popupCloseBtn
              }
              onMouseEnter={() =>
                setHoveredBtn(
                  "popupClose"
                )
              }
              onMouseLeave={() =>
                setHoveredBtn(null)
              }
              onClick={
                closePopup
              }
            >
              OK
            </button>
          </div>
        </div>
      )}

      {/* Main Jobs List */}
      <div
        style={
          styles.mainContentRow
        }
      >
        <div
          style={
            styles.contentCard
          }
        >
          <div
            style={
              styles.cardHeader
            }
          >
            <div>
              <p
                style={
                  styles.cardSubtitle
                }
              >
                View and manage all submitted job requests
              </p>
            </div>

            <div
              style={
                styles.headerActionsRow
              }
            >
              <button
                type="button"
                style={
                  hoveredBtn ===
                  "refresh"
                    ? {
                        ...styles.refreshIconBtn,
                        background:
                          "#F6FAF8",
                        borderColor:
                          "#7AAE8A",
                      }
                    : styles.refreshIconBtn
                }
                onMouseEnter={() =>
                  setHoveredBtn(
                    "refresh"
                  )
                }
                onMouseLeave={() =>
                  setHoveredBtn(
                    null
                  )
                }
                onClick={() =>
                  void fetchJobs()
                }
                title="Refresh"
              >
                ⟳ Refresh
              </button>
            </div>
          </div>

          {/* Filters */}
          <div
            style={
              styles.filtersRow
            }
          >
            <div
              style={
                styles.filterGroup
              }
            >
              <label
                style={
                  styles.filterLabel
                }
              >
                Search
              </label>

              <input
                type="text"
                aria-label="Search jobs"
                placeholder="Search name, location..."
                value={
                  searchTerm
                }
                onChange={(event) =>
                  setSearchTerm(
                    event.target.value
                  )
                }
                onFocus={() =>
                  setFocusedInput(
                    "search"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  focusedInput ===
                  "search"
                    ? {
                        ...styles.filterInput,
                        ...styles.filterInputFocus,
                      }
                    : styles.filterInput
                }
              />
            </div>

            <div
              style={
                styles.filterGroup
              }
            >
              <label
                style={
                  styles.filterLabel
                }
              >
                Location
              </label>

              <input
                type="text"
                aria-label="Filter jobs by location"
                placeholder="Search location..."
                value={
                  jobFilters.location
                }
                onChange={(event) =>
                  updateJobFilter(
                    "location",
                    event.target.value
                  )
                }
                onFocus={() =>
                  setFocusedInput(
                    "location"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  focusedInput ===
                  "location"
                    ? {
                        ...styles.filterInput,
                        ...styles.filterInputFocus,
                      }
                    : styles.filterInput
                }
              />
            </div>

            <div
              style={
                styles.filterGroup
              }
            >
              <label
                style={
                  styles.filterLabel
                }
              >
                Priority
              </label>

              <select
                value={
                  jobFilters.priority
                }
                onChange={(event) =>
                  updateJobFilter(
                    "priority",
                    event.target.value
                  )
                }
                aria-label="Filter jobs by priority"
                onFocus={() =>
                  setFocusedInput(
                    "priority"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  focusedInput ===
                  "priority"
                    ? {
                        ...styles.filterInput,
                        ...styles.filterInputFocus,
                      }
                    : styles.filterInput
                }
              >
                {PRIORITY_FILTER_OPTIONS.map(
                  (option) => (
                    <option
                      key={
                        option.value
                      }
                      value={
                        option.value
                      }
                    >
                      {
                        option.label
                      }
                    </option>
                  )
                )}
              </select>
            </div>

            <div
              style={
                styles.filterGroup
              }
            >
              <label
                style={
                  styles.filterLabel
                }
              >
                Service
              </label>

              <select
                value={
                  jobFilters.service_type
                }
                onChange={(event) =>
                  updateJobFilter(
                    "service_type",
                    event.target.value
                  )
                }
                aria-label="Filter jobs by service type"
                onFocus={() =>
                  setFocusedInput(
                    "service"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  focusedInput ===
                  "service"
                    ? {
                        ...styles.filterInput,
                        ...styles.filterInputFocus,
                      }
                    : styles.filterInput
                }
              >
                <option value="ALL">
                  All Services
                </option>

                {serviceTypes.map(
                  (service) => (
                    <option
                      key={
                        service.value
                      }
                      value={
                        service.value
                      }
                    >
                      {
                        service.label
                      }
                    </option>
                  )
                )}
              </select>
            </div>

            <div
              style={
                styles.filterGroup
              }
            >
              <label
                style={
                  styles.filterLabel
                }
              >
                Status
              </label>

              <select
                value={
                  jobFilters.status
                }
                onChange={(event) =>
                  updateJobFilter(
                    "status",
                    event.target.value
                  )
                }
                aria-label="Filter jobs by status"
                onFocus={() =>
                  setFocusedInput(
                    "status"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  focusedInput ===
                  "status"
                    ? {
                        ...styles.filterInput,
                        ...styles.filterInputFocus,
                      }
                    : styles.filterInput
                }
              >
                <option value="ALL">
                  All Statuses
                </option>
                <option value="CREATED">
                  Unassigned
                </option>
                <option value="ASSIGNED">
                  Assigned
                </option>
                <option value="EN_ROUTE">
                  En Route
                </option>
                <option value="IN_PROGRESS">
                  In Progress
                </option>
                <option value="COMPLETED">
                  Completed
                </option>
                <option value="CANCELLED">
                  Cancelled
                </option>
              </select>
            </div>
          </div>

          <div
            style={
              styles.filterGroup
            }
          >
            <label
              style={
                styles.filterLabel
              }
            >
              Technician
            </label>

            <select
              value={
                jobFilters.technician
              }
              onChange={(event) =>
                updateJobFilter(
                  "technician",
                  event.target.value
                )
              }
              aria-label="Filter jobs by technician"
              onFocus={() =>
                setFocusedInput(
                  "technician"
                )
              }
              onBlur={() =>
                setFocusedInput(
                  null
                )
              }
              style={
                focusedInput ===
                "technician"
                  ? {
                      ...styles.filterInput,
                      ...styles.filterInputFocus,
                    }
                  : styles.filterInput
              }
            >
              <option value="ALL">
                {techniciansLoading
                  ? "Loading technicians..."
                  : "All Technicians"}
              </option>

              {technicians.map(
                (technician) => (
                  <option
                    key={
                      technician.technician_id
                    }
                    value={String(
                      technician.technician_id
                    )}
                  >
                    {
                      technician.technician_name
                    }
                  </option>
                )
              )}
            </select>

            {techniciansError && (
              <span
                style={{
                  fontSize:
                    "11px",
                  color:
                    "#7A2020",
                }}
              >
                {
                  techniciansError
                }
              </span>
            )}
          </div>

          <div
            style={
              styles.filterGroup
            }
          >
            <label
              style={
                styles.filterLabel
              }
            >
              SLA
            </label>

            <select
              value={
                jobFilters.sla
              }
              onChange={(event) =>
                updateJobFilter(
                  "sla",
                  event.target.value
                )
              }
              aria-label="Filter jobs by SLA"
              onFocus={() =>
                setFocusedInput(
                  "sla"
                )
              }
              onBlur={() =>
                setFocusedInput(
                  null
                )
              }
              style={
                focusedInput ===
                "sla"
                  ? {
                      ...styles.filterInput,
                      ...styles.filterInputFocus,
                    }
                  : styles.filterInput
              }
            >
              <option value="ALL">
                All SLA
              </option>
              <option value="WITHIN_SLA">
                Within SLA
              </option>
              <option value="APPROACHING_BREACH">
                Approaching Breach
              </option>
              <option value="BREACHED">
                Breached
              </option>
            </select>
          </div>

          <p
            style={
              styles.resultsCount
            }
          >
            Showing{" "}
            <strong>
              {totalJobsCount === 0
                ? 0
                : (safeJobsPage -
                    1) *
                    JOBS_PAGE_SIZE +
                  1}
              –
              {Math.min(
                safeJobsPage *
                  JOBS_PAGE_SIZE,
                totalJobsCount
              )}
            </strong>{" "}
            of{" "}
            <strong>
              {
                totalJobsCount
              }
            </strong>{" "}
            job
            {totalJobsCount !== 1
              ? "s"
              : ""}{" "}
            found
          </p>

          <div
            style={{
              ...styles.tableContainer,
              display:
                "flex",
              flexDirection:
                "column",
              ...(jobsLoading
                ? {
                    justifyContent:
                      "center",
                    alignItems:
                      "center",
                    minHeight:
                      "350px",
                    flex: 1,
                  }
                : {}),
            }}
          >
            {jobsLoading ? (
              <LoadingSpinner
                message="Loading jobs..."
              />
            ) : jobsError ? (
              <div
                style={{
                  minHeight:
                    "350px",
                  display:
                    "flex",
                  flexDirection:
                    "column",
                  alignItems:
                    "center",
                  justifyContent:
                    "center",
                  gap:
                    "12px",
                  padding:
                    "24px",
                  textAlign:
                    "center",
                }}
              >
                <div
                  style={{
                    fontSize:
                      "15px",
                    fontWeight:
                      600,
                    color:
                      "#7A2020",
                  }}
                >
                  {
                    jobsError
                  }
                </div>

                <div
                  style={{
                    fontSize:
                      "13px",
                    color:
                      "#6B7280",
                  }}
                >
                  Your search or filters could not be loaded.
                </div>

                <button
                  type="button"
                  onClick={() =>
                    void fetchJobs()
                  }
                  style={
                    styles.refreshIconBtn
                  }
                >
                  Retry
                </button>
              </div>
            ) : jobs.length ===
              0 ? (
              <EmptyState
                title={
                  (
                    searchTerm.trim() ||
                    jobFilters.status !==
                      "ALL" ||
                    jobFilters.priority !==
                      "ALL" ||
                    jobFilters.service_type !==
                      "ALL" ||
                    jobFilters.sla !==
                      "ALL" ||
                    jobFilters.technician !==
                      "ALL" ||
                    jobFilters.location.trim()
                  )
                    ? "No jobs match your filters"
                    : "No jobs found"
                }
                description={
                  (
                    searchTerm.trim() ||
                    jobFilters.status !==
                      "ALL" ||
                    jobFilters.priority !==
                      "ALL" ||
                    jobFilters.service_type !==
                      "ALL" ||
                    jobFilters.sla !==
                      "ALL" ||
                    jobFilters.technician !==
                      "ALL" ||
                    jobFilters.location.trim()
                  )
                    ? "Try adjusting your search terms or filters."
                    : "Get started by creating your first job request."
                }
                action={
                  (
                    searchTerm.trim() ||
                    jobFilters.status !==
                      "ALL" ||
                    jobFilters.priority !==
                      "ALL" ||
                    jobFilters.service_type !==
                      "ALL" ||
                    jobFilters.sla !==
                      "ALL" ||
                    jobFilters.technician !==
                      "ALL" ||
                    jobFilters.location.trim()
                  ) ? (
                    <button
                      type="button"
                      style={
                        styles.refreshIconBtn
                      }
                      onClick={() => {
                        setSearchTerm(
                          ""
                        );
                        clearJobFilters();
                      }}
                    >
                      Clear Filters
                    </button>
                  ) : null
                }
              />
            ) : (
              <table
                style={
                  styles.dashboardTable
                }
              >
                <thead>
                  <tr>
                    <th
                      style={{
                        ...styles.th,
                        width:
                          "8%",
                      }}
                    >
                      Job ID
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "20%",
                      }}
                    >
                      Customer
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "13%",
                      }}
                    >
                      Location
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "8%",
                      }}
                    >
                      Priority
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "15%",
                      }}
                    >
                      Service Type
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "11%",
                      }}
                    >
                      Preferred Date
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "10%",
                      }}
                    >
                      Status
                    </th>

                    <th
                      style={{
                        ...styles.th,
                        width:
                          "15%",
                      }}
                    >
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody
                  key={
                    safeJobsPage
                  }
                  className="jobs-table-body"
                >
                  {jobs.map(
                    (job) => (
                      <tr
                        key={
                          job.id
                        }
                        style={
                          hoveredRow ===
                          job.id
                            ? {
                                background:
                                  "#F8FBF9",
                              }
                            : undefined
                        }
                        onMouseEnter={() =>
                          setHoveredRow(
                            job.id
                          )
                        }
                        onMouseLeave={() =>
                          setHoveredRow(
                            null
                          )
                        }
                      >
                        <td
                          style={{
                            ...styles.td,
                            ...styles.jobIdCell,
                          }}
                        >
                          <span
                            style={{
                              fontFamily:
                                "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
                              color:
                                "#5C9470",
                              fontWeight:
                                700,
                            }}
                          >
                            {
                              job.id
                            }
                          </span>

                          <CopyJobIdButton
                            jobId={
                              job.id
                            }
                          />
                        </td>

                        <td
                          style={{
                            ...styles.td,
                            ...styles.customerCell,
                            maxWidth:
                              0,
                          }}
                        >
                          <div
                            style={{
                              overflow:
                                "hidden",
                              textOverflow:
                                "ellipsis",
                              whiteSpace:
                                "nowrap",
                            }}
                            title={
                              job.customer_name
                            }
                          >
                            <strong>
                              {
                                job.customer_name
                              }
                            </strong>
                          </div>

                          {job.issue_description && (
                            <div
                              style={
                                styles.issueSub
                              }
                              title={
                                job.issue_description
                              }
                            >
                              {
                                job.issue_description
                              }
                            </div>
                          )}
                        </td>

                        <td
                          style={{
                            ...styles.td,
                            maxWidth:
                              0,
                          }}
                        >
                          <div
                            style={{
                              display:
                                "flex",
                              alignItems:
                                "center",
                              gap:
                                "6px",
                              overflow:
                                "hidden",
                            }}
                          >
                            <span
                              style={{
                                overflow:
                                  "hidden",
                                textOverflow:
                                  "ellipsis",
                                whiteSpace:
                                  "nowrap",
                                flex: 1,
                              }}
                              title={
                                job.location
                              }
                            >
                              {
                                job.location
                              }
                            </span>

                            <a
                              href={`https://maps.google.com/?q=${encodeURIComponent(
                                job.location
                              )}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Open in Maps"
                              onClick={(
                                event
                              ) =>
                                event.stopPropagation()
                              }
                              style={{
                                color:
                                  "#9CA3AF",
                                display:
                                  "flex",
                                alignItems:
                                  "center",
                                flexShrink:
                                  0,
                              }}
                            >
                              <ExternalLink
                                size={
                                  12
                                }
                              />
                            </a>
                          </div>
                        </td>

                        <td
                          style={
                            styles.td
                          }
                        >
                          <span
                            style={
                              getPriorityStyle(
                                job.priority
                              )
                            }
                          >
                            {normalizeP(
                              job.priority
                            )}
                          </span>
                        </td>

                        <td
                          style={{
                            ...styles.td,
                            maxWidth:
                              0,
                          }}
                        >
                          <div
                            style={{
                              overflow:
                                "hidden",
                              textOverflow:
                                "ellipsis",
                              whiteSpace:
                                "nowrap",
                            }}
                            title={
                              formatServiceType(
                                job.service_type
                              )
                            }
                          >
                            {formatServiceType(
                              job.service_type
                            )}
                          </div>
                        </td>

                        <td
                          style={{
                            ...styles.td,
                            maxWidth:
                              0,
                          }}
                        >
                          <div
                            style={{
                              overflow:
                                "hidden",
                              textOverflow:
                                "ellipsis",
                              whiteSpace:
                                "nowrap",
                            }}
                            title={
                              job.preferred_service_date
                            }
                          >
                            {
                              job.preferred_service_date
                            }
                          </div>
                        </td>

                        <td
                          style={
                            styles.td
                          }
                        >
                          <span
                            style={
                              getStatusStyle(
                                job.status
                              )
                            }
                          >
                            {formatStatus(
                              job.status
                            )}
                          </span>
                        </td>

                        <td
                          style={
                            styles.td
                          }
                        >
                          <div
                            style={{
                              display:
                                "flex",
                              gap:
                                "12px",
                            }}
                          >
                            <button
                              type="button"
                              style={{
                                ...styles.iconActionBtn,
                                color:
                                  "#16a34a",
                              }}
                              onClick={() =>
                                setViewJob(
                                  job
                                )
                              }
                              title="View job details"
                              aria-label="View job"
                            >
                              <Eye
                                size={
                                  15
                                }
                              />
                            </button>

                            <button
                              type="button"
                              style={{
                                ...styles.iconActionBtn,
                                color:
                                  "#ca8a04",
                              }}
                              onClick={() =>
                                handleEdit(
                                  job
                                )
                              }
                              title="Edit job"
                              aria-label="Edit job"
                            >
                              <Pencil
                                size={
                                  15
                                }
                              />
                            </button>

                            <button
                              type="button"
                              style={{
                                ...styles.iconActionBtn,
                                color:
                                  "#dc2626",
                              }}
                              onClick={() =>
                                void handleDelete(
                                  job.id
                                )
                              }
                              title="Delete job"
                              aria-label="Delete job"
                            >
                              <Trash2
                                size={
                                  15
                                }
                              />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            )}
          </div>

          {!jobsLoading && (
            <div
              style={
                styles.jobsPagination
              }
            >
              <span
                style={
                  styles.jobsPageInfo
                }
              >
                Page{" "}
                <strong
                  style={{
                    color:
                      "#2F4F3E",
                  }}
                >
                  {
                    safeJobsPage
                  }
                </strong>{" "}
                of{" "}
                <strong
                  style={{
                    color:
                      "#2F4F3E",
                  }}
                >
                  {
                    jobsTotalPages
                  }
                </strong>{" "}
                ·{" "}
                {
                  totalJobsCount
                }{" "}
                results
              </span>

              <div
                style={
                  styles.jobsPageControls
                }
              >
                <button
                  type="button"
                  style={
                    safeJobsPage ===
                    1
                      ? {
                          ...styles.jobsPageBtn,
                          opacity:
                            0.4,
                          cursor:
                            "not-allowed",
                        }
                      : styles.jobsPageBtn
                  }
                  onClick={() =>
                    setJobsPage(
                      1
                    )
                  }
                  disabled={
                    safeJobsPage ===
                    1
                  }
                >
                  «
                </button>

                <button
                  type="button"
                  style={
                    safeJobsPage ===
                    1
                      ? {
                          ...styles.jobsPageBtn,
                          opacity:
                            0.4,
                          cursor:
                            "not-allowed",
                        }
                      : styles.jobsPageBtn
                  }
                  onClick={() =>
                    setJobsPage(
                      (page) =>
                        Math.max(
                          1,
                          page -
                            1
                        )
                    )
                  }
                  disabled={
                    safeJobsPage ===
                    1
                  }
                >
                  ‹ Prev
                </button>

                <div
                  style={
                    styles.jobsPageNumbers
                  }
                >
                  {getJobsPageNums().map(
                    (page) => (
                      <button
                        type="button"
                        key={
                          page
                        }
                        style={
                          page ===
                          safeJobsPage
                            ? {
                                ...styles.jobsPageNum,
                                background:
                                  "#7AAE8A",
                                borderColor:
                                  "#7AAE8A",
                                color:
                                  "#FFFFFF",
                              }
                            : styles.jobsPageNum
                        }
                        onClick={() =>
                          setJobsPage(
                            page
                          )
                        }
                      >
                        {
                          page
                        }
                      </button>
                    )
                  )}
                </div>

                <button
                  type="button"
                  style={
                    safeJobsPage ===
                    jobsTotalPages
                      ? {
                          ...styles.jobsPageBtn,
                          opacity:
                            0.4,
                          cursor:
                            "not-allowed",
                        }
                      : styles.jobsPageBtn
                  }
                  onClick={() =>
                    setJobsPage(
                      (page) =>
                        Math.min(
                          jobsTotalPages,
                          page +
                            1
                        )
                    )
                  }
                  disabled={
                    safeJobsPage ===
                    jobsTotalPages
                  }
                >
                  Next ›
                </button>

                <button
                  type="button"
                  style={
                    safeJobsPage ===
                    jobsTotalPages
                      ? {
                          ...styles.jobsPageBtn,
                          opacity:
                            0.4,
                          cursor:
                            "not-allowed",
                        }
                      : styles.jobsPageBtn
                  }
                  onClick={() =>
                    setJobsPage(
                      jobsTotalPages
                    )
                  }
                  disabled={
                    safeJobsPage ===
                    jobsTotalPages
                  }
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
        <div
          style={
            styles.popupOverlay
          }
          onClick={
            closeViewJob
          }
        >
          <div
            style={{
              ...styles.viewJobModal,
              maxWidth:
                "1180px",
              width:
                "96%",
              height:
                "min(900px, calc(100vh - 24px))",
              maxHeight:
                "calc(100vh - 24px)",
              display:
                "flex",
              flexDirection:
                "column",
              boxSizing:
                "border-box",
            }}
            onClick={(
              event
            ) =>
              event.stopPropagation()
            }
          >
            <div
              style={
                styles.viewModalHeader
              }
            >
              <div>
                <h3
                  style={
                    styles.viewModalHeaderTitle
                  }
                >
                  Job Details & Status History
                </h3>

                <span
                  style={{
                    display:
                      "block",
                    marginTop:
                      "3px",
                    fontSize:
                      "10px",
                    color:
                      "#64748B",
                  }}
                >
                  Job #{viewJob.id} ·{" "}
                  {formatStatus(
                    viewJob.status
                  )}
                </span>
              </div>

              <button
                type="button"
                onClick={
                  closeViewJob
                }
                aria-label="Close job details"
                style={{
                  background:
                    "#FFFFFF",
                  border:
                    "1px solid #DDE7E1",
                  width:
                    "32px",
                  height:
                    "32px",
                  borderRadius:
                    "8px",
                  fontSize:
                    "20px",
                  cursor:
                    "pointer",
                  color:
                    "#64748B",
                }}
              >
                ×
              </button>
            </div>

            <div
              className="job-view-content"
            >
              {/* LEFT PANEL */}
              <div
                className="job-view-panel job-view-panel-left"
              >
                {/* Job Details */}
                <section
                  className="job-view-section"
                >
                  <div
                    className="job-view-status-row"
                  >
                    <div>
                      <h4
                        className="job-view-section-title"
                      >
                        Job Details
                      </h4>

                      <span
                        className="job-view-section-subtitle"
                      >
                        Core job information from the selected backend record
                      </span>
                    </div>

                    <span
                      style={
                        getStatusStyle(
                          viewJob.status
                        )
                      }
                    >
                      {
                        formatStatus(
                          viewJob.status
                        )
                      }
                    </span>
                  </div>

                  <div
                    className="job-view-detail-grid"
                  >
                    <div className="job-view-detail-card">
                      <span className="job-view-detail-label">
                        Job ID
                      </span>
                      <div className="job-view-detail-value">
                        #{viewJob.id}
                      </div>
                    </div>

                    <div className="job-view-detail-card">
                      <span className="job-view-detail-label">
                        Customer
                      </span>
                      <div className="job-view-detail-value">
                        {
                          viewJob.customer_name
                        }
                      </div>
                    </div>

                    <div className="job-view-detail-card job-view-detail-card-wide">
                      <span className="job-view-detail-label">
                        Location
                      </span>
                      <div className="job-view-detail-value">
                        {
                          viewJob.location
                        }
                      </div>
                    </div>

                    <div className="job-view-detail-card">
                      <span className="job-view-detail-label">
                        Priority
                      </span>
                      <div className="job-view-detail-value">
                        <span
                          style={
                            getPriorityStyle(
                              viewJob.priority
                            )
                          }
                        >
                          {normalizeP(
                            viewJob.priority
                          )}
                        </span>
                      </div>
                    </div>

                    <div className="job-view-detail-card">
                      <span className="job-view-detail-label">
                        Service Type
                      </span>
                      <div className="job-view-detail-value">
                        {formatServiceType(
                          viewJob.service_type
                        )}
                      </div>
                    </div>

                    <div className="job-view-detail-card">
                      <span className="job-view-detail-label">
                        Contact
                      </span>
                      <div className="job-view-detail-value">
                        {
                          viewJob.contact_number ||
                          "N/A"
                        }
                      </div>
                    </div>

                    <div className="job-view-detail-card">
                      <span className="job-view-detail-label">
                        Preferred Date
                      </span>
                      <div className="job-view-detail-value">
                        {
                          viewJob.preferred_service_date ||
                          "N/A"
                        }
                      </div>
                    </div>

                    {viewJob.issue_description && (
                      <div className="job-view-detail-card job-view-detail-card-wide">
                        <span className="job-view-detail-label">
                          Issue
                        </span>
                        <div className="job-view-detail-value">
                          {
                            viewJob.issue_description
                          }
                        </div>
                      </div>
                    )}
                  </div>

                  {viewJob.status?.toUpperCase() !==
                    "COMPLETED" && (
                    <button
                      type="button"
                      onClick={() =>
                        setIsClosureModalOpen(
                          true
                        )
                      }
                      disabled={
                        !isTechnician
                      }
                      style={{
                        marginTop:
                          "12px",
                        width:
                          "100%",
                        padding:
                          "10px 14px",
                        backgroundColor:
                          isTechnician
                            ? "#166534"
                            : "#94A3B8",
                        color:
                          "#FFFFFF",
                        border:
                          "none",
                        borderRadius:
                          "8px",
                        fontWeight:
                          650,
                        fontSize:
                          "12px",
                        cursor:
                          isTechnician
                            ? "pointer"
                            : "not-allowed",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        justifyContent:
                          "center",
                        gap:
                          "6px",
                      }}
                      title={
                        !isTechnician
                          ? "Only logged-in technicians can complete jobs"
                          : "Complete Job"
                      }
                    >
                      <CheckCircle2
                        size={
                          16
                        }
                      />
                      Complete Job
                    </button>
                  )}
                </section>

                {/* Closure Summary */}
                {(viewJob.status?.toUpperCase() ===
                  "COMPLETED" ||
                  closureDetails) && (
                  <section
                    className="job-view-section"
                  >
                    <h4
                      className="job-view-section-title"
                    >
                      Closure Summary
                    </h4>

                    <span
                      className="job-view-section-subtitle"
                    >
                      Persisted completion information and backend-authoritative closure record
                    </span>

                    <div
                      className="job-view-detail-grid"
                    >
                      <div className="job-view-detail-card">
                        <span className="job-view-detail-label">
                          Completed By
                        </span>
                        <div className="job-view-detail-value">
                          {
                            closureDetails?.technician_id ||
                            viewJob.completed_by ||
                            "Technician"
                          }
                        </div>
                      </div>

                      <div className="job-view-detail-card">
                        <span className="job-view-detail-label">
                          Completed Time
                        </span>
                        <div className="job-view-detail-value">
                          {closureDetails?.completed_at
                            ? new Date(
                                closureDetails.completed_at
                              ).toLocaleString()
                            : viewJob.completed_at
                              ? new Date(
                                  viewJob.completed_at
                                ).toLocaleString()
                              : "N/A"}
                        </div>
                      </div>

                      {closureDetails?.work_summary && (
                        <div className="job-view-detail-card job-view-detail-card-wide">
                          <span className="job-view-detail-label">
                            Work Summary
                          </span>

                          <div className="job-view-detail-value">
                            {
                              closureDetails.work_summary
                            }
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Completion Report */}
                    <div
                      style={{
                        marginTop:
                          "12px",
                        padding:
                          "11px",
                        background:
                          "#F9FBFA",
                        border:
                          "1px solid #DCE7E0",
                        borderRadius:
                          "10px",
                      }}
                    >
                      <h5
                        style={{
                          margin:
                            0,
                          fontSize:
                            "12px",
                          fontWeight:
                            750,
                          color:
                            "#334155",
                        }}
                      >
                        Completion Report
                      </h5>

                      <span
                        style={{
                          display:
                            "block",
                          marginTop:
                            "3px",
                          fontSize:
                            "10px",
                          color:
                            "#64748B",
                          lineHeight:
                            1.4,
                        }}
                      >
                        Completion report, checklist and metadata from the backend-authoritative closure record
                      </span>

                      {closureDetailsLoading ? (
                        <div
                          style={{
                            minHeight:
                              "90px",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            gap:
                              "8px",
                            color:
                              "#64748B",
                            fontSize:
                              "11px",
                          }}
                        >
                          <Loader2
                            size={
                              14
                            }
                            className="animate-spin"
                          />
                          Loading completion report...
                        </div>
                      ) : closureDetailsError ? (
                        <div
                          role="alert"
                          style={{
                            marginTop:
                              "10px",
                            padding:
                              "9px",
                            background:
                              "#FEF2F2",
                            border:
                              "1px solid #FECACA",
                            color:
                              "#7A2020",
                            borderRadius:
                              "8px",
                            fontSize:
                              "10px",
                          }}
                        >
                          {
                            closureDetailsError
                          }
                        </div>
                      ) : !closureDetails ? (
                        <div
                          style={{
                            minHeight:
                              "70px",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            color:
                              "#64748B",
                            fontSize:
                              "10px",
                            textAlign:
                              "center",
                          }}
                        >
                          No completion report is currently available for this job.
                        </div>
                      ) : (
                        <div
                          style={{
                            display:
                              "flex",
                            flexDirection:
                              "column",
                            gap:
                              "9px",
                            marginTop:
                              "10px",
                          }}
                        >
                          {(closureDetails.work_summary ||
                            closureDetails.completion_notes) && (
                            <div
                              style={{
                                padding:
                                  "9px",
                                background:
                                  "#FFFFFF",
                                border:
                                  "1px solid #E2E8F0",
                                borderRadius:
                                  "8px",
                              }}
                            >
                              <span className="job-view-detail-label">
                                Completed Work Summary
                              </span>
                              <div
                                style={{
                                  marginTop:
                                    "4px",
                                  fontSize:
                                    "10px",
                                  color:
                                    "#334155",
                                  lineHeight:
                                    1.5,
                                  whiteSpace:
                                    "pre-wrap",
                                  overflowWrap:
                                    "anywhere",
                                }}
                              >
                                {
                                  closureDetails.work_summary ||
                                  closureDetails.completion_notes
                                }
                              </div>
                            </div>
                          )}

                          {closureDetails.work_report && (
                            <div
                              style={{
                                padding:
                                  "9px",
                                background:
                                  "#FFFFFF",
                                border:
                                  "1px solid #E2E8F0",
                                borderRadius:
                                  "8px",
                              }}
                            >
                              <span className="job-view-detail-label">
                                Work Report
                              </span>

                              {closureDetails.work_report.summary && (
                                <div
                                  style={{
                                    marginTop:
                                      "4px",
                                    fontSize:
                                      "10px",
                                    color:
                                      "#334155",
                                    lineHeight:
                                      1.5,
                                    whiteSpace:
                                      "pre-wrap",
                                    overflowWrap:
                                      "anywhere",
                                  }}
                                >
                                  {
                                    closureDetails.work_report.summary
                                  }
                                </div>
                              )}

                              <div
                                style={{
                                  display:
                                    "flex",
                                  flexWrap:
                                    "wrap",
                                  gap:
                                    "6px",
                                  marginTop:
                                    "7px",
                                }}
                              >
                                {Array.isArray(
                                  closureDetails.work_report.parts_used
                                ) &&
                                closureDetails.work_report.parts_used.length >
                                  0 ? (
                                  closureDetails.work_report.parts_used.map(
                                    (
                                      part: string,
                                      index: number
                                    ) => (
                                      <span
                                        key={`${part}-${index}`}
                                        style={{
                                          fontSize:
                                            "9px",
                                          padding:
                                            "3px 7px",
                                          borderRadius:
                                            "999px",
                                          background:
                                            "#E8F0FE",
                                          color:
                                            "#2F5090",
                                          fontWeight:
                                            700,
                                        }}
                                      >
                                        {
                                          part
                                        }
                                      </span>
                                    )
                                  )
                                ) : (
                                  <span
                                    style={{
                                      fontSize:
                                        "10px",
                                      color:
                                        "#64748B",
                                    }}
                                  >
                                    No parts were recorded.
                                  </span>
                                )}

                                {closureDetails.work_report.duration_minutes !=
                                  null && (
                                  <span
                                    style={{
                                      fontSize:
                                        "9px",
                                      padding:
                                        "3px 7px",
                                      borderRadius:
                                        "999px",
                                      background:
                                        "#ECFDF5",
                                      color:
                                        "#166534",
                                      fontWeight:
                                        700,
                                    }}
                                  >
                                    Duration:{" "}
                                    {
                                      closureDetails.work_report
                                        .duration_minutes
                                    }{" "}
                                    min
                                  </span>
                                )}
                              </div>
                            </div>
                          )}

                          {closureDetails.checklist?.items &&
                            closureDetails.checklist.items.length >
                              0 && (
                              <div
                                style={{
                                  padding:
                                    "9px",
                                  background:
                                    "#FFFFFF",
                                  border:
                                    "1px solid #E2E8F0",
                                  borderRadius:
                                    "8px",
                                }}
                              >
                                <span className="job-view-detail-label">
                                  Completion Checklist
                                </span>

                                <div
                                  style={{
                                    display:
                                      "flex",
                                    flexDirection:
                                      "column",
                                    gap:
                                      "5px",
                                    marginTop:
                                      "6px",
                                  }}
                                >
                                  {closureDetails.checklist.items.map(
                                    (
                                      item: any,
                                      index: number
                                    ) => {
                                      const isCompleted =
                                        String(
                                          item?.status ||
                                            ""
                                        ).toUpperCase() ===
                                        "COMPLETED";

                                      return (
                                        <div
                                          key={`${item?.id || item?.label || "item"}-${index}`}
                                          style={{
                                            display:
                                              "flex",
                                            alignItems:
                                              "center",
                                            justifyContent:
                                              "space-between",
                                            gap:
                                              "8px",
                                            padding:
                                              "7px",
                                            background:
                                              "#F8FAFC",
                                            border:
                                              "1px solid #E5E7EB",
                                            borderRadius:
                                              "7px",
                                          }}
                                        >
                                          <span
                                            style={{
                                              fontSize:
                                                "10px",
                                              color:
                                                "#334155",
                                              overflowWrap:
                                                "anywhere",
                                            }}
                                          >
                                            {
                                              item?.label ||
                                              `Checklist item ${
                                                index +
                                                1
                                              }`
                                            }
                                            {item?.required
                                              ? " *"
                                              : ""}
                                          </span>

                                          <span
                                            style={{
                                              flexShrink:
                                                0,
                                              fontSize:
                                                "8px",
                                              fontWeight:
                                                700,
                                              padding:
                                                "3px 6px",
                                              borderRadius:
                                                "999px",
                                              background:
                                                isCompleted
                                                  ? "#DCFCE7"
                                                  : "#FEE2E2",
                                              color:
                                                isCompleted
                                                  ? "#166534"
                                                  : "#991B1B",
                                            }}
                                          >
                                            {isCompleted
                                              ? "COMPLETED"
                                              : "INCOMPLETE"}
                                          </span>
                                        </div>
                                      );
                                    }
                                  )}
                                </div>
                              </div>
                            )}

                          <div
                            style={{
                              padding:
                                "9px",
                              background:
                                "#FFFFFF",
                              border:
                                "1px solid #E2E8F0",
                              borderRadius:
                                "8px",
                            }}
                          >
                            <span className="job-view-detail-label">
                              Completion Metadata
                            </span>

                            <div
                              className="job-view-detail-grid"
                              style={{
                                marginTop:
                                  "7px",
                              }}
                            >
                              <div>
                                <span className="job-view-detail-label">
                                  Completed By
                                </span>
                                <div
                                  className="job-view-detail-value"
                                  style={{
                                    fontSize:
                                      "10px",
                                  }}
                                >
                                  {
                                    closureDetails.technician_id ||
                                    "Technician"
                                  }
                                </div>
                              </div>

                              <div>
                                <span className="job-view-detail-label">
                                  Completed At
                                </span>
                                <div
                                  className="job-view-detail-value"
                                  style={{
                                    fontSize:
                                      "10px",
                                  }}
                                >
                                  {closureDetails.completed_at
                                    ? new Date(
                                        closureDetails.completed_at
                                      ).toLocaleString()
                                    : "N/A"}
                                </div>
                              </div>

                              <div>
                                <span className="job-view-detail-label">
                                  Recorded At
                                </span>
                                <div
                                  className="job-view-detail-value"
                                  style={{
                                    fontSize:
                                      "10px",
                                  }}
                                >
                                  {closureDetails.created_at
                                    ? new Date(
                                        closureDetails.created_at
                                      ).toLocaleString()
                                    : "N/A"}
                                </div>
                              </div>

                              <div>
                                <span className="job-view-detail-label">
                                  Last Updated
                                </span>
                                <div
                                  className="job-view-detail-value"
                                  style={{
                                    fontSize:
                                      "10px",
                                  }}
                                >
                                  {closureDetails.updated_at
                                    ? new Date(
                                        closureDetails.updated_at
                                      ).toLocaleString()
                                    : "N/A"}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Job Documents */}
                    <div
                      style={{
                        marginTop:
                          "12px",
                        padding:
                          "11px",
                        background:
                          "#F9FBFA",
                        border:
                          "1px solid #DCE7E0",
                        borderRadius:
                          "10px",
                      }}
                    >
                      <h5
                        style={{
                          margin:
                            0,
                          fontSize:
                            "12px",
                          fontWeight:
                            750,
                          color:
                            "#334155",
                        }}
                      >
                        Job Documents
                      </h5>

                      <span
                        style={{
                          display:
                            "block",
                          marginTop:
                            "3px",
                          fontSize:
                            "10px",
                          color:
                            "#64748B",
                        }}
                      >
                        Completion photos from the backend-authoritative closure record
                      </span>

                      {closureDetailsLoading ? (
                        <div
                          style={{
                            minHeight:
                              "70px",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            color:
                              "#64748B",
                            fontSize:
                              "10px",
                          }}
                        >
                          Loading completion documents...
                        </div>
                      ) : closureDetailsError ? (
                        <div
                          style={{
                            marginTop:
                              "9px",
                            padding:
                              "8px",
                            background:
                              "#FEF2F2",
                            border:
                              "1px solid #FECACA",
                            color:
                              "#7A2020",
                            borderRadius:
                              "8px",
                            fontSize:
                              "10px",
                          }}
                        >
                          {
                            closureDetailsError
                          }
                        </div>
                      ) : !closureDetails ? (
                        <div
                          style={{
                            minHeight:
                              "60px",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            color:
                              "#64748B",
                            fontSize:
                              "10px",
                          }}
                        >
                          No completion documents are currently available.
                        </div>
                      ) : (
                        <div
                          style={{
                            marginTop:
                              "10px",
                          }}
                        >
                          {(closureDetails.before_images ??
                            []).length >
                            0 && (
                            <div
                              style={{
                                marginBottom:
                                  "9px",
                              }}
                            >
                              <span className="job-view-detail-label">
                                Before Images
                              </span>

                              <div className="job-view-image-grid">
                                {closureDetails.before_images.map(
                                  (
                                    image: string,
                                    index: number
                                  ) => {
                                    const imageName =
                                      getImageName(
                                        image,
                                        "before",
                                        index
                                      );

                                    const imageKey =
                                      `before:${image}`;

                                    const unavailable =
                                      failedDocumentImages[
                                        imageKey
                                      ];

                                    return (
                                      <button
                                        key={`${imageName}-${index}`}
                                        type="button"
                                        className="job-view-image-button"
                                        onClick={() =>
                                          openImagePreview(
                                            image,
                                            "before",
                                            index
                                          )
                                        }
                                        disabled={
                                          unavailable
                                        }
                                      >
                                        {unavailable ? (
                                          <div
                                            style={{
                                              width:
                                                "52px",
                                              height:
                                                "52px",
                                              display:
                                                "flex",
                                              alignItems:
                                                "center",
                                              justifyContent:
                                                "center",
                                              borderRadius:
                                                "6px",
                                              border:
                                                "1px solid #E2E8F0",
                                              color:
                                                "#94A3B8",
                                              fontSize:
                                                "9px",
                                              flexShrink:
                                                0,
                                            }}
                                          >
                                            Unavailable
                                          </div>
                                        ) : (
                                          <img
                                            src={
                                              image
                                            }
                                            alt={
                                              imageName
                                            }
                                            className="job-view-image"
                                            onError={() =>
                                              markDocumentImageUnavailable(
                                                imageKey
                                              )
                                            }
                                          />
                                        )}

                                        <span
                                          style={{
                                            fontSize:
                                              "10px",
                                            color:
                                              "#334155",
                                            fontWeight:
                                              650,
                                            overflowWrap:
                                              "anywhere",
                                          }}
                                        >
                                          {
                                            imageUnavailableLabel(
                                              imageName,
                                              unavailable
                                            )
                                          }
                                        </span>
                                      </button>
                                    );
                                  }
                                )}
                              </div>
                            </div>
                          )}

                          {(closureDetails.after_images ??
                            []).length >
                            0 && (
                            <div>
                              <span className="job-view-detail-label">
                                After Images
                              </span>

                              <div className="job-view-image-grid">
                                {closureDetails.after_images.map(
                                  (
                                    image: string,
                                    index: number
                                  ) => {
                                    const imageName =
                                      getImageName(
                                        image,
                                        "after",
                                        index
                                      );

                                    const imageKey =
                                      `after:${image}`;

                                    const unavailable =
                                      failedDocumentImages[
                                        imageKey
                                      ];

                                    return (
                                      <button
                                        key={`${imageName}-${index}`}
                                        type="button"
                                        className="job-view-image-button"
                                        onClick={() =>
                                          openImagePreview(
                                            image,
                                            "after",
                                            index
                                          )
                                        }
                                        disabled={
                                          unavailable
                                        }
                                      >
                                        {unavailable ? (
                                          <div
                                            style={{
                                              width:
                                                "52px",
                                              height:
                                                "52px",
                                              display:
                                                "flex",
                                              alignItems:
                                                "center",
                                              justifyContent:
                                                "center",
                                              borderRadius:
                                                "6px",
                                              border:
                                                "1px solid #BBF7D0",
                                              color:
                                                "#94A3B8",
                                              fontSize:
                                                "9px",
                                              flexShrink:
                                                0,
                                            }}
                                          >
                                            Unavailable
                                          </div>
                                        ) : (
                                          <img
                                            src={
                                              image
                                            }
                                            alt={
                                              imageName
                                            }
                                            className="job-view-image"
                                            onError={() =>
                                              markDocumentImageUnavailable(
                                                imageKey
                                              )
                                            }
                                          />
                                        )}

                                        <span
                                          style={{
                                            fontSize:
                                              "10px",
                                            color:
                                              "#166534",
                                            fontWeight:
                                              650,
                                            overflowWrap:
                                              "anywhere",
                                          }}
                                        >
                                          {
                                            imageUnavailableLabel(
                                              imageName,
                                              unavailable
                                            )
                                          }
                                        </span>
                                      </button>
                                    );
                                  }
                                )}
                              </div>
                            </div>
                          )}

                          {(closureDetails.before_images ??
                            []).length ===
                            0 &&
                            (closureDetails.after_images ??
                              []).length ===
                              0 && (
                              <div
                                style={{
                                  minHeight:
                                    "60px",
                                  display:
                                    "flex",
                                  alignItems:
                                    "center",
                                  justifyContent:
                                    "center",
                                  color:
                                    "#64748B",
                                  fontSize:
                                    "10px",
                                }}
                              >
                                No completion photos are attached to this closure record.
                              </div>
                            )}
                        </div>
                      )}
                    </div>
                  </section>
                )}

                {/* Customer Feedback */}
                {!isTechnician &&
                  viewJob.status?.toUpperCase() ===
                    "COMPLETED" && (
                    <section
                      className="job-view-section"
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                          gap: "10px",
                          flexWrap: "wrap",
                          marginBottom: "10px",
                        }}
                      >
                        <div>
                          <h4
                            className="job-view-section-title"
                          >
                            Customer Feedback
                          </h4>

                          <span
                            className="job-view-section-subtitle"
                          >
                            Backend-authoritative customer feedback for this job
                          </span>
                        </div>
                      </div>

                      {customerFeedbackLoading ? (
                        <div
                          style={{
                            minHeight:
                              "80px",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            gap:
                              "8px",
                            color:
                              "#64748B",
                            fontSize:
                              "10px",
                          }}
                        >
                          <Loader2
                            size={
                              14
                            }
                            className="animate-spin"
                          />
                          Loading customer feedback...
                        </div>
                      ) : customerFeedbackError ? (
                        <div
                          role="alert"
                          style={{
                            marginTop:
                              "10px",
                            padding:
                              "9px",
                            background:
                              "#FEF2F2",
                            border:
                              "1px solid #FECACA",
                            color:
                              "#7A2020",
                            borderRadius:
                              "8px",
                            fontSize:
                              "10px",
                          }}
                        >
                          {
                            customerFeedbackError
                          }
                        </div>
                      ) : !customerFeedbackDetails?.has_feedback ||
                        !customerFeedbackDetails.feedback ? (
                        <div
                          style={{
                            minHeight:
                              "70px",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            color:
                              "#64748B",
                            fontSize:
                              "10px",
                            textAlign:
                              "center",
                          }}
                        >
                          No customer feedback is available for this job.
                        </div>
                      ) : (
                        <div
                          style={{
                            display:
                              "flex",
                            flexDirection:
                              "column",
                            gap:
                              "9px",
                            marginTop:
                              "10px",
                          }}
                        >
                          <div className="job-view-feedback-rating">
                            <div>
                              <span className="job-view-detail-label">
                                Rating
                              </span>

                              <div
                                aria-label={`${customerFeedbackDetails.feedback.rating} out of 5 stars`}
                                style={{
                                  display:
                                    "flex",
                                  alignItems:
                                    "center",
                                  gap:
                                    "2px",
                                  marginTop:
                                    "4px",
                                }}
                              >
                                {Array.from(
                                  {
                                    length: 5,
                                  },
                                  (
                                    _,
                                    index
                                  ) => {
                                    const rating =
                                      customerFeedbackDetails.feedback?.rating ??
                                      0;

                                    const filled =
                                      index <
                                      rating;

                                    return (
                                      <Star
                                        key={
                                          index
                                        }
                                        size={
                                          14
                                        }
                                        fill={
                                          filled
                                            ? "currentColor"
                                            : "none"
                                        }
                                        color={
                                          filled
                                            ? "#D97706"
                                            : "#CBD5E1"
                                        }
                                        strokeWidth={
                                          1.8
                                        }
                                      />
                                    );
                                  }
                                )}
                              </div>
                            </div>

                            <span
                              style={{
                                display:
                                  "inline-flex",
                                alignItems:
                                  "center",
                                justifyContent:
                                  "center",
                                minHeight:
                                  "22px",
                                padding:
                                  "3px 9px",
                                borderRadius:
                                  "999px",
                                background:
                                  "#FEF3C7",
                                color:
                                  "#92400E",
                                fontSize:
                                  "10px",
                                fontWeight:
                                  750,
                              }}
                            >
                              {
                                customerFeedbackDetails
                                  .feedback
                                  .rating
                              }
                              /5
                            </span>
                          </div>

                          <div
                            className="job-view-invoice-card"
                          >
                            <span className="job-view-detail-label">
                              Comment
                            </span>

                            <div
                              style={{
                                marginTop:
                                  "4px",
                                fontSize:
                                  "10px",
                                color:
                                  "#334155",
                                lineHeight:
                                  1.5,
                                whiteSpace:
                                  "pre-wrap",
                                overflowWrap:
                                  "anywhere",
                              }}
                            >
                              {
                                customerFeedbackDetails
                                  .feedback
                                  .comment ||
                                "No comment provided."
                              }
                            </div>
                          </div>

                          <div
                            className="job-view-invoice-summary"
                            style={{
                              marginTop:
                                "0",
                            }}
                          >
                            <div className="job-view-invoice-card">
                              <span className="job-view-detail-label">
                                Submitted At
                              </span>

                              <div
                                className="job-view-detail-value"
                                style={{
                                  fontSize:
                                    "10px",
                                }}
                              >
                                {customerFeedbackDetails.feedback.created_at
                                  ? new Date(
                                      customerFeedbackDetails.feedback.created_at
                                    ).toLocaleString()
                                  : "N/A"}
                              </div>
                            </div>

                            <div className="job-view-invoice-card">
                              <span className="job-view-detail-label">
                                Last Updated
                              </span>

                              <div
                                className="job-view-detail-value"
                                style={{
                                  fontSize:
                                    "10px",
                                }}
                              >
                                {customerFeedbackDetails.feedback.updated_at
                                  ? new Date(
                                      customerFeedbackDetails.feedback.updated_at
                                    ).toLocaleString()
                                  : "N/A"}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      <div
                        style={{
                          marginTop:
                            "8px",
                          fontSize:
                            "9px",
                          color:
                            "#64748B",
                        }}
                      >
                        Customer identity and other sensitive customer fields are not exposed by this section.
                      </div>
                    </section>
                  )}

                {/* Audit History */}
                <section
                  className="job-view-section"
                >
                  <div
                    className="job-view-status-row"
                  >
                    <div>
                      <h4
                        className="job-view-section-title"
                      >
                        Audit History
                      </h4>

                      <span
                        className="job-view-section-subtitle"
                      >
                        Backend-authoritative permitted audit events
                      </span>
                    </div>

                  {auditHistory && (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        flexWrap: "wrap",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "10px",
                          color: "#64748b",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {auditHistory.total} event
                        {auditHistory.total !== 1 ? "s" : ""}
                      </span>

                      <button
                        type="button"
                        aria-label="Export audit history"
                        onClick={handleExportAuditHistory}
                        disabled={
                          auditHistoryExportLoading ||
                          auditHistory.events.length === 0
                        }
                        title={
                          auditHistory.events.length === 0
                            ? "No audit history is available to export"
                            : "Export the currently loaded filtered audit history"
                        }
                        style={{
                          border: "1px solid #dbe4ea",
                          background:
                            auditHistoryExportLoading ||
                            auditHistory.events.length === 0
                              ? "#f1f5f9"
                              : "#ffffff",
                          color:
                            auditHistoryExportLoading ||
                            auditHistory.events.length === 0
                              ? "#94a3b8"
                              : "#2F4F3E",
                          borderRadius: "7px",
                          padding: "5px 9px",
                          fontSize: "10px",
                          fontWeight: 700,
                          cursor:
                            auditHistoryExportLoading ||
                            auditHistory.events.length === 0
                              ? "not-allowed"
                              : "pointer",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {auditHistoryExportLoading
                          ? "Exporting..."
                          : "Export CSV"}
                      </button>
                    </div>
                  )}
                  </div>

                  {/* Audit History Filters */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "minmax(0, 1fr) minmax(0, 220px) auto",
                      gap: "8px",
                      alignItems: "end",
                      marginBottom: "10px",
                      padding: "9px",
                      border: "1px solid #e2e8f0",
                      borderRadius: "8px",
                      background: "#f8fafc",
                    }}
                  >
                    <div>
                      <label
                        htmlFor="audit-history-event-type"
                        style={{
                          display: "block",
                          marginBottom: "4px",
                          fontSize: "9px",
                          fontWeight: 700,
                          color: "#64748b",
                          textTransform: "uppercase",
                          letterSpacing: "0.04em",
                        }}
                      >
                        Event Type
                      </label>

                      <input
                        id="audit-history-event-type"
                        type="text"
                        value={auditHistoryEventType}
                        onChange={(event) => {
                          setAuditHistoryEventType(event.target.value);
                        }}
                        placeholder="e.g. JOB_ACCEPTED"
                        disabled={auditHistoryLoading}
                        style={{
                          width: "100%",
                          height: "30px",
                          padding: "0 9px",
                          border: "1px solid #dbe4ea",
                          borderRadius: "7px",
                          background: "#ffffff",
                          color: "#334155",
                          fontSize: "10px",
                          outline: "none",
                        }}
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="audit-history-source"
                        style={{
                          display: "block",
                          marginBottom: "4px",
                          fontSize: "9px",
                          fontWeight: 700,
                          color: "#64748b",
                          textTransform: "uppercase",
                          letterSpacing: "0.04em",
                        }}
                      >
                        Source
                      </label>

                      <select
                        id="audit-history-source"
                        value={auditHistorySource}
                        onChange={(event) => {
                          setAuditHistorySource(
                            event.target.value as JobAuditHistorySource | ""
                          );
                        }}
                        disabled={auditHistoryLoading}
                        style={{
                          width: "100%",
                          height: "30px",
                          padding: "0 8px",
                          border: "1px solid #dbe4ea",
                          borderRadius: "7px",
                          background: "#ffffff",
                          color: "#334155",
                          fontSize: "10px",
                          outline: "none",
                        }}
                      >
                        <option value="">All Sources</option>
                        <option value="audit_event">Audit Event</option>
                        <option value="enterprise_audit">
                          Enterprise Audit
                        </option>
                        <option value="assignment_override">
                          Assignment Override
                        </option>
                      </select>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        setAuditHistoryEventType("");
                        setAuditHistorySource("");
                        setAuditHistoryPage(1);
                      }}
                      disabled={
                        auditHistoryLoading ||
                        (!auditHistoryEventType && !auditHistorySource)
                      }
                      style={{
                        height: "30px",
                        padding: "0 10px",
                        border: "1px solid #dbe4ea",
                        borderRadius: "7px",
                        background:
                          auditHistoryLoading ||
                          (!auditHistoryEventType && !auditHistorySource)
                            ? "#f1f5f9"
                            : "#ffffff",
                        color:
                          auditHistoryLoading ||
                          (!auditHistoryEventType && !auditHistorySource)
                            ? "#94a3b8"
                            : "#2F4F3E",
                        fontSize: "10px",
                        fontWeight: 700,
                        cursor:
                          auditHistoryLoading ||
                          (!auditHistoryEventType && !auditHistorySource)
                            ? "not-allowed"
                            : "pointer",
                      }}
                    >
                      Clear Filters
                    </button>
                  </div>

                  {auditHistoryExportError && (
                    <div
                      role="alert"
                      style={{
                        marginBottom: "8px",
                        padding: "6px 9px",
                        border: "1px solid #fecaca",
                        borderRadius: "7px",
                        background: "#fef2f2",
                        color: "#991b1b",
                        fontSize: "10px",
                        fontWeight: 600,
                      }}
                    >
                      {auditHistoryExportError}
                    </div>
                  )}

                  {auditHistoryLoading ? (
                    <div
                      style={{
                        minHeight:
                          "90px",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        justifyContent:
                          "center",
                        gap:
                          "8px",
                        color:
                          "#64748B",
                        fontSize:
                          "10px",
                      }}
                    >
                      <Loader2
                        size={
                          14
                        }
                        className="animate-spin"
                      />
                      Loading audit history...
                    </div>
                  ) : auditHistoryError ? (
                    <div
                      style={{
                        marginTop:
                          "10px",
                        padding:
                          "14px",
                        border:
                          "1px solid #FECACA",
                        background:
                          "#FEF2F2",
                        borderRadius:
                          "9px",
                        textAlign:
                          "center",
                      }}
                    >
                      <div
                        style={{
                          fontSize:
                            "10px",
                          color:
                            "#7A2020",
                        }}
                      >
                        {
                          auditHistoryError
                        }
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          if (!viewJob) {
                            return;
                          }

                          void loadAuditHistory(
                            viewJob.id,
                            auditHistoryPage
                          );
                        }}
                        style={{
                          marginTop:
                            "8px",
                          border:
                            "1px solid #D7E2DB",
                          background:
                            "#FFFFFF",
                          color:
                            "#2F4F3E",
                          borderRadius:
                            "7px",
                          padding:
                            "6px 10px",
                          fontSize:
                            "10px",
                          fontWeight:
                            700,
                          cursor:
                            "pointer",
                        }}
                      >
                        Retry
                      </button>
                    </div>
                  ) : !auditHistory ||
                    auditHistory.events.length ===
                      0 ? (
                    <div
                      style={{
                        minHeight:
                          "70px",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        justifyContent:
                          "center",
                        marginTop:
                          "8px",
                        color:
                          "#64748B",
                        fontSize:
                          "10px",
                        textAlign:
                          "center",
                      }}
                    >
                      No permitted audit history is currently available for this job.
                    </div>
                  ) : (
                    <>
                      <div className="job-view-audit-list">
                        {auditHistory.events.map(
                          (event) => (
                            <div
                              key={
                                event.id
                              }
                              className="job-view-audit-event"
                            >
                              <div className="job-view-audit-event-header">
                                <strong className="job-view-audit-event-title">
                                  {
                                    event.title
                                  }
                                </strong>

                                <span className="job-view-audit-event-time">
                                  {event.timestamp
                                    ? new Date(
                                        event.timestamp
                                      ).toLocaleString()
                                    : "N/A"}
                                </span>
                              </div>

                              <div className="job-view-audit-event-description">
                                {
                                  event.description
                                }
                              </div>

                              <div className="job-view-meta-row">
                                <span
                                  className="job-view-meta-pill"
                                  style={{
                                    background:
                                      "#E8F0FE",
                                    color:
                                      "#2F5090",
                                  }}
                                >
                                  {
                                    event.actor_name
                                  }
                                </span>

                                <span
                                  className="job-view-meta-pill"
                                  style={{
                                    background:
                                      "#EEF2F7",
                                    color:
                                      "#475569",
                                  }}
                                >
                                  {
                                    event.actor_role
                                  }
                                </span>

                                <span
                                  className="job-view-meta-pill"
                                  style={{
                                    background:
                                      "#ECFDF5",
                                    color:
                                      "#166534",
                                  }}
                                >
                                  {
                                    event.event_type
                                  }
                                </span>

                                <span
                                  className="job-view-meta-pill"
                                  style={{
                                    background:
                                      "#FFF7ED",
                                    color:
                                      "#9A3412",
                                  }}
                                >
                                  {
                                    event.source
                                  }
                                </span>
                              </div>
                            </div>
                          )
                        )}
                      </div>

                      {/* Pagination only when there is more than one page */}
                      {auditTotalPages >
                        1 ? (
                        <div
                          className="job-view-pagination"
                        >
                          <span
                            style={{
                              fontSize:
                                "10px",
                              color:
                                "#64748B",
                              fontWeight:
                                650,
                            }}
                          >
                            Showing{" "}
                            {Math.min(
                              (auditHistoryPage -
                                1) *
                                (auditHistory.page_size ||
                                  AUDIT_HISTORY_PAGE_SIZE) +
                                1,
                              auditHistory.total
                            )}
                            –
                            {Math.min(
                              auditHistoryPage *
                                (auditHistory.page_size ||
                                  AUDIT_HISTORY_PAGE_SIZE),
                              auditHistory.total
                            )}{" "}
                            of{" "}
                            {
                              auditHistory.total
                            }
                          </span>

                          <div className="job-view-pagination-controls">
                            <button
                              type="button"
                              className="job-view-pagination-button"
                              aria-label="Previous audit history page"
                              disabled={
                                auditHistoryPage <=
                                  1 ||
                                auditHistoryLoading
                              }
                              onClick={() => {
                                if (
                                  !viewJob ||
                                  auditHistoryPage <=
                                    1
                                ) {
                                  return;
                                }

                                void loadAuditHistory(
                                  viewJob.id,
                                  auditHistoryPage -
                                    1
                                );
                              }}
                            >
                              ‹ Previous
                            </button>

                            <span className="job-view-page-number">
                              Page{" "}
                              {
                                auditHistoryPage
                              }{" "}
                              of{" "}
                              {
                                auditTotalPages
                              }
                            </span>

                            <button
                              type="button"
                              className="job-view-pagination-button"
                              aria-label="Next audit history page"
                              disabled={
                                !auditHistory.has_more ||
                                auditHistoryLoading
                              }
                              onClick={() => {
                                if (
                                  !viewJob ||
                                  !auditHistory.has_more
                                ) {
                                  return;
                                }

                                void loadAuditHistory(
                                  viewJob.id,
                                  auditHistoryPage +
                                    1
                                );
                              }}
                            >
                              Next ›
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div
                          style={{
                            marginTop:
                              "10px",
                            paddingTop:
                              "9px",
                            borderTop:
                              "1px solid #E2E8F0",
                            fontSize:
                              "10px",
                            color:
                              "#64748B",
                            fontWeight:
                              650,
                          }}
                        >
                          Showing all{" "}
                          {
                            auditHistory.total
                          }{" "}
                          event
                          {auditHistory.total !==
                          1
                            ? "s"
                            : ""}
                        </div>
                      )}
                    </>
                  )}
                </section>
              </div>

              {/* RIGHT PANEL */}
              <div
                className="job-view-panel job-view-panel-right"
              >
                {/* Timeline */}
                <section
                  className="job-view-section"
                >
                  <div
                    className="job-view-timeline-wrap"
                  >
                    <JobStatusTimeline
                      jobId={
                        viewJob.id
                      }
                      currentStatus={
                        viewJob.status
                      }
                      refreshKey={
                        timelineRefreshKey
                      }
                    />
                  </div>
                </section>

                {/* Payment + Invoice */}
                <section
                  className="job-view-section"
                >
                  <div className="invoiceSectionHeader">
                    <div>
                      <h4
                        className="job-view-section-title"
                      >
                        Invoice
                      </h4>

                      <span
                        className="job-view-section-subtitle"
                      >
                        Backend-authoritative billing data for this job
                      </span>
                    </div>

                    {invoiceDetails && (
                      <button
                        type="button"
                        onClick={
                          handleDownloadInvoice
                        }
                        disabled={
                          invoiceDownloadLoading
                        }
                        style={{
                          display:
                            "inline-flex",
                          alignItems:
                            "center",
                          justifyContent:
                            "center",
                          gap:
                            "6px",
                          padding:
                            "7px 10px",
                          border:
                            "1px solid #7AAE8A",
                          background:
                            invoiceDownloadLoading
                              ? "#EEF2F7"
                              : "#F0FDF4",
                          color:
                            invoiceDownloadLoading
                              ? "#94A3B8"
                              : "#166534",
                          borderRadius:
                            "7px",
                          fontSize:
                            "10px",
                          fontWeight:
                            750,
                          cursor:
                            invoiceDownloadLoading
                              ? "not-allowed"
                              : "pointer",
                        }}
                        aria-label="Download invoice PDF"
                      >
                        <ExternalLink
                          size={
                            12
                          }
                        />
                        {invoiceDownloadLoading
                          ? "Preparing PDF..."
                          : "Download PDF"}
                      </button>
                    )}
                  </div>

                  {invoiceDownloadError && (
                    <div
                      role="alert"
                      style={{
                        marginTop:
                          "9px",
                        padding:
                          "8px",
                        background:
                          "#FEF2F2",
                        border:
                          "1px solid #FECACA",
                        color:
                          "#7A2020",
                        borderRadius:
                          "8px",
                        fontSize:
                          "10px",
                      }}
                    >
                      {
                        invoiceDownloadError
                      }
                    </div>
                  )}

                  {/* Task 8 - Payment Status */}
                  {viewJob.status?.toUpperCase() ===
                    "COMPLETED" && (
                    <div
                      data-testid="payment-status-section"
                      className="job-view-invoice-card job-view-invoice-card-wide"
                      style={{
                        marginTop:
                          "10px",
                        background:
                          "#F8FAFC",
                      }}
                    >
                      <div
                        style={{
                          display:
                            "flex",
                          alignItems:
                            "flex-start",
                          justifyContent:
                            "space-between",
                          gap:
                            "10px",
                          flexWrap:
                            "wrap",
                        }}
                      >
                        <div>
                          <h4
                            className="job-view-section-title"
                            style={{
                              fontSize:
                                "12px",
                            }}
                          >
                            Payment Status
                          </h4>

                          <div
                            style={{
                              marginTop:
                                "3px",
                              fontSize:
                                "10px",
                              color:
                                "#64748B",
                            }}
                          >
                            Backend-authoritative state for the job/invoice
                          </div>
                        </div>

                        {paymentStatusLoading ? (
                          <span
                            aria-label="Loading payment status"
                            style={{
                              display:
                                "inline-flex",
                              alignItems:
                                "center",
                              gap:
                                "5px",
                              padding:
                                "4px 8px",
                              borderRadius:
                                "999px",
                              background:
                                "#EEF2F7",
                              color:
                                "#64748B",
                              fontSize:
                                "9px",
                              fontWeight:
                                700,
                            }}
                          >
                            <Loader2
                              size={
                                11
                              }
                              className="animate-spin"
                            />
                            Loading payment status...
                          </span>
                        ) : paymentStatus ? (
                          (() => {
                            const statusKey =
                              String(
                                paymentStatus.status ||
                                  "UNAVAILABLE"
                              ).toUpperCase();

                            const metaMap: Record<
                              string,
                              {
                                label: string;
                                background: string;
                                color: string;
                              }
                            > = {
                              PENDING: {
                                label:
                                  "PENDING",
                                background:
                                  "#FFF7ED",
                                color:
                                  "#9A3412",
                              },
                              SUCCESSFUL: {
                                label:
                                  "SUCCESSFUL",
                                background:
                                  "#F0FDF4",
                                color:
                                  "#166534",
                              },
                              FAILED: {
                                label:
                                  "FAILED",
                                background:
                                  "#FEF2F2",
                                color:
                                  "#B91C1C",
                              },
                              UNAVAILABLE: {
                                label:
                                  "UNAVAILABLE",
                                background:
                                  "#F1F5F9",
                                color:
                                  "#475569",
                              },
                            };

                            const meta =
                              metaMap[
                                statusKey
                              ] ||
                              metaMap.UNAVAILABLE;

                            return (
                              <span
                                data-testid="payment-status-value"
                                style={{
                                  display:
                                    "inline-flex",
                                  alignItems:
                                    "center",
                                  padding:
                                    "4px 9px",
                                  borderRadius:
                                    "999px",
                                  background:
                                    meta.background,
                                  color:
                                    meta.color,
                                  fontSize:
                                    "9px",
                                  fontWeight:
                                    800,
                                }}
                              >
                                {
                                  meta.label
                                }
                              </span>
                            );
                          })()
                        ) : (
                          <span
                            data-testid="payment-status-value"
                            style={{
                              display:
                                "inline-flex",
                              alignItems:
                                "center",
                              padding:
                                "4px 9px",
                              borderRadius:
                                "999px",
                              background:
                                "#F1F5F9",
                              color:
                                "#475569",
                              fontSize:
                                "9px",
                              fontWeight:
                                800,
                            }}
                          >
                            Unavailable
                          </span>
                        )}
                      </div>

                      {paymentStatusError ? (
                        <div
                          role="alert"
                          style={{
                            marginTop:
                              "8px",
                            padding:
                              "8px",
                            background:
                              "#FEF2F2",
                            border:
                              "1px solid #FECACA",
                            borderRadius:
                              "7px",
                            color:
                              "#7A2020",
                            fontSize:
                              "10px",
                          }}
                        >
                          {
                            paymentStatusError
                          }
                        </div>
                      ) : (
                        <div
                          className="job-view-invoice-summary"
                          style={{
                            marginTop:
                              "9px",
                          }}
                        >
                          <div className="job-view-invoice-card">
                            <span className="job-view-detail-label">
                              Invoice Record
                            </span>

                            <div
                              className="job-view-detail-value"
                              style={{
                                fontSize:
                                  "10px",
                              }}
                            >
                              {paymentStatus?.invoice_id
                                ? `#${paymentStatus.invoice_id}`
                                : "N/A"}
                            </div>
                          </div>

                          <div className="job-view-invoice-card">
                            <span className="job-view-detail-label">
                              Updated At
                            </span>

                            <div
                              className="job-view-detail-value"
                              style={{
                                fontSize:
                                  "10px",
                              }}
                            >
                              {paymentStatus?.updated_at
                                ? new Date(
                                    paymentStatus.updated_at
                                  ).toLocaleString()
                                : "N/A"}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Invoice Loading / Error / Empty / Data */}
                  {invoiceDetailsLoading ? (
                    <div
                      style={{
                        minHeight:
                          "110px",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        justifyContent:
                          "center",
                        gap:
                          "8px",
                        color:
                          "#64748B",
                        fontSize:
                          "10px",
                      }}
                    >
                      <Loader2
                        size={
                          14
                        }
                        className="animate-spin"
                      />
                      Loading invoice...
                    </div>
                  ) : invoiceDetailsError ? (
                    <div
                      role="alert"
                      style={{
                        marginTop:
                          "10px",
                        padding:
                          "10px",
                        background:
                          "#FEF2F2",
                        border:
                          "1px solid #FECACA",
                        color:
                          "#7A2020",
                        borderRadius:
                          "8px",
                        fontSize:
                          "10px",
                      }}
                    >
                      {
                        invoiceDetailsError
                      }
                    </div>
                  ) : !invoiceDetails ? (
                    <div
                      style={{
                        minHeight:
                          "90px",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        justifyContent:
                          "center",
                        textAlign:
                          "center",
                        color:
                          "#64748B",
                        fontSize:
                          "10px",
                      }}
                    >
                      {viewJob.status?.toUpperCase() ===
                      "COMPLETED"
                        ? "No invoice data is currently available for this job."
                        : "Invoice will be available after the job is completed."}
                    </div>
                  ) : (
                    <div
                      style={{
                        marginTop:
                          "10px",
                      }}
                    >
                      <div
                        className="job-view-invoice-summary"
                      >
                        <div className="job-view-invoice-card">
                          <span className="job-view-detail-label">
                            Invoice Record
                          </span>

                          <div className="job-view-detail-value">
                            #
                            {
                              invoiceDetails.id
                            }
                          </div>
                        </div>

                        <div className="job-view-invoice-card">
                          <span className="job-view-detail-label">
                            Customer
                          </span>

                          <div className="job-view-detail-value">
                            {
                              invoiceDetails.customer_name ||
                              "N/A"
                            }
                          </div>
                        </div>

                        <div className="job-view-invoice-card">
                          <span className="job-view-detail-label">
                            Service
                          </span>

                          <div className="job-view-detail-value">
                            {formatServiceType(
                              invoiceDetails.service_type
                            ) ||
                              "N/A"}
                          </div>
                        </div>

                        <div className="job-view-invoice-card">
                          <span className="job-view-detail-label">
                            Completed At
                          </span>

                          <div className="job-view-detail-value">
                            {invoiceDetails.completed_at
                              ? new Date(
                                  invoiceDetails.completed_at
                                ).toLocaleString()
                              : "N/A"}
                          </div>
                        </div>

                        <div className="job-view-invoice-card job-view-invoice-card-wide">
                          <div className="job-view-cost-lines">
                            <div className="job-view-cost-line">
                              <span className="job-view-detail-label">
                                Labour Cost
                              </span>

                              <strong
                                style={{
                                  color:
                                    "#334155",
                                }}
                              >
                                {formatInvoiceCurrency(
                                  Number(
                                    invoiceDetails.labour_cost
                                  )
                                )}
                              </strong>
                            </div>

                            <div className="job-view-cost-line">
                              <span className="job-view-detail-label">
                                Material Cost
                              </span>

                              <strong
                                style={{
                                  color:
                                    "#334155",
                                }}
                              >
                                {formatInvoiceCurrency(
                                  Number(
                                    invoiceDetails.material_cost
                                  )
                                )}
                              </strong>
                            </div>

                            <div
                              className="job-view-cost-line"
                              style={{
                                paddingTop:
                                  "7px",
                                borderTop:
                                  "1px dashed #CBD5E1",
                              }}
                            >
                              <span className="job-view-detail-label">
                                Subtotal
                              </span>

                              <strong
                                style={{
                                  color:
                                    "#166534",
                                }}
                              >
                                {formatInvoiceCurrency(
                                  Number(
                                    invoiceDetails.subtotal
                                  )
                                )}
                              </strong>
                            </div>

                            <div className="job-view-cost-line">
                              <span className="job-view-detail-label">
                                GST (
                                {Number(
                                  invoiceDetails.gst_rate
                                )}
                                %)
                              </span>

                              <strong
                                style={{
                                  color:
                                    "#334155",
                                }}
                              >
                                {formatInvoiceCurrency(
                                  Number(
                                    invoiceDetails.gst_amount
                                  )
                                )}
                              </strong>
                            </div>

                            <div
                              className="job-view-cost-line job-view-cost-total"
                            >
                              <span
                                style={{
                                  fontSize:
                                    "10px",
                                  fontWeight:
                                    800,
                                  color:
                                    "#166534",
                                  textTransform:
                                    "uppercase",
                                }}
                              >
                                Total
                              </span>

                              <strong
                                style={{
                                  color:
                                    "#166534",
                                  fontSize:
                                    "15px",
                                }}
                              >
                                {formatInvoiceCurrency(
                                  Number(
                                    invoiceDetails.total_amount
                                  )
                                )}
                              </strong>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div
                        style={{
                          marginTop:
                            "8px",
                          fontSize:
                            "9px",
                          color:
                            "#64748B",
                          lineHeight:
                            1.4,
                        }}
                      >
                        Invoice preview is based on the persisted backend billing record; no client-side billing calculation is used.
                      </div>
                    </div>
                  )}
                </section>
              </div>
            </div>

            <JobClosureModal
              jobId={
                viewJob.id
              }
              isOpen={
                isClosureModalOpen
              }
              onClose={() =>
                setIsClosureModalOpen(
                  false
                )
              }
              onSuccess={
                handleClosureSuccess
              }
            />
          </div>
        </div>
      )}

      {/* Image Preview */}
      {selectedImage && (
        <div
          style={{
            position:
              "fixed",
            inset: 0,
            zIndex:
              10000,
            background:
              "rgba(15, 23, 42, 0.82)",
            display:
              "flex",
            alignItems:
              "center",
            justifyContent:
              "center",
            padding:
              "24px",
          }}
          onClick={() =>
            setSelectedImage(
              null
            )
          }
          role="dialog"
          aria-modal="true"
          aria-label={
            selectedImageName
          }
        >
          <div
            style={{
              position:
                "relative",
              width:
                "min(92vw, 1000px)",
              height:
                "min(88vh, 820px)",
              background:
                "#FFFFFF",
              borderRadius:
                "14px",
              boxShadow:
                "0 24px 70px rgba(0,0,0,.35)",
              display:
                "flex",
              flexDirection:
                "column",
              overflow:
                "hidden",
            }}
            onClick={(event) =>
              event.stopPropagation()
            }
          >
            <div
              style={{
                display:
                  "flex",
                alignItems:
                  "center",
                justifyContent:
                  "space-between",
                gap:
                  "12px",
                padding:
                  "12px 16px",
                borderBottom:
                  "1px solid #E2E8F0",
                background:
                  "#F8FAFC",
              }}
            >
              <span
                style={{
                  fontSize:
                    "13px",
                  fontWeight:
                    700,
                  color:
                    "#334155",
                  overflowWrap:
                    "anywhere",
                }}
              >
                {
                  selectedImageName
                }
              </span>

              <button
                type="button"
                onClick={() =>
                  setSelectedImage(
                    null
                  )
                }
                aria-label="Close image preview"
                style={{
                  width:
                    "32px",
                  height:
                    "32px",
                  borderRadius:
                    "50%",
                  border:
                    "none",
                  background:
                    "#E2E8F0",
                  color:
                    "#334155",
                  fontSize:
                    "20px",
                  lineHeight:
                    1,
                  cursor:
                    "pointer",
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{
                flex:
                  1,
                display:
                  "flex",
                alignItems:
                  "center",
                justifyContent:
                  "center",
                padding:
                  "18px",
                background:
                  "#0F172A",
                overflow:
                  "auto",
              }}
            >
              <img
                src={
                  selectedImage
                }
                alt={
                  selectedImageName
                }
                style={{
                  maxWidth:
                    "100%",
                  maxHeight:
                    "100%",
                  width:
                    "auto",
                  height:
                    "auto",
                  objectFit:
                    "contain",
                  borderRadius:
                    "8px",
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Job Form Sidebar */}
      <div
        style={{
          ...styles.jobFormSidebar,
          right:
            isFormOpen
              ? 0
              : "-420px",
        }}
      >
        <div
          style={
            styles.sidebarHeader
          }
        >
          <h3
            style={{
              margin:
                0,
              fontSize:
                "16px",
              fontWeight:
                700,
              color:
                "#2F4F3E",
            }}
          >
            {isEditing
              ? "Edit Job"
              : "Create New Job"}
          </h3>

          <button
            type="button"
            style={
              styles.closeSidebar
            }
            onClick={() =>
              setIsFormOpen(
                false
              )
            }
            aria-label="Close job form"
          >
            ×
          </button>
        </div>

        <div
          style={
            styles.sidebarBody
          }
        >
          {apiError && (
            <div
              style={
                styles.alertError
              }
            >
              {apiError}
            </div>
          )}

          <form
            onSubmit={
              handleSubmit
            }
            style={
              styles.jobForm
            }
          >
            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Customer Name{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <input
                type="text"
                name="customer_name"
                value={
                  formData.customer_name
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "customer_name"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                placeholder="Enter customer name"
                style={
                  getInputStyle(
                    "customer_name",
                    !!errors.customer_name
                  )
                }
              />

              {errors.customer_name && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.customer_name
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Location{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <input
                type="text"
                name="location"
                value={
                  formData.location
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "location"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                placeholder="Enter location"
                style={
                  getInputStyle(
                    "location",
                    !!errors.location
                  )
                }
              />

              {errors.location && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.location
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Priority{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <select
                name="priority"
                value={
                  formData.priority
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "priority"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  getInputStyle(
                    "priority",
                    !!errors.priority
                  )
                }
              >
                <option value="">
                  Select priority
                </option>

                {priorities.map(
                  (priority) => (
                    <option
                      key={
                        priority.value
                      }
                      value={
                        priority.value
                      }
                    >
                      {
                        priority.label
                      }
                    </option>
                  )
                )}
              </select>

              {errors.priority && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.priority
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Service Type{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <select
                name="service_type"
                value={
                  formData.service_type
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "service_type"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  getInputStyle(
                    "service_type",
                    !!errors.service_type
                  )
                }
              >
                <option value="">
                  Select service type
                </option>

                {getFormServiceTypes().map(
                  (service) => (
                    <option
                      key={
                        service.value
                      }
                      value={
                        service.value
                      }
                    >
                      {
                        service.label
                      }
                    </option>
                  )
                )}
              </select>

              {errors.service_type && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.service_type
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Contact Number{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <input
                type="text"
                name="contact_number"
                value={
                  formData.contact_number
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "contact_number"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                placeholder="9876543210"
                maxLength={
                  10
                }
                style={
                  getInputStyle(
                    "contact_number",
                    !!errors.contact_number
                  )
                }
              />

              {errors.contact_number && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.contact_number
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Preferred Service Date{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <input
                type="date"
                name="preferred_service_date"
                value={
                  formData.preferred_service_date
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "preferred_service_date"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  getInputStyle(
                    "preferred_service_date",
                    !!errors.preferred_service_date
                  )
                }
              />

              {errors.preferred_service_date && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.preferred_service_date
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Status{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <select
                name="status"
                value={
                  formData.status
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "status"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  getInputStyle(
                    "status"
                  )
                }
              >
                <option value="active">
                  Active
                </option>
                <option value="QUEUED">
                  Queued (Dispatch Queue)
                </option>
                <option value="ESCALATED">
                  Escalated (SLA Escalations)
                </option>
                <option value="in progress">
                  In Progress
                </option>
                <option value="completed">
                  Completed
                </option>
                <option value="cancelled">
                  Cancelled
                </option>
              </select>
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Tenant ID{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>{" "}
                <span
                  style={{
                    fontSize:
                      "11px",
                    color:
                      "#6B7280",
                    fontWeight:
                      400,
                  }}
                >
                  (Active Session)
                </span>
              </label>

              <input
                type="text"
                name="tenant_id"
                value={
                  formData.tenant_id
                }
                readOnly
                style={{
                  ...getInputStyle(
                    "tenant_id"
                  ),
                  background:
                    "#EEF2F6",
                  cursor:
                    "not-allowed",
                }}
              />
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                SLA Deadline (Optional)
              </label>

              <input
                type="datetime-local"
                name="sla_deadline"
                value={
                  formData.sla_deadline ||
                  ""
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "sla_deadline"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                style={
                  getInputStyle(
                    "sla_deadline"
                  )
                }
              />
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Attempt Count (Optional)
              </label>

              <input
                type="number"
                name="attempt_count"
                value={
                  formData.attempt_count ??
                  0
                }
                onChange={
                  handleChange
                }
                min={
                  0
                }
                placeholder="0"
                style={
                  getInputStyle(
                    "attempt_count"
                  )
                }
              />
            </div>

            <div
              style={
                styles.formGroup
              }
            >
              <label
                style={
                  styles.formLabel
                }
              >
                Issue Description{" "}
                <span
                  style={
                    styles.req
                  }
                >
                  *
                </span>
              </label>

              <textarea
                name="issue_description"
                value={
                  formData.issue_description
                }
                onChange={
                  handleChange
                }
                onFocus={() =>
                  setFocusedInput(
                    "issue_description"
                  )
                }
                onBlur={() =>
                  setFocusedInput(
                    null
                  )
                }
                placeholder="Describe the issue in detail..."
                rows={
                  4
                }
                style={
                  getInputStyle(
                    "issue_description",
                    !!errors.issue_description
                  )
                }
              />

              {errors.issue_description && (
                <span
                  style={
                    styles.fieldError
                  }
                >
                  {
                    errors.issue_description
                  }
                </span>
              )}
            </div>

            <div
              style={
                styles.formActions
              }
            >
              <button
                type="submit"
                disabled={
                  loading
                }
                style={
                  loading
                    ? {
                        ...styles.btnPrimary,
                        background:
                          "#A8CDB5",
                        cursor:
                          "not-allowed",
                        boxShadow:
                          "none",
                      }
                    : hoveredBtn ===
                        "submit"
                      ? {
                          ...styles.btnPrimary,
                          background:
                            "#5C9470",
                        }
                      : styles.btnPrimary
                }
                onMouseEnter={() =>
                  setHoveredBtn(
                    "submit"
                  )
                }
                onMouseLeave={() =>
                  setHoveredBtn(
                    null
                  )
                }
              >
                {loading
                  ? "Submitting..."
                  : isEditing
                    ? "Update Job"
                    : "Create Job"}
              </button>

              <button
                type="button"
                style={
                  hoveredBtn ===
                  "cancel"
                    ? {
                        ...styles.btnSecondary,
                        background:
                          "#EAF4EE",
                        borderColor:
                          "#7AAE8A",
                      }
                    : styles.btnSecondary
                }
                onClick={
                  handleCancelEdit
                }
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>

      {isFormOpen && (
        <div
          style={
            styles.sidebarOverlay
          }
          onClick={() =>
            setIsFormOpen(
              false
            )
          }
        />
      )}
    </div>
  );
}

function imageUnavailableLabel(
  imageName: string,
  unavailable: boolean
) {
  return unavailable
    ? `${imageName} — unavailable`
    : imageName;
}

const formatInvoiceCurrency = (
  value: number
) =>
  new Intl.NumberFormat(
    "en-IN",
    {
      style:
        "currency",
      currency:
        "INR",
      minimumFractionDigits:
        2,
      maximumFractionDigits:
        2,
    }
  ).format(
    Number.isFinite(
      value
    )
      ? value
      : 0
  );

const styles = {
  jobsPage: {
    fontFamily:
      "'Inter', sans-serif",
    background:
      "#EEF4F1",
    height:
      "100%",
    maxHeight:
      "100%",
    padding:
      "10px 14px",
    color:
      "#1F2933",
    display:
      "flex",
    flexDirection:
      "column",
    boxSizing:
      "border-box",
    overflow:
      "hidden",
  } as React.CSSProperties,

  popupOverlay: {
    position:
      "fixed",
    inset: 0,
    background:
      "rgba(31, 41, 51, 0.4)",
    zIndex:
      2000,
    display:
      "flex",
    alignItems:
      "center",
    justifyContent:
      "center",
  } as React.CSSProperties,

  successPopup: {
    background:
      "#FFFFFF",
    borderRadius:
      "16px",
    padding:
      "32px",
    maxWidth:
      "380px",
    width:
      "90%",
    textAlign:
      "center",
    boxShadow:
      "0 20px 50px rgba(47, 79, 62, 0.15)",
  } as React.CSSProperties,

  successIcon: {
    width:
      "52px",
    height:
      "52px",
    background:
      "#DDEEE5",
    color:
      "#2F4F3E",
    borderRadius:
      "50%",
    display:
      "flex",
    alignItems:
      "center",
    justifyContent:
      "center",
    fontSize:
      "24px",
    fontWeight:
      800,
    margin:
      "0 auto 14px",
  } as React.CSSProperties,

  jobIdBox: {
    background:
      "#F6FAF8",
    borderRadius:
      "6px",
    padding:
      "6px 14px",
    fontSize:
      "13px",
    color:
      "#2F4F3E",
    marginBottom:
      "10px",
    display:
      "inline-block",
    border:
      "1px solid #E3ECE7",
  } as React.CSSProperties,

  popupCloseBtn: {
    background:
      "#7AAE8A",
    color:
      "#FFFFFF",
    border:
      "none",
    padding:
      "10px 28px",
    borderRadius:
      "8px",
    fontWeight:
      700,
    fontSize:
      "13px",
    cursor:
      "pointer",
  } as React.CSSProperties,

  mainContentRow: {
    display:
      "flex",
    flexDirection:
      "column",
    flex: 1,
    overflow:
      "hidden",
    boxSizing:
      "border-box",
  } as React.CSSProperties,

  contentCard: {
    background:
      "#FFFFFF",
    borderRadius:
      "12px",
    padding:
      "8px 16px",
    boxShadow:
      "0 1px 4px rgba(47, 79, 62, 0.07)",
    border:
      "1px solid #E3ECE7",
    display:
      "flex",
    flexDirection:
      "column",
    flex: 1,
    overflow:
      "hidden",
    boxSizing:
      "border-box",
  } as React.CSSProperties,

  cardHeader: {
    display:
      "flex",
    justifyContent:
      "space-between",
    alignItems:
      "center",
    flexWrap:
      "wrap",
    gap:
      "8px",
    marginBottom:
      "6px",
    paddingBottom:
      "6px",
    borderBottom:
      "1px solid #E3ECE7",
  } as React.CSSProperties,

  cardSubtitle: {
    fontSize:
      "12px",
    color:
      "#6B7280",
    margin:
      "1px 0 0 0",
  } as React.CSSProperties,

  headerActionsRow: {
    display:
      "flex",
    gap:
      "8px",
  } as React.CSSProperties,

  refreshIconBtn: {
    background:
      "#FFFFFF",
    border:
      "1px solid #E3ECE7",
    color:
      "#2F4F3E",
    padding:
      "7px 14px",
    borderRadius:
      "8px",
    fontWeight:
      600,
    fontSize:
      "12px",
    cursor:
      "pointer",
    transition:
      "all .2s",
    boxShadow:
      "0 1px 3px rgba(47,79,62,.06)",
  } as React.CSSProperties,

  filtersRow: {
    display:
      "grid",
    gridTemplateColumns:
      "2fr 1fr 1fr 1fr 1fr",
    gap:
      "8px",
    marginBottom:
      "4px",
  } as React.CSSProperties,

  filterGroup: {
    display:
      "flex",
    flexDirection:
      "column",
    gap:
      "2px",
  } as React.CSSProperties,

  filterLabel: {
    fontSize:
      "10px",
    fontWeight:
      700,
    color:
      "#6B7280",
    textTransform:
      "uppercase",
    letterSpacing:
      ".05em",
  } as React.CSSProperties,

  filterInput: {
    padding:
      "5px 8px",
    border:
      "1.5px solid #E3ECE7",
    borderRadius:
      "8px",
    fontSize:
      "12px",
    color:
      "#1F2933",
    outline:
      "none",
    transition:
      "border-color .2s",
    background:
      "#FFFFFF",
  } as React.CSSProperties,

  filterInputFocus: {
    borderColor:
      "#7AAE8A",
    boxShadow:
      "0 0 0 2px rgba(122,174,138,.12)",
  } as React.CSSProperties,

  resultsCount: {
    fontSize:
      "11px",
    color:
      "#6B7280",
    fontWeight:
      500,
    marginBottom:
      "4px",
  } as React.CSSProperties,

  tableContainer: {
    width:
      "100%",
    overflowX:
      "auto",
    overflowY:
      "auto",
    flex:
      1,
    minHeight:
      0,
    boxSizing:
      "border-box",
    WebkitOverflowScrolling:
      "touch",
  } as React.CSSProperties,

  dashboardTable: {
    width:
      "100%",
    minWidth:
      "950px",
    borderCollapse:
      "collapse",
    tableLayout:
      "auto",
  } as React.CSSProperties,

  th: {
    background:
      "#F6FAF8",
    padding:
      "0 10px",
    height:
      "32px",
    textAlign:
      "left",
    fontSize:
      "9.5px",
    fontWeight:
      700,
    color:
      "#6B7280",
    textTransform:
      "uppercase",
    letterSpacing:
      "0.05em",
    borderBottom:
      "1px solid #E3ECE7",
    whiteSpace:
      "nowrap",
    overflow:
      "hidden",
    textOverflow:
      "ellipsis",
  } as React.CSSProperties,

  td: {
    padding:
      "4px 10px",
    fontSize:
      "11.5px",
    color:
      "#1F2933",
    borderBottom:
      "1px solid #F0F6F2",
    verticalAlign:
      "middle",
  } as React.CSSProperties,

  jobIdCell: {
    display:
      "flex",
    alignItems:
      "center",
    gap:
      "6px",
    fontWeight:
      700,
    color:
      "#5C9470",
  } as React.CSSProperties,

  customerCell: {
    fontWeight:
      600,
    color:
      "#2F4F3E",
  } as React.CSSProperties,

  issueSub: {
    display:
      "block",
    fontSize:
      "11.5px",
    color:
      "#6B7280",
    fontWeight:
      400,
    marginTop:
      "2px",
    whiteSpace:
      "nowrap",
    overflow:
      "hidden",
    textOverflow:
      "ellipsis",
  } as React.CSSProperties,

  viewJobModal: {
    background:
      "#FFFFFF",
    borderRadius:
      "16px",
    padding:
      0,
    maxWidth:
      "460px",
    width:
      "94%",
    boxShadow:
      "0 20px 50px rgba(47,79,62,.18)",
    overflow:
      "hidden",
  } as React.CSSProperties,

  viewModalHeader: {
    display:
      "flex",
    alignItems:
      "center",
    justifyContent:
      "space-between",
    gap:
      "12px",
    padding:
      "14px 18px",
    borderBottom:
      "1px solid #E3ECE7",
    background:
      "#F6FAF8",
  } as React.CSSProperties,

  viewModalHeaderTitle: {
    fontSize:
      "15px",
    fontWeight:
      750,
    color:
      "#2F4F3E",
    margin:
      0,
  } as React.CSSProperties,

  jobFormSidebar: {
    position:
      "fixed",
    top:
      0,
    right:
      0,
    width:
      "min(420px, 100vw)",
    maxWidth:
      "100vw",
    height:
      "100vh",
    background:
      "#FFFFFF",
    zIndex:
      2000,
    boxShadow:
      "-4px 0 24px rgba(47,79,62,.1)",
    display:
      "flex",
    flexDirection:
      "column",
    boxSizing:
      "border-box",
    transition:
      "right .3s cubic-bezier(0.4, 0, 0.2, 1)",
  } as React.CSSProperties,

  sidebarHeader: {
    padding:
      "20px 24px",
    borderBottom:
      "1px solid #E3ECE7",
    display:
      "flex",
    justifyContent:
      "space-between",
    alignItems:
      "center",
    background:
      "#F8FBF9",
  } as React.CSSProperties,

  closeSidebar: {
    background:
      "none",
    border:
      "none",
    fontSize:
      "22px",
    color:
      "#6B7280",
    cursor:
      "pointer",
    width:
      "32px",
    height:
      "32px",
    borderRadius:
      "6px",
    display:
      "flex",
    alignItems:
      "center",
    justifyContent:
      "center",
  } as React.CSSProperties,

  sidebarBody: {
    flex:
      1,
    overflowY:
      "auto",
    padding:
      "24px",
  } as React.CSSProperties,

  sidebarOverlay: {
    position:
      "fixed",
    inset: 0,
    background:
      "rgba(31,41,51,.35)",
    zIndex:
      1999,
    backdropFilter:
      "blur(2px)",
  } as React.CSSProperties,

  jobForm: {
    display:
      "flex",
    flexDirection:
      "column",
    gap:
      "12px",
  } as React.CSSProperties,

  formGroup: {
    display:
      "flex",
    flexDirection:
      "column",
    gap:
      "4px",
  } as React.CSSProperties,

  formLabel: {
    fontSize:
      "12px",
    fontWeight:
      600,
    color:
      "#2F4F3E",
    marginBottom:
      "4px",
  } as React.CSSProperties,

  req: {
    color:
      "#D96C6C",
  } as React.CSSProperties,

  formInput: {
    padding:
      "9px 12px",
    border:
      "1.5px solid #E3ECE7",
    borderRadius:
      "8px",
    fontSize:
      "13px",
    fontFamily:
      "'Inter', sans-serif",
    color:
      "#1F2933",
    background:
      "#FFFFFF",
    outline:
      "none",
    width:
      "100%",
    transition:
      "border-color .2s, box-shadow .2s",
  } as React.CSSProperties,

  formInputFocus: {
    borderColor:
      "#7AAE8A",
    boxShadow:
      "0 0 0 3px rgba(122, 174, 138, 0.15)",
  } as React.CSSProperties,

  inputError: {
    borderColor:
      "#D96C6C",
    boxShadow:
      "0 0 0 2px rgba(217,108,108,.1)",
  } as React.CSSProperties,

  fieldError: {
    fontSize:
      "11px",
    color:
      "#D96C6C",
    marginTop:
      "2px",
  } as React.CSSProperties,

  alertError: {
    background:
      "#FDF2F2",
    color:
      "#9B3A3A",
    border:
      "1px solid #F5C6C6",
    borderRadius:
      "8px",
    padding:
      "10px 14px",
    fontSize:
      "12px",
    fontWeight:
      500,
    marginBottom:
      "14px",
  } as React.CSSProperties,

  formActions: {
    display:
      "flex",
    gap:
      "10px",
    marginTop:
      "10px",
  } as React.CSSProperties,

  btnPrimary: {
    background:
      "#7AAE8A",
    color:
      "#FFFFFF",
    border:
      "none",
    padding:
      "10px 20px",
    borderRadius:
      "8px",
    fontWeight:
      700,
    fontSize:
      "13px",
    cursor:
      "pointer",
    flex:
      1,
  } as React.CSSProperties,

  btnSecondary: {
    background:
      "#F6FAF8",
    color:
      "#2F4F3E",
    border:
      "1.5px solid #E3ECE7",
    padding:
      "10px 16px",
    borderRadius:
      "8px",
    fontWeight:
      600,
    fontSize:
      "13px",
    cursor:
      "pointer",
  } as React.CSSProperties,

  jobsPagination: {
    display:
      "flex",
    alignItems:
      "center",
    justifyContent:
      "space-between",
    padding:
      "6px 0 0 0",
    borderTop:
      "1px solid #E3ECE7",
    flexWrap:
      "wrap",
    gap:
      "6px",
    marginTop:
      "6px",
  } as React.CSSProperties,

  jobsPageInfo: {
    fontSize:
      "11px",
    color:
      "#6B7280",
    fontWeight:
      500,
  } as React.CSSProperties,

  jobsPageControls: {
    display:
      "flex",
    alignItems:
      "center",
    gap:
      "6px",
  } as React.CSSProperties,

  jobsPageBtn: {
    padding:
      "3px 8px",
    background:
      "#FFFFFF",
    border:
      "1.5px solid #E3ECE7",
    borderRadius:
      "6px",
    fontSize:
      "10px",
    fontWeight:
      600,
    color:
      "#2F4F3E",
    cursor:
      "pointer",
  } as React.CSSProperties,

  jobsPageNumbers: {
    display:
      "flex",
    gap:
      "4px",
  } as React.CSSProperties,

  jobsPageNum: {
    width:
      "22px",
    height:
      "22px",
    borderRadius:
      "6px",
    border:
      "1.5px solid #E3ECE7",
    background:
      "#FFFFFF",
    fontSize:
      "10px",
    fontWeight:
      600,
    color:
      "#6B7280",
    cursor:
      "pointer",
    padding:
      0,
    display:
      "flex",
    alignItems:
      "center",
    justifyContent:
      "center",
  } as React.CSSProperties,

  iconActionBtn: {
    display:
      "inline-flex",
    alignItems:
      "center",
    justifyContent:
      "center",
    width:
      "28px",
    height:
      "28px",
    border:
      "none",
    background:
      "none",
    padding:
      0,
    cursor:
      "pointer",
    outline:
      "none",
  } as React.CSSProperties,
};

export default JobCreationForm;