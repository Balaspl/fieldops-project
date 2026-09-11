import api from "./api";

export interface Dispatcher {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  role: string;
  tenant_id: string;
  organization_name: string | null;
  is_active: boolean;
  is_on_duty: boolean;
  phone_number: string | null;
  last_login: string | null;
}

/**
 * Get dispatchers belonging to the current active tenant.
 *
 * Backend is responsible for tenant isolation.
 * The JWT token is automatically attached by api.ts.
 */
export const getDispatchers = async (): Promise<Dispatcher[]> => {
  const response = await api.get<Dispatcher[]>("/dispatchers");
  return response.data;
};

/**
 * Request body for provisioning a technician.
 *
 * Tenant/organization and role are NOT sent from the frontend.
 * Backend should derive them from the authenticated dispatcher.
 */
export interface ProvisionTechnicianRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}

/**
 * Provision a new technician account.
 */
export const provisionTechnician = async (
  data: ProvisionTechnicianRequest
) => {
  const response = await api.post(
    "/dispatchers/provision-technician",
    data
  );

  return response.data;
};

const dispatcherService = {
  getDispatchers,
  provisionTechnician,
};

export default dispatcherService;