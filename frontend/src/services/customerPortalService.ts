/**
 * Customer Portal API service.
 * All API calls for the customer portal.
 *
 * Customer profile requests intentionally use the backend's
 * authenticated customer scope. The frontend does not send
 * tenant_id or user_id as an authorization selector.
 */
import api from "./api";

export interface CustomerProfile {
  id: string;
  user_id: string;
  tenant_id: string;
  full_name: string;
  mobile_number: string;
  address: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  company_name: string | null;
  profile_completed: boolean;
  email: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerProfilePayload {
  full_name: string;
  mobile_number: string;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  company_name?: string | null;
}

export interface CustomerProfileResponse extends CustomerProfile {}

export interface ChangeCustomerPasswordPayload {
  current_password: string;
  new_password: string;
  confirm_password: string;
}


export interface CustomerNotificationPreferences {
  profile_id: string | null;
  tenant_id: string;
  customer_id: string;
  sms_enabled: boolean;
  email_enabled: boolean;
  push_enabled: boolean;
  portal_enabled: boolean;
  preferred_locale: string;
  revision: number;
  source:
    | "PROFILE"
    | "COMPATIBILITY_DEFAULT";
  updated_at: string | null;
  updated_by: string | null;
}

export interface CustomerNotificationPreferencesUpdate {
  sms_enabled?: boolean;
  email_enabled?: boolean;
  push_enabled?: boolean;
  portal_enabled?: boolean;
  preferred_locale?: string;
}


export interface CustomerSupportRequestCreate {
  subject: string;
  description: string;
}

export interface CustomerSupportRequestResponse {
  id: number;
  request_number: string;
  subject: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}
// Profile
export const getCustomerProfile = () =>
  api.get<CustomerProfileResponse>(
    "/api/customer/profile",
  );

export const createCustomerProfile = (
  data: CustomerProfilePayload,
) =>
  api.post<CustomerProfileResponse>(
    "/api/customer/profile",
    data,
  );

export const updateCustomerProfile = (
  data: Partial<CustomerProfilePayload>,
) =>
  api.put<CustomerProfileResponse>(
    "/api/customer/profile",
    data,
  );

export const changeCustomerPassword = (
  data: ChangeCustomerPasswordPayload,
) =>
  api.post(
    "/api/customer/change-password",
    data,
  );

// Notification Preferences

export const getCustomerNotificationPreferences = () =>
  api.get<CustomerNotificationPreferences>(
    "/api/customer/notification-preferences",
  );

export const updateCustomerNotificationPreferences = (
  data: CustomerNotificationPreferencesUpdate,
) =>
  api.patch<CustomerNotificationPreferences>(
    "/api/customer/notification-preferences",
    data,
  );

// Service Requests
export const getServiceRequests = (
  status?: string,
) =>
  api.get(
    "/api/customer/service-requests",
    {
      params: status
        ? { status }
        : {},
    },
  );

export const createServiceRequest = (
  data: any,
) =>
  api.post(
    "/api/customer/service-requests",
    data,
  );

export const getServiceRequest = (
  id: number,
) =>
  api.get(
    `/api/customer/service-requests/${id}`,
  );

export const updateServiceRequest = (
  id: number,
  data: any,
) =>
  api.put(
    `/api/customer/service-requests/${id}`,
    data,
  );

export const cancelServiceRequest = (
  id: number,
) =>
  api.post(
    `/api/customer/service-requests/${id}/cancel`,
  );

// Customer Support Requests

export const getCustomerSupportRequests = () =>
  api.get<CustomerSupportRequestResponse[]>(
    "/api/customer/support-requests",
  );

export const createCustomerSupportRequest = (
  data: CustomerSupportRequestCreate,
) =>
  api.post<CustomerSupportRequestResponse>(
    "/api/customer/support-requests",
    data,
  );

// Job Tracking
export interface CustomerJobTrackingResponse {
  id: number;
  customer_name: string | null;
  status: string | null;
  priority: string | null;
  service_type: string | null;
  location: string | null;
  site_address: string | null;
  site_latitude: number | null;
  site_longitude: number | null;
  assigned_technician_id: number | null;
  assigned_technician_name: string | null;
  assigned_technician_photo: string | null;
  assigned_technician_phone: string | null;
  assigned_technician_skills: string[] | null;
  assigned_technician_experience: string | null;
  assigned_technician_certifications: string[] | null;
  technician_latitude: number | null;
  technician_longitude: number | null;
  technician_accuracy: number | null;
  technician_last_ping: string | null;
  live_tracking: boolean;
  tracking_tenant_id: string | null;

