
import { api } from './client';

// ==================================================
// COMMON HELPERS
// ==================================================

export const unwrap = <T = any>(value: any): T =>
  (value?.data !== undefined ? value.data : value) as T;

export const asArray = <T = any>(value: any): T[] => {
  const raw = unwrap<any>(value);

  if (Array.isArray(raw)) return raw as T[];

  for (const key of [
    'items',
    'results',
    'jobs',
    'technicians',
    'services',
    'requests',
    'data',
  ]) {
    if (Array.isArray(raw?.[key])) {
      return raw[key] as T[];
    }
  }

  return [];
};

// ==================================================
// STAFF PROVISIONING
// ==================================================

export type OrganizationUserRole = 'technician' | 'dispatcher';

export interface ProvisionOrganizationUserRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone_number: string;
  role: OrganizationUserRole;
}

/**
 * Creates a Technician or Dispatcher user account.
 *
 * Backend:
 * POST /organizations/{organizationId}/admin
 */
export async function provisionOrganizationUser(
  organizationId: string,
  payload: ProvisionOrganizationUserRequest
) {
  if (!organizationId || organizationId === '__platform__') {
    throw new Error('A valid organization ID is required.');
  }

  return unwrap(
    await api.post(
      `/organizations/${encodeURIComponent(organizationId)}/admin`,
      {
        first_name: payload.first_name.trim(),
        last_name: payload.last_name.trim(),
        email: payload.email.trim().toLowerCase(),
        password: payload.password,
        phone_number: payload.phone_number.trim(),
        role: payload.role,
      }
    )
  );
}

// ==================================================
// DASHBOARD
// ==================================================

export async function getDashboardData(
  timeRange = 'week',
  dateRange?: {
    start_date: string;
    end_date: string;
  } | null
) {
  const params: Record<string, string> = {
    time_range: timeRange,
  };

  if (dateRange) {
    const [sy, sm, sd] = dateRange.start_date.split('-').map(Number);
    const [ey, em, ed] = dateRange.end_date.split('-').map(Number);

    params.start_datetime = new Date(
      sy,
      sm - 1,
      sd
    ).toISOString();

    params.end_datetime = new Date(
      ey,
      em - 1,
      ed + 1
    ).toISOString();
  }

  const [stats, kpi, jobs, techs] = await Promise.allSettled([
    api.get('/jobs/stats', { params }),
    api.get('/planning/kpi'),
    api.get('/jobs', {
      params: { page: 1, limit: 8 },
    }),
    api.get('/technicians', {
      params: { page: 1, limit: 100 },
    }),
  ]);

  return {
    stats:
      stats.status === 'fulfilled'
        ? unwrap<any>(stats.value)
        : {},

    kpi:
      kpi.status === 'fulfilled'
        ? unwrap<any>(kpi.value)
        : {},

    jobs:
      jobs.status === 'fulfilled'
        ? asArray(jobs.value)
        : [],

    technicians:
      techs.status === 'fulfilled'
        ? asArray(techs.value)
        : [],

    errors: [stats, kpi, jobs, techs].filter(
      x => x.status === 'rejected'
    ).length,
  };
}

// ==================================================
// TECHNICIANS
// ==================================================

export async function getTechnicians(
  params: Record<string, any> = {}
) {
  return asArray(
    await api.get('/technicians', { params })
  );
}

/**
 * Paginated technician list.
 * Preserves X-Total-Count from the backend response.
 */
export async function getTechniciansPage(
  params: Record<string, any> = {}
) {
  const response = await api.get('/technicians', { params });
  const items = asArray(response);

  const totalHeader =
    response.headers?.['x-total-count'] ??
    response.headers?.['X-Total-Count'];

  const parsedTotal = Number(totalHeader);

  return {
    items,
    total:
      totalHeader !== undefined && Number.isFinite(parsedTotal)
        ? parsedTotal
        : items.length,
  };
}

/**
 * Fetch one technician.
 */
