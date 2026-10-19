
export interface JobNotificationDetail {
  id: string | number;
  title: string;
  description: string;
  location: string;
  priority: string;
  customer_name: string;
  customer_phone: string;
  estimated_value: number;
  sla_deadline: string;
  distance_km: number;
  required_skills: string[];
}

/* ─── Notification Models ─────────────────────────────────────────── */

export type NotificationType =
  | "JOB_ASSIGNED"
  | "SLA_WARNING"
  | "JOB_UPDATED"
  | "SYSTEM"
  | "TECHNICIAN_ACCEPTED"
  | "TECHNICIAN_REJECTED"
  | "EN_ROUTE"
  | "ON_SITE"
  | "COMPLETED"
  | "CANCELLED"
  | "CLOSED"
  | "DELAYED";

export interface TechnicianNotification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  isRead: boolean;
  createdAt: string;
  jobId?: string | number;
  job?: JobNotificationDetail | null;

  /**
   * Stable identifier for the notification card.
   * Example: "job_123".
   */
  groupKey?: string;

  /**
   * Monotonically increasing backend event version.
   * A card should not be replaced by an older or equal version.
   */
  eventVersion?: number;
}

export interface NotificationBellProps {
  unreadCount: number;
  onClick: () => void;
  isAnimated?: boolean;
  showSound?: boolean;
  className?: string;
}

export interface NotificationDetailProps {
  notification: TechnicianNotification;
  job?: JobNotificationDetail;
  loading?: boolean;
  error?: string;
  onAccept: (jobId: string | number) => void;
  onReject: (jobId: string | number, reason: string) => void;
  onReassign: (
    jobId: string | number,
    colleagueId?: number,
    reason?: string
  ) => void;
  onClose: () => void;
  socket?: any;
}

export interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: TechnicianNotification[];
  onNotificationClick: (
    notification: TechnicianNotification
  ) => void;
  onMarkAllAsRead?: () => void;
  onDismissNotification?: (notificationId: string) => void;
  loading?: boolean;
}

export interface PermissionRequestProps {
  onPermissionChange?: (status: string) => void;
  className?: string;
  compact?: boolean;
}

/* ─── Acceptance Timer & Action Components ─────────────────────────── */

export type UrgencyLevel =
  | "safe"
  | "caution"
  | "warning"
  | "critical";

export type ActionState =
  | "IDLE"
  | "LOADING"
  | "SUCCESS"
  | "ERROR"
  | "TIMEOUT";

export interface CountdownTimerProps {
  expiresAt: string;
  onExpire: () => void;
  onWarning: () => void;
  jobId: string | number;
  hidden?: boolean;
  condensed?: boolean;
}

export interface ActionButtonsProps {
  onAccept: (jobId: string | number) => Promise<void>;
  onReject: (
    jobId: string | number,
    reason: string
  ) => Promise<void>;
  onReassign: (
    jobId: string | number,
    colleagueId?: number,
    reason?: string
  ) => Promise<void>;
  jobId: string | number;
  disabled?: boolean;
}

export interface WaitingStateProps {
  state: ActionState;
  message?: string;
  onRetry?: () => void;
  onCancel?: () => void;
  onClose?: () => void;
}

export interface UseCountdownReturn {
  minutes: number;
  seconds: number;
  totalSeconds: number;
  isExpired: boolean;
  urgencyLevel: UrgencyLevel;
}

export interface UseActionStateReturn {
  state: ActionState;
  message: string;
  execute: (
    actionFn: () => Promise<void>,
    label?: string
  ) => Promise<void>;
  retry: () => void;
  reset: () => void;
}

/* ─── Toast Notification System ────────────────────────────────────── */

export type ToastType =
  | "success"
  | "warning"
  | "error"
  | "info";

export type ToastPriority = "normal" | "critical";

export type DispatchEventType =
  | "job.assigned"
  | "job.accepted"
  | "job.rejected"
  | "job.expired"
  | "job.en_route";

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message: string;
  jobId?: string | number;
  timestamp: string;
  autoDismiss: number;
  priority: ToastPriority;
  eventType?: DispatchEventType;
  batchCount?: number;
  batchItems?: Array<{
    title: string;
    message: string;
  }>;
}

export interface ToastContextValue {
  toasts: ToastItem[];
  addToast: (
    toast: Omit<ToastItem, "id" | "timestamp">
  ) => string;
  dismissToast: (id: string) => void;
  pauseToast: (id: string) => void;
  resumeToast: (id: string) => void;
  soundEnabled: boolean;
  setSoundEnabled: (enabled: boolean) => void;
}
