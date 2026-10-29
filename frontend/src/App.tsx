import { useState, useEffect, useRef, lazy, Suspense } from "react";
import logo from "./assets/logo.png";
import {
  Search,
  ChevronsLeft,
  ChevronsRight,
  LayoutDashboard,
  Briefcase,
  Users,
  Calendar,
  User,
  Activity,
  BellRing,
  LogOut,
  History,
  Settings,
  PlusCircle,
  FileText,
  Navigation,
  Headphones,
  Bell,
  ChevronDown,
  Menu,
  MapPin,
  Wrench,
} from "lucide-react";
import useAuthStore from "./store/authStore";
import NotificationBell from "./components/notifications/NotificationBell";
// Import notification modules
import NotificationDrawer from "./components/notifications/NotificationDrawer";
import NotificationDetail from "./components/notifications/NotificationDetail";
import ToastContainer from "./components/notifications/ToastContainer";
import {
  fetchNotifications,
  markNotificationAsRead,
  connectNotificationSocket,
  disconnectNotificationSocket,
  subscribeToDispatchEvents,
  createToastFromNotification,
  acceptJob,
  rejectJob,
  reassignJob,
  batchMarkAsRead,
  dismissNotification,
} from "./services/notificationService";
import {
  startHeartbeatLoop,
  stopHeartbeatLoop,
} from "./services/heartbeatService";
import {
  getAdminCustomerSupportRequests,
  getCustomerProfile,
} from "./services/customerPortalService";
import ErrorBoundary from "./components/ui/ErrorBoundary";
import SuperAdminServicesPage from "./pages/SuperAdminServicesPage";
import { ToastProvider, useToast } from "./hooks/useToast";
import LoadingSpinner from "./components/ui/LoadingSpinner";
import TechnicianLocationTracker from "./components/technician/TechnicianLocationTracker";
import TechnicianAvailabilityLocation from "./components/technician/TechnicianAvailabilityLocation";
import CustomerSupportWidget from "./components/customer/CustomerSupportWidget";

// Lazy load page components
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ResetPasswordPage = lazy(
  () => import("./pages/ResetPasswordPage"),
);
const OrganizationOnboardingPage = lazy(
  () => import("./pages/OrganizationOnboardingPage"),
);
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const JobsPage = lazy(() => import("./pages/JobsPage"));
const TechniciansDispatchersPage = lazy(
  () => import("./pages/TechniciansDispatchersPage"),
);
const PlanningPage = lazy(() => import("./pages/PlanningPage"));
const TrackingDashboardPage = lazy(
  () => import("./pages/OrganizationLiveTrackingPage"),
);
const ProfilePage = lazy(() => import("./pages/ProfilePage"));

// Lazy load Technician Portal pages
const TechnicianPortalDashboard = lazy(
  () => import("./pages/technician/TechnicianPortalDashboard"),
);
const TechnicianProfilePage = lazy(
  () => import("./pages/technician/TechnicianProfilePage"),
);
const TechnicianJobsPage = lazy(
  () => import("./pages/technician/TechnicianJobsPage"),
);
const TechnicianJobHistoryPage = lazy(
  () => import("./pages/technician/TechnicianJobHistoryPage"),
);
const TechnicianBillingReportPage = lazy(
  () => import("./pages/technician/TechnicianBillingReportPage"),
);

const TechnicianPerformanceReportPage = lazy(
  () =>
    import(
      "./pages/technician/TechnicianPerformanceReportPage"
    ),
);

const TechnicianNotificationsPage = lazy(
  () => import("./pages/technician/TechnicianNotificationsPage"),
);
const TechnicianSettingsPage = lazy(
  () => import("./pages/technician/TechnicianSettingsPage"),
);

// Lazy load Customer Portal pages
const CustomerPortalDashboard = lazy(
  () => import("./pages/customer/CustomerPortalDashboard"),
);
const CustomerProfilePage = lazy(
  () => import("./pages/customer/CustomerProfilePage"),
);
const CustomerServiceRequestsPage = lazy(
  () => import("./pages/customer/CustomerServiceRequestsPage"),
);
const CustomerJobTrackingPage = lazy(
  () => import("./pages/customer/CustomerTrackingPage"),
);
const CustomerNotificationsPage = lazy(
  () => import("./pages/customer/CustomerNotificationsPage"),
);
const CustomerServiceHistoryPage = lazy(
  () => import("./pages/customer/CustomerServiceHistoryPage"),
);
const CustomerInvoicePage = lazy(
  () => import("./pages/customer/CustomerInvoicePage"),
);
const CustomerSettingsPage = lazy(
  () => import("./pages/customer/CustomerSettingsPage"),
);

const CustomerSupportPage = lazy(
  () => import("./pages/customer/CustomerSupportPage"),
);

interface NotificationItem {
  id: string | number;
  type: string;
  title: string;
  message: string;
  isRead: boolean;
  createdAt: string;
  jobId?: string | number;
  job?: any;
}

const styles = {
  appShell: {
  display: "flex",
  minHeight: "100vh",
  height: "100vh",
  paddingTop: "72px",
  boxSizing: "border-box",
  overflow: "hidden",
  fontFamily: "'Inter', sans-serif",
} as React.CSSProperties,

  sidebar: {
    width: "220px",
    minWidth: "220px",
    background: "#EAF4EE",
    borderRight: "1px solid #E3ECE7",
    display: "flex",
    flexDirection: "column",
    position: "relative",
    height: "calc(100vh - 72px)",
    zIndex: 200,
    boxShadow: "2px 0 8px rgba(47, 79, 62, 0.04)",
    transition:
      "width 0.3s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    boxSizing: "border-box",
  } as React.CSSProperties,

  sidebarCollapsed: {
    width: "60px",
    minWidth: "60px",
  } as React.CSSProperties,

  sidebarMobile: {
    width: "100%",
    minWidth: 0,
    height: "64px",
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    top: "auto",
    display: "flex",
    flexDirection: "row",
    alignItems: "center",
    borderRight: "none",
    borderTop: "1px solid #E3ECE7",
    padding: "4px 6px",
    overflow: "hidden",
    boxShadow: "0 -2px 8px rgba(47, 79, 62, 0.06)",
    zIndex: 9999,
    background: "#EAF4EE",
    boxSizing: "border-box",
  } as React.CSSProperties,

  sidebarContent: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    flex: 1,
    padding: "0px 12px",
    boxSizing: "border-box",
    overflowY: "auto",
    overflowX: "hidden",
  } as React.CSSProperties,

  sidebarContentCollapsed: {
  padding: "0px 6px",
} as React.CSSProperties,

  sidebarContentMobile: {
    display: "flex",
    flexDirection: "row",
    height: "100%",
    padding: 0,
    overflowX: "auto",
    overflowY: "hidden",
    alignItems: "center",
    width: "100%",
    minWidth: 0,
    boxSizing: "border-box",
  } as React.CSSProperties,

  sidebarBrand: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    padding: "4px 0 14px",
    marginBottom: "8px",
  } as React.CSSProperties,

  brandLogoWrap: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
  } as React.CSSProperties,

  brandLogoImg: {
    width: "90px",
    objectFit: "contain",
    display: "block",
    transition:
      "width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
  } as React.CSSProperties,

  sidebarNav: {
  display: "flex",
  flexDirection: "column",
  gap: "2px",
  flex: 1,
  marginTop: "0px",
} as React.CSSProperties,

  sidebarNavMobile: {
    display: "flex",
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "center",
    width: "100%",
    minWidth: 0,
    height: "100%",
    marginTop: 0,
    gap: 0,
    flex: 1,
  } as React.CSSProperties,

  navGroupLabel: {
    fontSize: "10px",
    fontWeight: 700,
    color: "#7AAE8A",
    letterSpacing: ".08em",
    textTransform: "uppercase",
    padding: "0 6px",
    marginBottom: "6px",
  } as React.CSSProperties,

  navItem: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    width: "100%",
    padding: "8px 10px 8px 6px",
    border: "none",
    borderRadius: "8px",
    background: "transparent",
    color: "#6B7280",
    fontSize: "13px",
    fontWeight: 500,
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    textAlign: "left",
    transition: "all .15s",
    whiteSpace: "nowrap",
    overflow: "hidden",
  } as React.CSSProperties,

  navItemMobile: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "2px",
    fontSize: "8px",
    padding: "3px 2px",
    borderRadius: "6px",
    width: "auto",
    minWidth: 0,
    height: "56px",
    flex: "1 1 0",
    textAlign: "center",
    whiteSpace: "nowrap",
    overflow: "hidden",
  } as React.CSSProperties,

  navItemCollapsed: {
    justifyContent: "center",
    padding: "8px 0",
    gap: 0,
  } as React.CSSProperties,

  navActive: {
    background: "#DDEEE5",
    color: "#2F4F3E",
    fontWeight: 700,
    boxShadow: "inset 3px 0 0 #7AAE8A",
  } as React.CSSProperties,

  navActiveMobile: {
    boxShadow: "none",
    borderBottom: "2px solid #7AAE8A",
    borderRadius: 0,
    background: "transparent",
  } as React.CSSProperties,

  navGroup: {
    display: "flex",
    flexDirection: "column",
    margin: "4px 0",
  } as React.CSSProperties,

  navGroupMobile: {
    display: "flex",
    flexDirection: "row",
    margin: 0,
    alignItems: "center",
  } as React.CSSProperties,

  navGroupHeader: {
    fontSize: "13.5px",
    fontWeight: 600,
    color: "#6B7280",
    padding: "6px 8px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    textAlign: "left",
    letterSpacing: "0.01em",
    transition: "color 0.2s ease",
    whiteSpace: "nowrap",
    overflow: "hidden",
  } as React.CSSProperties,

  navGroupItems: {
    display: "flex",
    flexDirection: "column",
    gap: "3px",
    marginLeft: "10px",
    borderLeft: "1.5px solid #E3ECE7",
    paddingLeft: "4px",
  } as React.CSSProperties,

  navGroupItemsMobile: {
    display: "flex",
    flexDirection: "row",
    gap: "4px",
    marginLeft: 0,
    borderLeft: "none",
    paddingLeft: 0,
  } as React.CSSProperties,

  sidebarToggle: {
    position: "absolute",
    top: "8px",
    right: "12px",
    width: "30px",
    height: "30px",
    border: "none",
    background: "transparent",
    color: "#7AAE8A",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    zIndex: 300,
    transition:
      "color 0.2s ease, transform 0.2s ease",
  } as React.CSSProperties,

    sidebarToggleCollapsed: {
    right: "15px",
    top: "8px",
  } as React.CSSProperties,

  sidebarProfileMini: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "10px 8px",
    borderTop: "1px solid #E3ECE7",
    marginTop: "auto",
    flexShrink: 0,
    transition:
      "padding 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
  } as React.CSSProperties,

  sidebarProfileMiniCollapsed: {
    flexDirection: "column",
    alignItems: "center",
    gap: "12px",
    padding: "12px 0",
    borderTop: "1px solid #E3ECE7",
    marginTop: "auto",
    flexShrink: 0,
  } as React.CSSProperties,

  miniAvatar: {
    width: "32px",
    height: "32px",
    minWidth: "32px",
    borderRadius: "50%",
    background: "#7AAE8A",
    color: "#fff",
    fontSize: "13px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  miniInfo: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  miniName: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#1F2933",
  } as React.CSSProperties,

  miniRole: {
    fontSize: "10px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  mainArea: {
    flex: 1,
    height: "calc(100vh - 72px)",
    display: "flex",
    flexDirection: "column",
    minWidth: 0,
  } as React.CSSProperties,

  mainAreaMobile: {
    marginLeft: 0,
    marginBottom: "64px",
    height: "calc(100vh - 72px - 64px)",
    width: "100%",
  } as React.CSSProperties,

  pageWrap: {
    flex: 1,
    background: "#EEF4F1",
    overflowY: "hidden",
    height: 0,
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  pageWrapMobile: {
    paddingBottom: "10px",
  } as React.CSSProperties,
};

