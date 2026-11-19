
export type AppRole =
  | "customer"
  | "technician"
  | "super_admin"
  | "dispatcher";

export interface AuthUser {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role: string;
  tenant_id?: string | null;
  organization_name?: string | null;
  [key: string]: unknown;
}

export function normalizeRole(value: unknown): AppRole | null {
  const role = String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[ -]+/g, "_");

  if (role === "customer") return "customer";
  if (role === "technician") return "technician";

  if (["super_admin", "superadmin"].includes(role)) {
    return "super_admin";
  }

  if (role === "dispatcher") return "dispatcher";

  return null;
}

export function homeRoute(
  role: unknown
):
  | "/customer"
  | "/technician/(app)/dashboard"
  | "/super-admin/dashboard"
  | null {
  switch (normalizeRole(role)) {
    case "customer":
      return "/customer";

    case "technician":
      return "/technician/(app)/dashboard";

    case "super_admin":
    case "dispatcher":
      return "/super-admin/dashboard";

    default:
      return null;
  }
}

export function fullName(user: AuthUser): string {
  const name = [user.first_name, user.last_name]
    .filter(Boolean)
    .join(" ")
    .trim();

  return name || user.email;
}
