export interface AuthUser {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role: string;
  tenant_id: string;
  organization_name?: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export interface MfaChallengeResponse {
  status: string;
  mfa_required: true;
  challenge: string;
  expires_in: number;
}

export type LoginResponse = TokenResponse | MfaChallengeResponse;

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

export interface DashboardStats {
  total_requests: number;
  pending_requests: number;
  active_jobs: number;
  completed_jobs: number;
}

export interface ServiceCatalogItem {
  id: number;
  tenant_id?: string | null;
  service_type: string;
  category: string;
  issue: string;
  description?: string | null;
  is_active?: boolean;
  priority?: string | null;
  required_skill?: string | null;
}

export interface ServiceRequest {
  id: number;
  request_number: string;
  customer_user_id?: string;
  tenant_id?: string;
  title: string;
  description: string;
  service_type?: string | null;
  priority: string;
  preferred_visit_date?: string | null;
  images?: string[] | null;
  location?: string | null;
  contact_number?: string | null;
  status: string;
  linked_job_id?: number | null;
  assigned_technician_id?: number | null;
  assigned_technician_name?: string | null;
  assigned_technician_phone?: string | null;
  created_job?: {
    id: number;
    status?: string;
    site_latitude?: number | null;
    site_longitude?: number | null;
  } | null;
  cancellation_reason?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerJob {
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

  // Tracking timeline and journey details
  technician_accepted?: boolean;
  accepted_at?: string | null;
  assigned_at?: string | null;
  en_route_at?: string | null;
  distance_travelled_km?: number | null;
  issue_description?: string | null;
  preferred_service_date?: string | null;
  preferred_service_time?: string | null;

  // Technician GPS information
  technician_latitude: number | null;
  technician_longitude: number | null;
  technician_accuracy: number | null;
  technician_last_ping: string | null;

  // Live tracking and ETA
  live_tracking: boolean;
  tracking_tenant_id: string | null;
  estimated_arrival: string | null;
  eta_status: string | null;
  eta_source: string | null;
  eta_confidence: string | null;
  eta_duration_minutes: number | null;
  eta_distance_km: number | null;
  eta_traffic_delay_minutes: number | null;
  eta_message: string | null;
  eta_updated_at: string | null;

  // Job lifecycle timestamps
  created_at: string | null;
  on_site_at: string | null;
  work_started_at: string | null;
  completed_at: string | null;
}

export interface JobMessage {
  id: string;
  job_id: number;
  sender_user_id: string;
  sender_role: "CUSTOMER" | "TECHNICIAN";
  body: string;
  created_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  is_mine: boolean;
  delivery_status?: string;
}

export interface JobConversation {
  job_id: number;
  job_reference: string;
  status: string;
  participant_name: string | null;
  technician_name: string | null;
  assigned: boolean;
  can_send: boolean;
  read_only_reason: string | null;
  unread_count: number;
  messages: JobMessage[];
}

export interface CustomerInvoice {
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
  organization_name?: string | null;
  technician_name?: string | null;
}

export interface PaymentHistoryItem {
  invoice_id: string;
  job_id: number;
  service_type: string;
  total_amount: number;
  payment_status: string;
  payment_status_updated_at: string | null;
  invoice_created_at: string | null;
  completed_at: string | null;
}

export interface PaymentStatus {
  job_id: number;
  invoice_id: number | null;
  status: "PENDING" | "SUCCESSFUL" | "FAILED" | "UNAVAILABLE";
  updated_at: string | null;
}

export interface ServiceHistoryItem {
  linked_job_id?: number | null;
  title?: string | null;
  service_type?: string | null;
  status?: string | null;
  created_at?: string | null;
}

export interface CustomerFeedback {
  job_id: number;
  has_feedback: boolean;
  feedback: {
    id: number;
    rating: number;
    comment: string | null;
    created_at: string | null;
    updated_at: string | null;
  } | null;
}

export interface CustomerNotification {
  id: string;
  type?: string | null;
  title?: string | null;
  message?: string | null;
  status?: string | null;
  isRead?: boolean;
  createdAt?: string | null;
  jobId?: number | null;
  groupKey?: string | null;
  eventVersion?: number | null;
  metadata?: Record<string, unknown>;
}

export interface NotificationFeed {
  notifications: CustomerNotification[];
  unread_count: number;
}

export interface NotificationPreferences {
  profile_id: string | null;
  tenant_id: string;
  customer_id: string;
  sms_enabled: boolean;
  email_enabled: boolean;
  push_enabled: boolean;
  portal_enabled: boolean;
  preferred_locale: string;
  daily_engagement_enabled: boolean;
  timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  revision: number;
  source: string;
  updated_at: string | null;
  updated_by: string | null;
}

export interface SupportRequest {
  id: number;
  request_number: string;
  subject: string;
  description: string;
  related_job_id: number | null;
  status: string;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LocationSearchResult {
  name?: string | null;
  formatted_address: string;
  latitude: number;
  longitude: number;
  place_id?: string | null;
  type?: string | null;
}

export interface ReverseLocation {
  verified?: boolean;
  address?: string;
  display_name?: string;
  formatted_address?: string;
  name?: string;
  city?: string;
  state?: string;
  pincode?: string;
  latitude?: number;
  longitude?: number;
  message?: string;
}