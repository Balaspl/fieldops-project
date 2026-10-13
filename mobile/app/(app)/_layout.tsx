
import { Redirect, Tabs } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { useAuthStore } from "../../src/auth/authStore";
import { LoadingState } from "../../src/components/ScreenState";

export default function AppLayout() {
  const isLoading = useAuthStore((state) => state.isLoading);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);

  if (isLoading) {
    return <LoadingState label="Checking your session..." />;
  }

  if (!isAuthenticated || !user) {
    return <Redirect href="/(auth)/login" />;
  }

  if (user.role.toLowerCase() !== "technician") {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Access restricted</Text>
        <Text style={styles.message}>
          This mobile workspace is for technician accounts.
          Contact your FieldOps administrator if you need access.
        </Text>
      </View>
    );
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: "#1D4ED8",
        tabBarInactiveTintColor: "#64748B",
        tabBarLabelStyle: styles.tabLabel,
        tabBarStyle: styles.tabBar
      }}
    >
      <Tabs.Screen
        name="dashboard"
        options={{ title: "Home", tabBarLabel: "Home" }}
      />

      <Tabs.Screen
        name="jobs"
        options={{ title: "My Jobs", tabBarLabel: "My Jobs" }}
      />

      <Tabs.Screen
        name="history"
        options={{ title: "Job History", tabBarLabel: "History" }}
      />

      <Tabs.Screen
        name="notifications"
        options={{ title: "Notifications", tabBarLabel: "Alerts" }}
      />

      <Tabs.Screen
        name="profile"
        options={{ title: "My Profile", tabBarLabel: "Profile" }}
      />

      <Tabs.Screen
        name="jobs/[jobId]"
        options={{
          href: null,
          title: "Job Details"
        }}
      />

      <Tabs.Screen
        name="jobs/[jobId]/expenses"
        options={{
          href: null,
          title: "Submit Expense"
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F8FAFC",
    padding: 24
  },
  title: {
    color: "#0F172A",
    fontSize: 23,
    fontWeight: "700",
    marginBottom: 12
  },
  message: {
    color: "#64748B",
    fontSize: 15,
    lineHeight: 23,
    textAlign: "center"
  },
  tabBar: {
    backgroundColor: "#FFFFFF",
    borderTopColor: "#E2E8F0",
    height: 62,
    paddingTop: 6,
    paddingBottom: 5
  },
  tabLabel: {
    fontSize: 12,
    fontWeight: "600"
  }
});
