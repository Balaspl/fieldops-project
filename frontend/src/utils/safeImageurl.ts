export const getSafeImageUrl = (
  value: string | null | undefined,
): string | null => {
  if (!value) return null;

  const trimmed = value.trim();

  // Allow application-relative image paths.
  if (trimmed.startsWith("/")) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed, window.location.origin);

    // Only HTTP(S) URLs are allowed.
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      return null;
    }

    // Don't allow credentials inside image URLs.
    if (url.username || url.password) {
      return null;
    }

    return url.href;
  } catch {
    return null;
  }
};