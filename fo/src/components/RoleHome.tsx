import { useEffect, useState } from "react";
import { router } from "expo-router";
import { Text, View } from "react-native";
import { fullName } from "../auth/roles";
import { useAuthStore } from "../auth/authStore";
import { customerApi, recordsFrom, superAdminApi, technicianApi } from "../api/roleApis";
import { ActionButton, Card, ErrorMessage, Heading, ListRow, Screen, SkeletonRows } from "./ui";

type Role = "customer" | "technician" | "super_admin";
const roleConfig = {
  customer: { title: "Your service hub", load: customerApi.dashboard, links: [["My requests", "/customer/requests"], ["Track a job", "/customer/tracking"], ["Profile", "/customer/profile"]] },
  technician: { title: "Technician workspace", load: technicianApi.dashboard, links: [["My jobs", "/technician/jobs"], ["Profile", "/technician/profile"]] },
  super_admin: { title: "Operations overview", load: superAdminApi.dashboard, links: [["Jobs", "/super-admin/jobs"], ["Users", "/super-admin/users"], ["Organizations", "/super-admin/organizations"], ["Profile", "/super-admin/profile"]] },
} as const;

export function RoleHome({ role }: { role: Role }) {
  const user = useAuthStore((s) => s.user); const logout = useAuthStore((s) => s.logout);
  const [data, setData] = useState<unknown>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(true);
  const config = roleConfig[role];
  useEffect(() => { let active = true; config.load().then((value) => { if (active) setData(value); }).catch((e) => { if (active) setError(e instanceof Error ? e.message : "Could not load dashboard."); }).finally(() => { if (active) setBusy(false); }); return () => { active = false; }; }, [config]);
  return <Screen scroll><Heading title={`Hello, ${user ? fullName(user).split(" ")[0] : "there"}`} subtitle={config.title} />
    {busy ? <SkeletonRows /> : error ? <ErrorMessage message={error} /> : <Card><Text style={{ fontSize: 16, fontWeight: "800", color: "#142B24" }}>Dashboard data is up to date</Text><Text style={{ color: "#65786F" }}>{role === "super_admin" ? "Your operations summary is ready." : role === "customer" ? "Your service information is ready." : "Your work information is ready."}</Text>{role === "super_admin" && Array.isArray(data) ? <Text style={{ color: "#65786F" }}>Jobs, staffing, and planning summaries loaded where available.</Text> : null}</Card>}
    <View style={{ gap: 10 }}>{config.links.map(([label, route]) => <ListRow key={route} title={label} detail={`Open ${label.toLowerCase()}`} onPress={() => router.push(route as never)} />)}</View>
    <ActionButton title="Sign out" secondary onPress={() => void logout()} />
  </Screen>;
}

export function RoleList({ title, subtitle, load, detailBase }: { title: string; subtitle: string; load: () => Promise<unknown>; detailBase?: string }) {
  const [items, setItems] = useState<Record<string, unknown>[] | null>(null); const [error, setError] = useState("");
  useEffect(() => { let active = true; load().then((data) => { if (active) setItems(recordsFrom(data)); }).catch((e) => { if (active) setError(e instanceof Error ? e.message : "Could not load records."); }); return () => { active = false; }; }, [load]);
  return <Screen scroll><Heading title={title} subtitle={subtitle} />{items === null && !error ? <SkeletonRows /> : error ? <ErrorMessage message={error} /> : items?.length ? items.map((item, index) => {
    const id = String(item.id ?? item.job_id ?? index); const name = String(item.title ?? item.job_number ?? item.name ?? item.organization_name ?? item.email ?? `Record ${index + 1}`); const detail = [item.status, item.service_type, item.email].filter(Boolean).map(String).join(" · ");
    return <ListRow key={`${id}-${index}`} title={name} detail={detail || undefined} onPress={detailBase ? () => router.push(`${detailBase}/${encodeURIComponent(id)}` as never) : undefined} />;
  }) : <Card><Text style={{ color: "#65786F" }}>No records are available yet.</Text></Card>}</Screen>;
}
