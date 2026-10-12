export const getSafePhoneUrl = (
  value: string | null | undefined,
): string | null => {
  if (!value) return null;

  const phone = value.trim();

  // Keep digits, spaces, +, -, parentheses and dots.
  // Reject everything else.
  if (!/^[0-9+().\-\s]{3,30}$/.test(phone)) {
    return null;
  }

  return `tel:${phone}`;
};