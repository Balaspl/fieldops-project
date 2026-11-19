import { apiClient } from "../../api/client";
import { env } from "../../config/env";
import { getAccessTokenSync } from "../../auth/session";
export const api = apiClient;
export const getAccessToken = getAccessTokenSync;
export const getApiBaseUrl = () => env.API_BASE_URL;
