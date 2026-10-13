
const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
const configuredWsBaseUrl = process.env.EXPO_PUBLIC_WS_BASE_URL;

if (!apiBaseUrl || !apiBaseUrl.trim()) {
  throw new Error(
    "EXPO_PUBLIC_API_BASE_URL is missing. Check the mobile .env file."
  );
}

function validateUrl(value: string, name: string): string {
  try {
    const parsed = new URL(value);

    if (
      parsed.protocol !== "http:" &&
      parsed.protocol !== "https:" &&
      parsed.protocol !== "ws:" &&
      parsed.protocol !== "wss:"
    ) {
      throw new Error("Unsupported URL protocol.");
    }

    return value.replace(/\/+$/, "");
  } catch {
    throw new Error(`${name} is not a valid URL.`);
  }
}

const validatedApiUrl = validateUrl(
  apiBaseUrl,
  "EXPO_PUBLIC_API_BASE_URL"
);

const parsedApiUrl = new URL(validatedApiUrl);

const defaultWsUrl = validatedApiUrl.replace(
  /^https?:/,
  parsedApiUrl.protocol === "https:" ? "wss:" : "ws:"
);

export const env = {
  API_BASE_URL: validatedApiUrl,
  WS_BASE_URL: configuredWsBaseUrl
    ? validateUrl(configuredWsBaseUrl, "EXPO_PUBLIC_WS_BASE_URL")
    : defaultWsUrl
};
