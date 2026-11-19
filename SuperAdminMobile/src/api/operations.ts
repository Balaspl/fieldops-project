import { api } from './client';

export const unwrap = <T = any>(value: any): T => (value?.data !== undefined ? value.data : value) as T;
export const asArray = <T = any>(value: any): T[] => {
  const raw = unwrap<any>(value);
  if (Array.isArray(raw)) return raw as T[];
  for (const key of ['items', 'results', 'jobs', 'technicians', 'services', 'requests', 'data']) {
    if (Array.isArray(raw?.[key])) return raw[key] as T[];
  }
  return [];
};

export async function getDashboardData(timeRange = 'week', dateRange?: { start_date: string; end_date: string } | null) {
  const params: Record<string, string> = { time_range: timeRange };
  if (dateRange) {
    const [sy, sm, sd] = dateRange.start_date.split('-').map(Number);
    const [ey, em, ed] = dateRange.end_date.split('-').map(Number);
    params.start_datetime = new Date(sy, sm - 1, sd).toISOString();
    params.end_datetime = new Date(ey, em - 1, ed + 1).toISOString();
  }
  const [stats, jobs, techs] = await Promise.allSettled([
    api.get('/jobs/stats', { params }),
    api.get('/jobs'),
    api.get('/technicians'),
  ]);
  return {
    stats: stats.status === 'fulfilled' ? unwrap<any>(stats.value) : {},
    jobs: jobs.status === 'fulfilled' ? asArray(jobs.value) : [],
    technicians: techs.status === 'fulfilled' ? asArray(techs.value) : [],
    errors: [stats, jobs, techs].filter(x => x.status === 'rejected').length,
  };
}

export async function getTechnicians(params: Record<string, any> = {}) {
  return asArray(await api.get('/technicians', { params }));
}

/**
 * Load one page of technicians and preserve the backend's X-Total-Count header.
 * The technicians route applies the authenticated user's tenant scope and
 * supports server-side search, status, zone, skill, page, and limit filters.
 */
export async function getTechniciansPage(params: Record<string, any> = {}) {
  const response = await api.get('/technicians', { params });
  const items = asArray(response);
  const totalHeader = response.headers?.['x-total-count'] ?? response.headers?.['X-Total-Count'];
  const parsedTotal = Number(totalHeader);

  return {
    items,
    total: Number.isFinite(parsedTotal) && totalHeader !== undefined
      ? parsedTotal
      : items.length,
  };
}

/**
 * Fetch one technician through the existing tenant-scoped backend route.
 * The backend applies TECHNICIANS_VIEW_ALL permission and tenant filtering.
 */
export async function getTechnicianById(technicianId: number | string) {
  const id = Number(technicianId);
  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new Error('A valid technician ID is required.');
  }
  return unwrap<any>(await api.get(`/technicians/${id}`));
}

/**
 * Fetch only the jobs assigned to one technician.
 * Authorization and tenant visibility remain enforced by GET /jobs.
 */
export async function getTechnicianAssignedJobs(technicianId: number | string) {
  const id = Number(technicianId);
  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new Error('A valid technician ID is required.');
  }
  return getJobs({ technician_id: id });
}

export async function getDispatchers() {
  return asArray(await api.get('/dispatchers'));
}
export async function getJobs(params: Record<string, any> = {}) {
  return asArray(await api.get('/jobs', { params }));
}
export async function getPendingJobs(params: Record<string, any> = {}) {
  return asArray(await api.get('/jobs/pending', { params }));
}
export async function getAvailableTechnicians() {
  return asArray(await api.get('/technicians/available'));
}
export async function getJobPlan(jobId: number | string, adminOverride = false) {
  return unwrap<any>(await api.post(`/jobs/${jobId}/plan`, null, { params: { admin_override: adminOverride } }));
}
export async function assignJob(jobId: number | string, technicianId: number | string) {
  return unwrap(await api.post('/assign-job', { job_id: jobId, technician_id: technicianId }));
}
export async function assignJobsBulk(jobIds: Array<number | string>, technicianId: number | string) {
  return unwrap(await api.post('/assign-jobs-bulk', { job_ids: jobIds, technician_id: technicianId }));
}
export async function cancelJobsBulk(jobIds: Array<number | string>, reason: string) {
  return unwrap(await api.post('/jobs/bulk-cancel', { job_ids: jobIds, reason }));
}
export async function overrideAssignment(jobId: number | string, technicianId: number | string, justification: string) {
  return unwrap(await api.post(`/technicians/assignments/${jobId}/override`, { technician_id: String(technicianId), justification }));
}
export async function forceAssignEscalation(jobId: number | string, technicianId: number | string, reason: string) {
  return unwrap(await api.post(`/escalations/${jobId}/force-assign`, { tech_id: String(technicianId), reason }));
}
export async function extendEscalatedSla(jobId: number | string, minutes: number) {
  return unwrap(await api.post(`/escalations/${jobId}/extend-sla`, { minutes }));
}
export async function cancelEscalatedJob(jobId: number | string, reason: string) {
  return unwrap(await api.post(`/escalations/${jobId}/cancel`, { reason }));
}
export async function updateTechnician(id: number | string, payload: Record<string, any>) {
  return unwrap(await api.put(`/technicians/${id}`, payload));
}

