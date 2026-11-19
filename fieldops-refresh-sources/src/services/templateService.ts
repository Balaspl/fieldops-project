/**
 * templateService.ts
 * API service for Notification Templates.
 * Covers: POST   /templates
 *         GET    /templates
 *         POST   /templates/preview
 */

import api from "./api";

export interface TemplateCreatePayload {
  name: string;
  type: string;           // e.g. "JOB_ASSIGNED"
  channel: string;        // e.g. "push" | "sms" | "in_app"
  locale: string;         // e.g. "en"
  format: string;         // e.g. "text"
  title_template: string;
  body_template: string;
}

export interface TemplatePreviewPayload {
  title_template: string;
  body_template: string;
  mock_context: Record<string, string>;
}

/** Create or update a notification template (auto-versions on conflict) */
export const createTemplate = async (
  payload: TemplateCreatePayload
): Promise<any> => {
  const response = await api.post("/templates", payload);
  return response.data;
};

/** List all active notification templates */
export const listTemplates = async (): Promise<any[]> => {
  try {
    const response = await api.get("/templates");
    return response.data || [];
  } catch (error) {
    console.error("Failed to fetch templates:", error);
    return [];
  }
};

/** Preview a template with mock context variables */
export const previewTemplate = async (
  payload: TemplatePreviewPayload
): Promise<{ rendered_title: string; rendered_body: string }> => {
  const response = await api.post("/templates/preview", payload);
  return response.data;
};
