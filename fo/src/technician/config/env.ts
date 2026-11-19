import { env } from "../../config/env";
export { env };
export const APP_ENV = env.APP_ENV;
export const API_BASE_URL = env.API_BASE_URL;
export const WS_BASE_URL = (process.env.EXPO_PUBLIC_WS_BASE_URL?.trim() || env.API_BASE_URL.replace(/^http/, "ws")).replace(/\/$/, "");
