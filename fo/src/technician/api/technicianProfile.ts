import { apiClient } from "./client";

export interface TechnicianProfile {
  id?: string;
  full_name: string;
  email?: string;
  mobile_number: string;
  date_of_birth?: string | null;
  gender?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  emergency_contact?: string | null;
  skills: string[];
  experience?: string | null;
  certifications: string[];
  profile_photo?: string | null;
  profile_completed: boolean;
}

export interface ServicesTaxonomy {
  service_types: string[];
  categories_by_type: Record<string, string[]>;
  issues_by_category: Record<string, Array<{
    issue: string;
    category?: string;
    service_type?: string;
    description?: string;
  }>>;
}

export async function getTechnicianProfile(): Promise<TechnicianProfile> {
  const response = await apiClient.get<TechnicianProfile>("/api/technician/profile");
  return response.data;
}

export async function saveTechnicianProfile(
  profile: TechnicianProfile,
  create: boolean
): Promise<TechnicianProfile> {
  const payload = {
    full_name: profile.full_name,
    mobile_number: profile.mobile_number,
    date_of_birth: profile.date_of_birth || null,
    gender: profile.gender || null,
    address: profile.address || null,
    city: profile.city || null,
    state: profile.state || null,
    pincode: profile.pincode || null,
    emergency_contact: profile.emergency_contact || null,
    skills: profile.skills,
    experience: profile.experience || null,
    certifications: profile.certifications,
    profile_photo: profile.profile_photo || null
  };
  const response = create
    ? await apiClient.post<TechnicianProfile>("/api/technician/profile", payload)
    : await apiClient.put<TechnicianProfile>("/api/technician/profile", payload);
  return response.data;
}

export async function getOrganizationServicesTaxonomy(
  tenantId?: string | number
): Promise<ServicesTaxonomy> {
  const response = await apiClient.get<ServicesTaxonomy>("/api/services/taxonomy", {
    params: tenantId ? { tenant_id: tenantId } : undefined
  });
  return response.data;
}
