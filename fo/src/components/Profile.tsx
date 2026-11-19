import { Text } from "react-native";
import { fullName } from "../auth/roles";
import { useAuthStore } from "../auth/authStore";
import { ActionButton, Card, Heading, Screen } from "./ui";

export function Profile() {
  const user = useAuthStore((s) => s.user); const logout = useAuthStore((s) => s.logout);
  return <Screen scroll><Heading title="Profile" subtitle="Your shared FieldOps account" /><Card><Text style={{ fontSize: 19, fontWeight: "800", color: "#142B24" }}>{user ? fullName(user) : ""}</Text><Text style={{ color: "#65786F" }}>{user?.email}</Text><Text style={{ color: "#65786F" }}>Role: {user?.role}</Text></Card><ActionButton title="Sign out" onPress={() => void logout()} /></Screen>;
}
