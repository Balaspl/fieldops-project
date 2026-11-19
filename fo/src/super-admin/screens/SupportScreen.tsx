import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Modal, RefreshControl, Text, View } from 'react-native';
import { api } from '../api/client';
import { getSupportRequests, updateSupportRequest } from '../api/operations';
import { Card, EmptyState, ErrorBanner, Field, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { dateTime, statusLabel, statusTone, text } from '../utils/format';

const FILTERS = ['ALL', 'OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'] as const;
type Filter = typeof FILTERS[number];
const STATUSES = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'] as const;

export default function SupportScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('ALL');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [nextStatus, setNextStatus] = useState<string>('IN_PROGRESS');
  const [resolutionNote, setResolutionNote] = useState('');
  const [assignToMe, setAssignToMe] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try { setRows(await getSupportRequests('ALL')); }
    catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Unable to load customer support requests.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter(row => (filter === 'ALL' || row.status === filter) && (!term || [row.request_number, row.subject, row.description, row.customer?.name, row.customer?.email, row.job?.id].some(value => String(value || '').toLowerCase().includes(term))));
  }, [rows, search, filter]);

  const open = async (row: any) => {
    setSelected(row); setNextStatus(row.status === 'OPEN' ? 'IN_PROGRESS' : row.status || 'IN_PROGRESS'); setResolutionNote(row.resolution_note || ''); setAssignToMe(false); setDetailLoading(true);
    try { const response = await api.get(`/api/admin/customer-support/${row.id}`); setSelected(response.data); }
    catch (e: any) { Alert.alert('Details unavailable', e?.response?.data?.detail || e?.message || 'Could not load request details.'); }
    finally { setDetailLoading(false); }
  };

  const update = async () => {
    if (!selected) return;
    if (['RESOLVED', 'CLOSED'].includes(nextStatus) && resolutionNote.trim().length === 0) { Alert.alert('Resolution note required', 'The backend requires a resolution note before resolving or closing a support case.'); return; }
    setSaving(true);
    try {
      const updated = await updateSupportRequest(Number(selected.id), { status: nextStatus, resolution_note: resolutionNote.trim() || undefined, assign_to_me: assignToMe });
      setSelected(updated); setAssignToMe(false); await load(true); Alert.alert('Support case updated', `Request ${text(updated.request_number)} is now ${statusLabel(updated.status)}.`);
    } catch (e: any) { Alert.alert('Update failed', e?.response?.data?.detail || e?.message || 'Could not update the support case.'); }
    finally { setSaving(false); }
  };

  const counts = useMemo(() => ({ open: rows.filter(r => r.status === 'OPEN').length, progress: rows.filter(r => r.status === 'IN_PROGRESS').length, resolved: rows.filter(r => ['RESOLVED', 'CLOSED'].includes(r.status)).length }), [rows]);

  return <>
    <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
      <ScreenHeading title="Customer Support" subtitle="Tenant-scoped customer cases, linked job context, sentiment triage and resolution." action={<Pill label="Staff workspace" tone="green" />} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Card style={{ flex: 1, padding: 12, gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Open</Text><Text style={{ color: colors.amber, fontSize: 22, fontWeight: '900' }}>{counts.open}</Text></Card>
        <Card style={{ flex: 1, padding: 12, gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>In progress</Text><Text style={{ color: colors.blue, fontSize: 22, fontWeight: '900' }}>{counts.progress}</Text></Card>
        <Card style={{ flex: 1, padding: 12, gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Resolved</Text><Text style={{ color: colors.forest, fontSize: 22, fontWeight: '900' }}>{counts.resolved}</Text></Card>
      </View>
      <SearchField value={search} onChangeText={setSearch} placeholder="Search case, customer, email or job…" />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{FILTERS.map(value => <PrimaryButton key={value} title={value === 'ALL' ? 'All' : statusLabel(value)} compact variant={filter === value ? 'primary' : 'secondary'} onPress={() => setFilter(value)} />)}</View>
      {error ? <ErrorBanner message={error} /> : null}
      <SectionTitle title="Support requests" subtitle="Newest requests are shown first" />
      {loading ? <Text style={{ textAlign: 'center', padding: 24, color: colors.muted }}>Loading support requests…</Text> : visible.length === 0 ? <EmptyState title="No support requests" detail="There are no cases for the selected status or search." onRetry={() => load(true)} /> : visible.map(row => <Card key={String(row.id)} onPress={() => void open(row)} style={{ gap: 9 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 11, flex: 1 }}>{text(row.request_number, `CASE-${row.id}`)}</Text><Pill label={statusLabel(row.status)} tone={statusTone(row.status)} /></View>
        <Text style={{ color: colors.ink, fontSize: 14, fontWeight: '900' }}>{text(row.subject)}</Text>
        <Text style={{ color: colors.text, fontSize: 11, lineHeight: 17 }} numberOfLines={2}>{text(row.description)}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}><Pill label={statusLabel(row.category)} tone="neutral" /><Pill label={`${statusLabel(row.priority)} priority`} tone={statusTone(row.priority)} /></View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.muted, fontSize: 9 }}>CUSTOMER</Text><Text style={{ color: colors.ink, fontSize: 11, fontWeight: '800' }}>{text(row.customer?.name, 'Customer')}</Text></View><View style={{ flex: 1, alignItems: 'flex-end', gap: 3 }}><Text style={{ color: colors.muted, fontSize: 9 }}>CREATED</Text><Text style={{ color: colors.text, fontSize: 10 }}>{dateTime(row.created_at)}</Text></View></View>
        {row.related_job_id ? <Text style={{ color: colors.blue, fontSize: 10, fontWeight: '800' }}>Linked job #{row.related_job_id}</Text> : null}
      </Card>)}
      <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10, lineHeight: 16 }}>Updates use the existing support API and its Customers Manage permission. The backend controls tenant visibility, status validation, case audit records and customer notifications.</Text></Card>
    </ScreenScroll>

    <Modal visible={!!selected} transparent animationType="slide" onRequestClose={() => setSelected(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'flex-end' }}><View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '94%', gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.ink, fontSize: 20, fontWeight: '900' }}>Case {text(selected?.request_number)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Customer support case detail</Text></View><PrimaryButton title="Close" compact variant="secondary" onPress={() => setSelected(null)} /></View>
        {detailLoading ? <Text style={{ textAlign: 'center', padding: 24, color: colors.muted }}>Loading complete case context…</Text> : <ScreenScroll contentContainerStyle={{ padding: 0, paddingBottom: 22 }}>
          <Card style={{ gap: 7 }}><Text style={{ color: colors.ink, fontSize: 15, fontWeight: '900' }}>{text(selected?.subject)}</Text><Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }}>{text(selected?.description)}</Text><Pill label={statusLabel(selected?.status)} tone={statusTone(selected?.status)} /><Text style={{ color: colors.muted, fontSize: 10 }}>{text(selected?.customer?.name)} · {text(selected?.customer?.email)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Phone: {text(selected?.customer?.phone_number)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Assigned staff: {text(selected?.assigned_staff_name, 'Unassigned')}</Text></Card>
          {selected?.job ? <Card style={{ gap: 5 }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 13 }}>Linked job #{selected.job.id}</Text><Text style={{ color: colors.text, fontSize: 11 }}>{text(selected.job.service_type)} · {text(selected.job.status)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{text(selected.job.location || selected.job.site_address)}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Technician: {text(selected.job.assigned_technician_name)}</Text></Card> : null}
          {selected?.sentiment_triage ? <Card style={{ gap: 7, borderColor: selected.sentiment_triage.requires_human ? '#FECACA' : colors.border }}><View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 13 }}>Sentiment triage</Text><Pill label={text(selected.sentiment_triage.urgency, 'Analyzed')} tone={selected.sentiment_triage.requires_human ? 'red' : 'blue'} /></View><Text style={{ color: colors.text, fontSize: 11, lineHeight: 17 }}>{text(selected.sentiment_triage.summary || selected.sentiment_triage.reason || selected.sentiment_triage.sentiment)}</Text>{selected.sentiment_triage.requires_human ? <Pill label="Human review requested" tone="red" /> : null}</Card> : null}
          <SectionTitle title="Case activity" subtitle="Backend-recorded customer and staff updates" />
          {(selected?.updates || []).length === 0 ? <Text style={{ color: colors.muted, fontSize: 11 }}>No case updates recorded yet.</Text> : selected.updates.map((entry: any, index: number) => <Card key={String(entry.id || index)} style={{ padding: 12, gap: 4 }}><Text style={{ color: colors.ink, fontWeight: '800', fontSize: 11 }}>{text(entry.title || entry.status || entry.actor_name)}</Text><Text style={{ color: colors.text, fontSize: 10, lineHeight: 15 }}>{text(entry.message || entry.note || entry.description)}</Text><Text style={{ color: colors.muted, fontSize: 9 }}>{dateTime(entry.created_at)}</Text></Card>)}
          {(selected?.chat_transcript || []).length > 0 ? <><SectionTitle title="Linked conversation" />{selected.chat_transcript.slice(-12).map((entry: any, index: number) => <Card key={String(entry.id || index)} style={{ padding: 11, gap: 4 }}><Text style={{ color: colors.forest, fontWeight: '800', fontSize: 10 }}>{text(entry.sender_name || entry.sender_role)}</Text><Text style={{ color: colors.text, fontSize: 11 }}>{text(entry.message || entry.body)}</Text><Text style={{ color: colors.muted, fontSize: 9 }}>{dateTime(entry.created_at)}</Text></Card>)}</> : null}
          <SectionTitle title="Update request" subtitle="The backend requires a resolution note to resolve or close" />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{STATUSES.map(value => <PrimaryButton key={value} title={statusLabel(value)} compact variant={nextStatus === value ? 'primary' : 'secondary'} onPress={() => setNextStatus(value)} />)}</View>
          {['RESOLVED', 'CLOSED'].includes(nextStatus) ? <Field label="RESOLUTION NOTE (REQUIRED)" value={resolutionNote} onChangeText={setResolutionNote} placeholder="Describe how the issue was resolved…" multiline numberOfLines={3} /> : <Field label="INTERNAL / CUSTOMER NOTE (OPTIONAL)" value={resolutionNote} onChangeText={setResolutionNote} placeholder="Add a resolution or handover note…" multiline numberOfLines={3} />}
          <PrimaryButton title={assignToMe ? 'Will assign to me · tap to cancel' : 'Assign this case to me'} variant="secondary" compact onPress={() => setAssignToMe(v => !v)} />
          <PrimaryButton title="Save support update" onPress={update} loading={saving} />
        </ScreenScroll>}
      </View></View>
    </Modal>
  </>;
}
