
import { Stack } from "expo-router";

import { GuardedRoleLayout } from "../../src/components/RoleLayout";

export default function Layout() {
  return (
    <GuardedRoleLayout role="customer">
      <Stack
        screenOptions={{
          headerShown: false,
          animation: "slide_from_right",
        }}
      />
    </GuardedRoleLayout>
  );
}
