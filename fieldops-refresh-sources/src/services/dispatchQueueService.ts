/**
 * dispatchQueueService.ts
 * API service for fetching dispatch queue data.
 */

import api from "./api";
import type { DispatchQueueResponse } from "../types/dispatchQueue";

export interface DispatchQueueParams {
  status?: string;
  priority?: string;
  zone?: string;
  cursor?: string;
  limit?: number;
}

/**
 * Fetch dispatch queue jobs with optional filters and cursor pagination.
 */
export const getDispatchQueue = async (
  params: DispatchQueueParams = {}
): Promise<DispatchQueueResponse> => {
  try {
    const response = await api.get<DispatchQueueResponse>("/dispatch/queue", {
      params: {
        ...(params.status && { status: params.status }),
        ...(params.priority && { priority: params.priority }),
        ...(params.zone && { zone: params.zone }),
        ...(params.cursor && { cursor: params.cursor }),
        ...(params.limit && { limit: params.limit }),
      },
    });
    return response.data;
  } catch (error) {
    console.error("Failed to fetch dispatch queue:", error);
    throw error;
  }
};
