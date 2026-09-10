import { useState, useEffect, useRef, lazy, Suspense } from "react";
import logo from "./assets/logo.png";
import {
  ChevronsLeft,
  ChevronsRight,
  LayoutDashboard,
  Briefcase,
  Users,
  Calendar,
  FlaskConical,
  Info,
  User,
  ChevronDown,
  Activity,
  BellRing,
  LogOut,
  History,
  Settings,
  PlusCircle,
  FileText,
  Navigation,
} from "lucide-react";
import useAuthStore from "./store/authStore";

// Import notification modules
import NotificationBell from "./components/notifications/NotificationBell";
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
import { getAllTechnicians } from "./services/technicianService";
import { getTechnicianNotifications } from "./services/technicianPortalService";
import { ToastProvider, useToast } from "./hooks/useToast";
import LoadingSpinner from "./components/ui/LoadingSpinner";

// Lazy load page components
const LoginPage = lazy(() => import("./pages/LoginPage"));
const OrganizationOnboardingPage = lazy(
  () => import("./pages/OrganizationOnboardingPage"),
);
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const JobsPage = lazy(() => import("./pages/JobsPage"));
const TechDashboardPage = lazy(() => import("./pages/TechDashboardPage"));
const DispatcherPage = lazy(() => import("./pages/dispatcher/DispatcherPage"));
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
  () => import("./pages/customer/CustomerJobTrackingPage"),
);
const CustomerNotificationsPage = lazy(
  () => import("./pages/customer/CustomerNotificationsPage"),
);
const CustomerServiceHistoryPage = lazy(
  () => import("./pages/customer/CustomerServiceHistoryPage"),
);
const CustomerSettingsPage = lazy(
  () => import("./pages/customer/CustomerSettingsPage"),
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

interface Technician {
  tech_id?: string | number;
  technician_id?: string | number;
  id?: string | number;
  technician_name?: string;
  name?: string;
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
    transition: "width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
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
    transition: "color 0.2s ease, transform 0.2s ease",
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
    transition: "padding 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
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

  sidebarSimulationControls: {
    padding: "12px 10px",
    borderTop: "1px solid #E3ECE7",
    marginTop: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  } as React.CSSProperties,

  simulationCard: {
    background: "#F9FAF9",
    border: "1px solid #E3ECE7",
    borderRadius: "12px",
    padding: "10px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  } as React.CSSProperties,

  simulationHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  } as React.CSSProperties,

  simulationTitleWrap: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  simulationTitle: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#1F2937",
  } as React.CSSProperties,

  simulationLabel: {
    fontSize: "10px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  dropdownWrapper: {
    position: "relative",
    display: "flex",
    alignItems: "center",
    background: "#FFFFFF",
    border: "1.5px solid #CBD5E1",
    borderRadius: "10px",
    width: "100%",
    height: "36px",
  } as React.CSSProperties,

  userCircle: {
    width: "24px",
    height: "24px",
    borderRadius: "50%",
    background: "#E6F4EA",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    position: "absolute",
    left: "8px",
  } as React.CSSProperties,

  simulationSelect: {
    width: "100%",
    height: "100%",
    border: "none",
    background: "transparent",
    paddingLeft: "38px",
    paddingRight: "28px",
    fontSize: "12px",
    fontWeight: 600,
    color: "#1F2937",
    outline: "none",
    cursor: "pointer",
    appearance: "none",
  } as React.CSSProperties,

  dropdownChevron: {
    position: "absolute",
    right: "10px",
    pointerEvents: "none",
  } as React.CSSProperties,

  statusActiveBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 10px",
    background: "#EDF7F2",
    borderRadius: "8px",
  } as React.CSSProperties,

  statusActiveLeft: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  statusDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    background: "#0F9D58",
    display: "inline-block",
  } as React.CSSProperties,

  statusText: {
    fontSize: "9.5px",
    fontWeight: 700,
    color: "#0F9D58",
    letterSpacing: "0.02em",
  } as React.CSSProperties,

  simulateAlertBtn: {
    width: "100%",
    height: "36px",
    background: "#7AAE8A",
    border: "none",
    borderRadius: "8px",
    color: "#FFFFFF",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    transition: "all 0.2s ease",
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
  .simulate-alert-btn-style:hover {
    background-color: #5C9470 !important;
  }
  .simulate-alert-btn-style:active {
    transform: scale(0.98) !important;
  }
`;

function AppInner() {
  const { user, logout } = useAuthStore();
  const { addToast } = useToast();

  const userRole = (user?.role || "").toLowerCase();
  const isTechnician = userRole === "technician";
  const isCustomer = userRole === "customer";
  const isDispatcher = userRole === "dispatcher";
  const isSuperAdmin = userRole === "super_admin";
  const isAdminOrDispatcher = !isTechnician && !isCustomer;

  const [activeTab, setActiveTab] = useState(() => {
    // if (isTechnician) return "tech_jobs";
    if (isTechnician) return "tech_dashboard";
    if (isCustomer) return "cust_dashboard";
    return "dashboard";
  });
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);

  const handleTabChange = (tab: string) => {
    if (tab === activeTab) return;
    setIsNavigating(true);
    setActiveTab(tab);
    setTimeout(() => {
      setIsNavigating(false);
    }, 400);
  };

  const getLoadingMessage = (tab: string) => {
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
      case "cust_requests":
      case "cust_create_request":
        return "Loading Service Requests...";
      case "cust_tracking":
        return "Loading Real-Time Job Tracking...";
      default:
        return "Loading page...";
    }
  };

  // Notification States
  const [isNotificationDrawerOpen, setIsNotificationDrawerOpen] =
    useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [selectedNotification, setSelectedNotification] =
    useState<NotificationItem | null>(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState<any>(null);
  const [isBellAnimated, setIsBellAnimated] = useState(false);
  const [activeTechId, setActiveTechId] = useState<string | number | null>(
    null,
  ); // set after fetching real technicians
  const [techList, setTechList] = useState<Technician[]>([]);

  const [windowWidth, setWindowWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 500,
  );

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Real-time technician toast notification pop-up
  const seenNotifIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!isTechnician) return;

    const checkNewJobNotifications = async () => {
      try {
        const res = await getTechnicianNotifications();
        const list = res.data.notifications || [];
        list.forEach((n: any) => {
          if (!n.isRead && !seenNotifIdsRef.current.has(n.id)) {
            seenNotifIdsRef.current.add(n.id);
            addToast({
              title: n.title || "New Job Assigned",
              message: n.message || "A new job has been assigned to you.",
              type: "info",
              autoDismiss: 7000,
              priority: "normal",
            });
          }
        });
      } catch (e) {}
    };

    checkNewJobNotifications();
    const interval = setInterval(checkNewJobNotifications, 4000);
    return () => clearInterval(interval);
  }, [isTechnician, addToast]);

  const isMobileLayout = windowWidth <= 500;

  // Lazy fetch registered technicians if not already loaded
  const ensureActiveTechLoaded = async () => {
    if (techList.length > 0 && activeTechId !== null) {
      return activeTechId;
    }
    try {
      const response = await getAllTechnicians();
      if (response.data && response.data.length > 0) {
        setTechList(response.data);
        // Pick the first technician's UUID
        const firstTech = response.data[0];
        const techId =
          firstTech.tech_id || firstTech.technician_id || firstTech.id;
        if (techId) {
          setActiveTechId(techId);
          return techId;
        }
      }
    } catch (err) {
      console.warn("Failed to fetch technicians list lazily.", err);
    }
    return null;
  };

  // Fetch notifications only when the notification drawer is opened or notification feature is active
  useEffect(() => {
    if (!activeTechId || !isNotificationDrawerOpen) return;

    const loadNotifications = async () => {
      try {
        const data = await fetchNotifications(activeTechId);
        setNotifications(data.notifications);
        setUnreadCount(data.unreadCount);
      } catch (err) {
        console.error("Failed to load notifications:", err);
      }
    };
    loadNotifications();
  }, [activeTechId, isNotificationDrawerOpen]);

  // Fetch notifications and initialize socket listeners for the active technician
  useEffect(() => {
    if (!activeTechId) return;

    // Start heartbeat loop (POST /technicians/{id}/heartbeat every 30 seconds)
    startHeartbeatLoop(String(activeTechId), 30000, () => ({
      last_lat: 13.0827 + (Math.random() - 0.5) * 0.01,
      last_lng: 80.2707 + (Math.random() - 0.5) * 0.01,
    }));

    // 2. Connect Socket.io
    const socketHandlers = {
      onConnect: () => {
        console.log("Connected to notification server.");
      },
      onDisconnect: () => {
        console.log("Disconnected from notification server.");
      },
      onNewNotification: (notif: NotificationItem) => {
        setNotifications((prev) => [notif, ...prev]);
        setUnreadCount((prev) => prev + 1);
        // Mirror to toast system
        addToast(createToastFromNotification(notif as any));
        // Trigger bell bounce animation
        setIsBellAnimated(true);
        setTimeout(() => setIsBellAnimated(false), 1000);
      },
      onUnreadCount: (count: number) => {
        setUnreadCount(count);
      },
    };

    const socket = connectNotificationSocket(activeTechId, socketHandlers);

    // Subscribe to dispatch-specific job.* events
    const unsubscribeDispatch = subscribeToDispatchEvents(socket, addToast);

    return () => {
      stopHeartbeatLoop();
      unsubscribeDispatch();
      disconnectNotificationSocket(socket);
    };
  }, [activeTechId]);

  // Handlers for NotificationDetail Actions
  const handleAcceptJob = async (jobId: string | number) => {
    console.log(`Accepting job ID: ${jobId}`);
    const isMock =
      selectedNotification &&
      typeof selectedNotification.id === "string" &&
      selectedNotification.id.startsWith("notif-");
    if (!isMock) {
      await acceptJob(jobId);
    }
    if (selectedNotification) {
      await handleMarkAsRead(selectedNotification.id);
    }
  };

  const handleRejectJob = async (jobId: string | number, reason: string) => {
    console.log(`Rejecting job ID: ${jobId} for reason: ${reason}`);
    const isMock =
      selectedNotification &&
      typeof selectedNotification.id === "string" &&
      selectedNotification.id.startsWith("notif-");
    if (!isMock) {
      await rejectJob(jobId, reason);
    }
    if (selectedNotification) {
      await handleMarkAsRead(selectedNotification.id);
    }
  };

  const handleReassignJob = async (
    jobId: string | number,
    colleagueId?: string | number,
    reason?: string,
  ) => {
    console.log(
      `Requesting reassignment for job ID: ${jobId} to colleague: ${colleagueId} with reason: ${reason}`,
    );
    const isMock =
      selectedNotification &&
      typeof selectedNotification.id === "string" &&
      selectedNotification.id.startsWith("notif-");
    if (!isMock && colleagueId) {
      await reassignJob(jobId, colleagueId, reason || "");
    }
    if (selectedNotification) {
      await handleMarkAsRead(selectedNotification.id);
    }
  };

  const handleNotificationClick = async (notif: NotificationItem) => {
    setSelectedNotification(notif);
    setSelectedJobDetail(notif.job || null);
    setIsNotificationDrawerOpen(false); // Close drawer to display details

    // Mark as read immediately on click
    if (!notif.isRead) {
      await handleMarkAsRead(notif.id);
    }
  };

  const handleMarkAsRead = async (notifId: string | number) => {
    const isMock = typeof notifId === "string" && notifId.startsWith("notif-");
    if (!isMock) {
      await markNotificationAsRead(notifId);
    }
    setNotifications((prev) =>
      prev.map((n) => (n.id === notifId ? { ...n, isRead: true } : n)),
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
  };

  const handleMarkAllAsRead = async () => {
    const unreadIds = notifications
      .filter((n) => !n.isRead)
      .map((n) => String(n.id));
    const realUnreadIds = unreadIds.filter((id) => !id.startsWith("notif-"));
    if (realUnreadIds.length > 0) {
      try {
        await batchMarkAsRead(realUnreadIds);
      } catch (err) {
        console.error("Failed to batch mark notifications as read", err);
      }
    }
    setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })));
    setUnreadCount(0);
  };

  const handleDismissNotification = async (notifId: string) => {
    const isMock = typeof notifId === "string" && notifId.startsWith("notif-");
    if (!isMock) {
      try {
        await dismissNotification(notifId);
      } catch (err) {
        console.error(`Failed to dismiss notification ${notifId}`, err);
      }
    }
    setNotifications((prev) =>
      prev.filter((n) => String(n.id) !== String(notifId)),
    );
    const notif = notifications.find((n) => String(n.id) === String(notifId));
    if (notif && !notif.isRead) {
      setUnreadCount((prev) => Math.max(0, prev - 1));
    }
  };

  const handleToastNavigate = (jobId: string | number) => {
    // Find matching notification in the state
    const matchingNotif = notifications.find(
      (n) =>
        String(n.jobId) === String(jobId) || String(n.id) === String(jobId),
    );

    if (matchingNotif) {
      setSelectedNotification(matchingNotif);
      setSelectedJobDetail(matchingNotif.job || null);
      setIsNotificationDrawerOpen(false);
    } else {
      // Create a temporary/placeholder notification detail so we can open it!
      const tempNotif: NotificationItem = {
        id: `notif-temp-${Date.now()}`,
        type: "JOB_ASSIGNED",
        title: "Job Notification",
        message: "Details for job #" + jobId,
        isRead: true,
        createdAt: new Date().toISOString(),
        jobId: jobId,
        job: {
          id: jobId,
          title: "Dispatch Assignment",
          description: "Scheduled dispatch details for job #" + jobId,
          location: "Chennai Site",
          priority: "MEDIUM",
          customer_name: "Customer",
          customer_phone: "+91 9876543210",
          estimated_value: 1500,
          sla_deadline: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
          distance_km: 4.5,
          required_skills: [],
        },
      };
      setSelectedNotification(tempNotif);
      setSelectedJobDetail(tempNotif.job);
      setIsNotificationDrawerOpen(false);
    }
  };

  // Helper function to trigger mock dispatch events (cycles through all types)
  const MOCK_EVENTS = [
    {
      eventType: "job.assigned",
      type: "info" as const,
      title: "Job Assigned",
      message: "AC Repair Service → Rajesh Kumar",
      autoDismiss: 5000,
      priority: "normal",
      jobId: 101,
    },
    {
      eventType: "job.accepted",
      type: "success" as const,
      title: "Job Accepted",
      message: "Rajesh Kumar accepted AC Repair at ABC Corp",
      autoDismiss: 5000,
      priority: "normal",
      jobId: 101,
    },
    {
      eventType: "job.rejected",
      type: "warning" as const,
      title: "Job Rejected",
      message: "Vijay Iyer rejected Plumbing — Too far",
      autoDismiss: 8000,
      priority: "critical",
      jobId: 102,
    },
    {
      eventType: "job.expired",
      type: "error" as const,
      title: "Job Expired",
      message: "Electrical Repair — Re-dispatching…",
      autoDismiss: 10000,
      priority: "critical",
      jobId: 103,
    },
    {
      eventType: "job.en_route",
      type: "info" as const,
      title: "Tech En Route",
      message: "Arjun Sharma is en route — ETA 12 min",
      autoDismiss: 5000,
      priority: "normal",
      jobId: 104,
    },
  ];
  const mockCursorRef = useRef(0);

  const triggerMockNotification = () => {
    const event = MOCK_EVENTS[mockCursorRef.current % MOCK_EVENTS.length];
    mockCursorRef.current += 1;

    // Fire as toast
    // Fire as toast
    addToast({
      title: event.title,
      message: event.message,
      type: "info",
      autoDismiss: event.autoDismiss,
      priority: "low" as any,
    });

    // Also populate the bell/drawer with an equivalent notification
    const newNotif: NotificationItem = {
      id: `notif-${Date.now()}`,
      type: event.eventType === "job.assigned" ? "JOB_ASSIGNED" : "SYSTEM",
      title: event.title,
      message: event.message,
      isRead: false,
      createdAt: new Date().toISOString(),
      jobId: event.jobId,
      job: {
        id: event.jobId,
        title: event.title,
        description: event.message,
        location: "Chennai",
        priority: event.priority === "critical" ? "HIGH" : "MEDIUM",
        customer_name: "Demo Customer",
        customer_phone: "+91 9876543210",
        estimated_value: 2500,
        sla_deadline: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
        distance_km: 6.8,
        required_skills: [],
      },
    };
    setNotifications((prev) => [newNotif, ...prev]);
    setUnreadCount((prev) => prev + 1);
    setIsBellAnimated(true);
    setTimeout(() => setIsBellAnimated(false), 1000);
  };

  const getItemStyle = (tab: string, isSub = false) => {
    const active = activeTab === tab;
    let base = {
      ...styles.navItem,
      ...(isMobileLayout ? styles.navItemMobile : {}),
      ...(!isMobileLayout && sidebarCollapsed ? styles.navItemCollapsed : {}),
      ...(isSub ? { fontSize: "13px", padding: "5px 6px" } : {}),
    };
    if (active) {
      base = {
        ...base,
        ...styles.navActive,
        ...(isMobileLayout ? styles.navActiveMobile : {}),
      };
    }
    return base;
  };

  return (
    <div style={styles.appShell}>
      <style>{localCss}</style>
      <aside
        style={
          isMobileLayout
            ? styles.sidebarMobile
            : sidebarCollapsed
              ? { ...styles.sidebar, ...styles.sidebarCollapsed }
              : styles.sidebar
        }
      >
        <button
          className="sidebar-toggle-style"
          style={
            isMobileLayout
              ? { display: "none" }
              : sidebarCollapsed
                ? { ...styles.sidebarToggle, ...styles.sidebarToggleCollapsed }
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

        <div
          className="sidebar-content-style"
          style={{
            ...styles.sidebarContent,
            ...(isMobileLayout ? styles.sidebarContentMobile : {}),
            ...(!isMobileLayout && sidebarCollapsed
              ? styles.sidebarContentCollapsed
              : {}),
          }}
        >
          <div
            style={isMobileLayout ? { display: "none" } : styles.sidebarBrand}
          >
            <div style={styles.brandLogoWrap}>
              <img src={logo} alt="FieldOps Logo" style={styles.brandLogoImg} />
            </div>
          </div>

          {isTechnician ? (
            <nav
              style={
                isMobileLayout ? styles.sidebarNavMobile : styles.sidebarNav
              }
            >
              <span
                style={
                  isMobileLayout || sidebarCollapsed
                    ? { display: "none" }
                    : styles.navGroupLabel
                }
              >
                TECHNICIAN
              </span>
              <button
                className="nav-item-style"
                style={getItemStyle("tech_dashboard")}
                onClick={() => handleTabChange("tech_dashboard")}
              >
                <LayoutDashboard size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={sidebarCollapsed ? { display: "none" } : {}}
                >
                  Dashboard
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("tech_jobs")}
                onClick={() => handleTabChange("tech_jobs")}
              >
                <Briefcase size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={sidebarCollapsed ? { display: "none" } : {}}
                >
                  Assigned Jobs
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("tech_history")}
                onClick={() => handleTabChange("tech_history")}
              >
                <History size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={sidebarCollapsed ? { display: "none" } : {}}
                >
                  Job History
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("tech_notifications")}
                onClick={() => handleTabChange("tech_notifications")}
              >
                <BellRing size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={sidebarCollapsed ? { display: "none" } : {}}
                >
                  Notifications
                </span>
              </button>
            </nav>
          ) : isCustomer ? (
            <nav
              style={
                isMobileLayout ? styles.sidebarNavMobile : styles.sidebarNav
              }
            >
              <span
                style={
                  isMobileLayout || sidebarCollapsed
                    ? { display: "none" }
                    : styles.navGroupLabel
                }
              >
                CUSTOMER PORTAL
              </span>
              <button
                className="nav-item-style"
                style={getItemStyle("cust_dashboard")}
                onClick={() => handleTabChange("cust_dashboard")}
              >
                <LayoutDashboard size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Dashboard
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("cust_profile")}
                onClick={() => handleTabChange("cust_profile")}
              >
                <User size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  My Profile
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("cust_create_request")}
                onClick={() => handleTabChange("cust_create_request")}
              >
                <PlusCircle size={18} style={{ flexShrink: 0 }} />
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
              <button
                className="nav-item-style"
                style={getItemStyle("cust_requests")}
                onClick={() => handleTabChange("cust_requests")}
              >
                <FileText size={18} style={{ flexShrink: 0 }} />
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
              <button
                className="nav-item-style"
                style={getItemStyle("cust_tracking")}
                onClick={() => handleTabChange("cust_tracking")}
              >
                <Navigation size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Job Tracking
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("cust_notifications")}
                onClick={() => handleTabChange("cust_notifications")}
              >
                <BellRing size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Notifications
                </span>
              </button>
              <button
                className="nav-item-style"
                style={getItemStyle("cust_history")}
                onClick={() => handleTabChange("cust_history")}
              >
                <History size={18} style={{ flexShrink: 0 }} />
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
              <button
                className="nav-item-style"
                style={getItemStyle("cust_settings")}
                onClick={() => handleTabChange("cust_settings")}
              >
                <Settings size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
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
                isMobileLayout ? styles.sidebarNavMobile : styles.sidebarNav
              }
            >
              <span
                style={
                  isMobileLayout || sidebarCollapsed
                    ? { display: "none" }
                    : styles.navGroupLabel
                }
              >
                MAIN MENU
              </span>

              <button
                className="nav-item-style"
                style={getItemStyle("dashboard")}
                onClick={() => handleTabChange("dashboard")}
              >
                <LayoutDashboard size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Dashboard
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle("jobs")}
                onClick={() => handleTabChange("jobs")}
              >
                <Briefcase size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Jobs
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle("techboard")}
                onClick={() => handleTabChange("techboard")}
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
                  Technicians
                </span>
              </button>
              {!isDispatcher && (
                <button
                  className="nav-item-style"
                  style={getItemStyle("dispatchers")}
                  onClick={() => handleTabChange("dispatchers")}
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
                style={getItemStyle("planning")}
                onClick={() => handleTabChange("planning")}
              >
                <Calendar size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Planning
                </span>
              </button>

              <button
                className="nav-item-style"
                style={getItemStyle("tracking")}
                onClick={() => handleTabChange("tracking")}
              >
                <Activity size={18} style={{ flexShrink: 0 }} />
                <span
                  className="nav-text"
                  style={
                    isMobileLayout || sidebarCollapsed
                      ? { display: "none" }
                      : {}
                  }
                >
                  Live Tracking
                </span>
              </button>
            </nav>
          )}

          {/* Active tech switcher and demo controls for Admin/Dispatcher */}
          {isAdminOrDispatcher && (
            <div
              style={
                isMobileLayout || sidebarCollapsed
                  ? { display: "none" }
                  : styles.sidebarSimulationControls
              }
              onMouseEnter={ensureActiveTechLoaded}
            >
              <div style={styles.simulationCard}>
                <div style={styles.simulationHeader}>
                  <div style={styles.simulationTitleWrap}>
                    <FlaskConical
                      size={14}
                      color="#0F9D58"
                      style={{ flexShrink: 0 }}
                    />
                    <span style={styles.simulationTitle}>Simulation Lab</span>
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "4px",
                  }}
                >
                  <span style={styles.simulationLabel}>
                    Simulated Technician
                  </span>
                  <div style={styles.dropdownWrapper}>
                    <div style={styles.userCircle}>
                      <User size={12} color="#0F9D58" />
                    </div>
                    {techList.length === 0 ? (
                      <select
                        style={styles.simulationSelect}
                        onClick={ensureActiveTechLoaded}
                        onFocus={ensureActiveTechLoaded}
                      >
                        <option>Click to load techs...</option>
                      </select>
                    ) : (
                      activeTechId !== null && (
                        <select
                          style={styles.simulationSelect}
                          value={activeTechId}
                          onChange={(e) => setActiveTechId(e.target.value)}
                        >
                          {techList.map((t) => {
                            const val = t.tech_id || t.technician_id || t.id;
                            return (
                              <option key={val} value={val}>
                                {t.technician_name || t.name}
                              </option>
                            );
                          })}
                        </select>
                      )
                    )}
                    <ChevronDown
                      size={14}
                      color="#64748B"
                      style={styles.dropdownChevron}
                    />
                  </div>
                </div>

                <button
                  type="button"
                  className="simulate-alert-btn-style"
                  style={styles.simulateAlertBtn}
                  onClick={() => {
                    ensureActiveTechLoaded().then(() => {
                      triggerMockNotification();
                    });
                  }}
                  title="Test Notification UI"
                >
                  <BellRing
                    size={16}
                    color="#FFFFFF"
                    style={{ flexShrink: 0 }}
                  />
                  <span>Simulate Alert</span>
                </button>
              </div>
            </div>
          )}

          <div
            style={
              isMobileLayout
                ? { display: "none" }
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
                display: "flex",
                alignItems: "center",
                gap: "10px",
                cursor: "pointer",
                flex: 1,
                minWidth: 0,
              }}
              title="Click to open Profile & Settings"
            >
              <div style={styles.miniAvatar}>
                {user?.first_name ? user.first_name[0].toUpperCase() : "U"}
              </div>

              <div
                style={sidebarCollapsed ? { display: "none" } : styles.miniInfo}
              >
                <span style={styles.miniName}>
                  {user ? `${user.first_name} ${user.last_name}` : "User"}
                </span>
                <span style={styles.miniRole}>
                  {user ? user.role.replace("_", " ").toUpperCase() : "Role"}
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
                onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "#94a3b8")}
              >
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <div
        style={
          isMobileLayout
            ? { ...styles.mainArea, ...styles.mainAreaMobile }
            : styles.mainArea
        }
      >
        <main
          style={{
            ...styles.pageWrap,
            ...(isMobileLayout ? styles.pageWrapMobile : {}),
            overflowY: activeTab === "dashboard" ? "auto" : "hidden",
          }}
        >
          {/* Selected Notification Detail view */}
          {selectedNotification && (
            <NotificationDetail
              notification={selectedNotification as any}
              job={selectedJobDetail}
              onAccept={handleAcceptJob}
              onReject={handleRejectJob}
              onReassign={handleReassignJob}
              onClose={() => {
                setSelectedNotification(null);
                setSelectedJobDetail(null);
              }}
            />
          )}

          {isNavigating ? (
            <LoadingSpinner
              message={getLoadingMessage(activeTab)}
              fullPage={true}
            />
          ) : (
            <Suspense
              fallback={
                <LoadingSpinner message="Loading page..." fullPage={true} />
              }
            >
              {/* Admin / Dispatcher Tabs */}
              {activeTab === "dashboard" && (
                <DashboardPage
                  onViewTab={(tab) => handleTabChange(tab)}
                  unreadCount={unreadCount}
                  isBellAnimated={isBellAnimated}
                  onOpenBellDrawer={() => {
                    setIsNotificationDrawerOpen(true);
                    ensureActiveTechLoaded();
                  }}
                />
              )}
              {activeTab === "jobs" && <JobsPage />}
              {activeTab === "techboard" && <TechDashboardPage />}
              {activeTab === "dispatchers" && <DispatcherPage />}
              {activeTab === "planning" && <PlanningPage />}
              {activeTab === "tracking" && <TrackingDashboardPage />}
              {activeTab === "profile" && <ProfilePage />}

              {/* Technician Portal Tabs */}
              {activeTab === "tech_dashboard" && (
                <TechnicianPortalDashboard onNavigate={handleTabChange} />
              )}
              {activeTab === "tech_profile" && <TechnicianProfilePage />}
              {activeTab === "tech_jobs" && <TechnicianJobsPage />}
              {activeTab === "tech_history" && <TechnicianJobHistoryPage />}
              {activeTab === "tech_notifications" && (
                <TechnicianNotificationsPage />
              )}
              {activeTab === "tech_settings" && <TechnicianSettingsPage />}

              {/* Customer Portal Tabs */}
              {activeTab === "cust_dashboard" && (
                <CustomerPortalDashboard onNavigate={handleTabChange} />
              )}
              {activeTab === "cust_profile" && <CustomerProfilePage />}

              {activeTab === "cust_create_request" && (
                <CustomerServiceRequestsPage
                  createOnly={true}
                  onNavigate={handleTabChange}
                />
              )}

              {activeTab === "cust_requests" && (
                <CustomerServiceRequestsPage
                  createOnly={false}
                  onNavigate={handleTabChange}
                />
              )}

              {activeTab === "cust_tracking" && <CustomerJobTrackingPage />}
              {activeTab === "cust_notifications" && (
                <CustomerNotificationsPage />
              )}
              {activeTab === "cust_history" && <CustomerServiceHistoryPage />}
              {activeTab === "cust_settings" && <CustomerSettingsPage />}
            </Suspense>
          )}
        </main>
      </div>

      {/* Slide-out Drawer */}
      <NotificationDrawer
        isOpen={isNotificationDrawerOpen}
        onClose={() => setIsNotificationDrawerOpen(false)}
        notifications={notifications as any}
        onNotificationClick={handleNotificationClick}
        onMarkAllAsRead={handleMarkAllAsRead}
        onDismissNotification={handleDismissNotification}
      />

      {/* Real-time toast overlay */}
      <ToastContainer onNavigate={handleToastNavigate} />
    </div>
  );
}

// Wrap with ToastProvider & Auth check at the root
function AppContent() {
  const { isAuthenticated, loadFromStorage } = useAuthStore();
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    if (isAuthenticated) {
      setShowOnboarding(false);
    }
  }, [isAuthenticated]);

  // Show organization onboarding page
  if (!isAuthenticated && showOnboarding) {
    return (
      <Suspense fallback={<LoadingSpinner />}>
        <OrganizationOnboardingPage
          onBackToLogin={() => setShowOnboarding(false)}
        />
      </Suspense>
    );
  }

  // Show login page
  if (!isAuthenticated) {
    return (
      <Suspense fallback={<LoadingSpinner />}>
        <LoginPage onCreateOrganization={() => setShowOnboarding(true)} />
      </Suspense>
    );
  }

  // User is authenticated
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
