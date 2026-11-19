
import { Redirect, Slot } from "expo-router";
import type { ReactNode } from "react";

import { useAuthStore } from "../auth/authStore";
import { normalizeRole } from "../auth/roles";
import { LoadingState, Screen } from "./ui";

type GuardedRole = "customer" | "technician" | "super_admin";

interface GuardedRoleLayoutProps {
  role: GuardedRole;
  children?: ReactNode;
}

export function GuardedRoleLayout({
  role,
  children,
}: GuardedRoleLayoutProps) {
  const { user, initialized } = useAuthStore();

  if (!initialized) {
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  }

  if (!user) {
    return <Redirect href="/login" />;
  }

  const userRole = normalizeRole(user.role);

  const hasAccess =
    role === "super_admin"
      ? userRole === "super_admin" || userRole === "dispatcher"
      : userRole === role;

  if (!hasAccess) {
    return <Redirect href="/" />;
  }

  return children ? <>{children}</> : <Slot />;
}
