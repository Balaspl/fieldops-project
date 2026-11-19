import { useEffect, useState } from "react";
import { Text } from "react-native";
import { technicianApi, recordsFrom } from "../../src/api/roleApis";
import { Heading, ListRow, Screen, SkeletonRows } from "../../src/components/ui";
export default function Tracking() { const [jobs, setJobs] = useState<Record<string, unknown>[] | null>(null); useEffect(() => { technicianApi.jobs().then((v) => setJobs(recordsFrom(v))).catch(() => setJobs([])); }, []); return <Screen scroll><Heading title="My active jobs" subtitle="Assigned jobs that may require location updates" />{jobs === null ? <SkeletonRows /> : jobs.filter((j) => !["completed", "closed", "cancelled"].includes(String(j.status ?? "").toLowerCase())).map((job, i) => <ListRow key={String(job.id ?? i)} title={String(job.title ?? job.job_number ?? `Job ${i + 1}`)} detail={String(job.status ?? "Active")} />)}{jobs?.length === 0 ? <Text>No assigned jobs are active.</Text> : null}</Screen>; }
