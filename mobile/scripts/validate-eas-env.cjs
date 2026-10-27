const { isIP } = require("node:net");

function isPrivateOrLocalHost(hostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");

  if (
    host === "localhost" ||
    host === "localhost.localdomain" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host === "0.0.0.0" ||
    host === "::" ||
    host === "::1" ||
    host === "10.0.2.2"
  ) {
    return true;
  }

  if (isIP(host) === 4) {
    const [a, b] = host.split(".").map(Number);

    return (
      a === 0 ||
      a === 10 ||
      a === 127 ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) ||
      (a === 100 && b >= 64 && b <= 127)
    );
  }

  if (isIP(host) === 6) {
    return host.startsWith("fc") ||
      host.startsWith("fd") ||
      /^fe[89ab]/.test(host);
  }

  return false;
}

function parseUrl(value, name, protocols) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} is required for an EAS build.`);
  }

  if (value !== value.trim()) {
    throw new Error(`${name} must not contain surrounding whitespace.`);
  }

  let parsed;

  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid absolute URL.`);
  }

  if (!protocols.includes(parsed.protocol)) {
    throw new Error(`${name} uses an unsupported URL protocol.`);
  }

  if (!parsed.hostname || parsed.username || parsed.password) {
    throw new Error(`${name} must have a hostname and must not contain credentials.`);
  }

  return parsed;
}

function validateBuildEnvironment(environment = process.env) {
  const profile = environment.EAS_BUILD_PROFILE || "local";
  const api = parseUrl(
    environment.EXPO_PUBLIC_API_BASE_URL,
    "EXPO_PUBLIC_API_BASE_URL",
    ["http:", "https:"],
  );
  const websocket = parseUrl(
    environment.EXPO_PUBLIC_WS_BASE_URL,
    "EXPO_PUBLIC_WS_BASE_URL",
    ["ws:", "wss:"],
  );

  if (profile === "production") {
    if (api.protocol !== "https:" || websocket.protocol !== "wss:") {
      throw new Error("Production requires HTTPS API and WSS WebSocket URLs.");
    }

    if (
      isPrivateOrLocalHost(api.hostname) ||
      isPrivateOrLocalHost(websocket.hostname)
    ) {
      throw new Error("Production URLs must not point to localhost or private networks.");
    }
  }

  return { profile };
}

if (require.main === module) {
  try {
    const result = validateBuildEnvironment();
    console.log(`Build environment validation passed (${result.profile}).`);
  } catch (error) {
    console.error(`Build environment validation failed: ${error.message}`);
    process.exitCode = 1;
  }
}

module.exports = { validateBuildEnvironment };