  // Backend-authoritative customer ETA fields.
  estimated_arrival: string | null;
  eta_status: string | null;
  eta_source: string | null;
  eta_confidence: string | null;
  eta_duration_minutes: number | null;
  eta_distance_km: number | null;
  eta_traffic_delay_minutes: number | null;
  eta_message: string | null;
  eta_updated_at: string | null;

  created_at: string | null;
  completed_at: string | null;
}

export const getCustomerJobs = () =>
  api.get<CustomerJobTrackingResponse[]>(
    "/api/customer/jobs",
  );

export const getCustomerJobDetail = (
  id: number,
) =>
  api.get<CustomerJobTrackingResponse>(
    `/api/customer/jobs/${id}`,
  );

// Customer Invoice View
export interface CustomerInvoiceResponse {
  id: string;
  job_id: number;
  customer_name: string;
  service_type: string;
  location: string;
  work_summary: string;
  labour_cost: number;
  material_cost: number;
  subtotal: number;
  gst_rate: number;
  gst_amount: number;
  total_amount: number;
  completed_at: string | null;
  created_at: string | null;
}

export interface CustomerPaymentHistoryResponse {
  invoice_id: string;
  job_id: number;
  service_type: string;
  total_amount: number;
  payment_status: string;
  payment_status_updated_at: string | null;
  invoice_created_at: string | null;
  completed_at: string | null;
}

export interface CustomerPaymentStatusResponse {
  job_id: number;
  invoice_id: number | null;
  status: "PENDING" | "SUCCESSFUL" | "FAILED" | "UNAVAILABLE";
  updated_at: string | null;
}

export const getCustomerInvoices = () =>
  api.get<CustomerInvoiceResponse[]>(
    "/api/customer/invoices",
  );

export const getCustomerInvoice = (
  jobId: number,
) =>
  api.get<CustomerInvoiceResponse>(
    `/api/customer/invoices/${jobId}`,
  );

export const getCustomerPaymentHistory = () =>
  api.get<CustomerPaymentHistoryResponse[]>(
    "/api/customer/payment-history",
  );

export const getCustomerPaymentStatus = (
  jobId: number,
) =>
  api.get<CustomerPaymentStatusResponse>(
    `/api/customer/invoices/${jobId}/payment-status`,
  );

// Service History
export const getServiceHistory = () =>
  api.get(
    "/api/customer/service-history",
  );

// Customer Feedback
export interface CustomerFeedbackSubmitRequest {
  rating: number;
  comment?: string | null;
}

export interface CustomerFeedbackRecordResponse {
  id: number;
  rating: number;
  comment: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CustomerFeedbackResponse {
  job_id: number;
  has_feedback: boolean;
  feedback: CustomerFeedbackRecordResponse | null;
}

export const getCustomerFeedback = (
  jobId: number,
) =>
  api.get<CustomerFeedbackResponse>(
    `/api/customer/jobs/${jobId}/feedback`,
  );

export const submitCustomerFeedback = (
  jobId: number,
  data: CustomerFeedbackSubmitRequest,
) =>
  api.post<CustomerFeedbackResponse>(
    `/api/customer/jobs/${jobId}/feedback`,
    data,
  );

// Notifications
export const getCustomerNotifications = () =>
  api.get(
    "/api/customer/notifications",
  );

export const markCustomerNotificationRead = (
  id: string,
) =>
  api.put(
    `/api/customer/notifications/${id}/read`,
  );

export const markAllCustomerNotificationsRead = () =>
  api.put(
    "/api/customer/notifications/read-all",
  );

// Dashboard
export const getCustomerDashboard = () =>
  api.get(
    "/api/customer/dashboard",
  );

// Planning - Declined Jobs (Admin/Dispatcher)
export const getDeclinedJobs = () =>
  api.get(
    "/planning/declined-jobs",
  );

export const reassignDeclinedJob = (
  jobId: number,
  newTechnicianId: number,
) =>
  api.post(
    `/planning/declined-jobs/${jobId}/reassign?new_technician_id=${newTechnicianId}`,
  );