export async function getTechnicianById(
  technicianId: number | string
) {
  const id = Number(technicianId);

  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new Error('A valid technician ID is required.');
  }

  return unwrap<any>(
    await api.get(`/technicians/${id}`)
  );
}

/**
 * Fetch jobs assigned to one technician.
 */
export async function getTechnicianAssignedJobs(
  technicianId: number | string
) {
  const id = Number(technicianId);

  if (!Number.isSafeInteger(id) || id <= 0) {
    throw new Error('A valid technician ID is required.');
  }

  return getJobs({
    technician_id: id,
  });
}

/**
 * Update technician availability.
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
    | 'DEACTIVATED'
) {
  const id = String(technicianId).trim();

  if (!id) {
    throw new Error('A valid technician ID is required.');
  }

  return unwrap(
    await api.put(
      `/technicians/${encodeURIComponent(id)}/availability`,
      { technician_status }
    )
  );
}

export async function getAvailableTechnicians() {
  return asArray(
    await api.get('/technicians/available')
  );
}

/**
 * Legacy update function.
 * Retained for existing screens that use it.
 */
export async function updateTechnician(
  id: number | string,
  payload: Record<string, any>
) {
  return unwrap(
    await api.put(`/technicians/${id}`, payload)
  );
}

/**
 * Legacy delete function.
 * Retained for existing flows; the new Team screen
 * should use deactivate/reactivate instead.
 */
export async function deleteTechnician(
  id: number | string
) {
  return unwrap(
    await api.delete(`/technicians/${id}`)
  );
}

/**
 * Legacy technician provisioning endpoint.
 * Retained for existing flows that still use it.
 */
export async function provisionTechnician(payload: {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone_number?: string;
  technician_skill?: string;
  technician_location?: string;
}) {
  return unwrap(
    await api.post(
      '/dispatchers/provision-technician',
      payload
    )
  );
}

// ==================================================
// DISPATCHERS
// ==================================================

export async function getDispatchers() {
  return asArray(
    await api.get('/dispatchers')
  );
}

// ==================================================
// JOBS
// ==================================================

export async function getJobs(
  params: Record<string, any> = {}
) {
  return asArray(
    await api.get('/jobs', { params })
  );
}

export async function getPendingJobs(
  params: Record<string, any> = {}
) {
  return asArray(
    await api.get('/jobs/pending', { params })
  );
}

export async function getJobPlan(
  jobId: number | string,
  adminOverride = false
) {
  return unwrap<any>(
    await api.post(
      `/jobs/${jobId}/plan`,
      null,
      {
        params: {
          admin_override: adminOverride,
        },
      }
    )
  );
}

export async function assignJob(
  jobId: number | string,
  technicianId: number | string
) {
  return unwrap(
    await api.post('/assign-job', {
      job_id: jobId,
      technician_id: technicianId,
    })
  );
}

export async function assignJobsBulk(
  jobIds: Array<number | string>,
  technicianId: number | string
) {
  return unwrap(
    await api.post('/assign-jobs-bulk', {
      job_ids: jobIds,
      technician_id: technicianId,
    })
  );
}

export async function cancelJobsBulk(
  jobIds: Array<number | string>,
  reason: string
) {
  return unwrap(
    await api.post('/jobs/bulk-cancel', {
      job_ids: jobIds,
      reason,
    })
  );
}

export async function overrideAssignment(
  jobId: number | string,
  technicianId: number | string,
  justification: string
) {
  return unwrap(
    await api.post(
      `/technicians/assignments/${jobId}/override`,
      {
        technician_id: String(technicianId),
        justification,
      }
    )
  );
}

// ==================================================
// ESCALATIONS
// ==================================================

export async function forceAssignEscalation(
  jobId: number | string,
  technicianId: number | string,
  reason: string
) {
  return unwrap(
    await api.post(
      `/escalations/${jobId}/force-assign`,
      {
        tech_id: String(technicianId),
        reason,
      }
    )
  );
}

