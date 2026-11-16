import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshControl, Text, View } from 'react-native';
import { Activity, Bot, BrainCircuit, CheckCircle2, ChevronRight, Clock3, MessageCircle, ShieldAlert } from 'lucide-react-native';
import { getAgentTracking, getAgentTrackingJob } from '../api/operations';
import { Card, EmptyState, ErrorBanner, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { dateTime, statusLabel, statusTone, text, timeAgo } from '../utils/format';
import type { AgentJob } from '../types';

const agentIcon = (label: string) => {
  const name = label.toLowerCase();
  if (name.includes('sentiment')) return <BrainCircuit size={16} color={colors.purple} />;
  if (name.includes('communication')) return <MessageCircle size={16} color={colors.blue} />;
  if (name.includes('closure')) return <CheckCircle2 size={16} color={colors.forest} />;
  if (name.includes('dispatcher')) return <Activity size={16} color={colors.amber} />;
  return <Bot size={16} color={colors.forest} />;
};

export default function AgentTrackingScreen() {
  const [jobs, setJobs] = useState<AgentJob[]>([]);
  const [selected, setSelected] = useState<AgentJob | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'ALL' | 'ACTIVE' | 'WAITING'>('ALL');

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const result = await getAgentTracking();
      const rows = Array.isArray(result?.jobs) ? result.jobs : Array.isArray(result) ? result : [];
      setJobs(rows);
      setSelected(current => current ? rows.find((row: AgentJob) => row.job_id === current.job_id) || current : null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Agent workflow tracking is unavailable.');
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  const openJob = async (job: AgentJob) => {
    setSelected(job); setDetail(null); setDetailLoading(true);
    try { setDetail(await getAgentTrackingJob(job.job_id)); }
    catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Unable to load workflow detail.'); }
    finally { setDetailLoading(false); }
  };

  useEffect(() => { void load(); const timer = setInterval(() => { void load(true); }, 30000); return () => clearInterval(timer); }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return jobs.filter(job => {
      const matchFilter = filter === 'ALL' || (filter === 'ACTIVE' ? !['COMPLETED', 'CLOSED', 'CANCELLED', 'CANCELED'].includes(String(job.status).toUpperCase()) : job.current_agent === 'Dispatcher');
      const matchSearch = !term || [job.job_number, job.service_type, job.customer_name, job.location, job.technician_name, job.current_agent, job.status].some(value => String(value || '').toLowerCase().includes(term));
      return matchFilter && matchSearch;
    });
  }, [jobs, search, filter]);

  const timeline = detail?.events || [];
  const stages = detail?.stages || selected?.stages || [];

  return <>
    <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
      <ScreenHeading title="Agent Tracking" subtitle="Read-only view of the backend job lifecycle, agent decisions, notifications, sentiment and workflow events." action={<Pill label="Live refresh" tone="green" />} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Tracked jobs</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 23 }}>{jobs.length}</Text></Card>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Waiting acceptance</Text><Text style={{ color: colors.amber, fontWeight: '900', fontSize: 23 }}>{jobs.filter(job => job.current_agent === 'Dispatcher').length}</Text></Card>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Active</Text><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 23 }}>{jobs.filter(job => !['COMPLETED', 'CLOSED', 'CANCELLED', 'CANCELED'].includes(String(job.status).toUpperCase())).length}</Text></Card>
      </View>
      <SearchField value={search} onChangeText={setSearch} placeholder="Search job, customer, agent or service…" />
      <View style={{ flexDirection: 'row', backgroundColor: '#E7EFEA', padding: 4, borderRadius: 13, gap: 4 }}>
        {(['ALL', 'ACTIVE', 'WAITING'] as const).map(value => <PrimaryButton key={value} title={value === 'ALL' ? 'All jobs' : value === 'ACTIVE' ? 'Active' : 'Waiting'} compact style={{ flex: 1 }} variant={filter === value ? 'primary' : 'ghost'} onPress={() => setFilter(value)} />)}
      </View>
      {error ? <ErrorBanner message={error} /> : null}
      <SectionTitle title="Workflow monitor" subtitle="Select a job to inspect its stages and event history" />
      {loading ? <Text style={{ color: colors.muted, textAlign: 'center', padding: 24 }}>Loading agent workflows…</Text> : visible.length === 0 ? <EmptyState title="No matching workflows" detail="No jobs are currently visible for this tenant or selected filter." onRetry={() => load(true)} /> : visible.map(job => <Card key={job.job_id} onPress={() => void openJob(job)} style={{ gap: 10, borderColor: selected?.job_id === job.job_id ? colors.forest : colors.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}><Text style={{ color: colors.forest, fontSize: 12, fontWeight: '900' }}>JOB #{text(job.job_number, String(job.job_id))}</Text><Pill label={statusLabel(job.status)} tone={statusTone(job.status)} /></View>
        <Text style={{ color: colors.ink, fontWeight: '900', fontSize: 14 }}>{text(job.service_type, 'Service request')}</Text>
        <Text style={{ color: colors.muted, fontSize: 11 }}>{text(job.customer_name)} · {text(job.location)}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}><Pill label={text(job.current_agent, 'Workflow')} tone="purple" /><Pill label={`${job.stages?.filter(s => s.state === 'complete').length || 0}/${job.stages?.length || 7} stages`} tone="neutral" /></View>
        <Text style={{ color: colors.text, fontSize: 11, lineHeight: 17 }}>{text(job.current_detail)}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 10 }}>Updated {timeAgo(job.updated_at)}</Text><View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}><Text style={{ color: colors.forest, fontSize: 11, fontWeight: '800' }}>Inspect workflow</Text><ChevronRight size={14} color={colors.forest} /></View></View>
      </Card>)}
      <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10, lineHeight: 16 }}>This screen does not run agents from the phone or fabricate agent states. It reads the server-side workflow summary, sentiment analysis, audit trail, chat and delivery events from the existing Agent Tracking API.</Text></Card>
    </ScreenScroll>

    {selected ? <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(7,25,16,.52)', justifyContent: 'flex-end' }}>
      <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '92%' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}><View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.ink, fontSize: 19, fontWeight: '900' }}>Job #{selected.job_number || selected.job_id}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{text(selected.customer_name)} · {text(selected.service_type)}</Text></View><PrimaryButton title="Close" compact variant="secondary" onPress={() => { setSelected(null); setDetail(null); }} /></View>
        {detailLoading ? <Text style={{ padding: 22, textAlign: 'center', color: colors.muted }}>Loading agent timeline…</Text> : <View style={{ maxHeight: '88%' }}>
          <ScreenScroll contentContainerStyle={{ padding: 0, paddingBottom: 30 }}>
            <Card style={{ gap: 7 }}><Text style={{ fontSize: 10, fontWeight: '900', color: colors.muted }}>CURRENT OWNER</Text><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 16 }}>{text(detail?.current_agent || selected.current_agent)}</Text><Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }}>{text(detail?.current_detail || selected.current_detail)}</Text></Card>
            <SectionTitle title="Agent stages" subtitle="Authoritative lifecycle as reported by the backend" />
            {stages.map((stage: any, index: number) => <View key={stage.key || index} style={{ flexDirection: 'row', gap: 11 }}>
              <View style={{ width: 28, alignItems: 'center' }}><View style={{ width: 28, height: 28, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: stage.state === 'complete' ? '#DDF4E6' : stage.state === 'active' ? '#E5EDFF' : '#EDF1EE' }}>{stage.state === 'complete' ? <CheckCircle2 size={16} color={colors.forest} /> : agentIcon(stage.label)}</View>{index < stages.length - 1 ? <View style={{ height: 36, width: 1, backgroundColor: colors.border }} /> : null}</View>
              <View style={{ flex: 1, gap: 4, paddingBottom: 13 }}><View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 6 }}><Text style={{ color: colors.ink, fontSize: 12, fontWeight: '900', flex: 1 }}>{stage.label}</Text><Pill label={statusLabel(stage.state)} tone={stage.state === 'complete' ? 'green' : stage.state === 'active' ? 'blue' : 'neutral'} /></View><Text style={{ color: colors.muted, fontSize: 11, lineHeight: 16 }}>{stage.detail}</Text>{stage.timestamp ? <Text style={{ color: colors.muted, fontSize: 9 }}>{dateTime(stage.timestamp)}</Text> : null}</View>
            </View>)}
            <SectionTitle title="Event history" subtitle={`${timeline.length} recorded events`} />
            {timeline.length === 0 ? <EmptyState title="No detailed events" detail="The workflow summary is available, but no detailed events have been recorded yet." /> : [...timeline].reverse().map((event: any, index: number) => <Card key={`${event.timestamp || 'event'}-${index}`} style={{ gap: 6, padding: 13 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>{agentIcon(event.agent)}<Text style={{ color: colors.ink, fontWeight: '900', fontSize: 12, flex: 1 }}>{text(event.title)}</Text><Pill label={text(event.kind)} tone={statusTone(event.delivery_status || event.kind)} /></View>
              <Text style={{ color: colors.text, fontSize: 11, lineHeight: 17 }}>{text(event.detail)}</Text>
              <Text style={{ color: colors.muted, fontSize: 9 }}>{text(event.agent)} · {dateTime(event.timestamp)}</Text>
              {event.urgency || event.severity || event.requires_human ? <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}><Pill label={`Urgency ${text(event.urgency)}`} tone="amber" /><Pill label={`Severity ${text(event.severity)}`} tone="red" />{event.requires_human ? <Pill label="Human review required" tone="red" /> : null}</View> : null}
              {event.error ? <Text style={{ color: colors.red, fontSize: 10 }}>Delivery error: {event.error}</Text> : null}
            </Card>)}
          </ScreenScroll>
        </View>}
      </View>
    </View> : null}
  </>;
}
