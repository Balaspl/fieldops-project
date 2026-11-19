/**
 * Resolve the web catalogue's existing /services/* image paths for React Native.
 *
 * The assets stay in the web frontend's public/services directory. They are not
 * copied into the mobile bundle. Configure EXPO_PUBLIC_WEB_ASSET_BASE_URL with
 * the web frontend's origin (not the backend API origin).
 *
 * Android emulator example: http://10.0.2.2:5173
 * Physical device example:  http://<your-development-computer-LAN-IP>:5173
 * Production example:       https://<your-web-frontend-host>
 */

const WEB_ASSET_BASE_URL = (process.env.EXPO_PUBLIC_WEB_ASSET_BASE_URL || '').trim().replace(/\/+$/, '');

function encodePathSegment(segment: string): string {
  // Keep already-encoded paths stable while safely encoding spaces, commas,
  // parentheses and other characters used in the web catalogue filenames.
  try {
    return encodeURIComponent(decodeURIComponent(segment));
  } catch {
    return encodeURIComponent(segment);
  }
}

function normalizeServiceAssetPath(assetPath: string): string | null {
  const trimmed = assetPath.trim().replace(/\\/g, '/');
  if (!trimmed) return null;

  // The catalogue uses paths under /services. Do not accept arbitrary relative
  // paths that could accidentally resolve to the API or another app route.
  const withoutLeadingSlash = trimmed.replace(/^\/+/, '');
  if (!withoutLeadingSlash.startsWith('services/')) return null;

  const encodedSegments = withoutLeadingSlash
    .split('/')
    .filter(Boolean)
    .map(encodePathSegment);

  return `/${encodedSegments.join('/')}`;
}

/**
 * Return an absolute URL for an existing web catalogue image.
 *
 * Returns undefined when the path is empty/unsupported or when the web asset
 * origin has not been configured. This avoids silently requesting images from
 * the backend API host, which is a different origin in the mobile setup.
 */
export function getServiceAssetUrl(assetPath: string | null | undefined): string | undefined {
  if (typeof assetPath !== 'string' || !assetPath.trim()) return undefined;

  const trimmed = assetPath.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;

  if (!WEB_ASSET_BASE_URL || !/^https?:\/\//i.test(WEB_ASSET_BASE_URL)) {
    return undefined;
  }

  const normalizedPath = normalizeServiceAssetPath(trimmed);
  if (!normalizedPath) return undefined;

  return `${WEB_ASSET_BASE_URL}${normalizedPath}`;
}

/** Exposed for a simple configuration check in the Services screen. */
export function isServiceAssetBaseUrlConfigured(): boolean {
  return /^https?:\/\//i.test(WEB_ASSET_BASE_URL);
}