/**
 * Update technician availability using the dedicated backend endpoint.
 * Backend enforces TECHNICIANS_MANAGE and tenant isolation.
 */
export async function updateTechnicianAvailability(
  technicianId: number | string,
  technician_status:
    | 'Available'
    | 'Busy'
    | 'Assigned'
    | 'Offline'
    | 'En Route'
    | 'On Site'
    | 'On Break'
    | 'Suspended'
    | 'Deactivated'
    | 'AVAILABLE'
    | 'BUSY'
    | 'ASSIGNED'
    | 'OFFLINE'
    | 'EN_ROUTE'
    | 'ON_SITE'
    | 'ON_BREAK'
    | 'SUSPENDED'
    | 'DEACTIVATED',
) {
  const id = String(technicianId).trim();

  if (!id) {
    throw new Error('A valid technician ID is required.');
  }

  return unwrap(
    await api.put(
      `/technicians/${encodeURIComponent(id)}/availability`,
      { technician_status },
    ),
  );
}
export async function deleteTechnician(id: number | string) {
  return unwrap(await api.delete(`/technicians/${id}`));
}
export async function provisionTechnician(payload: {
  first_name: string; last_name: string; email: string; password: string;
  phone_number?: string; technician_skill: string; technician_location: string;
}) {
  return unwrap(await api.post('/dispatchers/provision-technician', payload));
}
export interface ServiceCatalogBatchPayload {
  service_type: string;
  groups: Array<{
    category: string;
    issues: string[];
  }>;
}

export async function getServices(search?: string) {
  return asArray(await api.get('/api/admin/services', { params: search ? { search } : undefined }));
}
export async function getTaxonomy() {
  return unwrap<any>(await api.get('/api/admin/services/taxonomy-suggestions'));
}
export async function createService(payload: Record<string, any>) {
  return unwrap(await api.post('/api/admin/services', payload));
}

/**
 * Create or reactivate a group of selected issues for one service type.
 * This is the same batch endpoint used by the web service-offering wizard.
 * The backend derives tenant scope and permissions from the authenticated user.
 */
export async function createServicesBatch(payload: ServiceCatalogBatchPayload) {
  return asArray(await api.post('/api/admin/services/batch', payload));
}

export async function toggleService(id: number) {
  return unwrap(await api.patch(`/api/admin/services/${id}/toggle-active`));
}
export async function deleteService(id: number) {
  await api.delete(`/api/admin/services/${id}`);
}
export async function getAgentTracking() {
  return unwrap<any>(await api.get('/api/admin/agent-tracking', { params: { limit: 250 } }));
}
export async function getAgentTrackingJob(id: number) {
  return unwrap<any>(await api.get(`/api/admin/agent-tracking/${id}`));
}
export async function getCommunicationActivity(params: { search?: string; channel?: string; status?: string; limit?: number; offset?: number } = {}) {
  return unwrap<any>(await api.get('/admin/communication-center', { params }));
}
export async function getJobClosure(id: number | string) {
  return unwrap<any>(await api.get(`/jobs/${id}/closure`));
}
export async function getSupportRequests(status?: string) {
  return asArray(await api.get('/api/admin/customer-support', { params: status && status !== 'ALL' ? { status } : undefined }));
}
export async function updateSupportRequest(id: number, payload: Record<string, any>) {
  return unwrap(await api.patch(`/api/admin/customer-support/${id}`, payload));
}

export async function getAdminNotifications(params: { limit?: number; offset?: number; status?: string } = {}) {
  return unwrap<any>(await api.get('/admin/notifications', { params: { limit: 50, offset: 0, ...params } }));
}
export async function markAdminNotificationRead(id: string) {
  return unwrap(await api.patch(`/notifications/${encodeURIComponent(id)}/read`));
}
export async function markAdminNotificationsRead(ids: string[]) {
  return unwrap(await api.patch('/notifications/batch-read', { notification_ids: ids }));
}
export async function dismissAdminNotification(id: string) {
  return unwrap(await api.patch(`/notifications/${encodeURIComponent(id)}/dismiss`));
}