const localCss = `
  .nav-item-style:hover {
    background-color: #EAF4EE !important;
    color: #2F4F3E !important;
  }

  .nav-group-header-style:hover {
    color: #2F4F3E !important;
  }

  .nav-group-header-style:hover .chevron-icon-style {
    color: #2F4F3E !important;
  }

  .sidebar-toggle-style:hover {
    color: #5C9470 !important;
    transform: scale(1.2) !important;
  }

  .sidebar-content-style::-webkit-scrollbar {
    display: none !important;
  }

`;

function AppInner() {
  const { user, accessToken, logout } = useAuthStore();
  console.log("AUTH USER:", user);
  const { addToast } = useToast();
  useEffect(() => {
  const handleSSOCallback = async () => {
    if (window.location.pathname !== "/auth/sso/callback") {
      return;
    }

    try {
      localStorage.setItem("auth_mode", "sso");

      const success = await useAuthStore
        .getState()
        .loadFromSession();

      if (success) {
        window.history.replaceState({}, "", "/");
      } else {
        localStorage.removeItem("auth_mode");
        window.location.href = "/login";
      }
    } catch (error) {
      console.error("SSO session initialization failed:", error);

      localStorage.removeItem("auth_mode");
      window.location.href = "/login";
    }
  };

  handleSSOCallback();
}, []);

  const userRole =
    (user?.role || "").toLowerCase();

  const isTechnician =
    userRole === "technician";
  const [
  technicianAvailability,
  setTechnicianAvailability,
] = useState("Not Available");

  const isCustomer =
    userRole === "customer";

  const isDispatcher =
    userRole === "dispatcher";

  const isSuperAdmin =
    userRole === "super_admin" ||
    userRole === "admin" ||
    userRole === "head" ||
    (user as any)?.role === "super_admin" ||
    (user as any)?.role === "admin" ||
    (user as any)?.is_superadmin === true;

  const isAdminOrDispatcher =
    !isTechnician && !isCustomer;

  const [activeTab, setActiveTab] =
    useState(() => {
      if (
        isCustomer &&
        new URLSearchParams(window.location.search).get("tab") ===
          "cust_invoices"
      ) {
        return "cust_invoices";
      }

      if (isTechnician)
        return "tech_dashboard";

      if (isCustomer)
        return "cust_requests";

      return "dashboard";
    });

  const isTechnicianShell = isTechnician;

  useEffect(() => {
    if (
      isCustomer &&
      new URLSearchParams(window.location.search).get("tab") ===
        "cust_invoices"
    ) {
      setActiveTab("cust_invoices");
    }
  }, [isCustomer]);

  const [previousCustomerTab, setPreviousCustomerTab] =
    useState<string>("cust_requests");
  const [selectedCustomerNotificationId, setSelectedCustomerNotificationId] =
    useState<string | null>(null);

  const [customerLocation, setCustomerLocation] =
    useState("Chennai, Tamil Nadu");

  const [customerName, setCustomerName] = useState(() => {
    if (user?.first_name && user.first_name.toLowerCase() !== "carl") {
      return `${user.first_name} ${user.last_name || ""}`.trim();
    }
    return "lincy";
  });

  useEffect(() => {
    if (!isCustomer) return;
    let active = true;

    const handleProfileData = (profile: any) => {
      if (!profile) return;
      if (profile.city && profile.state) {
        setCustomerLocation(`${profile.city}, ${profile.state}`);
      } else if (profile.city) {
        setCustomerLocation(profile.city);
      } else if (profile.address) {
        setCustomerLocation(profile.address);
      }

      if (profile.full_name && profile.full_name.trim()) {
        const cleaned = profile.full_name.trim();
        if (cleaned.toLowerCase() !== "carl customer" && cleaned.toLowerCase() !== "carl") {
          setCustomerName(cleaned);
        } else {
          setCustomerName("lincy");
        }
      } else if (user?.first_name && user.first_name.toLowerCase() !== "carl") {
        setCustomerName(`${user.first_name} ${user.last_name || ""}`.trim());
      }
    };

    const fetchProfile = () => {
      getCustomerProfile()
        .then((res: any) => {
          if (!active) return;
          handleProfileData(res?.data);
        })
        .catch(() => {});
    };

    fetchProfile();

    const onProfileUpdated = (event: any) => {
      if (event?.detail) {
        handleProfileData(event.detail);
      } else {
        fetchProfile();
      }
    };

    window.addEventListener("customer-profile-updated", onProfileUpdated);

    return () => {
      active = false;
      window.removeEventListener("customer-profile-updated", onProfileUpdated);
    };
  }, [isCustomer, activeTab, user]);

  const [sidebarCollapsed, setSidebarCollapsed] =
    useState(false);

  const [timeRange, setTimeRange] = useState("week");
  const [
  selectedCompletedJobForView,
  setSelectedCompletedJobForView,
] = useState<any | null>(null);

  const [isNavigating, setIsNavigating] =
    useState(false);

  const handleTabChange = (
    tab: string,
  ) => {
    let targetTab = tab;
    if (targetTab === "my_requests") {
      targetTab = "cust_requests";
    }
    // The standalone Jobs module is removed; use Planning for job workflows.
    if (targetTab === "jobs") {
      targetTab = "planning";
    }
    if (targetTab === activeTab) return;

    setIsNavigating(true);
    setActiveTab(targetTab);

    setTimeout(() => {
      setIsNavigating(false);
    }, 400);
  };

  const getLoadingMessage = (
    tab: string,
  ) => {
    switch (tab) {
      case "dashboard":
        return "Assembling Operations Center Dashboard...";

      case "jobs":
        return "Loading Jobs & Service Requests...";

      case "techboard":
        return "Loading Technician Dashboard...";

      case "dispatchers":
        return "Loading Dispatchers...";

      case "planning":
        return "Loading Planning Board...";

      case "services":
        return "Loading Services Catalog...";

      case "profile":
        return "Loading Account & Organization Control...";

      case "tech_dashboard":
      case "cust_dashboard":
        return "Loading Dashboard...";

      case "tech_profile":
      case "cust_profile":
        return "Loading Profile...";

      case "tech_jobs":
        return "Loading Assigned Jobs...";
      
      case "tech_performance_report":
        return "Loading Technician Performance Report...";

      case "cust_requests":
      case "cust_create_request":
        return "Loading Service Requests...";

      case "cust_tracking":
        return "Loading Real-Time Job Tracking...";

      case "cust_support":
      case "customer_support":
        return "Loading Customer Support...";

      case "cust_invoices":
        return "Loading Customer Invoices...";

      default:
        return "Loading page...";
    }
  };

  // Notification States
  const [
    isNotificationDrawerOpen,
    setIsNotificationDrawerOpen,
  ] = useState(false);

  const [unreadCount, setUnreadCount] =
    useState(0);

  const [
    notifications,
    setNotifications,
  ] = useState<NotificationItem[]>([]);

  const [
    selectedNotification,
    setSelectedNotification,
  ] =
    useState<NotificationItem | null>(
      null,
    );

  const [
    selectedJobDetail,
    setSelectedJobDetail,
  ] = useState<any>(null);

  const [selectedSupportRequestId, setSelectedSupportRequestId] =
    useState<number | null>(null);

  const [openSupportCount, setOpenSupportCount] =
    useState(0);

  const supportSeenIdsRef =
    useRef<Set<number>>(new Set());

  const [isBellAnimated, setIsBellAnimated] =
    useState(false);

  const [windowWidth, setWindowWidth] =
    useState(
      typeof window !== "undefined"
        ? window.innerWidth
        : 500,
    );

  useEffect(() => {
    const handleResize = () =>
      setWindowWidth(
        window.innerWidth,
      );

    window.addEventListener(
      "resize",
      handleResize,
    );

    return () => {
      window.removeEventListener(
        "resize",
        handleResize,
      );
    };
  }, []);

  // Poll staff-visible support requests so new customer issues surface
  // immediately in the staff portal without overloading the notification table.
  useEffect(() => {
    if (!isSuperAdmin && !isDispatcher) {
      setOpenSupportCount(0);
      supportSeenIdsRef.current.clear();
      return;
    }

    let initialized = false;

    const checkCustomerSupportRequests = async () => {
      try {
        const response =
          await getAdminCustomerSupportRequests("OPEN");

        const openRequests =
          response.data || [];

        setOpenSupportCount(
          openRequests.length,
        );

        if (!initialized) {
          openRequests.forEach((item) => {
            supportSeenIdsRef.current.add(
              item.id,
            );
          });

          initialized = true;
          return;
        }

        openRequests.forEach((item) => {
          if (
            supportSeenIdsRef.current.has(
              item.id,
            )
          ) {
            return;
          }

          supportSeenIdsRef.current.add(
            item.id,
          );

          addToast({
            title:
              "New Customer Support Request",
            message:
              `${item.customer.name}: ${item.subject}`,
            type: "warning",
            autoDismiss: 0,
            priority: "critical",
            jobId: `support:${item.id}`,
          });
        });
      } catch (error) {
        console.error(
          "Failed to check customer support requests:",
          error,
        );
      }
    };

    void checkCustomerSupportRequests();

    const interval = setInterval(
      checkCustomerSupportRequests,
      10000,
    );

    return () =>
      clearInterval(interval);
  }, [
    isSuperAdmin,
    isDispatcher,
    addToast,
  ]);

  const isMobileLayout =
    windowWidth <= 500;

  // Load notifications after authentication so the bell count is correct
  // before the admin opens the drawer.
  useEffect(() => {
    if (!user?.id) {
      return;
    }

    let cancelled = false;

    const loadNotifications = async () => {
      try {
        const data = await fetchNotifications(
          user.id,
          isTechnician ? "technician" : isCustomer ? "customer" : "admin",
        );

        if (cancelled) return;

        setNotifications(data.notifications || []);
        setUnreadCount(data.unreadCount || 0);
      } catch (err) {
        console.error("Failed to load notifications:", err);
      }
    };

    void loadNotifications();

    return () => {
      cancelled = true;
    };
  }, [user?.id, isTechnician, isCustomer]);

  // Technician heartbeat
  // Heartbeat must use the logged-in technician's user ID.
  // For Tech Bala:
  // user.id === Technician.tech_id
  useEffect(() => {
    if (!isTechnician || !user?.id) {
      return;
    }

    // Availability is explicit; login and page visibility never start it.
    if ((technicianAvailability || "").toLowerCase() !== "available") {
      stopHeartbeatLoop();
      return;
    }

    const technicianId = String(user.id);

    console.log(
      "STARTING HEARTBEAT FOR:",
      technicianId,
    );

    startHeartbeatLoop(
      technicianId,
      60000,
    );

    return () => {
      console.log(
        "STOPPING HEARTBEAT FOR:",
        technicianId,
      );

      stopHeartbeatLoop();
    };
  }, [
    isTechnician,
    user?.id,
    technicianAvailability,
  ]);

  // Track socket notification IDs to prevent duplicate toasts on reconnects.
  const seenSocketNotificationIdsRef = useRef<Set<string>>(new Set());

  // Connect using authenticated credentials. The backend derives user,
  // tenant, and technician rooms from the verified JWT or SSO cookie.
  useEffect(() => {
    const isSsoSession = localStorage.getItem("auth_mode") === "sso";

    if (!accessToken && !isSsoSession) {
      return;
    }

    const socketHandlers = {
      onConnect: () => {
        console.log("Connected to notification server.");
      },

      onDisconnect: (reason?: string) => {
        console.log("Disconnected from notification server.", reason);
      },

      onNewNotification: (notif: NotificationItem) => {
        const notificationId = String(notif.id);

        if (seenSocketNotificationIdsRef.current.has(notificationId)) {
          return;
        }
        seenSocketNotificationIdsRef.current.add(notificationId);

        setNotifications((prev) => {
          const alreadyPresent = prev.some(
            (item) => String(item.id) === notificationId,
          );
          return alreadyPresent ? prev : [notif, ...prev];
        });

        if (!notif.isRead) {
          setUnreadCount((prev) => prev + 1);
        }

        // Only show a toast when the server sent actual notification content.
        if (notif.title?.trim() || notif.message?.trim()) {
          addToast(createToastFromNotification(notif as any));
        }

        setIsBellAnimated(true);
        window.setTimeout(() => {
          setIsBellAnimated(false);
        }, 1000);
      },

      onUnreadCount: (count: number) => {
        setUnreadCount(count);
      },
    };

    const socket = connectNotificationSocket(
      accessToken == null ? null : String(accessToken),
      socketHandlers,
    );
    const unsubscribeDispatch = subscribeToDispatchEvents(socket, addToast);

    return () => {
      unsubscribeDispatch();
      disconnectNotificationSocket(socket);
    };
  }, [accessToken, addToast]);

  // NotificationDetail Actions
  const handleAcceptJob = async (jobId: string | number) => {
    try {
      await acceptJob(jobId);
      if (selectedNotification) {
        await handleMarkAsRead(selectedNotification.id);
      }
    } catch (error) {
      console.error("Failed to accept job:", error);
      throw error;
    }
  };

  const handleRejectJob = async (
    jobId: string | number,
    reason: string,
  ) => {
    try {
      await rejectJob(jobId, reason);
      if (selectedNotification) {
        await handleMarkAsRead(selectedNotification.id);
      }
    } catch (error) {
      console.error("Failed to reject job:", error);
      throw error;
    }
  };

  const handleReassignJob = async (
    jobId: string | number,
    colleagueId?: string | number,
    reason?: string,
  ) => {
    if (colleagueId === undefined || colleagueId === null || colleagueId === "") {
      return;
    }

    try {
      await reassignJob(jobId, colleagueId, reason || "");
      if (selectedNotification) {
        await handleMarkAsRead(selectedNotification.id);
      }
    } catch (error) {
      console.error("Failed to reassign job:", error);
      throw error;
    }
  };

  const handleNotificationClick = async (
    notif: NotificationItem,
  ) => {
    // Customer: open the customer notifications page.
    if (isCustomer) {
      if (activeTab !== "cust_notifications") {
        setPreviousCustomerTab(activeTab);
      }

      setSelectedCustomerNotificationId(String(notif.id));
      setIsNotificationDrawerOpen(false);
      handleTabChange("cust_notifications");

      if (!notif.isRead) {
        await handleMarkAsRead(notif.id);
      }

      return;
    }

    // Technician: open technician notifications.
    if (isTechnician) {
      setIsNotificationDrawerOpen(false);
      handleTabChange("tech_notifications");

      if (!notif.isRead) {
        await handleMarkAsRead(notif.id);
      }

      return;
    }

    // Super Admin: mark as read without opening job details.
    if (isSuperAdmin) {
      if (!notif.isRead) {
        await handleMarkAsRead(notif.id);
      }

      return;
    }

    // Other roles: preserve the existing job-details behavior.
    setSelectedNotification(notif);
    setSelectedJobDetail(notif.job || null);
    setIsNotificationDrawerOpen(false);

    if (!notif.isRead) {
      await handleMarkAsRead(notif.id);
    }
  };

  const handleMarkAsRead = async (notifId: string | number) => {
    try {
      await markNotificationAsRead(notifId);
      setNotifications((prev) =>
        prev.map((notification) =>
          String(notification.id) === String(notifId)
            ? { ...notification, isRead: true }
            : notification,
        ),
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (error) {
      console.error("Failed to mark notification as read:", error);
    }
  };

  const handleMarkAllAsRead = async () => {
    const unreadIds = notifications
      .filter((notification) => !notification.isRead)
      .map((notification) => String(notification.id));

    if (unreadIds.length === 0) {
      setUnreadCount(0);
      return;
    }

    try {
      await batchMarkAsRead(unreadIds);
      setNotifications((prev) =>
        prev.map((notification) => ({ ...notification, isRead: true })),
      );
      setUnreadCount(0);
    } catch (error) {
      console.error("Failed to mark all notifications as read:", error);
    }
  };

  const handleDismissNotification = async (notifId: string) => {
    try {
      await dismissNotification(notifId);
      const dismissed = notifications.find(
        (notification) => String(notification.id) === String(notifId),
      );

      setNotifications((prev) =>
        prev.filter(
          (notification) => String(notification.id) !== String(notifId),
        ),
      );

      if (dismissed && !dismissed.isRead) {
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
    } catch (error) {
      console.error(`Failed to dismiss notification ${notifId}:`, error);
    }
  };

  const handleToastNavigate =
    (jobId: string | number) => {
      const navigationTarget =
        String(jobId);

      if (
        navigationTarget.startsWith(
          "support:",
        )
      ) {
        const supportRequestId =
          Number(
            navigationTarget.slice(
              "support:".length,
            ),
          );

        if (
          Number.isFinite(
            supportRequestId,
          )
        ) {
          setSelectedSupportRequestId(
            supportRequestId,
          );

          setActiveTab(
            "customer_support",
          );

          setIsNavigating(true);
          setIsNotificationDrawerOpen(
            false,
          );

          window.setTimeout(() => {
            setIsNavigating(false);
          }, 400);
        }

        return;
      }

      const matchingNotif =
        notifications.find(
          (n) =>
            String(n.jobId) ===
              String(jobId) ||
            String(n.id) ===
              String(jobId),
        );

      if (matchingNotif) {
        setSelectedNotification(
          matchingNotif,
        );

        setSelectedJobDetail(
          matchingNotif.job ||
            null,
        );

        setIsNotificationDrawerOpen(
          false,
        );
      } else {
        console.warn(
          "No persisted notification is available for this job:",
          jobId,
        );
      }
    };

  const getItemStyle = (
    tab: string,
    isSub = false,
  ) => {
    const active =
      activeTab === tab;

    let base = {
      ...styles.navItem,
      ...(isMobileLayout
        ? styles.navItemMobile
        : {}),
      ...(!isMobileLayout &&
      sidebarCollapsed
        ? styles.navItemCollapsed
        : {}),
      ...(isSub
        ? {
            fontSize:
              "13px",
            padding:
              "5px 6px",
          }
        : {}),
    };

    if (active) {
      base = {
        ...base,
        ...styles.navActive,
        ...(isMobileLayout
          ? styles.navActiveMobile
          : {}),
      };
    }

    return base;
  };

  return (
    <div
      style={
  isCustomer
    ? {
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        fontFamily: "'Inter', sans-serif",
      }
    : (isSuperAdmin || isDispatcher || isTechnician)
      ? {
          ...styles.appShell,
          paddingTop: isTechnician ? "60px" : "72px",
        }
      : {
          display: "flex",
          minHeight: "100vh",
          height: "100vh",
          fontFamily: "'Inter', sans-serif",
        }
}
    >
      <style>
        {localCss}
      </style>
      {(isSuperAdmin || isDispatcher) && (
      <header
  style={{
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    height: "72px",
    display: "flex",
    alignItems: "center",
    background: "#EAF4EE",
    borderBottom: "1px solid #E3ECE7",
    boxShadow: "0 1px 4px rgba(47, 79, 62, 0.05)",
    zIndex: 1000,
    boxSizing: "border-box",
  }}
>
  {/* Fixed logo area — does not collapse */}
  <div
    style={{
      width: isMobileLayout ? "104px" : "220px",
      minWidth: isMobileLayout ? "104px" : "220px",
      height: "100%",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "#EAF4EE",
      boxSizing: "border-box",
    }}
  >
    <img
      src={logo}
      alt="FieldOps Commander"
      style={{
        width: isMobileLayout ? "84px" : "110px",
        maxWidth: "calc(100% - 16px)",
        objectFit: "contain",
        display: "block",
      }}
    />
  </div>

  {/* Fixed search and profile controls */}
  <div
    style={{
      flex: 1,
      minWidth: 0,
      height: "100%",
      display: "flex",
      alignItems: "center",
      gap: "16px",
      padding: "0 16px",
      boxSizing: "border-box",
    }}
  >
    {!isMobileLayout && (
      <div
        style={{
          flex: "1 1 auto",
          minWidth: 0,
          display: "flex",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            position: "relative",
            width: "100%",
            maxWidth: "520px",
          }}
        >
          <Search
            size={19}
            style={{
              position: "absolute",
              left: "15px",
              top: "50%",
              transform: "translateY(-50%)",
              color: "#94A3B8",
              pointerEvents: "none",
            }}
          />

          <input
            type="search"
            aria-label="Search by name, email, phone, or ID"
            placeholder="Search by name, email, phone, or ID..."
            style={{
              width: "100%",
              height: "44px",
              boxSizing: "border-box",
              padding: "0 18px 0 44px",
              border: "1px solid #168653",
              borderRadius: "24px",
              outline: "none",
              background: "#FFFFFF",
              color: "#334155",
              fontSize: "14px",
              boxShadow: "0 0 0 3px rgba(22, 134, 83, 0.10)",
            }}
          />
        </div>
      </div>
    )}

    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: isMobileLayout ? "8px" : "14px",
        flexShrink: 0,
        marginLeft: "auto",
      }}
    >
      {!isMobileLayout && (
        <div style={{ position: "relative" }}>
          <Calendar
            size={14}
            style={{
              position: "absolute",
              left: "10px",
              top: "50%",
              transform: "translateY(-50%)",
              color: "#374151",
              pointerEvents: "none",
            }}
          />

          <select
            value={timeRange}
            onChange={(event) => setTimeRange(event.target.value)}
            aria-label="Dashboard date range"
            style={{
              height: "38px",
              padding: "0 12px 0 30px",
              border: "1px solid #E2E8F0",
              borderRadius: "8px",
              background: "#FFFFFF",
              color: "#374151",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <option value="week">This Week</option>
            <option value="month">This Month</option>
            <option value="all">All Time</option>
          </select>
        </div>
      )}
            <NotificationBell
  unreadCount={unreadCount}
  onClick={() =>
    setIsNotificationDrawerOpen((open) => !open)
  }
  isAnimated={isBellAnimated}
  showSound={true}
/>

      {!isMobileLayout && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "2px",
            whiteSpace: "nowrap",
          }}
        >
          <span
            style={{
              fontSize: "14px",
              fontWeight: 700,
              color: "#111827",
            }}
          >
            {user?.first_name || "User"}
          </span>

          <span
            style={{
              fontSize: "12px",
              color: "#64748B",
            }}
          >
            {(user?.role || "USER").replace(/_/g, " ").toUpperCase()}
          </span>
        </div>
      )}

            <button
        type="button"
        aria-label="Open profile and settings"
        title="Open Profile & Settings"
        onClick={() =>
          handleTabChange(
            isTechnician
              ? "tech_settings"
              : isCustomer
                ? "cust_profile"
                : "profile",
          )
        }
        style={{
          width: "44px",
          height: "44px",
          minWidth: "44px",
          borderRadius: "50%",
          border: "none",
          padding: 0,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#168653",
          color: "#FFFFFF",
          fontSize: "18px",
          fontWeight: 600,
        }}
      >
        {(user?.first_name?.trim()?.charAt(0) || "U").toUpperCase()}
      </button>
    </div>
  </div>
</header>  )}

      {/* Customer Top Navbar */}
      {isCustomer && (
        <header
          style={{
            height: "60px",
            minHeight: "60px",
            background: "#FFFFFF",
            borderBottom: "1px solid #E2E8F0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: isMobileLayout ? "0 12px" : "0 24px",
            zIndex: 350,
            boxSizing: "border-box",
            width: "100%",
            flexShrink: 0,
          }}
        >
          {/* Left: Original FC FieldOps Commander Logo */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              cursor: "pointer",
            }}
            onClick={() => handleTabChange("cust_requests")}
            title="FieldOps Home"
          >
            <img
              src={logo}
              alt="FieldOps Commander"
              style={{
                height: "32px",
                width: "auto",
                objectFit: "contain",
                display: "block",
              }}
            />
          </div>

          {/* Right: Location + Notification Bell + Customer Profile */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: isMobileLayout ? "10px" : "18px",
            }}
          >
            {/* Location Pill */}
            {!isMobileLayout && (
              <div
                onClick={() => handleTabChange("cust_profile")}
                title="Customer Location (from Profile) - Click to manage"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  background: "#FFFFFF",
                  border: "1px solid #E2E8F0",
                  borderRadius: "999px",
                  padding: "7px 18px",
                  color: "#334155",
                  fontSize: "13px",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "all 0.2s",
                  boxShadow: "0 1px 2px rgba(0, 0, 0, 0.04)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "#F8FAFC";
                  e.currentTarget.style.borderColor = "#CBD5E1";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "#FFFFFF";
                  e.currentTarget.style.borderColor = "#E2E8F0";
                }}
              >
                <MapPin size={15} color="#059669" style={{ flexShrink: 0 }} />
                <span
                  style={{
                    maxWidth: "220px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {customerLocation}
                </span>
                <ChevronDown size={14} color="#64748B" style={{ flexShrink: 0 }} />
              </div>
            )}

            {/* Notification Bell */}
            <button
              type="button"
              onClick={() => setIsNotificationDrawerOpen(true)}
              title="Notifications"
              style={{
                background: "transparent",
                border: "none",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                position: "relative",
                padding: "6px",
              }}
            >
              <Bell size={20} color="#475569" />
              {(unreadCount > 0 || notifications.filter((n) => !n.isRead).length > 0) && (
                <span
                  style={{
                    position: "absolute",
                    top: "0px",
                    right: "-2px",
                    minWidth: "16px",
                    height: "16px",
                    padding: "0 4px",
                    borderRadius: "999px",
                    background: "#EF4444",
                    color: "#FFFFFF",
                    fontSize: "10px",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 0 0 2px #FFFFFF",
                  }}
                >
                  {(unreadCount || notifications.filter((n) => !n.isRead).length) > 99
                    ? "99+"
                    : (unreadCount || notifications.filter((n) => !n.isRead).length)}
                </span>
              )}
            </button>

            {/* Customer Profile Pill */}
            <div
              onClick={() => handleTabChange("cust_profile")}
              title="Customer Profile - Click to manage"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  width: "38px",
                  height: "38px",
                  borderRadius: "50%",
                  background: "#059669",
                  color: "#FFFFFF",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: "16px",
                  flexShrink: 0,
                }}
              >
                {customerName ? customerName[0].toUpperCase() : (user?.first_name ? user.first_name[0].toUpperCase() : "C")}
              </div>
              {!isMobileLayout && (
                <div style={{ display: "flex", flexDirection: "column", textAlign: "left" }}>
                  <span style={{ fontSize: "14px", fontWeight: 700, color: "#0F172A", lineHeight: 1.2 }}>
                    {customerName || (user ? `${user.first_name || ""} ${user.last_name || ""}`.trim() : "Customer")}
                  </span>
                  <span style={{ fontSize: "10px", fontWeight: 700, color: "#0D9488", letterSpacing: "0.08em", lineHeight: 1.2 }}>
                    CUSTOMER
                  </span>
                </div>
              )}
            </div>
          </div>
        </header>
      )}

      {/* Shared technician navbar: shown across every technician page. */}
      {isTechnician && (
        <header
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            width: "100%",
            height: "60px",
            minHeight: "60px",
            padding: isMobileLayout ? "0 12px" : "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            background: "#FFFFFF",
            borderBottom: "1px solid #E2E8F0",
            boxSizing: "border-box",
            zIndex: 1000,
          }}
        >
          <button
            type="button"
            aria-label="Go to technician dashboard"
            title="FieldOps Home"
            onClick={() => handleTabChange("tech_dashboard")}
            style={{ border: 0, padding: 0, background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", flexShrink: 0 }}
          >
            <img src={logo} alt="FieldOps Commander" style={{ height: 34, width: "auto", objectFit: "contain", display: "block" }} />
          </button>

          <div style={{ display: "flex", alignItems: "center", gap: isMobileLayout ? 8 : 18 }}>
            <div
              aria-label="Service area: Chennai, Tamil Nadu"
              style={{ display: "flex", alignItems: "center", gap: 8, padding: isMobileLayout ? "8px 10px" : "9px 14px", border: "1px solid #E2E8F0", borderRadius: 24, color: "#334155", fontSize: 13, whiteSpace: "nowrap" }}
            >
              <MapPin size={16} color="#059669" />
              {!isMobileLayout && <span>Chennai, Tamil Nadu</span>}
              {!isMobileLayout && <ChevronDown size={14} color="#64748B" />}
            </div>

            <button
              type="button"
              aria-label="Open technician notifications"
              title="Notifications"
              onClick={() => setIsNotificationDrawerOpen(true)}
              style={{ background: "transparent", border: 0, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", position: "relative", padding: 6 }}
            >
              <Bell size={20} color="#475569" />
              {unreadCount > 0 && (
                <span style={{ position: "absolute", top: 0, right: -2, minWidth: 16, height: 16, padding: "0 4px", borderRadius: 999, background: "#EF4444", color: "#FFFFFF", fontSize: 10, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 0 2px #FFFFFF" }}>
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </button>

            <button
              type="button"
              aria-label="Open technician profile"
              onClick={() => handleTabChange("tech_profile")}
              style={{ border: 0, padding: 0, background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, textAlign: "left" }}
            >
              <span style={{ width: 40, height: 40, borderRadius: "50%", background: "#059669", color: "#FFFFFF", display: "grid", placeItems: "center", fontWeight: 700, flexShrink: 0 }}>
                {user?.first_name ? user.first_name[0].toUpperCase() : "T"}
              </span>
              {!isMobileLayout && (
                <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <strong style={{ color: "#0F172A", fontSize: 13, lineHeight: 1.2, whiteSpace: "nowrap" }}>
                    {user ? `${user.first_name || ""} ${user.last_name || ""}`.trim() : "Technician"}
                  </strong>
                  <small style={{ color: "#0D9488", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em" }}>TECHNICIAN</small>
                </span>
              )}
            </button>
          </div>
        </header>
      )}

      {isTechnician && !isMobileLayout && (
        <button
          type="button"
          aria-label={sidebarCollapsed ? "Expand technician sidebar" : "Collapse technician sidebar"}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          style={{
            position: "fixed",
            top: 60,
            left: sidebarCollapsed ? 60 : 220,
            zIndex: 1001,
            width: 28,
            height: 28,
            padding: 0,
            border: "1px solid #D7E3DC",
            borderRadius: "0 8px 8px 0",
            background: "#FFFFFF",
            color: "#475569",
            boxShadow: "2px 2px 8px rgba(15, 23, 42, 0.10)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Menu size={16} />
        </button>
      )}

      {/* Main Body Layout (Sidebar + Main Area) */}
      <div
        style={
          isCustomer
            ? {
                display: "flex",
                flex: 1,
                minHeight: 0,
                height: "calc(100vh - 60px)",
                width: "100%",
                overflow: "hidden",
                position: "relative",
              }
            : { display: "contents" }
        }
      >
        <aside
          style={
            isCustomer
              ? {
                  width: sidebarCollapsed ? "64px" : "240px",
                  minWidth: sidebarCollapsed ? "64px" : "240px",
                  background: "#FFFFFF",
                  borderRight: "1px solid #E2E8F0",
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                  position: "relative",
                  zIndex: 200,
                  boxSizing: "border-box",
                  transition: "width 0.25s ease, min-width 0.25s ease",
                }
            : isTechnicianShell && !isMobileLayout
              ? {
                  ...(sidebarCollapsed
                    ? {
                        ...styles.sidebar,
                        ...styles.sidebarCollapsed,
                      }
                    : styles.sidebar),
                  position: "relative",
                  top: 0,
                  height: "calc(100vh - 60px)",
                }
              : isMobileLayout
                ? styles.sidebarMobile
                : sidebarCollapsed
                  ? {
                      ...styles.sidebar,
                      ...styles.sidebarCollapsed,
                    }
                  : styles.sidebar
          }
        >
          {/* Customer attached semi-circle toggle tab (matches reference image) */}
          {isCustomer && !isMobileLayout && (
            <button
              type="button"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-label="Toggle sidebar"
              style={{
                position: "absolute",
                right: "0px",
                top: "16px",
                width: "18px",
                height: "32px",
                borderTopLeftRadius: "16px",
                borderBottomLeftRadius: "16px",
                borderTopRightRadius: "0px",
                borderBottomRightRadius: "0px",
                background: "#FFFFFF",
                border: "1px solid #CBD5E1",
                borderRight: "none",
                boxShadow: "-2px 1px 4px rgba(0, 0, 0, 0.06)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                zIndex: 300,
                padding: "0 0 0 2px",
                transition: "background 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "#F8FAFC";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "#FFFFFF";
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "2.5px",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <span
                  style={{
                    width: "9px",
                    height: "1.5px",
                    backgroundColor: "#64748B",
                    borderRadius: "1px",
                    display: "block",
                  }}
                />
                <span
                  style={{
                    width: "9px",
                    height: "1.5px",
                    backgroundColor: "#64748B",
                    borderRadius: "1px",
                    display: "block",
                  }}
                />
                <span
                  style={{
                    width: "9px",
                    height: "1.5px",
                    backgroundColor: "#64748B",
                    borderRadius: "1px",
                    display: "block",
                  }}
                />
              </div>
            </button>
          )}

          {/* Toggle button for non-customer roles */}
          {!isCustomer && !isTechnicianShell && (
            <button
              className="sidebar-toggle-style"
              style={
                isMobileLayout
                  ? {
                      display: "none",
                    }
                  : sidebarCollapsed
                    ? {
                        ...styles.sidebarToggle,
                        ...styles.sidebarToggleCollapsed,
                      }
                    : styles.sidebarToggle
              }
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              aria-label="Toggle sidebar"
            >
              {sidebarCollapsed ? (
                <ChevronsRight size={18} />
              ) : (
                <ChevronsLeft size={18} />
              )}
            </button>
          )}

          <div
            className="sidebar-content-style"
            style={
              isCustomer
                ? {
                    display: "flex",
                    flexDirection: "column",
                    height: "100%",
                    flex: 1,
                    padding: sidebarCollapsed ? "12px 6px" : "12px 10px",
                    boxSizing: "border-box",
                    overflowY: "auto",
                    overflowX: "hidden",
                  }
                : {
                    ...styles.sidebarContent,
                    ...(isMobileLayout
                      ? styles.sidebarContentMobile
                      : {}),
                    ...(!isMobileLayout &&
                    sidebarCollapsed
                      ? styles.sidebarContentCollapsed
                      : {}),
                  }
            }
          >
      {/* Compact spacer below the fixed header */}
<div
  aria-hidden="true"
  style={
    isMobileLayout || isTechnician
      ? { display: "none" }
      : {
          height: "38px",
          minHeight: "38px",
          flexShrink: 0,
          padding: 0,
          margin: 0,
        }
  }
/>

          {isTechnician ? (
            <nav
              style={
                isMobileLayout
                  ? styles.sidebarNavMobile
                  : styles.sidebarNav
              }
            >
              <span
                style={
                  isMobileLayout ||
                  sidebarCollapsed
                    ? {
                        display:
                          "none",
                      }
                    : styles.navGroupLabel
                }
              >
                TECHNICIAN
              </span>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tech_dashboard",
                )}
                onClick={() =>
                  handleTabChange(
                    "tech_dashboard",
                  )
                }
              >
                <LayoutDashboard
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Dashboard
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tech_jobs",
                )}
                onClick={() =>
                  handleTabChange(
                    "tech_jobs",
                  )
                }
              >
                <Briefcase
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Assigned Jobs
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tech_history",
                )}
                onClick={() =>
                  handleTabChange(
                    "tech_history",
                  )
                }
              >
                <History
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Job History
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tech_billing_reports",
                )}
                onClick={() =>
                  handleTabChange(
                    "tech_billing_reports",
                  )
                }
              >
                <FileText
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Billing Report
                </span>
              </button>

              {/* On mobile, keep Logout in the horizontal bottom navigation. */}
              {isMobileLayout && (
                <button
                  type="button"
                  className="nav-item-style"
                  style={getItemStyle("logout")}
                  onClick={() => logout()}
                  title="Logout"
                  aria-label="Logout"
                >
                  <LogOut size={18} style={{ flexShrink: 0 }} />
                  <span
                    className="nav-text"
                    style={sidebarCollapsed ? { display: "none" } : {}}
                  >
                    Logout
                  </span>
                </button>
              )}
            </nav>
          ) : isCustomer ? (
            <nav
                style={
                  isMobileLayout
                    ? styles.sidebarNavMobile
                    : styles.sidebarNav
                }
              >
                {/* 1. New Request */}
              <button
                className="nav-item-style"
                style={getItemStyle("cust_create_request")}
                onClick={() => handleTabChange("cust_create_request")}
              >
                <PlusCircle
                  size={18}
                  style={{ flexShrink: 0 }}
                />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  New Request
                </span>
              </button>

              {/* 3. My Requests */}
              <button
                className="nav-item-style"
                style={getItemStyle("cust_requests")}
                onClick={() => handleTabChange("cust_requests")}
              >
                <FileText
                  size={18}
                  style={{ flexShrink: 0 }}
                />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  My Requests
                </span>
              </button>

              {/* 4. Service History */}
              <button
                className="nav-item-style"
                style={getItemStyle("cust_history")}
                onClick={() => handleTabChange("cust_history")}
              >
                <History
                  size={18}
                  style={{ flexShrink: 0 }}
                />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Service History
                </span>
              </button>

              {/* 5. Support */}
              <button
                className="nav-item-style"
                style={getItemStyle("cust_support")}
                onClick={() => handleTabChange("cust_support")}
              >
                <Headphones
                  size={18}
                  style={{ flexShrink: 0 }}
                />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Support
                </span>
              </button>
            </nav>
          ) : (
            <nav
              style={
                isMobileLayout
                  ? styles.sidebarNavMobile
                  : styles.sidebarNav
              }
            >
              <span
                style={
                  isMobileLayout ||
                  sidebarCollapsed
                    ? {
                        display:
                          "none",
                      }
                    : styles.navGroupLabel
                }
              >
                MAIN MENU
              </span>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "dashboard",
                )}
                onClick={() =>
                  handleTabChange(
                    "dashboard",
                  )
                }
              >
                <LayoutDashboard
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Dashboard
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "techboard",
                )}
                onClick={() =>
                  handleTabChange(
                    "techboard",
                  )
                }
              >
                <Users
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Technicians
                </span>
              </button>

              {!isDispatcher && (
                <button
                  className="nav-item-style"
                  style={getItemStyle("dispatchers")}
                  onClick={() => handleTabChange("dispatchers")}
                  title="Dispatchers"
                >
                  <Users size={18} style={{ flexShrink: 0 }} />
                  <span
                    className="nav-text"
                    style={
                      isMobileLayout || sidebarCollapsed
                        ? { display: "none" }
                        : {}
                    }
                  >
                    Dispatchers
                  </span>
                </button>
              )}

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "planning",
                )}
                onClick={() =>
                  handleTabChange(
                    "planning",
                  )
                }
              >
                <Calendar
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Planning
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tracking",
                )}
                onClick={() =>
                  handleTabChange(
                    "tracking",
                  )
                }
              >
                <Activity
                  size={18}
                  style={{
                    flexShrink: 0,
                  }}
                />

                <span
                  className="nav-text"
                  style={
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Live Tracking
                </span>
              </button>

              {isSuperAdmin && (
                <button
                  className="nav-item-style"
                  style={getItemStyle("services")}
                  onClick={() => handleTabChange("services")}
                  title="Services"
                >
                  <Wrench
                    size={18}
                    style={{
                      flexShrink: 0,
                    }}
                  />
                  <span
                    className="nav-text"
                    style={
                      isMobileLayout ||
                      sidebarCollapsed
                        ? {
                            display:
                              "none",
                          }
                        : {}
                    }
                  >
                    Services
                  </span>
                </button>
              )}

              {(isSuperAdmin ||
                isDispatcher) && (
                <button
                  className="nav-item-style"
                  style={getItemStyle(
                    "customer_support",
                  )}
                  onClick={() => {
                    setSelectedSupportRequestId(
                      null,
                    );

                    handleTabChange(
                      "customer_support",
                    );
                  }}
                  title="Customer Support"
                >
                  <Headphones
                    size={18}
                    style={{
                      flexShrink: 0,
                    }}
                  />

                  <span
                    className="nav-text"
                    style={
                      isMobileLayout ||
                      sidebarCollapsed
                        ? {
                            display:
                              "none",
                          }
                        : {
                            display:
                              "flex",
                            alignItems:
                              "center",
                            gap: "8px",
                          }
                    }
                  >
                    Customer Support

                    {openSupportCount >
                      0 && (
                      <span
                        style={{
                          minWidth: "20px",
                          height: "20px",
                          padding: "0 6px",
                          borderRadius:
                            "999px",
                          background:
                            "#DC2626",
                          color:
                            "#FFFFFF",
                          fontSize: "10px",
                          fontWeight: 800,
                          display:
                            "inline-flex",
                          alignItems:
                            "center",
                          justifyContent:
                            "center",
                        }}
                      >
                        {openSupportCount >
                        99
                          ? "99+"
                          : openSupportCount}
                      </span>
                    )}
                  </span>
                </button>
              )}
              {isMobileLayout && (isSuperAdmin || isDispatcher) && (
                <button
                  type="button"
                  className="nav-item-style"
                  style={getItemStyle("logout")}
                  onClick={() => logout()}
                  title="Logout"
                  aria-label="Logout"
                >
                  <LogOut size={18} />
                  <span className="nav-text" style={{ display: "none" }}>
                    Logout
                  </span>
                </button>
              )}
            </nav>
          )}

          {isCustomer ? (
            <div
              style={{
                marginTop: "auto",
                padding: sidebarCollapsed ? "12px 6px" : "12px 14px",
                borderTop: "1px solid #E2E8F0",
              }}
            >
              <button
                type="button"
                onClick={() => logout()}
                title="Log out"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: sidebarCollapsed ? "0" : "10px",
                  justifyContent: sidebarCollapsed ? "center" : "flex-start",
                  background: "transparent",
                  border: "none",
                  color: "#64748B",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: "pointer",
                  padding: "8px 10px",
                  borderRadius: "8px",
                  width: "100%",
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "#EF4444";
                  e.currentTarget.style.background = "#FEF2F2";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "#64748B";
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <LogOut size={18} />
                {!sidebarCollapsed && <span>Logout</span>}
              </button>
            </div>
          ) : (isSuperAdmin || isDispatcher) ? (
            <div
              style={{
                display: isMobileLayout ? "none" : "block",
                marginTop: "auto",
                padding: sidebarCollapsed ? "12px 6px" : "12px 14px",
                borderTop: "1px solid #E2E8F0",
                flexShrink: 0,
              }}
            >
              <button
                type="button"
                onClick={() => logout()}
                title="Log out"
                aria-label="Log out"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: sidebarCollapsed ? "center" : "flex-start",
                  gap: sidebarCollapsed ? "0" : "10px",
                  background: "transparent",
                  border: "none",
                  color: "#64748B",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: "pointer",
                  padding: "8px 10px",
                  borderRadius: "8px",
                  width: "100%",
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "#EF4444";
                  e.currentTarget.style.background = "#FEF2F2";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "#64748B";
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <LogOut size={18} />
                {!sidebarCollapsed && <span>Logout</span>}
              </button>
            </div>
          ) : isTechnician ? (
            <div
              style={{
                // Desktop: fixed footer at the bottom of the vertical sidebar.
                // Mobile: Logout is rendered as the last item in the bottom nav.
                display: isMobileLayout ? "none" : "block",
                marginTop: "auto",
                padding: sidebarCollapsed ? "12px 6px" : "12px 14px",
                borderTop: "1px solid #E2E8F0",
                flexShrink: 0,
                boxSizing: "border-box",
              }}
            >
              <button
                type="button"
                onClick={() => logout()}
                title="Log out"
                aria-label="Log out"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: sidebarCollapsed ? "center" : "flex-start",
                  gap: "10px",
                  background: "transparent",
                  border: "none",
                  color: "#64748B",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: "pointer",
                  padding: "8px 10px",
                  borderRadius: "8px",
                  width: "100%",
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "#EF4444";
                  e.currentTarget.style.background = "#FEF2F2";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "#64748B";
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <LogOut size={18} />
                {!sidebarCollapsed && <span>Logout</span>}
              </button>
            </div>
          ) : (
            <div
  style={{
    display: (isSuperAdmin || isDispatcher) ? "none" : "flex",
    alignItems: "center",
    gap: "10px",
    padding: sidebarCollapsed ? "12px 6px" : "12px 14px",
    borderTop: "1px solid #E2E8F0",
    marginTop: "auto",
  }}
>
            <div
              onClick={() =>
                handleTabChange(
                  isCustomer ? "cust_profile" : "profile",
                )
              }
              style={{
                display: isSuperAdmin ? "flex" : "none",
                alignItems:
                  "center",
                gap: "10px",
                cursor:
                  "pointer",
                flex: 1,
                minWidth: 0,
              }}
              title="Click to open Profile & Settings"
            >
              <div
                style={
                  styles.miniAvatar
                }
              >
                {user?.first_name
                  ? user.first_name[0].toUpperCase()
                  : "U"}
              </div>

              <div
                style={
                  sidebarCollapsed
                    ? {
                        display:
                          "none",
                      }
                    : styles.miniInfo
                }
              >
                <span
                  style={
                    styles.miniName
                  }
                >
                  {user
                    ? `${user.first_name} ${user.last_name}`
                    : "User"}
                </span>

                <span
                  style={
                    styles.miniRole
                  }
                >
                  {user
                    ? user.role
                        .replace(
                          "_",
                          " ",
                        )
                        .toUpperCase()
                    : "Role"}
                </span>
              </div>
            </div>

            <div
              style={
                sidebarCollapsed
                  ? {
                      marginTop: "12px",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: "8px",
                    }
                  : {
                      marginLeft: "auto",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }
              }
            >
              <button
                title="Log out"
                onClick={() => logout()}
                style={{
                  background: "none",
                  border: "none",
                  color: "#94a3b8",
                  cursor: "pointer",
                  padding: "6px",
                  display: "flex",
                  alignItems: "center",
                  borderRadius: "6px",
                  transition: "color 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "#ef4444";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "#94a3b8";
                }}
              >
                <LogOut size={18} />
              </button>
            </div>
          </div>
          )}
        </div>
      </aside>

      <div
        style={
          isCustomer
            ? {
                ...styles.mainArea,
                height: "100%",
              }
            : isMobileLayout
              ? {
                  ...styles.mainArea,
                  ...styles.mainAreaMobile,
                  height: isTechnician
                    ? "calc(100vh - 60px - 64px)"
                    : "calc(100vh - 72px - 64px)",
                }
              : isTechnician
                ? {
                    ...styles.mainArea,
                    height: "calc(100vh - 60px)",
                  }
                : styles.mainArea
        }
      >
        <main
          style={{
            ...styles.pageWrap,
            ...(isMobileLayout
              ? styles.pageWrapMobile
              : {}),
            overflowY: "auto",
            minHeight: 0,
          }}
        >
          {isTechnician && (
  <>
              <TechnicianAvailabilityLocation
            technicianId={String(user?.id)}
            tenantId={String(user?.tenant_id)}
            technicianStatus={
              technicianAvailability}/>

              <TechnicianLocationTracker user={user} />
            </>
          )}
          {selectedNotification && (
            <NotificationDetail
              notification={
                selectedNotification as any
              }
              job={
                selectedJobDetail
              }
              onAccept={
                handleAcceptJob
              }
              onReject={
                handleRejectJob
              }
              onReassign={
                handleReassignJob
              }
              onClose={() => {
                setSelectedNotification(
                  null,
                );
                setSelectedJobDetail(
                  null,
                );
              }}
            />
          )}

          {isNavigating ? (
            <LoadingSpinner
              message={getLoadingMessage(
                activeTab,
              )}
              fullPage={true}
            />
          ) : (
            <ErrorBoundary fallbackTitle="View Loading Error">
            <Suspense
              fallback={
                <LoadingSpinner
                  message="Loading page..."
                  fullPage={true}
                />
              }
            >
              {activeTab ===
                "dashboard" && (
                <DashboardPage
                  onViewTab={(
                    tab,
                  ) =>
                    handleTabChange(
                      tab,
                    )
                  }
                  unreadCount={
                    unreadCount
                  }
                  isBellAnimated={
                    isBellAnimated
                  }
                  onOpenBellDrawer={() => {
                    setIsNotificationDrawerOpen(
                      true,
                    );
                  }}
                  timeRange={timeRange}
                  onTimeRangeChange={setTimeRange}
                />
              )}


              {(activeTab === "techboard" || activeTab === "dispatchers") && (
                <TechniciansDispatchersPage
                  activeView={activeTab === "dispatchers" ? "dispatchers" : "technicians"}
                  allowDispatcherToggle={isSuperAdmin}
                  onViewChange={(view: "technicians" | "dispatchers") =>
                    handleTabChange(view === "dispatchers" ? "dispatchers" : "techboard")
                  }
                />
              )}

              {activeTab ===
                "planning" && (
                <PlanningPage
  onViewCompletedJob={setSelectedCompletedJobForView}
/>
              )}

              {selectedCompletedJobForView && (
  <JobsPage
    initialViewJob={selectedCompletedJobForView}
    modalOnly={true}
    onViewJobClosed={() =>
      setSelectedCompletedJobForView(null)
    }
  />
)}

              {activeTab ===
                "tracking" && (
                <TrackingDashboardPage />
              )}

              {activeTab ===
                "profile" && (
                <ProfilePage />
              )}

              {activeTab ===
                "tech_dashboard" && (
                <TechnicianPortalDashboard
                  onNavigate={
                    handleTabChange
                  }
                   onAvailabilityChange={setTechnicianAvailability}
                />
              )}

              {activeTab ===
                "tech_profile" && (
                <TechnicianProfilePage
                  onNavigate={handleTabChange}
                />
              )}

              {activeTab ===
                "tech_jobs" && (
                <TechnicianJobsPage />
              )}

              {activeTab ===
                "tech_history" && (
                <TechnicianJobHistoryPage />
              )}

              {activeTab ===
                "tech_billing_reports" && (
                <TechnicianBillingReportPage />
              )}

              {activeTab ===
                "tech_performance_report" && (
                <TechnicianPerformanceReportPage />
              )}

              {activeTab ===
                "tech_notifications" && (
                <TechnicianNotificationsPage />
              )}

              {activeTab ===
                "tech_settings" && (
                <TechnicianSettingsPage />
              )}

              {activeTab ===
                "cust_dashboard" && (
                <CustomerPortalDashboard
                  onNavigate={
                    handleTabChange
                  }
                />
              )}

              {activeTab ===
                "cust_profile" && (
                <CustomerProfilePage
                  onClose={() => handleTabChange("cust_requests")}
                  onNavigate={handleTabChange}
                />
              )}

              {activeTab ===
                "cust_create_request" && (
                <CustomerServiceRequestsPage
                  createOnly={true}
                  onNavigate={
                    handleTabChange
                  }
                />
              )}

              {activeTab ===
                "cust_requests" && (
                <CustomerServiceRequestsPage
                  createOnly={false}
                  onNavigate={
                    handleTabChange
                  }
                />
              )}

              {activeTab ===
                "cust_tracking" && (
                <CustomerJobTrackingPage token={accessToken || ""} />
              )}

              {activeTab ===
                "cust_notifications" && (
                <CustomerNotificationsPage
                  onClose={() =>
                    handleTabChange(
                      previousCustomerTab || "cust_requests",
                    )
                  }
                  selectedNotificationId={
                    selectedCustomerNotificationId
                  }
                  onNotificationsRead={(readId) => {
                    if (readId) {
                      setNotifications((prev) =>
                        prev.map((n) =>
                          String(n.id) === String(readId)
                            ? { ...n, isRead: true }
                            : n,
                        ),
                      );
                      setUnreadCount((c) => Math.max(0, c - 1));
                    }
                  }}
                  onAllNotificationsRead={() => {
                    setNotifications((prev) =>
                      prev.map((n) => ({ ...n, isRead: true })),
                    );
                    setUnreadCount(0);
                  }}
                />
              )}

              {activeTab ===
                "cust_invoices" && (
                <CustomerInvoicePage />
              )}

              {activeTab ===
                "cust_history" && (
                <CustomerServiceHistoryPage />
              )}
              {activeTab ===
                "cust_support" && (
                <CustomerSupportPage />
              )}

              {activeTab ===
                "customer_support" &&
                (isSuperAdmin ||
                  isDispatcher) && (
                <CustomerSupportPage
                  initialRequestId={
                    selectedSupportRequestId
                  }
                />
              )}

              {activeTab === "services" && (
                <SuperAdminServicesPage />
              )}
              {activeTab ===
                "cust_settings" && (
                <CustomerSettingsPage />
              )}
            </Suspense>
            </ErrorBoundary>
          )}
        </main>
      </div>
      {/* End Main Body Layout */}
      </div>

      {isCustomer && user?.id && (
        <CustomerSupportWidget
          customerId={String(user.id)}
          onSupportClick={() => handleTabChange("cust_support")}
          onServiceRequestsClick={() => handleTabChange("cust_requests")}
          onTrackingClick={() => handleTabChange("cust_tracking")}
        />
      )}

      <NotificationDrawer
        isOpen={
          isNotificationDrawerOpen
        }
        onClose={() =>
          setIsNotificationDrawerOpen(
            false,
          )
        }
        notifications={
          notifications as any
        }
        onNotificationClick={
          handleNotificationClick
        }
        onMarkAllAsRead={
          handleMarkAllAsRead
        }
        onDismissNotification={
          handleDismissNotification
        }
        onViewAll={
          isCustomer
            ? () => {
                if (activeTab !== "cust_notifications") {
                  setPreviousCustomerTab(activeTab);
                }
                setIsNotificationDrawerOpen(false);
                handleTabChange("cust_notifications");
              }
            : isTechnician
            ? () => {
                setIsNotificationDrawerOpen(false);
                handleTabChange("tech_notifications");
              }
            : undefined
        }
      />

      <ToastContainer
        onNavigate={
          handleToastNavigate
        }
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Authentication wrapper
// ─────────────────────────────────────────────
//
// Supports both:
//
// 1. Normal JWT/localStorage authentication
// 2. Enterprise SSO/HttpOnly cookie authentication
//
// For SSO:
//
//   /auth/sso/callback
//          ↓
//   HttpOnly cookie
//          ↓
//   loadFromSession()
//          ↓
//   GET /auth/me
//          ↓
//   Zustand user
//          ↓
//   AppInner
// ─────────────────────────────────────────────
function AppContent() {
  const {
    isAuthenticated,
    isLoading,
    loadFromStorage,
    loadFromSession,
  } = useAuthStore();

  const [
    showOnboarding,
    setShowOnboarding,
  ] = useState(false);

  /*
   * Password reset route
   *
   * Example:
   * /reset-password?token=abc123
   */
  const isResetPasswordPage =
    window.location.pathname ===
    "/reset-password";

  const resetToken =
    new URLSearchParams(
      window.location.search,
    ).get("token");

  /*
   * Initialize authentication
   */
  useEffect(() => {
    let mounted = true;

    const initializeAuthentication =
      async () => {
        /*
         * Determine which authentication mode
         * is currently being used.
         *
         * local = normal email/password login
         * sso   = enterprise SSO login
         */
        const authMode =
          localStorage.getItem(
            "auth_mode",
          );

        /*
         * --------------------------------------------------
         * NORMAL LOGIN
         * --------------------------------------------------
         *
         * Normal login stores the JWT in localStorage.
         *
         * Therefore we restore the authentication
         * state from localStorage.
         *
         * IMPORTANT:
         * We do NOT call /auth/me here.
         */
        if (authMode === "local") {
          loadFromStorage();

          return;
        }

        /*
         * --------------------------------------------------
         * SSO LOGIN
         * --------------------------------------------------
         *
         * SSO authentication uses HttpOnly cookies.
         *
         * The frontend cannot read the HttpOnly cookie,
         * so we ask the backend to verify the session.
         *
         * This internally calls:
         *
         * GET /auth/me
         */
        if (authMode === "sso") {
          await loadFromSession();

          if (!mounted) {
            return;
          }

          /*
           * Check the latest Zustand state after
           * the session validation.
           */
          const currentState =
            useAuthStore.getState();

          /*
           * The SSO session is no longer valid.
           *
           * Remove the stale authentication mode so
           * that the next application load does not
           * repeatedly try /auth/me.
           */
          if (
            !currentState.isAuthenticated
          ) {
            localStorage.removeItem(
              "auth_mode",
            );
          }

          return;
        }

        /*
         * --------------------------------------------------
         * NO AUTHENTICATION
         * --------------------------------------------------
         *
         * There is no auth_mode in localStorage.
         *
         * This normally means the user has not logged in.
         *
         * IMPORTANT:
         *
         * Do NOT call loadFromSession().
         *
         * Otherwise the application will unnecessarily
         * call:
         *
         * GET /auth/me
         *
         * and receive:
         *
         * 401 Authentication required
         *
         * The LoginPage will be displayed below.
         */
      };

    initializeAuthentication();

    return () => {
      mounted = false;
    };
  }, [
    loadFromStorage,
    loadFromSession,
  ]);

  /*
   * Hide onboarding after successful login.
   */
  useEffect(() => {
    if (isAuthenticated) {
      setShowOnboarding(false);
    }
  }, [isAuthenticated]);

  /*
   * --------------------------------------------------
   * PASSWORD RESET PAGE
   * --------------------------------------------------
   *
   * This must be checked before the authentication
   * loading screen and normal login page.
   */
  if (isResetPasswordPage) {
    return (
      <Suspense
        fallback={
          <LoadingSpinner />
        }
      >
        <ResetPasswordPage
          token={resetToken || ""}
          onBackToLogin={() => {
            window.history.replaceState(
              {},
              "",
              "/",
            );

            window.location.reload();
          }}
        />
      </Suspense>
    );
  }

  /*
   * --------------------------------------------------
   * AUTHENTICATION LOADING
   * --------------------------------------------------
   *
   * Prevent the login page from flashing while
   * authentication is being checked.
   */
  if (isLoading) {
    return (
      <LoadingSpinner
        message="Checking authentication..."
        fullPage={true}
      />
    );
  }

  /*
   * --------------------------------------------------
   * ORGANIZATION ONBOARDING
   * --------------------------------------------------
   */
  if (
    !isAuthenticated &&
    showOnboarding
  ) {
    return (
      <Suspense
        fallback={
          <LoadingSpinner />
        }
      >
        <OrganizationOnboardingPage
          onBackToLogin={() =>
            setShowOnboarding(false)
          }
        />
      </Suspense>
    );
  }

  /*
   * --------------------------------------------------
   * LOGIN PAGE
   * --------------------------------------------------
   */
  if (!isAuthenticated) {
    return (
      <Suspense
        fallback={
          <LoadingSpinner />
        }
      >
        <LoginPage
          onCreateOrganization={() =>
            setShowOnboarding(true)
          }
        />
      </Suspense>
    );
  }

  /*
   * --------------------------------------------------
   * AUTHENTICATED APPLICATION
   * --------------------------------------------------
   */
  return <AppInner />;
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

export default App;
