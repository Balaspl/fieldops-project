import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Modal, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { AlertCircle, ArrowDown, ArrowUp, Check, CheckCircle2, CircleMinus, CircleX, Clock3, Equal, Eye, Filter, Layers, LoaderCircle, MapPin, Navigation, RotateCcw, UserRound } from 'lucide-react-native';
import { api } from '../api/client';
import {
  assignJob,
  assignJobsBulk,
  cancelJobsBulk,
  cancelEscalatedJob,
  extendEscalatedSla,
  forceAssignEscalation,
  getAvailableTechnicians,
  getJobPlan,
  overrideAssignment,
  asArray,
  unwrap,
} from '../api/operations';
import { Card, EmptyState, ErrorBanner, Field, Pill, PrimaryButton, ScreenScroll, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { dateTime, statusLabel, statusTone, text } from '../utils/format';

type Tab = 'total' | 'planned' | 'enroute' | 'inprogress' | 'completed' | 'declined' | 'escalations';
type FilterState = { technician: string; service: string; status: string; priority: string; sla: string };
const DEFAULT_FILTERS: FilterState = { technician: 'ALL', service: 'ALL', status: 'ALL', priority: 'ALL', sla: 'ALL' };

const jobStatus = (job: any) => String(job?.status || job?.job_status || '').toUpperCase();
const isEscalated = (job: any) => ['ESCALATED', 'ESCALATED_TO_CTO'].includes(jobStatus(job));
const technicianName = (tech: any) => tech?.technician_name || tech?.technician || tech?.name || 'Technician';

const statusOptions = [
  { label: 'All Statuses', value: 'ALL', icon: Layers, color: '#087B50', tint: '#E9F8EF' },
  { label: 'Unassigned', value: 'UNASSIGNED', icon: CircleMinus, color: '#475569', tint: '#F1F5F9' },
  { label: 'Assigned', value: 'ASSIGNED', icon: UserRound, color: '#1D4ED8', tint: '#EDF4FF' },
  { label: 'En Route', value: 'EN_ROUTE', icon: Navigation, color: '#6B21A8', tint: '#F4EEFF' },
  { label: 'In Progress', value: 'IN_PROGRESS', icon: LoaderCircle, color: '#C2410C', tint: '#FFF3E8' },
  { label: 'Completed', value: 'COMPLETED', icon: CheckCircle2, color: '#047857', tint: '#E9FBF3' },
  { label: 'Cancelled', value: 'CANCELLED', icon: CircleX, color: '#B91C1C', tint: '#FFF0F0' },
];
const hiddenStatusTabs: Tab[] = ['enroute', 'inprogress', 'completed'];

export default function PlanningScreen() {
  const [tab, setTab] = useState<Tab>('planned');
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [serviceOptions, setServiceOptions] = useState<string[]>([]);
  const [filterPicker, setFilterPicker] = useState<'technician' | 'service' | null>(null);
  const [technicianOptions, setTechnicianOptions] = useState<any[]>([]);
  const [allJobs, setAllJobs] = useState<any[]>([]);
  const [pending, setPending] = useState<any[]>([]);
  const [assigned, setAssigned] = useState<any[]>([]);
  const [enRouteJobs, setEnRouteJobs] = useState<any[]>([]);
  const [inProgressJobs, setInProgressJobs] = useState<any[]>([]);
  const [completedJobs, setCompletedJobs] = useState<any[]>([]);
  const [declinedJobs, setDeclinedJobs] = useState<any[]>([]);
  const [tabCounts, setTabCounts] = useState<Record<Tab, number>>({ total: 0, planned: 0, enroute: 0, inprogress: 0, completed: 0, declined: 0, escalations: 0 });
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [selectedJob, setSelectedJob] = useState<any | null>(null);
  const [detailJob, setDetailJob] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [declinedJobForReassign, setDeclinedJobForReassign] = useState<any | null>(null);
  const [cancelEscalationJob, setCancelEscalationJob] = useState<any | null>(null);
  const [escalationCancelReason, setEscalationCancelReason] = useState('');
  const [cancelEscalationLoading, setCancelEscalationLoading] = useState(false);
  const [reassignTechnicians, setReassignTechnicians] = useState<any[]>([]);
  const [reassignTechId, setReassignTechId] = useState<string | number | null>(null);
  const [reassignLoading, setReassignLoading] = useState(false);
  const [selectedTechId, setSelectedTechId] = useState<string | number | null>(null);
  const [forceMode, setForceMode] = useState(false);
  const [justification, setJustification] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [extendingSla, setExtendingSla] = useState(false);
  const [slaExtensionJob, setSlaExtensionJob] = useState<any | null>(null);
  const [slaExtensionMinutes, setSlaExtensionMinutes] = useState('30');
  const [rankedTechnicians, setRankedTechnicians] = useState<any[]>([]);
  const [rankingLoading, setRankingLoading] = useState(false);
  const [rankingError, setRankingError] = useState('');
  const [selectedJobIds, setSelectedJobIds] = useState<Array<string | number>>([]);
  const [bulkMode, setBulkMode] = useState<'assign' | 'cancel' | null>(null);
  const [bulkTechnicians, setBulkTechnicians] = useState<any[]>([]);
  const [bulkTechId, setBulkTechId] = useState<string | number | null>(null);
  const [bulkReason, setBulkReason] = useState('');
  const [bulkLoading, setBulkLoading] = useState(false);
  const loadRequestId = useRef(0);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([api.get('/technicians'), api.get('/jobs/service-types')]).then(([techResult, serviceResult]) => {
      if (!active) return;
      if (techResult.status === 'fulfilled') {
        const value = unwrap<any>(techResult.value);
        setTechnicianOptions(Array.isArray(value) ? value : value?.items || []);
      }
      if (serviceResult.status === 'fulfilled') {
        const value = unwrap<any>(serviceResult.value);
        setServiceOptions(Array.isArray(value) ? value : []);
      }
    });
    return () => { active = false; };
  }, []);

  const load = useCallback(async (silent = false) => {
    const requestId = ++loadRequestId.current;
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    const params = {
      status: ['total', 'planned'].includes(tab) && filters.status !== 'ALL' ? filters.status : undefined,
      priority: filters.priority === 'ALL' ? undefined : filters.priority,
      service_type: filters.service === 'ALL' ? undefined : filters.service,
      sla: filters.sla === 'ALL' ? undefined : filters.sla,
      technician_id: filters.technician === 'ALL' ? undefined : Number(filters.technician),
    };
    const [jobsResult, pendingResult, assignedResult, enRouteResult, inProgressResult, completedResult, declinedResult] = await Promise.allSettled([
      api.get('/jobs', { params }),
      api.get('/jobs/pending'),
      api.get('/planned-assignments'),
      api.get('/dispatch/queue', { params: { status: 'EN_ROUTE', limit: 100 } }),
      api.get('/jobs', { params: { ...params, status: 'IN_PROGRESS' } }),
      api.get('/jobs', { params: { ...params, status: 'COMPLETED_OR_CLOSED' } }),
      api.get('/planning/declined-jobs'),
    ]);
    if (requestId !== loadRequestId.current) return;
    const responseRows = (result: PromiseSettledResult<any>) => result.status === 'fulfilled' ? asArray(result.value) : [];
    const responseCount = (result: PromiseSettledResult<any>, rows: any[]) => {
      if (result.status !== 'fulfilled') return rows.length;
      const raw = result.value?.headers?.['x-total-count'] ?? result.value?.headers?.['X-Total-Count'];
      const count = Number.parseInt(String(raw ?? ''), 10);
      return Number.isFinite(count) ? Math.max(count, rows.length) : rows.length;
    };
    const jobRows = responseRows(jobsResult);
    const filteredJobIds = new Set(jobRows.map((job: any) => String(job.id ?? job.job_id)));
    const pendingRows = responseRows(pendingResult);
    const assignedRows = responseRows(assignedResult);
    const enRouteRows = responseRows(enRouteResult);
    const inProgressRows = responseRows(inProgressResult);
    const completedRows = responseRows(completedResult);
    const declinedRows = responseRows(declinedResult);
    const escalatedRows = pendingRows.filter(isEscalated);
    setAllJobs(jobRows);
    setPending(pendingRows);
    setAssigned(assignedRows);
    setEnRouteJobs(enRouteRows);
    setInProgressJobs(inProgressRows);
    setCompletedJobs(completedRows);
    setDeclinedJobs(declinedRows);
    setTabCounts({
      total: responseCount(jobsResult, jobRows),
      planned: responseCount(pendingResult, pendingRows) + responseCount(assignedResult, assignedRows),
      enroute: enRouteRows.length,
      inprogress: responseCount(inProgressResult, inProgressRows),
      completed: responseCount(completedResult, completedRows),
      declined: declinedRows.length,
      escalations: escalatedRows.length,
    });
    if (jobsResult.status === 'rejected' && pendingResult.status === 'rejected' && assignedResult.status === 'rejected') {
      setError((jobsResult.reason as any)?.response?.data?.detail || 'Unable to load the planning workspace.');
    } else if ([jobsResult, pendingResult, assignedResult, enRouteResult, inProgressResult, completedResult, declinedResult].some(result => result.status === 'rejected')) {
      setError('Some planning lists could not be refreshed.');
    }
    setLoading(false); setRefreshing(false);
  }, [filters.priority, filters.service, filters.sla, filters.status, filters.technician, tab]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => { void load(true); }, 35000);
    return () => clearInterval(timer);
  }, [load]);

  const escalations = useMemo(() => pending.filter(isEscalated), [pending]);
  const plannedOnly = useMemo(() => assigned.filter((job: any) => ['ASSIGNED', 'WAITING_FOR_ACCEPT', 'WAITING_FOR_ACCEPTANCE', 'ACCEPTED', 'ACCEPTED_BY_TECHNICIAN'].includes(String(job.status || '').trim().toUpperCase().replace(/[\s-]+/g, '_'))), [assigned]);
  const plannedJobs = useMemo(() => [...pending.filter((job: any) => !isEscalated(job)), ...plannedOnly], [pending, plannedOnly]);
  const source = tab === 'total' ? allJobs : tab === 'planned' ? plannedJobs : tab === 'enroute' ? enRouteJobs : tab === 'inprogress' ? inProgressJobs : tab === 'completed' ? completedJobs : tab === 'declined' ? declinedJobs : escalations;
  const matchingIds = useMemo(() => new Set(allJobs.map((job: any) => String(job.id ?? job.job_id))), [allJobs]);
  const rows = useMemo(() => {
    const filteredSource = ['total', 'declined', 'escalations'].includes(tab) ? source : source.filter((job: any) => matchingIds.has(String(job.id ?? job.job_id)));
    return filteredSource;
  }, [source, tab, matchingIds]);
  const selectableRows = tab === 'total' ? rows.filter((job: any) => job.assigned_technician_id == null && !isEscalated(job) && !['COMPLETED', 'CLOSED', 'CANCELLED', 'CANCELED', 'REJECTED_BY_TECHNICIAN'].includes(jobStatus(job))) : [];

  const toggleJobSelection = (id: string | number) => setSelectedJobIds(current => current.some(value => String(value) === String(id)) ? current.filter(value => String(value) !== String(id)) : [...current, id]);
  const openBulkAction = async (mode: 'assign' | 'cancel') => {
    setBulkMode(mode); setBulkReason(''); setBulkTechId(null); setBulkTechnicians([]);
    if (mode === 'assign') {
      try { setBulkTechnicians(await getAvailableTechnicians()); }
      catch (e: any) { setBulkMode(null); Alert.alert('Technician list unavailable', e?.response?.data?.detail || e?.message || 'Cannot fetch technicians.'); }
    }
  };
  const submitBulkAction = async () => {
    if (!selectedJobIds.length) return;
    if (bulkMode === 'assign' && bulkTechId === null) { Alert.alert('Select a technician', 'Choose a technician for the selected jobs.'); return; }
    if (bulkMode === 'cancel' && !bulkReason.trim()) { Alert.alert('Reason required', 'Enter a cancellation reason.'); return; }
    setBulkLoading(true);
    try {
      if (bulkMode === 'assign') await assignJobsBulk(selectedJobIds, bulkTechId!);
      else await cancelJobsBulk(selectedJobIds, bulkReason.trim());
      setBulkMode(null); setSelectedJobIds([]); setBulkReason('');
      Alert.alert(bulkMode === 'assign' ? 'Bulk assignment submitted' : 'Jobs cancelled', bulkMode === 'assign' ? 'The backend processed the selected jobs using its dispatch rules.' : 'The backend recorded the cancellation reason for the selected jobs.');
      await load(true);
    } catch (e: any) { Alert.alert('Bulk action failed', e?.response?.data?.detail || e?.message || 'The backend could not complete this action.'); }
    finally { setBulkLoading(false); }
  };

  const openAssignment = async (job: any) => {
    setSelectedJob(job); setSelectedTechId(null); setForceMode(isEscalated(job)); setJustification(''); setTechnicians([]); setRankedTechnicians([]); setRankingError('');
    try {
      const list = await getAvailableTechnicians();
      setTechnicians(list);
    } catch (e: any) {
      Alert.alert('Technician list unavailable', e?.response?.data?.detail || e?.message || 'Cannot fetch available technicians.');
      setTechnicians([]);
    }
  };

  const openJobDetails = async (job: any) => {
    setDetailJob(job);
    setDetailLoading(true);
    try {
      const result = unwrap<any>(await api.get(`/jobs/${job.id ?? job.job_id}`));
      setDetailJob(result);
    } catch {
      // The list row remains usable as a read-only fallback if details are unavailable.
    } finally {
      setDetailLoading(false);
    }
  };

  const submitEscalationCancel = async () => {
    const id = cancelEscalationJob?.id ?? cancelEscalationJob?.job_id;
    if (id == null || !escalationCancelReason.trim()) {
      Alert.alert('Reason required', 'Enter a cancellation reason before continuing.');
      return;
    }
    setCancelEscalationLoading(true);
    try {
      await cancelEscalatedJob(id, escalationCancelReason.trim());
      setCancelEscalationJob(null);
      setEscalationCancelReason('');
      Alert.alert('Escalated job cancelled', `Job #${id} was cancelled.`);
      await load(true);
    } catch (e: any) {
      Alert.alert('Cancellation failed', e?.response?.data?.detail || e?.message || 'The backend could not cancel this job.');
    } finally {
      setCancelEscalationLoading(false);
    }
  };

  const openDeclinedReassignment = (job: any) => {
    setDeclinedJobForReassign(job);
    setReassignTechId(null);
    const eligible = technicianOptions.filter((tech: any) => {
      const status = String(tech.technician_status || '').trim().toLowerCase().replace(/[\s_-]+/g, ' ');
      return status === 'available' && Number(tech.current_jobs ?? 0) < Number(tech.max_jobs ?? 5);
    });
    setReassignTechnicians(eligible);
  };

  const submitDeclinedReassignment = async () => {
    if (!declinedJobForReassign || reassignTechId === null) return;
    setReassignLoading(true);
    try {
      const jobId = declinedJobForReassign.id ?? declinedJobForReassign.job_id;
      await api.post(`/planning/declined-jobs/${jobId}/reassign`, null, { params: { new_technician_id: Number(reassignTechId) } });
      setDeclinedJobForReassign(null);
      Alert.alert('Job reassigned', `Job #${jobId} was reassigned through the backend planning workflow.`);
      await load(true);
    } catch (e: any) { Alert.alert('Reassignment failed', e?.response?.data?.detail || e?.message || 'The backend could not reassign this job.'); }
    finally { setReassignLoading(false); }
  };

  const loadRankedTechnicians = async () => {
    if (!selectedJob) return;
    setRankingLoading(true); setRankingError('');
    try {
      const plan = await getJobPlan(selectedJob.id ?? selectedJob.job_id, forceMode);
      setRankedTechnicians(Array.isArray(plan?.ranked_technicians) ? plan.ranked_technicians : []);
    } catch (e: any) {
      setRankingError(e?.response?.data?.detail || e?.message || 'The backend could not generate technician recommendations.');
      setRankedTechnicians([]);
    } finally { setRankingLoading(false); }
  };

  const submitAssignment = async () => {
    if (!selectedJob || selectedTechId === null) {
      Alert.alert('Select a technician', 'Choose a technician before submitting this assignment.'); return;
    }
    const escalated = isEscalated(selectedJob);
    if ((forceMode || escalated) && justification.trim().length < 8) {
      Alert.alert('Justification required', 'Enter at least 8 characters explaining why this override is necessary.'); return;
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

  const extendSla = (job: any) => { setSlaExtensionJob(job); setSlaExtensionMinutes('30'); };
  const submitSlaExtension = async () => {
    const minutes = Number.parseInt(slaExtensionMinutes, 10);
    if (!slaExtensionJob || !Number.isFinite(minutes) || minutes <= 0) {
      Alert.alert('Invalid extension', 'Enter a positive number of minutes.');
      return;
    }
    setExtendingSla(true);
    try {
      await extendEscalatedSla(slaExtensionJob.id ?? slaExtensionJob.job_id, minutes);
      setSlaExtensionJob(null);
      Alert.alert('SLA extended', `The backend extended the deadline by ${minutes} minutes.`);
      await load(true);
    } catch (e: any) {
      Alert.alert('SLA not extended', e?.response?.data?.detail || e?.message || 'The SLA extension failed.');
    } finally { setExtendingSla(false); }
  };

  const tabTitle: Record<Tab, string> = { total: 'Total Jobs', planned: 'Planned Assignments', enroute: 'En Route Jobs', inprogress: 'In Progress', completed: 'Completed', declined: 'Technician Declined Jobs', escalations: 'SLA Escalations' };
  const tabOrder: Tab[] = ['total', 'planned', 'enroute', 'inprogress', 'completed', 'declined', 'escalations'];
  const changeTab = (nextTab: Tab) => {
    setTab(nextTab);
    if (hiddenStatusTabs.includes(nextTab) || (nextTab === 'planned' && !['ALL', 'UNASSIGNED', 'ASSIGNED'].includes(filters.status))) {
      setFilters(current => ({ ...current, status: 'ALL' }));
    }
  };
  const updateFilter = (key: keyof FilterState, value: string) => {
    setFilters(current => ({ ...current, [key]: value }));
    setSelectedJobIds([]);
  };
  const clearFilters = () => { setFilters(DEFAULT_FILTERS); setSelectedJobIds([]); };
  const serviceTitle = filters.service === 'ALL' ? 'All Services' : filters.service;
  const technicianTitle = filters.technician === 'ALL' ? 'All Technicians' : technicianName(technicianOptions.find((tech: any) => String(tech.technician_id ?? tech.id) === filters.technician));
  const displayRows = rows;

  return <>
    <ScreenScroll contentContainerStyle={{ gap: 7, paddingHorizontal: 8, paddingTop: 7, paddingBottom: 16 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
      <Card style={{ gap: 6, padding: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6, paddingBottom: 5, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, flex: 1 }}><View style={{ width: 29, height: 29, borderRadius: 9, backgroundColor: '#E5F4EA', alignItems: 'center', justifyContent: 'center' }}><Filter size={16} color="#16864E" /></View><View><Text style={{ color: '#24382C', fontSize: 13, fontWeight: '900' }}>Job Filters</Text><Text style={{ color: '#728176', fontSize: 10, marginTop: 1 }}>Search and narrow down jobs</Text></View></View>
          <Pressable onPress={clearFilters} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 30, paddingHorizontal: 8, borderWidth: 1, borderColor: '#DDE8E0', borderRadius: 8 }}><RotateCcw size={12} color="#315840" /><Text style={{ color: '#315840', fontSize: 10, fontWeight: '800' }}>Clear</Text></Pressable>
        </View>
        <View style={{ gap: 5 }}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <View style={{ flex: 1, gap: 3 }}><Text style={filterLabel}>TECHNICIAN</Text><Pressable onPress={() => setFilterPicker('technician')} style={selectField}><Text numberOfLines={1} style={selectText}>{technicianTitle}</Text><Text style={selectChevron}>⌄</Text></Pressable></View>
            <View style={{ flex: 1, gap: 3 }}><Text style={filterLabel}>SERVICE</Text><Pressable onPress={() => setFilterPicker('service')} style={selectField}><Text numberOfLines={1} style={selectText}>{serviceTitle}</Text><Text style={selectChevron}>⌄</Text></Pressable></View>
          </View>
        </View>
        {!hiddenStatusTabs.includes(tab) ? <View style={{ paddingBottom: 5, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 3 }}>
          <Text style={filterLabel}>STATUS</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>{(tab === 'planned' ? statusOptions.slice(1, 3) : statusOptions).map(item => <FilterChip key={item.value} {...item} selected={filters.status === item.value} onPress={() => updateFilter('status', item.value)} />)}</View>
        </View> : null}
        <View style={{ gap: 5 }}>
          <View style={{ gap: 3 }}><Text style={filterLabel}>PRIORITY</Text><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>{[
            { label: 'All', value: 'ALL', icon: Layers, color: '#087B50', tint: '#E9F8EF' }, { label: 'Critical', value: 'CRITICAL', icon: AlertCircle, color: '#B91C1C', tint: '#FFF0F0' }, { label: 'High', value: 'HIGH', icon: ArrowUp, color: '#C2410C', tint: '#FFF3E8' }, { label: 'Medium', value: 'MEDIUM', icon: Equal, color: '#1D4ED8', tint: '#EDF4FF' }, { label: 'Low', value: 'LOW', icon: ArrowDown, color: '#047857', tint: '#E9FBF3' },
          ].map(item => <FilterChip key={item.value} {...item} selected={filters.priority === item.value} onPress={() => updateFilter('priority', item.value)} />)}</View></View>
          <View style={{ gap: 3 }}><Text style={filterLabel}>SLA</Text><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>{[
            { label: 'All SLA', value: 'ALL', icon: Clock3, color: '#087B50', tint: '#E9F8EF' }, { label: 'Within SLA', value: 'WITHIN_SLA', icon: Check, color: '#047857', tint: '#E9FBF3' }, { label: 'Approaching Breach', value: 'APPROACHING_BREACH', icon: AlertCircle, color: '#92400E', tint: '#FFF7E2' }, { label: 'Breached', value: 'BREACHED', icon: AlertCircle, color: '#B91C1C', tint: '#FFF0F0' },
          ].map(item => <FilterChip key={item.value} {...item} selected={filters.sla === item.value} onPress={() => updateFilter('sla', item.value)} />)}</View></View>
        </View>
      </Card>
      {error ? <ErrorBanner message={error} /> : null}
      <View style={tabGrid}>
        {tabOrder.map(item => <Pressable key={item} onPress={() => changeTab(item)} style={[tabButton, tab === item && tabButtonActive]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}><View style={[tabDot, { backgroundColor: tabDotColors[item] }]} /><Text style={[tabCount, tab === item && tabCountActive]}>{tabCounts[item]}</Text></View>
          <Text numberOfLines={2} style={[tabText, tab === item && tabTextActive]}>{tabTitle[item]}</Text>
        </Pressable>)}
      </View>
      {tab === 'total' && selectableRows.length ? <Card style={{ gap: 9, padding: 12 }}><View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ color: colors.ink, fontSize: 12, fontWeight: '900' }}>{selectedJobIds.length} selected</Text><Pressable onPress={() => setSelectedJobIds(selectedJobIds.length === selectableRows.length ? [] : selectableRows.map(job => job.id ?? job.job_id))}><Text style={{ color: colors.forest, fontSize: 11, fontWeight: '900' }}>{selectedJobIds.length === selectableRows.length ? 'Clear selection' : 'Select all unassigned'}</Text></Pressable></View><View style={{ flexDirection: 'row', gap: 8 }}><View style={{ flex: 1 }}><PrimaryButton title="Bulk assign" compact disabled={!selectedJobIds.length} onPress={() => void openBulkAction('assign')} /></View><View style={{ flex: 1 }}><PrimaryButton title="Bulk cancel" compact variant="danger" disabled={!selectedJobIds.length} onPress={() => void openBulkAction('cancel')} /></View></View></Card> : null}
      <SectionTitle title={tabTitle[tab]} subtitle={`${displayRows.length} jobs`} />
      {loading ? <Text style={{ color: colors.muted, textAlign: 'center', padding: 24 }}>Loading planning data…</Text> : displayRows.length === 0 ? <EmptyState title={`No ${tabTitle[tab].toLowerCase()} found`} detail="There are no jobs to display for the selected filters." onRetry={() => load(true)} /> : displayRows.map((job: any) => {
        const id = job.id ?? job.job_id;
        const assignedTechValue = job.assigned_technician;
        const assignedTech = typeof assignedTechValue === 'string' ? assignedTechValue : assignedTechValue?.technician_name || assignedTechValue?.name || (typeof job.technician === 'string' ? job.technician : job.technician?.technician_name || job.technician?.name) || job.technician_name || null;
        const escalated = isEscalated(job);
        const cto = jobStatus(job) === 'ESCALATED_TO_CTO';
        const selectable = tab === 'total' && job.assigned_technician_id == null && !escalated && !['COMPLETED', 'CLOSED', 'CANCELLED', 'CANCELED', 'REJECTED_BY_TECHNICIAN'].includes(jobStatus(job));
        return <Card key={String(id)} style={{ gap: 3, padding: 8 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 5 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 }}><Text style={{ color: colors.forest, fontSize: 11, fontWeight: '900' }}>#{id}</Text><Text numberOfLines={1} style={{ color: colors.ink, fontSize: 11, fontWeight: '800', flex: 1 }}>{text(job.customer_name || job.customer)}</Text></View><Pill label={statusLabel(job.status || job.job_status)} tone={statusTone(job.status || job.job_status)} /></View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}><Text numberOfLines={1} style={{ color: colors.text, fontSize: 11, flex: 1 }}>{text(job.service_type, 'Service job')}</Text><Pill label={text(job.priority, 'Normal').toUpperCase()} tone={statusTone(job.priority)} /></View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}><MapPin size={12} color={colors.muted} /><Text numberOfLines={1} style={{ color: colors.muted, fontSize: 10, flex: 1 }}>{text(job.location)}</Text></View>
          {selectable ? <Pressable onPress={() => toggleJobSelection(id)} style={{ position: 'absolute', top: 43, right: 12, width: 22, height: 22, borderRadius: 6, borderWidth: 1, borderColor: selectedJobIds.some(value => String(value) === String(id)) ? colors.forest : colors.border, backgroundColor: selectedJobIds.some(value => String(value) === String(id)) ? colors.forest : colors.white, alignItems: 'center', justifyContent: 'center' }}>{selectedJobIds.some(value => String(value) === String(id)) ? <Text style={{ color: colors.white, fontSize: 12, fontWeight: '900' }}>✓</Text> : null}</Pressable> : null}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><View style={{ flex: 1, gap: 2 }}><Text style={{ color: colors.muted, fontSize: 9 }}>Technician</Text><Text numberOfLines={1} style={{ color: colors.forest, fontSize: 10, fontWeight: '800' }}>{text(assignedTech, 'Unassigned')}</Text></View><View style={{ flex: 1, alignItems: 'flex-end', gap: 2 }}><Text style={{ color: colors.muted, fontSize: 9 }}>SLA deadline</Text><Text numberOfLines={1} style={{ color: colors.text, fontSize: 10 }}>{dateTime(job.sla_deadline)}</Text></View></View>
          {tab === 'escalations' ? <View style={{ gap: 5 }}><View style={{ flexDirection: 'row', gap: 6 }}><View style={{ flex: 1 }}><PrimaryButton title="Extend SLA +30m" compact variant="secondary" loading={extendingSla} onPress={() => extendSla(job)} /></View><View style={{ flex: 1 }}><PrimaryButton title="Force assign" compact onPress={() => openAssignment(job)} /></View></View><PrimaryButton title="Cancel escalated job" compact variant="danger" onPress={() => { setCancelEscalationJob(job); setEscalationCancelReason(''); }} /></View> : tab === 'declined' ? <PrimaryButton title="Reassign job" compact onPress={() => void openDeclinedReassignment(job)} /> : selectable ? <PrimaryButton title="Assign technician" compact onPress={() => openAssignment(job)} /> : null}
          <Pressable onPress={() => void openJobDetails(job)} style={{ minHeight: 30, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, borderWidth: 1, borderColor: colors.border, borderRadius: 8 }}><Eye size={13} color={colors.forest} /><Text style={{ color: colors.forest, fontSize: 10, fontWeight: '800' }}>View job details</Text></Pressable>
        </Card>;
      })}
      <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10, lineHeight: 16 }}>Assignments, workload eligibility, SLA changes, tenant isolation, timers, audit events and notifications are validated and executed by the FieldOps backend.</Text></Card>
    </ScreenScroll>

    <Modal visible={!!selectedJob} animationType="slide" transparent onRequestClose={() => setSelectedJob(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, maxHeight: '92%', gap: 13 }}>
          <View style={{ gap: 4 }}><Text style={{ color: colors.ink, fontSize: 20, fontWeight: '900' }}>{isEscalated(selectedJob) ? 'Force-assign escalation' : 'Assign job'} #{selectedJob?.id ?? selectedJob?.job_id}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{text(selectedJob?.service_type)} · {text(selectedJob?.customer_name)}</Text></View>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Select technician</Text>
          <PrimaryButton title={rankingLoading ? 'Loading backend recommendations…' : 'Get backend ranked recommendations'} compact variant="secondary" loading={rankingLoading} onPress={() => void loadRankedTechnicians()} />
          {rankingError ? <ErrorBanner message={rankingError} /> : null}
          {rankedTechnicians.length ? <View style={{ gap: 8 }}><Text style={{ color: colors.forest, fontSize: 11, fontWeight: '900' }}>RECOMMENDED BY FIELDOPS BACKEND</Text>{rankedTechnicians.slice(0, 3).map((candidate: any) => <Card key={String(candidate.tech_id)} onPress={() => setSelectedTechId(candidate.tech_id)} style={{ padding: 12, gap: 5, borderColor: String(selectedTechId) === String(candidate.tech_id) ? colors.forest : colors.border }}><View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ color: colors.ink, fontSize: 12, fontWeight: '900', flex: 1 }}>#{candidate.rank} {candidate.name}</Text><Pill label={candidate.is_recommended ? 'Recommended' : `${Math.round(Number(candidate.composite_score) || 0)} score`} tone={candidate.is_recommended ? 'green' : 'blue'} /></View><Text style={{ color: colors.muted, fontSize: 10 }}>Distance {candidate.distance_km ?? '—'} km · Workload {candidate.active_jobs ?? 0}/{candidate.max_capacity ?? 3}</Text>{candidate.warnings?.length ? <Text style={{ color: colors.amber, fontSize: 10 }}>{candidate.warnings.join(' · ')}</Text> : null}</Card>)}</View> : null}
          <ScrollView style={{ maxHeight: 280 }} keyboardShouldPersistTaps="handled">
            {technicians.length === 0 ? <EmptyState title="No available technicians" detail="The backend did not return eligible technicians for this queue." /> : technicians.map((tech: any) => {
              const id = tech.technician_id ?? tech.id ?? tech.tech_id;
              const selected = String(selectedTechId) === String(id);
              const canChoose = tech.eligible_for_assignment !== false;
              return <Card key={String(id)} onPress={canChoose ? () => setSelectedTechId(id) : undefined} style={{ borderColor: selected ? colors.forest : colors.border, backgroundColor: selected ? '#F0F8F3' : colors.white, padding: 12, marginBottom: 8, gap: 6, opacity: canChoose ? 1 : 0.58 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ color: colors.ink, fontSize: 13, fontWeight: '900', flex: 1 }}>{technicianName(tech)}</Text><Pill label={statusLabel(tech.technician_status || tech.status)} tone={statusTone(tech.technician_status || tech.status)} /></View>
                <Text style={{ color: colors.muted, fontSize: 10 }}>{text(tech.technician_skill || tech.skill)} · Workload {tech.current_jobs ?? 0}/{tech.max_jobs ?? 5}</Text>
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
    <Modal visible={bulkMode !== null} animationType="slide" transparent onRequestClose={() => setBulkMode(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, maxHeight: '90%', gap: 12 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.ink, fontSize: 19, fontWeight: '900' }}>{bulkMode === 'assign' ? 'Bulk assign jobs' : 'Bulk cancel jobs'}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{selectedJobIds.length} pending jobs selected</Text></View><PrimaryButton title="Close" compact variant="secondary" onPress={() => setBulkMode(null)} /></View>
          {bulkMode === 'assign' ? <><Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Select technician</Text><ScrollView style={{ maxHeight: 350 }} keyboardShouldPersistTaps="handled">{bulkTechnicians.map((tech: any) => { const id = tech.technician_id ?? tech.id ?? tech.tech_id; const selected = String(bulkTechId) === String(id); return <Card key={String(id)} onPress={() => setBulkTechId(id)} style={{ padding: 12, marginBottom: 8, gap: 6, borderColor: selected ? colors.forest : colors.border }}><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 12 }}>{technicianName(tech)}</Text><Pill label={statusLabel(tech.technician_status || tech.status)} tone={statusTone(tech.technician_status || tech.status)} /></View><Text style={{ color: colors.muted, fontSize: 10 }}>{text(tech.technician_skill || tech.skill)} · Workload {tech.current_jobs ?? 0}/{tech.max_jobs ?? 5}</Text>{selected ? <Text style={{ color: colors.forest, fontSize: 10, fontWeight: '900' }}>SELECTED</Text> : null}</Card>; })}{bulkTechnicians.length === 0 ? <EmptyState title="No available technicians" detail="The backend returned no technicians for bulk assignment." /> : null}</ScrollView></> : <><Field label="CANCELLATION REASON" value={bulkReason} onChangeText={setBulkReason} placeholder="Explain why these jobs are being cancelled…" multiline numberOfLines={4} /><Text style={{ color: colors.amber, fontSize: 11, lineHeight: 16 }}>The backend will record this reason for every selected job.</Text></>}
          <PrimaryButton title={bulkLoading ? 'Submitting…' : bulkMode === 'assign' ? `Assign ${selectedJobIds.length} jobs` : `Cancel ${selectedJobIds.length} jobs`} variant={bulkMode === 'cancel' ? 'danger' : 'primary'} loading={bulkLoading} disabled={bulkMode === 'assign' ? bulkTechId === null : !bulkReason.trim()} onPress={() => void submitBulkAction()} />
          <PrimaryButton title="Go back" variant="secondary" onPress={() => setBulkMode(null)} />
        </View>
      </View>
    </Modal>
    <Modal visible={filterPicker !== null} animationType="slide" transparent onRequestClose={() => setFilterPicker(null)}>
      <View style={{ flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(7,25,16,.48)' }}>
        <View style={{ maxHeight: '72%', backgroundColor: colors.canvas, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 18, gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ color: colors.ink, fontSize: 17, fontWeight: '900' }}>{filterPicker === 'technician' ? 'Select technician' : 'Select service'}</Text><PrimaryButton title="Close" compact variant="secondary" onPress={() => setFilterPicker(null)} /></View>
          <ScrollView keyboardShouldPersistTaps="handled">
            <PickerRow label={filterPicker === 'technician' ? 'All Technicians' : 'All Services'} selected={(filterPicker === 'technician' ? filters.technician : filters.service) === 'ALL'} onPress={() => { updateFilter(filterPicker === 'technician' ? 'technician' : 'service', 'ALL'); setFilterPicker(null); }} />
            {filterPicker === 'technician' ? technicianOptions.map((tech: any) => { const value = String(tech.technician_id ?? tech.id ?? tech.tech_id); return <PickerRow key={value} label={technicianName(tech)} selected={filters.technician === value} onPress={() => { updateFilter('technician', value); setFilterPicker(null); }} />; }) : serviceOptions.map(service => <PickerRow key={service} label={service} selected={filters.service === service} onPress={() => { updateFilter('service', service); setFilterPicker(null); }} />)}
          </ScrollView>
        </View>
      </View>
    </Modal>
    <Modal visible={!!declinedJobForReassign} animationType="slide" transparent onRequestClose={() => setDeclinedJobForReassign(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, maxHeight: '82%', gap: 12 }}>
          <View style={{ gap: 4 }}><Text style={{ color: colors.ink, fontSize: 19, fontWeight: '900' }}>Reassign job #{declinedJobForReassign?.id ?? declinedJobForReassign?.job_id}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{text(declinedJobForReassign?.customer_name)} · {text(declinedJobForReassign?.service_type)}</Text></View>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Select an available technician</Text>
          <ScrollView style={{ maxHeight: 350 }} keyboardShouldPersistTaps="handled">{reassignTechnicians.map((tech: any) => { const id = tech.technician_id ?? tech.id ?? tech.tech_id; const selected = String(reassignTechId) === String(id); return <Card key={String(id)} onPress={() => setReassignTechId(id)} style={{ padding: 12, marginBottom: 8, gap: 6, borderColor: selected ? colors.forest : colors.border }}><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 12 }}>{technicianName(tech)}</Text><Pill label={statusLabel(tech.technician_status || tech.status)} tone={statusTone(tech.technician_status || tech.status)} /></View><Text style={{ color: colors.muted, fontSize: 10 }}>{text(tech.technician_skill || tech.skill)} · Workload {tech.current_jobs ?? 0}/{tech.max_jobs ?? 5}</Text>{selected ? <Text style={{ color: colors.forest, fontSize: 10, fontWeight: '900' }}>SELECTED</Text> : null}</Card>; })}{reassignTechnicians.length === 0 ? <EmptyState title="No available technicians" detail="The backend returned no eligible technicians for this reassignment." /> : null}</ScrollView>
          <PrimaryButton title="Confirm reassignment" loading={reassignLoading} disabled={reassignTechId === null} onPress={() => void submitDeclinedReassignment()} />
          <PrimaryButton title="Cancel" variant="secondary" onPress={() => setDeclinedJobForReassign(null)} />
        </View>
      </View>
    </Modal>
    <Modal visible={!!detailJob} animationType="slide" transparent onRequestClose={() => setDetailJob(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 16, maxHeight: '82%', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><View><Text style={{ color: colors.ink, fontSize: 17, fontWeight: '900' }}>Job Details</Text><Text style={{ color: colors.muted, fontSize: 10 }}>#{detailJob?.id ?? detailJob?.job_id}{detailLoading ? ' · Refreshing…' : ''}</Text></View><PrimaryButton title="Close" compact variant="secondary" onPress={() => setDetailJob(null)} /></View>
          <ScrollView><View style={{ gap: 9, paddingBottom: 6 }}>{[
            ['Customer', detailJob?.customer_name || detailJob?.customer], ['Service', detailJob?.service_type || detailJob?.required_skill], ['Technician', detailJob?.assigned_technician?.technician_name || detailJob?.technician_name || (typeof detailJob?.technician === 'string' ? detailJob.technician : null) || 'Unassigned'], ['Status', statusLabel(detailJob?.status || detailJob?.job_status)], ['Priority', detailJob?.priority], ['Location', detailJob?.location], ['Issue', detailJob?.issue_description], ['SLA deadline', dateTime(detailJob?.sla_deadline)], ['Created', dateTime(detailJob?.created_at)], ['Assigned', dateTime(detailJob?.assigned_at)], ['Rejection reason', detailJob?.rejection_reason],
          ].filter(([, value]) => value != null && value !== '').map(([label, value]) => <View key={String(label)} style={{ paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: colors.border }}><Text style={{ color: colors.muted, fontSize: 9, fontWeight: '800' }}>{label}</Text><Text style={{ color: colors.ink, fontSize: 12, marginTop: 2 }}>{String(value)}</Text></View>)}</View></ScrollView>
        </View>
      </View>
    </Modal>
    <Modal visible={!!cancelEscalationJob} animationType="slide" transparent onRequestClose={() => setCancelEscalationJob(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 18, gap: 12 }}>
          <Text style={{ color: colors.ink, fontSize: 18, fontWeight: '900' }}>Cancel escalated job #{cancelEscalationJob?.id ?? cancelEscalationJob?.job_id}</Text>
          <Field label="CANCELLATION REASON" value={escalationCancelReason} onChangeText={setEscalationCancelReason} placeholder="Explain why this escalated job must be cancelled…" multiline numberOfLines={4} />
          <PrimaryButton title="Confirm cancellation" variant="danger" loading={cancelEscalationLoading} disabled={!escalationCancelReason.trim()} onPress={() => void submitEscalationCancel()} />
          <PrimaryButton title="Keep job" variant="secondary" onPress={() => setCancelEscalationJob(null)} />
        </View>
      </View>
    </Modal>
    <Modal visible={!!slaExtensionJob} animationType="slide" transparent onRequestClose={() => setSlaExtensionJob(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 18, gap: 12 }}>
          <Text style={{ color: colors.ink, fontSize: 18, fontWeight: '900' }}>Extend SLA for job #{slaExtensionJob?.id ?? slaExtensionJob?.job_id}</Text>
          <Field label="EXTENSION TIME IN MINUTES" value={slaExtensionMinutes} onChangeText={setSlaExtensionMinutes} keyboardType="number-pad" placeholder="30" />
          <PrimaryButton title="Extend deadline" loading={extendingSla} disabled={!Number.parseInt(slaExtensionMinutes, 10) || Number.parseInt(slaExtensionMinutes, 10) <= 0} onPress={() => void submitSlaExtension()} />
          <PrimaryButton title="Cancel" variant="secondary" onPress={() => setSlaExtensionJob(null)} />
        </View>
      </View>
    </Modal>
  </>;
}

function FilterChip({ label, icon: Icon, selected, color, tint, onPress }: { label: string; icon: React.ComponentType<any>; selected: boolean; color: string; tint: string; onPress: () => void }) {
  return <Pressable onPress={onPress} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, minHeight: 29, paddingHorizontal: 7, borderWidth: 1, borderColor: selected ? color : `${color}30`, borderRadius: 16, backgroundColor: selected ? color : tint }}><Icon size={12} color={selected ? colors.white : color} /><Text numberOfLines={1} style={{ color: selected ? colors.white : color, fontSize: 9, fontWeight: '800' }}>{label}</Text></Pressable>;
}

function PickerRow({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return <Pressable onPress={onPress} style={{ minHeight: 46, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ color: selected ? colors.forest : colors.ink, fontSize: 13, fontWeight: selected ? '900' : '600' }}>{label}</Text>{selected ? <Text style={{ color: colors.forest, fontWeight: '900' }}>✓</Text> : null}</Pressable>;
}

const filterLabel = { color: '#405749', fontSize: 8, fontWeight: '800' as const, letterSpacing: 0.2 };
const selectField = { height: 31, borderWidth: 1, borderColor: '#DDE7E1', borderRadius: 7, backgroundColor: colors.white, paddingHorizontal: 7, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, gap: 3 };
const selectText = { color: colors.text, fontSize: 9, flex: 1 };
const selectChevron = { color: colors.muted, fontSize: 14, fontWeight: '800' as const };
const tabGrid = { flexDirection: 'row' as const, flexWrap: 'wrap' as const, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' as const };
const tabButton = { width: '25%' as const, minHeight: 46, paddingHorizontal: 3, paddingVertical: 3, flexDirection: 'column' as const, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 2, borderBottomWidth: 2, borderBottomColor: 'transparent' };
const tabButtonActive = { borderBottomColor: '#07965B' };
const tabDot = { width: 8, height: 8, borderRadius: 5 };
const tabDotColors: Record<Tab, string> = { total: '#0F766E', planned: '#10B981', enroute: '#3B82F6', inprogress: '#F59E0B', completed: '#2563EB', declined: '#DC2626', escalations: '#F59E0B' };
const tabText = { color: '#718096', fontSize: 8, fontWeight: '800' as const, textAlign: 'center' as const, lineHeight: 10, minHeight: 20 };
const tabTextActive = { color: colors.forest };
const tabCount = { paddingHorizontal: 5, paddingVertical: 2, borderRadius: 8, overflow: 'hidden' as const, color: '#526174', backgroundColor: '#F1F5F9', fontSize: 10, fontWeight: '900' as const };
const tabCountActive = { color: colors.forest, backgroundColor: '#E9F8EF' };
