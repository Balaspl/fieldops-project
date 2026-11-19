import axios from "axios";
export { apiClient } from "../../api/client";

export function isNetworkUnavailableError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  if (error.response || error.code === "ERR_CANCELED") return false;
  return Boolean(error.request) || ["ERR_NETWORK", "ECONNABORTED", "ETIMEDOUT", "ECONNRESET", "EHOSTUNREACH", "ENETUNREACH", "ENOTFOUND", "EAI_AGAIN"].includes(String(error.code ?? "").toUpperCase());
}
