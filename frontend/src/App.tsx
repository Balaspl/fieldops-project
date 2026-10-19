import { useState, useEffect, useRef, lazy, Suspense } from "react";
import logo from "./assets/logo.png";
import {
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
} from "lucide-react";
import useAuthStore from "./store/authStore";

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
import { getAdminCustomerSupportRequests } from "./services/customerPortalService";
import { ToastProvider, useToast } from "./hooks/useToast";
import LoadingSpinner from "./components/ui/LoadingSpinner";
import TechnicianLocationTracker from "./components/technician/TechnicianLocationTracker";
import TechnicianAvailabilityLocation from "./components/technician/TechnicianAvailabilityLocation";

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
const TechDashboardPage = lazy(() => import("./pages/TechDashboardPage"));
const DispatcherPage = lazy(
  () => import("./pages/dispatcher/DispatcherPage"),
);
const PlanningPage = lazy(() => import("./pages/PlanningPage"));
const TrackingDashboardPage = lazy(
  () => import("./pages/TrackingDashboardPage"),
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
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  sidebar: {
    width: "220px",
    minWidth: "220px",
    background: "#F3F8F5",
    borderRight: "1px solid #E3ECE7",
    display: "flex",
    flexDirection: "column",
    position: "sticky",
    top: 0,
    height: "100vh",
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
    background: "#F3F8F5",
    boxSizing: "border-box",
  } as React.CSSProperties,

  sidebarContent: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    flex: 1,
    padding: "16px 12px",
    boxSizing: "border-box",
    overflowY: "auto",
    overflowX: "hidden",
  } as React.CSSProperties,

  sidebarContentCollapsed: {
    padding: "12px 6px",
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
    marginTop: "16px",
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
    top: "78px",
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
    top: "40px",
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
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    minWidth: 0,
  } as React.CSSProperties,

  mainAreaMobile: {
    marginLeft: 0,
    marginBottom: "64px",
    height: "calc(100vh - 64px)",
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
    userRole === "super_admin";

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
        return "cust_dashboard";

      return "dashboard";
    });

  useEffect(() => {
    if (
      isCustomer &&
      new URLSearchParams(window.location.search).get("tab") ===
        "cust_invoices"
    ) {
      setActiveTab("cust_invoices");
    }
  }, [isCustomer]);

  const [sidebarCollapsed, setSidebarCollapsed] =
    useState(false);

  const [isNavigating, setIsNavigating] =
    useState(false);

  const handleTabChange = (
    tab: string,
  ) => {
    if (tab === activeTab) return;

    setIsNavigating(true);
    setActiveTab(tab);

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

    const technicianId = String(user.id);

    console.log(
      "STARTING HEARTBEAT FOR:",
      technicianId,
    );

    startHeartbeatLoop(
      technicianId,
      450000,
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

  const handleNotificationClick =
    async (
      notif: NotificationItem,
    ) => {
      setSelectedNotification(
        notif,
      );

      setSelectedJobDetail(
        notif.job || null,
      );

      setIsNotificationDrawerOpen(
        false,
      );

      if (!notif.isRead) {
        await handleMarkAsRead(
          notif.id,
        );
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
    <div style={styles.appShell}>
      <style>
        {localCss}
      </style>

      <aside
        style={
          isMobileLayout
            ? styles.sidebarMobile
            : sidebarCollapsed
              ? {
                  ...styles.sidebar,
                  ...styles.sidebarCollapsed,
                }
              : styles.sidebar
        }
      >
        <button
          className="sidebar-toggle-style"
          style={
            isMobileLayout
              ? {
                  display:
                    "none",
                }
              : sidebarCollapsed
                ? {
                    ...styles.sidebarToggle,
                    ...styles.sidebarToggleCollapsed,
                  }
                : styles.sidebarToggle
          }
          onClick={() =>
            setSidebarCollapsed(
              !sidebarCollapsed,
            )
          }
          aria-label="Toggle sidebar"
        >
          {sidebarCollapsed ? (
            <ChevronsRight
              size={18}
            />
          ) : (
            <ChevronsLeft
              size={18}
            />
          )}
        </button>

        <div
          className="sidebar-content-style"
          style={{
            ...styles.sidebarContent,
            ...(isMobileLayout
              ? styles.sidebarContentMobile
              : {}),
            ...(!isMobileLayout &&
            sidebarCollapsed
              ? styles.sidebarContentCollapsed
              : {}),
          }}
        >
          <div
            style={
              isMobileLayout
                ? {
                    display:
                      "none",
                  }
                : styles.sidebarBrand
            }
          >
            <div
              style={
                styles.brandLogoWrap
              }
            >
              <img
                src={logo}
                alt="FieldOps Logo"
                style={
                  styles.brandLogoImg
                }
              />
            </div>
          </div>

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

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tech_performance_report",
                )}
                onClick={() =>
                  handleTabChange(
                    "tech_performance_report",
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
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Performance Report
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "tech_notifications",
                )}
                onClick={() =>
                  handleTabChange(
                    "tech_notifications",
                  )
                }
              >
                <BellRing
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
                  Notifications
                </span>
              </button>
            </nav>
          ) : isCustomer ? (
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
                CUSTOMER PORTAL
              </span>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_dashboard",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_dashboard",
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
                  "cust_profile",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_profile",
                  )
                }
              >
                <User
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
                  My Profile
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_create_request",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_create_request",
                  )
                }
              >
                <PlusCircle
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
                  New Request
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_requests",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_requests",
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
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  My Requests
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_tracking",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_tracking",
                  )
                }
              >
                <Navigation
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
                  Job Tracking
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_invoices",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_invoices",
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
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Invoices
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_notifications",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_notifications",
                  )
                }
              >
                <BellRing
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
                  Notifications
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_history",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_history",
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
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Service History
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_support",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_support",
                  )
                }
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
                      : {}
                  }
                >
                  Support
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle(
                  "cust_settings",
                )}
                onClick={() =>
                  handleTabChange(
                    "cust_settings",
                  )
                }
              >
                <Settings
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
                  Settings
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
                  "jobs",
                )}
                onClick={() =>
                  handleTabChange(
                    "jobs",
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
                    isMobileLayout ||
                    sidebarCollapsed
                      ? {
                          display:
                            "none",
                        }
                      : {}
                  }
                >
                  Jobs
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
                  style={getItemStyle(
                    "dispatchers",
                  )}
                  onClick={() =>
                    handleTabChange(
                      "dispatchers",
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
            </nav>
          )}

          <div
            style={
              isMobileLayout
                ? {
                    display:
                      "none",
                  }
                : sidebarCollapsed
                  ? styles.sidebarProfileMiniCollapsed
                  : styles.sidebarProfileMini
            }
          >
            <div
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
                display:
                  "flex",
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
                      marginTop:
                        "12px",
                      display:
                        "flex",
                      flexDirection:
                        "column",
                      alignItems:
                        "center",
                      gap: "8px",
                    }
                  : {
                      marginLeft:
                        "auto",
                      display:
                        "flex",
                      alignItems:
                        "center",
                      gap: "8px",
                    }
              }
            >
              <button
                title="Log out"
                onClick={() =>
                  logout()
                }
                style={{
                  background:
                    "none",
                  border:
                    "none",
                  color:
                    "#94a3b8",
                  cursor:
                    "pointer",
                  padding:
                    "6px",
                  display:
                    "flex",
                  alignItems:
                    "center",
                  borderRadius:
                    "6px",
                  transition:
                    "color 0.2s",
                }}
                onMouseEnter={(
                  e,
                ) =>
                  (e.currentTarget.style.color =
                    "#ef4444")
                }
                onMouseLeave={(
                  e,
                ) =>
                  (e.currentTarget.style.color =
                    "#94a3b8")
                }
              >
                <LogOut
                  size={18}
                />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <div
        style={
          isMobileLayout
            ? {
                ...styles.mainArea,
                ...styles.mainAreaMobile,
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
                />
              )}

              {activeTab ===
                "jobs" && (
                <JobsPage />
              )}

              {activeTab ===
                "techboard" && (
                <TechDashboardPage />
              )}

              {activeTab ===
                "dispatchers" && (
                <DispatcherPage />
              )}

              {activeTab ===
                "planning" && (
                <PlanningPage />
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
                <TechnicianProfilePage />
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
                <CustomerProfilePage />
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
                <CustomerNotificationsPage />
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

              {activeTab ===
                "cust_settings" && (
                <CustomerSettingsPage />
              )}
            </Suspense>
          )}
        </main>
      </div>

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

