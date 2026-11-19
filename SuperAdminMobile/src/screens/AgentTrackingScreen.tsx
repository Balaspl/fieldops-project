import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Modal, RefreshControl, ScrollView, Text, View } from 'react-native';
import { Activity, AlertCircle, Bell, Bot, BrainCircuit, CalendarDays, Check, CheckCircle2, ChevronRight, CircleDashed, Clock3, FileText, LockKeyhole, Mail, MapPin, MessageCircle, Send, Smile, Smartphone } from 'lucide-react-native';
import { getAgentTracking, getAgentTrackingJob, getJobClosure } from '../api/operations';
import { Card, EmptyState, ErrorBanner, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { dateTime, statusLabel, statusTone, text, timeAgo } from '../utils/format';
import type { AgentJob } from '../types';

type Filter = 'ALL' | 'ACTIVE' | 'COMPLETE' | 'FAILED';
const terminal = (job: AgentJob) => ['COMPLETED', 'CLOSED', 'CANCELLED', 'CANCELED'].includes(String(job.status).toUpperCase());
const failed = (job: AgentJob) => ['FAILED', 'CANCELLED', 'CANCELED'].includes(String(job.status).toUpperCase());
const completed = (job: AgentJob) => ['COMPLETED', 'CLOSED'].includes(String(job.status).trim().toUpperCase());
const progressFor = (job: AgentJob) => {
  if (terminal(job) && !failed(job)) return 100;
  const stages = job.stages || [];
  if (!stages.length) return 0;
  const done = stages.filter(stage => stage.state === 'complete').length;
  const active = stages.some(stage => stage.state === 'active') ? 1 : 0;
  return Math.min(99, Math.round(((done + active * 0.45) / stages.length) * 100));
};

// The same display normalization used by the web Agent Tracking view. Workflow decisions remain server-owned.
function withClosureStage<T extends AgentJob>(job: T): T {
  const stages = (job.stages || []).filter(stage => stage.key !== 'closure');
  if (completed(job)) stages.push({ key: 'closure', label: 'Close Job', state: job.status.trim().toUpperCase() === 'CLOSED' ? 'complete' : 'active', detail: job.status.trim().toUpperCase() === 'CLOSED' ? 'Closure Agent recorded the final job closure.' : 'Closure requirements are ready for review.', timestamp: job.updated_at });
  return { ...job, stages };
}

const incompleteSignals = ['not finished', 'unfinished', 'not completed', 'not complete', 'incomplete', 'not done', 'not resolved', 'issue remains unresolved', 'work remains', 'needs further work', 'need more work', 'waiting for spare parts', 'waiting for parts', 'temporary repair', 'additional visit required'];
function closureEvent(job: AgentJob, closure: any, existing: any) {
  const report = closure?.work_report ?? {};
  const closureAgent = report.closure_agent ?? existing?.output?.closure_agent ?? null;
  const decision = closureAgent && typeof closureAgent === 'object' ? closureAgent : null;
  const followUp = String(decision?.follow_up_reason || '').trim();
  const workSummary = closure?.work_summary || report.summary || decision?.work_summary || existing?.input?.work_summary;
  const workIncomplete = existing?.output?.work_incomplete === true || incompleteSignals.some(signal => `${workSummary || ''} ${followUp}`.toLowerCase().includes(signal));
  const checklist = closure?.checklist?.items ?? existing?.input?.completion_checklist ?? [];
  const required = Array.isArray(checklist) ? checklist.filter((item: any) => item?.required === true) : [];
  if (workIncomplete && !required.some((item: any) => item.id === 'closure-follow-up')) required.push({ id: 'closure-follow-up', label: followUp || 'Complete the unfinished work.', required: true, status: 'REQUIRED' });
  const requirementsMet = required.every((item: any) => String(item.status || '').toUpperCase() === 'COMPLETED') && !workIncomplete;
  const detail = workIncomplete ? (followUp ? `Work is unfinished. Required follow-up: ${followUp}` : 'Work is unfinished and must be completed before closure.') : required.length ? (requirementsMet ? 'All required completion checklist items were completed.' : 'Some required completion checklist items need attention.') : 'No additional required checklist items were recorded for this job.';
  return { ...(existing || {}), timestamp: closure?.completed_at || existing?.timestamp || job.updated_at, agent: 'Closure Agent', title: 'Closure requirements check', detail, kind: 'closure', delivery_status: requirementsMet ? 'passed' : 'review', input: { ...(existing?.input || {}), completion_checklist: checklist, work_summary: workSummary || null, after_image_count: closure?.after_images?.length ?? existing?.input?.after_image_count ?? 0 }, output: { ...(existing?.output || {}), requirements_met: requirementsMet, work_incomplete: workIncomplete, checklist_recorded: Boolean(closure?.checklist || existing?.output?.checklist_recorded), required_checklist_items: required, closure_agent: closureAgent } };
}

function eventIcon(event: any) {
  if (event.kind === 'sentiment') return <BrainCircuit size={16} color={colors.purple} />;
  if (event.kind === 'escalation') return <AlertCircle size={16} color={colors.red} />;
  if (event.channel === 'email') return <Mail size={16} color={colors.blue} />;
  if (event.channel === 'push' || event.channel === 'in_app') return <Bell size={16} color={colors.forest} />;
  if (event.channel === 'sms') return <Smartphone size={16} color={colors.blue} />;
  if (event.kind === 'communication') return <MessageCircle size={16} color={colors.blue} />;
  if (event.kind === 'work') return <Activity size={16} color={colors.amber} />;
  return <Bot size={16} color={colors.forest} />;
}

function stageIcon(stage: any) {
  if (stage.state === 'complete') return <Check size={16} color={colors.forest} />;
  if (stage.state === 'active') return <Activity size={16} color={colors.blue} />;
  if (stage.state === 'waiting') return <Clock3 size={16} color={colors.muted} />;
  if (stage.state === 'locked') return <LockKeyhole size={16} color={colors.muted} />;
  return <CircleDashed size={16} color={colors.muted} />;
}

function stageStateLabel(state: string) {
  if (state === 'complete') return 'Complete';
  if (state === 'active') return 'Active';
  if (state === 'waiting') return 'Waiting';
  if (state === 'locked') return 'After acceptance';
  return 'On event';
}

async function fetchWorkflowDetail(jobId: number) {
  const normalized = withClosureStage(await getAgentTrackingJob(jobId));
  if (completed(normalized)) {
    let closure: any = null;
    try { closure = await getJobClosure(normalized.job_id); } catch { /* Older completed jobs may not have a closure record. */ }
    const events = normalized.events || [];
    const existing = events.find((event: any) => event.kind === 'closure');
    normalized.events = [...events.filter((event: any) => event.kind !== 'closure'), closureEvent(normalized, closure, existing)];
  } else normalized.events = (normalized.events || []).filter((event: any) => event.kind !== 'closure');
  return normalized;
}

export default function AgentTrackingScreen() {
  const [jobs, setJobs] = useState<AgentJob[]>([]);
  const [selected, setSelected] = useState<AgentJob | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<Filter>('ALL');
  const [detailedLog, setDetailedLog] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState<number[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [serverActiveCount, setServerActiveCount] = useState(0);
  const [waitingAcceptanceCount, setWaitingAcceptanceCount] = useState(0);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const result = await getAgentTracking();
      const rows = (Array.isArray(result?.jobs) ? result.jobs : Array.isArray(result) ? result : []).map(withClosureStage);
      setJobs(rows);
      setTotalCount(Number(result?.total ?? rows.length));
      setServerActiveCount(Number(result?.active ?? rows.filter((job: AgentJob) => !terminal(job) && !failed(job)).length));
      setWaitingAcceptanceCount(Number(result?.waiting_acceptance ?? rows.filter((job: AgentJob) => job.current_agent === 'Dispatcher').length));
      setSelected(current => current ? rows.find((row: AgentJob) => row.job_id === current.job_id) || current : null);
    } catch (e: any) {
      const status = e?.response?.status;
      setError(status === 404 ? 'Agent Tracking API was not found. Restart the backend so it loads the Agent Tracking route.' : status === 401 ? 'Your session has expired. Sign in again to load agent tracking.' : status === 403 ? 'Your account does not have access to Agent Tracking.' : status >= 500 ? 'The Agent Tracking API returned a server error. Check the backend logs for the request failure.' : 'Agent tracking could not connect to the API. Check the backend connection and try again.');
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  const openJob = useCallback(async (job: AgentJob) => {
    setSelected(job); setDetail(null); setDetailError(''); setDetailedLog(false); setExpandedEvents([]); setDetailLoading(true);
    try {
      const normalized = await fetchWorkflowDetail(job.job_id);
      setDetail(normalized); setSelected(normalized);
      const firstCommunication = (normalized.events || []).findIndex((event: any) => ['communication', 'notification', 'delivery'].includes(event.kind));
      setExpandedEvents(firstCommunication >= 0 ? [firstCommunication] : []);
    } catch (e: any) {
      const status = e?.response?.status;
      const backendDetail = e?.response?.data?.detail;
      setDetailError(status === 404 ? (backendDetail === 'Job not found.' || backendDetail === 'Job not found' ? 'This job is no longer available in your organization. Refresh the workflow list and try again.' : 'The running backend does not have the job detail route loaded. Restart it with the latest code, then try again.') : status === 401 ? 'Your session has expired. Sign in again to view this job’s progress.' : status === 403 ? 'Your account does not have permission to view this job.' : status >= 500 ? 'The backend failed while loading this job’s details. Check the backend logs for the API error.' : 'Could not connect to the job detail API. Check the backend connection and try again.');
    }
    finally { setDetailLoading(false); }
  }, []);

  useEffect(() => { void load(); const timer = setInterval(() => { void load(true); }, 20000); return () => clearInterval(timer); }, [load]);
  useEffect(() => {
    if (!selected) return;
    const timer = setInterval(async () => {
      try { const normalized = await fetchWorkflowDetail(selected.job_id); setDetail(normalized); setSelected(normalized); }
      catch { /* Keep the last successful timeline visible during brief refresh failures. */ }
    }, 20000);
    return () => clearInterval(timer);
  }, [selected?.job_id]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return jobs.filter(job => {
      const matchesFilter = filter === 'ALL' || (filter === 'ACTIVE' && !terminal(job) && !failed(job)) || (filter === 'COMPLETE' && terminal(job) && !failed(job)) || (filter === 'FAILED' && failed(job));
      const matchesSearch = !term || [job.job_number, job.service_type, job.status, job.technician_name, job.customer_name, job.location, job.current_agent].some(value => String(value || '').toLowerCase().includes(term));
      return matchesFilter && matchesSearch;
    });
  }, [jobs, search, filter]);

  const eventRows = detail?.events || [];
  const toggleEvent = (index: number) => setExpandedEvents(current => current.includes(index) ? current.filter(value => value !== index) : [...current, index]);
  const toggleDetailedLog = (value: boolean) => { setDetailedLog(value); setExpandedEvents(value ? eventRows.map((_: any, index: number) => index) : []); };
  const filters: { key: Filter; label: string; count: number }[] = [
    { key: 'ALL', label: 'All jobs', count: totalCount },
    { key: 'ACTIVE', label: 'Running', count: jobs.filter(job => !terminal(job) && !failed(job)).length },
    { key: 'COMPLETE', label: 'Completed', count: jobs.filter(job => terminal(job) && !failed(job)).length },
    { key: 'FAILED', label: 'Failed', count: jobs.filter(failed).length },
  ];

  return <>
    <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
      <ScreenHeading title="Agent Tracking" subtitle="Live server workflow stages, agent decisions, customer sentiment, notifications, and delivery results." action={<Pill label="Live refresh" tone="green" />} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Tracked jobs</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 23 }}>{totalCount}</Text></Card>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Waiting acceptance</Text><Text style={{ color: colors.amber, fontWeight: '900', fontSize: 23 }}>{waitingAcceptanceCount}</Text></Card>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Running</Text><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 23 }}>{serverActiveCount}</Text></Card>
      </View>
      <SearchField value={search} onChangeText={setSearch} placeholder="Search job, customer, agent or service…" />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7 }}>{filters.map(item => <PrimaryButton key={item.key} title={`${item.label} (${item.count})`} compact style={{ minWidth: 100 }} variant={filter === item.key ? 'primary' : 'ghost'} onPress={() => setFilter(item.key)} />)}</ScrollView>
      {error && !selected ? <ErrorBanner message={error} /> : null}
      <SectionTitle title="Job workflows" subtitle="Inspect the complete agent pipeline and event audit for each job" />
      {loading ? <Text style={{ color: colors.muted, textAlign: 'center', padding: 24 }}>Loading agent workflows…</Text> : visible.length === 0 ? <EmptyState title="No matching workflows" detail="No jobs are visible for this tenant or selected filter." onRetry={() => load(true)} /> : visible.map(job => {
        const progress = progressFor(job);
        return <Card key={job.job_id} onPress={() => void openJob(job)} style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}><View style={{ flex: 1 }}><Text style={{ color: colors.forest, fontSize: 12, fontWeight: '900' }}>JOB #{text(job.job_number, String(job.job_id))}</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 14, marginTop: 5 }}>{text(job.service_type, 'Service request')}</Text><Text style={{ color: colors.muted, fontSize: 10, marginTop: 3 }}>Updated {dateTime(job.updated_at)}</Text></View><View style={{ alignItems: 'flex-end', gap: 5 }}><Pill label={failed(job) ? 'Failed' : terminal(job) ? 'Completed' : 'Running'} tone={failed(job) ? 'red' : terminal(job) ? 'green' : 'blue'} />{job.priority ? <Pill label={text(job.priority)} tone={statusTone(job.priority)} /> : null}</View></View>
          <Text style={{ color: colors.muted, fontSize: 11 }}>{text(job.customer_name)} · {text(job.location)}</Text>
          <View style={{ backgroundColor: job.accepted ? '#EAF4EE' : '#FFF4DE', borderRadius: 12, padding: 11, gap: 4 }}><Text style={{ color: colors.forest, fontSize: 10, fontWeight: '900' }}>CURRENT STAGE · {text(job.current_agent, 'Workflow')}</Text><Text style={{ color: colors.text, fontSize: 11, lineHeight: 16 }}>{text(job.current_detail)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Technician: {text(job.technician_name, 'Not assigned')} · {job.accepted ? 'Accepted' : job.assigned_at ? 'Awaiting acceptance' : 'Not assigned'}</Text></View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><View style={{ flex: 1, height: 7, borderRadius: 4, backgroundColor: '#E8EEEA', overflow: 'hidden' }}><View style={{ width: `${progress}%`, height: '100%', borderRadius: 4, backgroundColor: colors.forest }} /></View><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 11 }}>{progress}%</Text></View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5 }}>{(job.stages || []).map(stage => <Pill key={stage.key} label={stage.label} tone={stage.state === 'complete' ? 'green' : stage.state === 'active' ? 'blue' : 'neutral'} />)}</View>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 10 }}>Updated {timeAgo(job.updated_at)}</Text><View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}><Text style={{ color: colors.forest, fontSize: 11, fontWeight: '800' }}>View workflow</Text><ChevronRight size={14} color={colors.forest} /></View></View>
        </Card>;
      })}
      <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10, lineHeight: 16 }}>Agent execution and lifecycle state are read from the same backend APIs as the web dashboard. This view does not run agents on the device.</Text></Card>
    </ScreenScroll>

    <Modal visible={!!selected} animationType="slide" transparent onRequestClose={() => { setSelected(null); setDetail(null); setDetailError(''); }}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.52)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '94%' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}><View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.ink, fontSize: 19, fontWeight: '900' }}>Job #{selected?.job_number || selected?.job_id}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{text(selected?.customer_name)} · {text(selected?.service_type)}</Text></View><PrimaryButton title="Close" compact variant="secondary" onPress={() => { setSelected(null); setDetail(null); setDetailError(''); }} /></View>
          {detailError ? <ErrorBanner message={detailError} /> : null}
          {detailLoading ? <Text style={{ padding: 22, textAlign: 'center', color: colors.muted }}>Loading job progress…</Text> : detail ? <ScreenScroll contentContainerStyle={{ padding: 0, paddingBottom: 26 }}>
            <SectionTitle title="Agent status overview" subtitle="Current activity across the job lifecycle" />
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>{[
              { name: 'Intake Agent', icon: <FileText size={16} color={colors.forest} />, active: true, running: false },
              { name: 'Planning Agent', icon: <CalendarDays size={16} color={colors.blue} />, active: Boolean(detail.assigned_at), running: false },
              { name: 'Dispatcher Agent', icon: <Send size={16} color={colors.amber} />, active: Boolean(detail.assigned_at), running: detail.current_agent === 'Dispatcher' },
              { name: 'Communication Agent', icon: <MessageCircle size={16} color={colors.blue} />, active: detail.accepted, running: false },
              { name: 'Sentiment Agent', icon: <Smile size={16} color={colors.purple} />, active: (detail.events || []).some((event: any) => event.kind === 'sentiment'), running: false },
              ...(detail.stages?.some((stage: any) => stage.key === 'closure') ? [{ name: 'Closure Agent', icon: <CheckCircle2 size={16} color={colors.forest} />, active: true, running: detail.status.toUpperCase() === 'COMPLETED' }] : []),
            ].map(agent => <View key={agent.name} style={{ flexGrow: 1, flexBasis: '47%', flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 12, backgroundColor: agent.running ? '#EAF1FF' : colors.white, borderWidth: 1, borderColor: agent.running ? '#B9CEFF' : colors.border }}><View style={{ width: 30, height: 30, borderRadius: 10, backgroundColor: '#F1F6F3', alignItems: 'center', justifyContent: 'center' }}>{agent.icon}</View><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.ink, fontSize: 10, fontWeight: '900' }}>{agent.name}</Text><Text style={{ color: agent.active ? colors.forest : colors.muted, fontSize: 9, fontWeight: '800' }}>● {agent.running ? 'Running' : agent.active ? 'Active' : 'Idle'}</Text></View></View>)}</View>
            <Card style={{ gap: 10 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><View><Text style={{ color: colors.muted, fontSize: 9, fontWeight: '800' }}>JOB ID</Text><Text style={{ color: colors.forest, fontSize: 13, fontWeight: '900' }}>JOB-{detail.job_number}</Text></View><Pill label={statusLabel(detail.status)} tone={statusTone(detail.status)} /></View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}><View style={{ minWidth: '44%', flex: 1 }}><Text style={factLabel}>CUSTOMER</Text><Text style={factValue}>{text(detail.customer_name, 'Customer')}</Text></View><View style={{ minWidth: '44%', flex: 1 }}><Text style={factLabel}>SERVICE</Text><Text style={factValue}>{text(detail.service_type, 'Service')}</Text></View><View style={{ minWidth: '44%', flex: 1 }}><Text style={factLabel}>PREFERRED VISIT</Text><Text style={factValue}>{[detail.preferred_service_date, detail.preferred_service_time].filter(Boolean).join(', ') || 'Not recorded'}</Text></View><View style={{ minWidth: '44%', flex: 1 }}><Text style={factLabel}>PRIORITY</Text><Text style={factValue}>{text(detail.priority, 'Not recorded')}</Text></View></View>
              {detail.location ? <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}><MapPin size={14} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 11, flex: 1 }}>{detail.location}</Text></View> : null}
            </Card>
            <SectionTitle title="Agent pipeline" subtitle="Live stage state from the backend" />
            {(detail.stages || []).map((stage: any, index: number) => <View key={stage.key || index} style={{ flexDirection: 'row', gap: 11 }}><View style={{ width: 28, alignItems: 'center' }}><View style={{ width: 28, height: 28, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: stage.state === 'complete' ? '#DDF4E6' : stage.state === 'active' ? '#E5EDFF' : '#EDF1EE' }}>{stageIcon(stage)}</View>{index < detail.stages.length - 1 ? <View style={{ height: 36, width: 1, backgroundColor: colors.border }} /> : null}</View><View style={{ flex: 1, gap: 4, paddingBottom: 13 }}><View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 6 }}><Text style={{ color: colors.ink, fontSize: 12, fontWeight: '900', flex: 1 }}>{({ intake: 'Request Received', planning: 'Plan Job', dispatch: 'Assign Technician', communication: 'Communicate', technician_work: 'Track Work', sentiment: 'Check Customer Mood', closure: 'Close Job' } as Record<string, string>)[stage.key] || stage.label}</Text><Pill label={stageStateLabel(stage.state)} tone={stage.state === 'complete' ? 'green' : stage.state === 'active' ? 'blue' : 'neutral'} /></View><Text style={{ color: colors.muted, fontSize: 11, lineHeight: 16 }}>{stage.detail}</Text>{stage.timestamp ? <Text style={{ color: colors.muted, fontSize: 9 }}>{dateTime(stage.timestamp)}</Text> : null}</View></View>)}
            <SectionTitle title="What happened in this job" subtitle={`${eventRows.length} recorded workflow events`} />
            <View style={{ flexDirection: 'row', gap: 7 }}><PrimaryButton title="Simple view" compact style={{ flex: 1 }} variant={!detailedLog ? 'primary' : 'ghost'} onPress={() => toggleDetailedLog(false)} /><PrimaryButton title="Detailed log" compact style={{ flex: 1 }} variant={detailedLog ? 'primary' : 'ghost'} onPress={() => toggleDetailedLog(true)} /></View>
            {eventRows.length === 0 ? <EmptyState title="No workflow events recorded" detail="Events will appear here as this job moves through its stages." /> : eventRows.map((event: any, index: number) => {
              const expanded = detailedLog || expandedEvents.includes(index);
              return <Card key={`${event.kind}-${event.timestamp}-${index}`} onPress={() => toggleEvent(index)} style={{ gap: 8, padding: 13 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>{eventIcon(event)}<Text style={{ color: colors.ink, fontWeight: '900', fontSize: 12, flex: 1 }}>{text(event.agent)}</Text><Pill label={text(event.delivery_status?.replace(/_/g, ' ') || (event.kind === 'communication' ? 'Chat' : 'Recorded'))} tone={['failed', 'permanent_failure', 'review'].includes(String(event.delivery_status).toLowerCase()) ? 'red' : 'neutral'} /></View>
              <Text style={{ color: colors.ink, fontWeight: '800', fontSize: 12 }}>{text(event.title)}</Text>
              {!detailedLog ? <Text style={{ color: colors.text, fontSize: 11, lineHeight: 17 }}>{event.channel ? `${String(event.channel).replace(/_/g, ' ')} · ` : ''}{text(event.detail)}</Text> : null}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ color: colors.muted, fontSize: 9 }}>{dateTime(event.timestamp)}</Text><Text style={{ color: colors.forest, fontSize: 10, fontWeight: '800' }}>{expanded ? 'Hide details' : 'View details'}</Text></View>
              {expanded ? <>
              {event.kind === 'communication' ? <View style={{ backgroundColor: '#EFF5FF', padding: 10, borderRadius: 10, gap: 4 }}><Text style={{ color: colors.blue, fontWeight: '900', fontSize: 10 }}>{event.sender_role ? `${event.sender_role} message` : 'Message'}</Text><Text style={{ color: colors.text, fontSize: 11 }}>{text(event.detail)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Customer mood: {text((event.message_id ? detail.events.find((item: any) => item.kind === 'sentiment' && item.source_message_id === event.message_id)?.detail : null), 'No sentiment analysis recorded for this message.')}</Text></View> : null}
              {event.kind === 'sentiment' ? <View style={{ gap: 4 }}><Text style={factText}>{text(event.detail)}</Text><Text style={factText}>Emotion: {text(event.emotion)} · Urgency: {text(event.urgency)} · Severity: {text(event.severity)}</Text><Text style={factText}>Issue type: {text(event.issue_categories?.map((value: string) => value.replace(/_/g, ' ')).join(', '), 'General')} · Confidence: {event.confidence == null ? 'Not recorded' : `${Math.round(event.confidence * 100)}%`}</Text><Text style={factText}>Analysis: {event.analysis_source === 'KEYWORD_FALLBACK' ? 'Safe keyword fallback' : 'AI analysis'}{event.language ? ` · ${String(event.language).toUpperCase()}` : ''} · Human review {event.requires_human ? 'requested' : 'not required'}</Text>{event.escalation_id != null ? <Text style={factText}>Escalation #{event.escalation_id} · {text(event.escalation_status, 'Open')} · Owner {text(event.escalation_owner_id, 'Tenant queue')}</Text> : null}</View> : null}
              {event.kind === 'delivery' || event.kind === 'notification' ? <View style={{ gap: 4 }}><Text style={factText}>{text(event.detail)}</Text><Text style={factText}>Delivery state: {text(event.delivery_status?.replace(/_/g, ' '), 'Recorded')}</Text><Text style={factText}>Recipient: {event.recipient_name ? `${event.recipient_name} · ` : ''}{text(event.recipient_role, 'Not recorded')}</Text>{event.attempts != null ? <Text style={factText}>Attempts: {event.attempts}</Text> : null}{event.event_version != null ? <Text style={factText}>Event version: {event.event_version}</Text> : null}{event.smtp_status != null ? <Text style={factText}>Mail server status: {event.smtp_status}</Text> : null}</View> : null}
              {event.kind === 'closure' ? <View style={{ backgroundColor: event.output?.requirements_met ? '#E8F7ED' : '#FFF4DE', padding: 11, borderRadius: 11, gap: 6 }}><Text style={{ fontWeight: '900', color: event.output?.requirements_met ? colors.forest : colors.amber }}>Closure requirements check</Text><Text style={{ fontWeight: '800', color: event.output?.requirements_met ? colors.forest : colors.amber }}>{event.output?.requirements_met ? 'Requirements met — ready to close' : 'Requirements need attention'}</Text><Text style={factText}>{text(event.detail)}</Text><Text style={{ color: colors.ink, fontSize: 10, fontWeight: '900', marginTop: 3 }}>{event.output?.checklist_recorded ? 'Required completion items' : 'Completion requirements'}</Text>{(event.output?.required_checklist_items || []).length ? (event.output.required_checklist_items || []).map((item: any, itemIndex: number) => <Text key={`${item.id || 'check'}-${itemIndex}`} style={factText}>{String(item.status).toUpperCase() === 'COMPLETED' ? '✓' : '!' } {text(item.label, 'Required item')} · {String(item.status).toUpperCase() === 'COMPLETED' ? 'Completed' : 'Incomplete'}</Text>) : <Text style={factText}>{event.output?.checklist_recorded ? 'No additional required checklist items for this job.' : 'No additional checklist requirements were recorded.'}</Text>}<Text style={factText}>Work summary: {text(event.input?.work_summary || event.output?.closure_agent?.work_summary)}</Text><Text style={factText}>Evidence attached: {Number(event.input?.after_image_count || 0)} completion photo{Number(event.input?.after_image_count || 0) === 1 ? '' : 's'}</Text><Text style={factText}>Follow-up: {event.output?.closure_agent ? (event.output.closure_agent.follow_up_required ? `Recommended${event.output.closure_agent.follow_up_reason ? `: ${event.output.closure_agent.follow_up_reason}` : ''}` : 'Not recommended') : 'No Closure Agent decision recorded'}</Text>{event.output?.closure_agent?.confidence != null ? <Text style={factText}>Agent confidence: {Math.round(Number(event.output.closure_agent.confidence) * 100)}%</Text> : null}{event.output?.closure_reason ? <Text style={factText}>Closure note: {event.output.closure_reason}</Text> : null}</View> : null}
              {event.kind === 'escalation' ? <View style={{ gap: 4 }}><Text style={factText}>{text(event.detail)}</Text><Text style={factText}>Escalation #{event.escalation_id ?? '—'}</Text><Text style={factText}>Priority: {text(event.severity, 'HIGH')}</Text><Text style={factText}>Owner: {text(event.recipient_id, 'Tenant escalation queue')}</Text><Text style={factText}>Status: {text(event.escalation_status || event.delivery_status, 'Not recorded')}</Text>{event.escalation_trigger ? <Text style={factText}>Trigger: {event.escalation_trigger}</Text> : null}</View> : null}
              {!['communication', 'sentiment', 'delivery', 'notification', 'closure', 'escalation'].includes(event.kind) ? <View style={{ gap: 4 }}><Text style={{ color: colors.ink, fontSize: 10, fontWeight: '900' }}>{text(event.agent)} details</Text><Text style={factText}>{text(event.detail)}</Text></View> : null}
              {event.error ? <Text style={{ color: colors.red, fontSize: 10 }}>Delivery detail: {event.error}</Text> : null}
              {detailedLog && (event.input || event.output || event.message_id || event.provider_message_id || event.source_message_id || event.event_type || event.recipient_id || event.attempts != null || event.urgency || event.severity) ? <View style={{ backgroundColor: '#F3F6F4', borderRadius: 10, padding: 10, gap: 7 }}>
                {event.message_id ? <Text style={factText}>Message ID: {event.message_id}</Text> : null}
                {event.source_message_id ? <Text style={factText}>Source message ID: {event.source_message_id}</Text> : null}
                {event.provider_message_id ? <Text style={factText}>Provider message ID: {event.provider_message_id}</Text> : null}
                {event.actor ? <Text style={factText}>Actor: {event.actor}</Text> : null}
                {event.event_type ? <Text style={factText}>Event type: {event.event_type}{event.event_version != null ? ` · version ${event.event_version}` : ''}</Text> : null}
                {event.recipient_id || event.recipient_name || event.recipient_role ? <Text style={factText}>Recipient: {text(event.recipient_name)} · {text(event.recipient_role)} · ID {text(event.recipient_id)}</Text> : null}
                {event.attempts != null ? <Text style={factText}>Delivery attempts: {event.attempts}</Text> : null}
                {event.smtp_status != null ? <Text style={factText}>Mail server status: {event.smtp_status}</Text> : null}
                {event.urgency || event.severity ? <Text style={factText}>Urgency: {text(event.urgency)} · Severity: {text(event.severity)}</Text> : null}
                {event.issue_categories?.length ? <Text style={factText}>Issue categories: {event.issue_categories.join(', ')}</Text> : null}
                {event.requires_human != null ? <Text style={factText}>Human review: {event.requires_human ? 'Required' : 'Not required'}</Text> : null}
                {event.analysis_source || event.language ? <Text style={factText}>Analysis: {text(event.analysis_source)} · Language: {text(event.language)}</Text> : null}
                {event.escalation_id != null ? <Text style={factText}>Escalation #{event.escalation_id} · {text(event.escalation_status)} · Owner {text(event.escalation_owner_id)} · Trigger {text(event.escalation_trigger)}</Text> : null}
                {event.input ? <><Text style={{ color: colors.ink, fontSize: 10, fontWeight: '900' }}>INPUT</Text><Text selectable style={factText}>{JSON.stringify(event.input, null, 2)}</Text></> : null}
                {event.output ? <><Text style={{ color: colors.ink, fontSize: 10, fontWeight: '900' }}>OUTPUT</Text><Text selectable style={factText}>{JSON.stringify(event.output, null, 2)}</Text></> : null}
              </View> : null}
              </> : null}
            </Card>;
            })}
          </ScreenScroll> : null}
        </View>
      </View>
    </Modal>
  </>;
}

const factText = { color: colors.text, fontSize: 10, lineHeight: 15 } as const;
const factLabel = { color: colors.muted, fontSize: 9, fontWeight: '800' as const };
const factValue = { color: colors.ink, fontSize: 11, fontWeight: '800' as const, marginTop: 3 };
