export type StaffRole = 'super_admin' | 'dispatcher';

export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  tenant_id: string;
  organization_name?: string | null;
  is_active?: boolean;
}

export interface Technician {
  technician_id: number;
  tech_id?: string | null;
  technician_name: string;
  technician_skill?: string;
  technician_location?: string;
  technician_status?: string;
  current_jobs?: number;
  max_jobs?: number;
  latitude?: number | null;
  longitude?: number | null;
  last_ping?: string | null;
  phone_number?: string | null;
  mobile_number?: string | null;
  email?: string | null;
}

export interface Dispatcher {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  name?: string;
  role: string;
  tenant_id: string;
  organization_name?: string | null;
  is_active: boolean;
  is_on_duty: boolean;
  phone_number?: string | null;
  last_login?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Job {
  id: number | string;
  job_id?: number | string;
  title?: string;
  customer_name?: string;
  customer?: string;
  service_type?: string;
  issue_description?: string;
  location?: string;
  priority?: string;
  status?: string;
  assigned_technician_id?: number | null;
  assigned_technician?: string | null;
  technician?: { tech_id?: string; name?: string; status?: string } | null;
  sla_deadline?: string | null;
  created_at?: string | null;
  preferred_service_date?: string | null;
  [key: string]: any;
}

export interface ServiceCatalogItem {
  id: number;
  tenant_id?: string | null;
  service_type: string;
  category: string;
  issue: string;
  description?: string | null;
  is_active: boolean;
  priority?: string;
  required_skill?: string | null;
}

export interface LivePosition {
  id: string;
  technicianId: string;
  name: string;
  latitude: number;
  longitude: number;
  status: string;
  lastPing?: string | null;
  accuracy?: number | null;
  jobId?: string | number | null;
  phone?: string | null;
  skill?: string | null;
}

export interface AgentStage {
  key: string;
  label: string;
  state: string;
  detail: string;
  timestamp: string | null;
}

export interface AgentJob {
  job_id: number;
  job_number: string | number;
  service_type: string;
  status: string;
  priority: string;
  technician_name: string | null;
  customer_name: string | null;
  location: string | null;
  created_at: string | null;
  updated_at: string | null;
  assigned_at: string | null;
  accepted: boolean;
  current_agent: string;
  current_detail: string;
  stages: AgentStage[];
}