export async function extendEscalatedSla(
  jobId: number | string,
  minutes: number
) {
  return unwrap(
    await api.post(
      `/escalations/${jobId}/extend-sla`,
      { minutes }
    )
  );
}

export async function cancelEscalatedJob(
  jobId: number | string,
  reason: string
) {
  return unwrap(
    await api.post(
      `/escalations/${jobId}/cancel`,
      { reason }
    )
  );
}

// ==================================================
// SERVICES
// ==================================================

export interface ServiceCatalogBatchPayload {
  service_type: string;
  groups: Array<{
    category: string;
    issues: string[];
  }>;
}

export async function getServices(search?: string) {
  return asArray(
    await api.get('/api/admin/services', {
      params: search
        ? { search }
        : undefined,
    })
  );
}

export async function getTaxonomy() {
  return unwrap<any>(
    await api.get(
      '/api/admin/services/taxonomy-suggestions'
    )
  );
}

export async function createService(
  payload: Record<string, any>
) {
  return unwrap(
    await api.post(
      '/api/admin/services',
      payload
    )
  );
}

export async function createServicesBatch(
  payload: ServiceCatalogBatchPayload
) {
  return asArray(
    await api.post(
      '/api/admin/services/batch',
      payload
    )
  );
}

export async function toggleService(id: number) {
  return unwrap(
    await api.patch(
      `/api/admin/services/${id}/toggle-active`
    )
  );
}

export async function deleteService(id: number) {
  await api.delete(
    `/api/admin/services/${id}`
  );
}

// ==================================================
// AGENT TRACKING
// ==================================================

export async function getAgentTracking() {
  return unwrap<any>(
    await api.get(
      '/api/admin/agent-tracking',
      {
        params: { limit: 250 },
      }
    )
  );
}

export async function getAgentTrackingJob(id: number) {
  return unwrap<any>(
    await api.get(
      `/api/admin/agent-tracking/${id}`
    )
  );
}

// ==================================================
// COMMUNICATION ACTIVITY
// ==================================================

export async function getCommunicationActivity(
  params: {
    search?: string;
    channel?: string;
    status?: string;
    limit?: number;
    offset?: number;
  } = {}
) {
  return unwrap<any>(
    await api.get(
      '/admin/communication-center',
      { params }
    )
  );
}

// ==================================================
// JOB CLOSURE
// ==================================================

export async function getJobClosure(
  id: number | string
) {
  return unwrap<any>(
    await api.get(
      `/jobs/${id}/closure`
    )
  );
}

// ==================================================
// CUSTOMER SUPPORT
// ==================================================

export async function getSupportRequests(
  status?: string
) {
  return asArray(
    await api.get(
      '/api/admin/customer-support',
      {
        params:
          status && status !== 'ALL'
            ? { status }
            : undefined,
      }
    )
  );
}

export async function updateSupportRequest(
  id: number,
  payload: Record<string, any>
) {
  return unwrap(
    await api.patch(
      `/api/admin/customer-support/${id}`,
      payload
    )
  );
}

// ==================================================
// ADMIN NOTIFICATIONS
// ==================================================

export async function getAdminNotifications(
  params: {
    limit?: number;
    offset?: number;
    status?: string;
  } = {}
) {
  return unwrap<any>(
    await api.get(
      '/admin/notifications',
      {
        params: {
          limit: 50,
          offset: 0,
          ...params,
        },
      }
    )
  );
}

export async function markAdminNotificationRead(
  id: string
) {
  return unwrap(
    await api.patch(
      `/notifications/${encodeURIComponent(id)}/read`
    )
  );
}

export async function markAdminNotificationsRead(
  ids: string[]
) {
  return unwrap(
    await api.patch(
      '/notifications/batch-read',
      {
        notification_ids: ids,
      }
    )
  );
}

export async function dismissAdminNotification(
  id: string
) {
  return unwrap(
    await api.patch(
      `/notifications/${encodeURIComponent(id)}/dismiss`
    )
  );
}
