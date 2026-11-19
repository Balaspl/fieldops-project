import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Modal, RefreshControl, ScrollView, Text, View } from 'react-native';
import { CalendarClock, MapPin, ShieldAlert, UserCheck } from 'lucide-react-native';
import { api } from '../api/client';
import {
  assignJob,
  extendEscalatedSla,
  forceAssignEscalation,
  getAvailableTechnicians,
  getPendingJobs,
  overrideAssignment,
  unwrap,
} from '../api/operations';
import { Card, EmptyState, ErrorBanner, Field, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { dateTime, statusLabel, statusTone, text } from '../utils/format';

type Tab = 'pending' | 'escalations' | 'assigned';

const jobStatus = (job: any) => String(job?.status || job?.job_status || '').toUpperCase();
const isEscalated = (job: any) => ['ESCALATED', 'ESCALATED_TO_CTO'].includes(jobStatus(job));
const technicianName = (tech: any) => tech?.technician_name || tech?.technician || tech?.name || 'Technician';
const technicianStatus = (tech: any) => String(tech?.technician_status || tech?.status || '').toUpperCase();
const normalEligible = (tech: any) => {
  const status = technicianStatus(tech);
  const explicit = tech?.eligible_for_assignment;
  return explicit !== false && (status === 'AVAILABLE' || status === 'ASSIGNED');
};
const escalationEligible = (tech: any) => !['BUSY', 'OFFLINE'].includes(technicianStatus(tech));

export default function PlanningScreen() {
  const [tab, setTab] = useState<Tab>('pending');
  const [pending, setPending] = useState<any[]>([]);
  const [assigned, setAssigned] = useState<any[]>([]);
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [selectedJob, setSelectedJob] = useState<any | null>(null);
  const [selectedTechId, setSelectedTechId] = useState<string | number | null>(null);
  const [forceMode, setForceMode] = useState(false);
  const [justification, setJustification] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [extendingSla, setExtendingSla] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    const [pendingResult, assignedResult] = await Promise.allSettled([
      getPendingJobs({ page: 1, limit: 100 }),
      api.get('/planned-assignments', { params: { page: 1, limit: 100 } }),
    ]);
    if (pendingResult.status === 'fulfilled') setPending(pendingResult.value);
    if (assignedResult.status === 'fulfilled') {
      const data = unwrap<any>(assignedResult.value);
      setAssigned(Array.isArray(data) ? data : data?.items || data?.results || []);
    }
    if (pendingResult.status === 'rejected' && assignedResult.status === 'rejected') {
      setError((pendingResult.reason as any)?.response?.data?.detail || 'Unable to load the planning workspace.');
    } else if (pendingResult.status === 'rejected') {
      setError((pendingResult.reason as any)?.response?.data?.detail || 'Unable to refresh the pending queue.');
    } else if (assignedResult.status === 'rejected') {
      setError((assignedResult.reason as any)?.response?.data?.detail || 'Unable to refresh planned assignments.');
    }
    setLoading(false); setRefreshing(false);
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => { void load(true); }, 35000);
    return () => clearInterval(timer);
  }, [load]);

  const escalations = useMemo(() => pending.filter(isEscalated), [pending]);
  const normalPending = useMemo(() => pending.filter(job => !isEscalated(job)), [pending]);
  const source = tab === 'pending' ? normalPending : tab === 'escalations' ? escalations : assigned;
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return source.filter((job: any) => !term || [job.id, job.job_id, job.customer_name, job.customer, job.location, job.service_type, job.issue_description, job.technician, job.assigned_technician].some(v => String(v || '').toLowerCase().includes(term)));
  }, [source, search]);

  const openAssignment = async (job: any) => {
    setSelectedJob(job); setSelectedTechId(null); setForceMode(isEscalated(job)); setJustification(''); setTechnicians([]);
    try {
      const list = await getAvailableTechnicians();
      setTechnicians(list);
    } catch (e: any) {
      Alert.alert('Technician list unavailable', e?.response?.data?.detail || e?.message || 'Cannot fetch available technicians.');
      setTechnicians([]);
    }
  };

  const submitAssignment = async () => {
    if (!selectedJob || selectedTechId === null) {
      Alert.alert('Select a technician', 'Choose a technician before submitting this assignment.'); return;
    }
    const escalated = isEscalated(selectedJob);
    if ((forceMode || escalated) && justification.trim().length < 8) {
      Alert.alert('Justification required', 'Enter at least 8 characters explaining why this override is necessary.'); return;
    }
    if (!forceMode && !normalEligible(technicians.find(t => String(t.technician_id ?? t.id ?? t.tech_id) === String(selectedTechId)))) {
      Alert.alert('Technician unavailable', 'Choose a technician marked Available or Assigned for a normal assignment.'); return;
    }
    setAssigning(true);
    try {
      const jobId = selectedJob.id ?? selectedJob.job_id;
      if (escalated) await forceAssignEscalation(jobId, selectedTechId, justification.trim());
      else if (forceMode) await overrideAssignment(jobId, selectedTechId, justification.trim());
      else await assignJob(jobId, selectedTechId);
      setSelectedJob(null);
      Alert.alert('Assignment submitted', escalated ? 'The escalation-specific force-assignment workflow completed.' : forceMode ? 'The backend accepted the manual override request.' : 'The job was assigned using the normal backend dispatch rules.');
      await load(true);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || 'Assignment failed.';
      Alert.alert('Assignment not completed', typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally { setAssigning(false); }
  };

  const extendSla = (job: any) => {
    Alert.alert('Extend SLA deadline', `Add 30 minutes to the SLA deadline for job #${job.id ?? job.job_id}?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Extend by 30 min', onPress: async () => {
        setExtendingSla(true);
        try {
          await extendEscalatedSla(job.id ?? job.job_id, 30);
          Alert.alert('SLA extended', 'The backend recorded the SLA extension and escalation response.');
          await load(true);
        } catch (e: any) {
          Alert.alert('SLA not extended', e?.response?.data?.detail || e?.message || 'The SLA extension failed.');
        } finally { setExtendingSla(false); }
      } },
    ]);
  };

  const tabTitle = tab === 'pending' ? 'Pending job queue' : tab === 'escalations' ? 'SLA escalations' : 'Planned assignments';
  const tabDescription = tab === 'pending' ? 'Unassigned jobs that have not entered escalation.' : tab === 'escalations' ? 'Manager and CTO escalations requiring an operational response.' : 'Jobs already linked to technicians.';

  return <>
    <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
      <ScreenHeading title="Planning & Dispatch" subtitle="Job planning, dispatch, manual overrides and SLA escalation handling." />
      <View style={{ flexDirection: 'row', gap: 4, backgroundColor: '#E7EFEA', padding: 4, borderRadius: 14 }}>
        <PrimaryButton title={`Pending (${normalPending.length})`} compact variant={tab === 'pending' ? 'primary' : 'ghost'} style={{ flex: 1 }} onPress={() => setTab('pending')} />
        <PrimaryButton title={`Escalated (${escalations.length})`} compact variant={tab === 'escalations' ? 'primary' : 'ghost'} style={{ flex: 1 }} onPress={() => setTab('escalations')} />
        <PrimaryButton title={`Assigned (${assigned.length})`} compact variant={tab === 'assigned' ? 'primary' : 'ghost'} style={{ flex: 1 }} onPress={() => setTab('assigned')} />
      </View>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Card style={{ flex: 1, padding: 12, gap: 4 }}><CalendarClock size={17} color={colors.amber} /><Text style={{ color: colors.muted, fontSize: 10 }}>Pending</Text><Text style={{ color: colors.ink, fontSize: 21, fontWeight: '900' }}>{normalPending.length}</Text></Card>
        <Card style={{ flex: 1, padding: 12, gap: 4 }}><ShieldAlert size={17} color={colors.red} /><Text style={{ color: colors.muted, fontSize: 10 }}>Escalated</Text><Text style={{ color: colors.ink, fontSize: 21, fontWeight: '900' }}>{escalations.length}</Text></Card>
        <Card style={{ flex: 1, padding: 12, gap: 4 }}><UserCheck size={17} color={colors.forest} /><Text style={{ color: colors.muted, fontSize: 10 }}>Assigned</Text><Text style={{ color: colors.ink, fontSize: 21, fontWeight: '900' }}>{assigned.length}</Text></Card>
      </View>
      <SearchField value={search} onChangeText={setSearch} placeholder="Search job, customer, service or location…" />
      {error ? <ErrorBanner message={error} /> : null}
      <SectionTitle title={tabTitle} subtitle={tabDescription} />
      {loading ? <Text style={{ color: colors.muted, textAlign: 'center', padding: 24 }}>Loading planning data…</Text> : rows.length === 0 ? <EmptyState title={tab === 'pending' ? 'No pending jobs' : tab === 'escalations' ? 'No active SLA escalations' : 'No planned assignments'} detail={search ? 'No records matched your search.' : tab === 'escalations' ? 'No jobs currently require escalation action.' : 'The backend currently has no records in this view.'} onRetry={() => load(true)} /> : rows.map((job: any) => {
        const id = job.id ?? job.job_id;
        const assignedTech = job.assigned_technician || job.technician || null;
        const escalated = isEscalated(job);
        const cto = jobStatus(job) === 'ESCALATED_TO_CTO';
        return <Card key={String(id)} style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><Text style={{ color: colors.forest, fontSize: 12, fontWeight: '900' }}>JOB #{id}</Text><Pill label={statusLabel(job.status || job.job_status)} tone={statusTone(job.status || job.job_status)} /></View>
          <Text style={{ color: colors.ink, fontSize: 15, fontWeight: '900' }}>{text(job.service_type, 'Service job')}</Text>
          <Text style={{ color: colors.text, fontSize: 12, lineHeight: 17 }}>{text(job.issue_description, job.description || 'No job description available.')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><MapPin size={14} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 11, flex: 1 }}>{text(job.location)}</Text></View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7, alignItems: 'center' }}><Pill label={`${text(job.priority, 'Normal')} priority`} tone={statusTone(job.priority)} /><Pill label={`Skill: ${text(job.required_skill || job.skill, 'Any')}`} tone="neutral" />{escalated ? <Pill label={cto ? 'CTO escalated' : 'Manager escalated'} tone="red" /> : null}</View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Customer</Text><Text style={{ color: colors.ink, fontSize: 12, fontWeight: '800' }}>{text(job.customer_name || job.customer)}</Text></View><View style={{ flex: 1, alignItems: 'flex-end', gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>SLA deadline</Text><Text style={{ color: colors.text, fontSize: 11 }}>{dateTime(job.sla_deadline)}</Text></View></View>
          {tab === 'assigned' ? <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 10 }}>Assigned technician</Text><Text style={{ color: colors.forest, fontSize: 11, fontWeight: '800' }}>{text(assignedTech || job.technician)}</Text></View> : tab === 'escalations' ? <View style={{ flexDirection: 'row', gap: 8 }}><View style={{ flex: 1 }}><PrimaryButton title="Extend SLA +30m" compact variant="secondary" loading={extendingSla} onPress={() => extendSla(job)} /></View><View style={{ flex: 1 }}><PrimaryButton title="Force assign" compact onPress={() => openAssignment(job)} /></View></View> : <PrimaryButton title="Assign technician" compact onPress={() => openAssignment(job)} />}
        </Card>;
      })}
      <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10, lineHeight: 16 }}>Assignments, workload eligibility, SLA changes, tenant isolation, timers, audit events and notifications are validated and executed by the FieldOps backend.</Text></Card>
    </ScreenScroll>

    <Modal visible={!!selectedJob} animationType="slide" transparent onRequestClose={() => setSelectedJob(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, maxHeight: '92%', gap: 13 }}>
          <View style={{ gap: 4 }}><Text style={{ color: colors.ink, fontSize: 20, fontWeight: '900' }}>{isEscalated(selectedJob) ? 'Force-assign escalation' : 'Assign job'} #{selectedJob?.id ?? selectedJob?.job_id}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{text(selectedJob?.service_type)} · {text(selectedJob?.customer_name)}</Text></View>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Select technician</Text>
          <ScrollView style={{ maxHeight: 280 }} keyboardShouldPersistTaps="handled">
            {technicians.length === 0 ? <EmptyState title="No available technicians" detail="The backend did not return eligible technicians for this queue." /> : technicians.map((tech: any) => {
              const id = tech.technician_id ?? tech.id ?? tech.tech_id;
              const selected = String(selectedTechId) === String(id);
              const eligible = normalEligible(tech);
              const escalatedJob = isEscalated(selectedJob);
              const canChoose = escalatedJob ? escalationEligible(tech) : (forceMode || eligible);
              return <Card key={String(id)} onPress={canChoose ? () => setSelectedTechId(id) : undefined} style={{ borderColor: selected ? colors.forest : colors.border, backgroundColor: selected ? '#F0F8F3' : colors.white, padding: 12, marginBottom: 8, gap: 6, opacity: canChoose ? 1 : 0.58 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ color: colors.ink, fontSize: 13, fontWeight: '900', flex: 1 }}>{technicianName(tech)}</Text><Pill label={statusLabel(tech.technician_status || tech.status)} tone={statusTone(tech.technician_status || tech.status)} /></View>
                <Text style={{ color: colors.muted, fontSize: 10 }}>{text(tech.technician_skill || tech.skill)} · Workload {tech.current_jobs ?? 0}/{tech.max_jobs ?? 5}</Text>
                {!escalatedJob && !eligible && !forceMode ? <Text style={{ color: colors.red, fontSize: 10 }}>Not eligible for normal assignment</Text> : null}
                {escalatedJob && !escalationEligible(tech) ? <Text style={{ color: colors.red, fontSize: 10 }}>Busy or offline technicians cannot receive an escalation assignment</Text> : null}
                {tech.eligible_for_assignment === false ? <Text style={{ color: colors.amber, fontSize: 10 }}>Backend eligibility check: restricted</Text> : null}
                {selected ? <Text style={{ color: colors.forest, fontSize: 10, fontWeight: '900' }}>SELECTED</Text> : null}
              </Card>;
            })}
          </ScrollView>
          {!isEscalated(selectedJob) ? <PrimaryButton title={forceMode ? 'Use normal assignment' : 'Manual override instead'} variant="ghost" compact onPress={() => { setForceMode(v => !v); setSelectedTechId(null); }} /> : null}
          {forceMode ? <><Text style={{ color: colors.amber, fontSize: 11, lineHeight: 16 }}>Manual override bypasses normal dispatch planning checks but remains subject to backend safety and tenant rules. A reason is mandatory.</Text><Field label="OVERRIDE JUSTIFICATION" value={justification} onChangeText={setJustification} placeholder="Explain why this assignment is necessary…" multiline numberOfLines={3} /></> : null}
          <PrimaryButton title={isEscalated(selectedJob) ? 'Confirm escalation force assignment' : forceMode ? 'Submit manual override' : 'Confirm assignment'} onPress={submitAssignment} loading={assigning} disabled={!technicians.length || selectedTechId === null} />
          <PrimaryButton title="Cancel" variant="secondary" onPress={() => setSelectedJob(null)} />
        </View>
      </View>
    </Modal>
  </>;
}
