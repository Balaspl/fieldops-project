import api from "./api";

export interface ServiceCatalogItem {
  id: number;
  tenant_id?: string;
  service_type: string;
  category: string;
  issue: string;
  description?: string;
  is_active: boolean;
  priority?: string;
  required_skill?: string;
}

export interface CreateServiceCatalogPayload {
  service_type: string;
  category: string;
  issue: string;
  description?: string;
  priority?: string;
}

export interface CategoryIssueGroupPayload {
  category: string;
  issues: string[];
}

export interface CreateServiceCatalogBatchPayload {
  service_type: string;
  groups: CategoryIssueGroupPayload[];
}

export interface TaxonomySuggestionsResponse {
  service_types: string[];
  categories_by_type: Record<string, string[]>;
  issues_by_category: Record<string, string[]>;
}

export interface TaxonomyIssueItem {
  id: number;
  issue: string;
  description: string;
  service_type: string;
  category: string;
  priority?: string;
}

export interface ServicesTaxonomyResponse {
  service_types: string[];
  categories_by_type: Record<string, string[]>;
  issues_by_category: Record<string, TaxonomyIssueItem[]>;
  raw_items: ServiceCatalogItem[];
}

export const getAdminServices = async (serviceType?: string, search?: string): Promise<ServiceCatalogItem[]> => {
  const params: any = {};
  if (serviceType && serviceType !== "ALL") params.service_type = serviceType;
  if (search) params.search = search;
  const res = await api.get("/api/admin/services", { params });
  return res.data;
};

export const getTaxonomySuggestions = async (): Promise<TaxonomySuggestionsResponse> => {
  const res = await api.get("/api/admin/services/taxonomy-suggestions");
  return res.data;
};

export const createAdminService = async (payload: CreateServiceCatalogPayload): Promise<ServiceCatalogItem> => {
  const res = await api.post("/api/admin/services", payload);
  return res.data;
};

export const createAdminServicesBatch = async (
  payload: CreateServiceCatalogBatchPayload
): Promise<ServiceCatalogItem[]> => {
  const res = await api.post("/api/admin/services/batch", payload);
  return res.data;
};

export const toggleServiceActive = async (id: number): Promise<ServiceCatalogItem> => {
  const res = await api.patch(`/api/admin/services/${id}/toggle-active`);
  return res.data;
};

export const deleteAdminService = async (id: number): Promise<void> => {
  await api.delete(`/api/admin/services/${id}`);
};

export const getCustomerCatalog = async (tenantId?: string): Promise<ServiceCatalogItem[]> => {
  const params: any = {};
  if (tenantId) params.tenant_id = tenantId;
  const res = await api.get("/api/services/catalog", { params });
  return res.data;
};

export const getServicesTaxonomy = async (tenantId?: string): Promise<ServicesTaxonomyResponse> => {
  const params: any = {};
  if (tenantId) params.tenant_id = tenantId;
  const res = await api.get("/api/services/taxonomy", { params });
  return res.data;
};
