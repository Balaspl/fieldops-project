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

const dispatcherService = {
  getDispatchers,
};

export default dispatcherService;
