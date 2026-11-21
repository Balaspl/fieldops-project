import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ImageBackground, Pressable, RefreshControl, ScrollView, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { Activity, AlertTriangle, BarChart3, BriefcaseBusiness, CalendarClock, CheckCircle2, ClipboardList, CreditCard } from 'lucide-react-native';
import { getDashboardData } from '../api/operations';
import { Card, MetricCard, ScreenScroll, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import type { AuthUser } from '../types';

type Period = 'today' | 'week' | 'month' | 'all' | 'custom';
const dayKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const isDateKey = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && (() => { const [year, month, day] = value.split('-').map(Number); return dayKey(new Date(year, month - 1, day)) === value; })();
const rangeFor = (period: Period) => {
  const today = new Date();
  if (period === 'today') return { start_date: dayKey(today), end_date: dayKey(today) };
  if (period === 'week') { const start = new Date(today); start.setDate(today.getDate() - today.getDay()); const end = new Date(start); end.setDate(start.getDate() + 6); return { start_date: dayKey(start), end_date: dayKey(end) }; }
  if (period === 'month') return { start_date: dayKey(new Date(today.getFullYear(), today.getMonth(), 1)), end_date: dayKey(new Date(today.getFullYear(), today.getMonth() + 1, 0)) };
  return null;
};
const money = (amount: unknown) => `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(Number(amount) || 0)}`;

export default function DashboardScreen({ user, onNavigate }: { user: AuthUser; onNavigate: (tab: string) => void }) {
  const { width: windowWidth } = useWindowDimensions();
  const [data, setData] = useState<any>({ stats: {}, jobs: [], technicians: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [period, setPeriod] = useState<Period>('week');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [customRange, setCustomRange] = useState<{ start_date: string; end_date: string } | null>(null);
  const [dateError, setDateError] = useState('');
  const dashboardRequest = useRef(0);

  const load = useCallback(async (silent = false) => {
    const requestId = ++dashboardRequest.current;
    if (period === 'custom' && !customRange) { setLoading(false); setRefreshing(false); return; }
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const dateRange = period === 'custom' ? customRange : rangeFor(period);
      const result = await getDashboardData(period === 'all' ? 'all' : period, dateRange);
      if (requestId !== dashboardRequest.current) return;
      setData(result);
      if (result.errors === 3) setError('Unable to load operations dashboard.');
      else if (result.errors) setError('Some dashboard information could not be refreshed.');
    } catch (e: any) { if (requestId === dashboardRequest.current) setError(e?.response?.data?.detail || e?.message || 'Unable to load operations dashboard.'); }
    finally { if (requestId === dashboardRequest.current) { setLoading(false); setRefreshing(false); } }
  }, [period, customRange]);

  useEffect(() => { void load(); const timer = setInterval(() => { void load(true); }, 45000); return () => clearInterval(timer); }, [load]);

  const stats = data.stats || {};
  const cards = stats.job_cards || {};
  const jobs = stats.jobs || {};
  const total = cards.total ?? jobs.total ?? 0;
  const metrics = [
    { label: 'Total Jobs', value: total, icon: <ClipboardList size={14} color={colors.forest} />, tone: 'green' as const, caption: 'Jobs in selected period', onPress: () => onNavigate('planning') },
    { label: 'Unassigned', value: cards.unassigned ?? jobs.pending ?? 0, icon: <CalendarClock size={14} color={colors.amber} />, tone: 'amber' as const, caption: 'Awaiting dispatch', onPress: () => onNavigate('planning') },
    { label: 'Accepted', value: cards.accepted ?? 0, icon: <CheckCircle2 size={14} color={colors.blue} />, tone: 'blue' as const, caption: 'Accepted by technician' },
    { label: 'Rejected', value: cards.rejected ?? 0, icon: <AlertTriangle size={14} color={colors.red} />, tone: 'red' as const, caption: 'Rejected by technician' },
    { label: 'En Route', value: cards.en_route ?? 0, icon: <Activity size={14} color={colors.purple} />, tone: 'purple' as const, caption: 'Technician travelling' },
    { label: 'In Progress', value: cards.in_progress ?? jobs.in_progress ?? jobs.active ?? 0, icon: <BriefcaseBusiness size={14} color={colors.amber} />, tone: 'amber' as const, caption: 'Work ongoing', onPress: () => onNavigate('planning') },
    { label: 'Completed', value: cards.completed ?? jobs.completed ?? 0, icon: <CheckCircle2 size={14} color={colors.forest} />, tone: 'green' as const, caption: 'Completed jobs' },
    { label: 'Payments', value: money((stats.payment_summary || {}).total_recorded), icon: <CreditCard size={14} color="#0D9488" />, tone: 'green' as const, caption: `Cash ${money((stats.payment_summary || {}).cash_total)} · UPI ${money((stats.payment_summary || {}).upi_total)}` },
  ];
  const categories = stats.categories || stats.service_technicians || {};
  const categoryRows = Object.entries(categories).filter(([, value]) => Number(value) > 0).sort((a, b) => Number(b[1]) - Number(a[1]));
  const activeRange = period === 'custom' ? customRange : rangeFor(period);
  const performance = useMemo(() => {
    const list = data.jobs || [];
    const keyOf = (value?: string | null) => {
      if (!value) return '';
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime()) ? String(value).slice(0, 10) : dayKey(parsed);
    };
    const today = new Date();
    const createdDays = list.map((job: any) => keyOf(job.created_at)).filter(Boolean).sort();
    const start = activeRange ? new Date(`${activeRange.start_date}T00:00:00`) : createdDays.length ? new Date(`${createdDays[0]}T00:00:00`) : new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const end = activeRange ? new Date(`${activeRange.end_date}T00:00:00`) : new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const selectedDays = activeRange ? Math.floor((end.getTime() - start.getTime()) / 86400000) + 1 : 0;
    const grouping = period === 'today' ? 'hourly' : activeRange ? selectedDays > 31 ? 'monthly' : 'daily' : 'monthly';
    const completionValue = (job: any) => {
      if (job.completed_at || job.closed_at) return job.completed_at || job.closed_at;
      if (!['COMPLETED', 'CLOSED'].includes(String(job.status || '').toUpperCase())) return '';
      const updated = keyOf(job.updated_at);
      const updatedInRange = activeRange ? updated >= activeRange.start_date && updated <= activeRange.end_date : Boolean(updated);
      return updatedInRange ? job.updated_at : job.created_at || job.updated_at;
    };
    const completionDay = (job: any) => keyOf(completionValue(job));
    const count = (from: Date, until: Date, completed: boolean) => list.filter((job: any) => {
      const key = completed ? completionDay(job) : keyOf(job.created_at);
      if (!key || key < dayKey(from) || key >= dayKey(until)) return false;
      return !activeRange || key >= activeRange.start_date && key <= activeRange.end_date;
    }).length;
    const buckets: { label: string; created: number; completed: number }[] = [];
    if (grouping === 'hourly') {
      const slots = [{ start: 8, end: 10, label: '8–10 AM' }, { start: 10, end: 12, label: '10 AM–12 PM' }, { start: 12, end: 14, label: '12–2 PM' }, { start: 14, end: 16, label: '2–4 PM' }, { start: 16, end: 18, label: '4–6 PM' }, { start: 18, end: 20, label: '6–8 PM' }];
      for (const slot of slots) {
        const inSlot = (value?: string | null) => { if (!value) return false; const date = new Date(value); return !Number.isNaN(date.getTime()) && dayKey(date) === dayKey(start) && date.getHours() >= slot.start && date.getHours() < slot.end; };
        buckets.push({ label: slot.label, created: list.filter((job: any) => inSlot(job.created_at)).length, completed: list.filter((job: any) => inSlot(completionValue(job))).length });
      }
    } else if (grouping === 'daily') {
      const cursor = new Date(start);
      while (cursor <= end) {
        const next = new Date(cursor); next.setDate(next.getDate() + 1);
        buckets.push({ label: cursor.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), created: count(cursor, next, false), completed: count(cursor, next, true) });
        cursor.setDate(cursor.getDate() + 1);
      }
    } else {
      const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
      while (cursor <= end) {
        const next = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
        buckets.push({ label: cursor.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }), created: count(cursor, next, false), completed: count(cursor, next, true) });
        cursor.setMonth(cursor.getMonth() + 1);
      }
    }
    return { buckets, grouping, label: grouping === 'hourly' ? 'Two-Hour View' : grouping === 'daily' ? 'Daily View' : 'Monthly View', max: Math.max(1, ...buckets.flatMap(bucket => [bucket.created, bucket.completed])) };
  }, [data.jobs, period, activeRange?.start_date, activeRange?.end_date]);
  const scopedJobs = useMemo(() => (data.jobs || []).filter((job: any) => {
    if (!activeRange) return true;
    const raw = job.created_at || job.preferred_service_date;
    if (!raw) return false;
    const parsed = new Date(raw);
    const key = Number.isNaN(parsed.getTime()) ? String(raw).slice(0, 10) : dayKey(parsed);
    return key >= activeRange.start_date && key <= activeRange.end_date;
  }), [data.jobs, activeRange?.start_date, activeRange?.end_date]);
  const activeWithSla = scopedJobs.filter((job: any) => {
    const status = String(job.status || '').toUpperCase().replace(/[^A-Z]/g, '');
    const terminal = ['COMPLETED', 'CLOSED', 'CANCELLED', 'CANCELED', 'REJECTEDBYTECHNICIAN'].includes(status);
    return !terminal && Boolean(job.sla_deadline) && Number.isFinite(new Date(job.sla_deadline).getTime());
  });
  const withinSla = activeWithSla.filter((job: any) => new Date(job.sla_deadline).getTime() >= Date.now()).length;
  const atRiskSla = activeWithSla.filter((job: any) => { const left = new Date(job.sla_deadline).getTime() - Date.now(); return left >= 0 && left <= 60 * 60 * 1000; }).length;
  const slaRate = activeWithSla.length ? Math.round(withinSla / activeWithSla.length * 100) : null;
  const topTechnicians = (data.technicians || []).map((technician: any) => {
    const related = scopedJobs.filter((job: any) => Number(job.assigned_technician_id) === Number(technician.technician_id ?? technician.id));
    const done = related.filter((job: any) => ['COMPLETED', 'CLOSED'].includes(String(job.status || '').toUpperCase())).length;
    return { name: technician.technician_name || technician.name || 'Technician', total: related.length, done, rate: related.length ? Math.round(done / related.length * 100) : 0 };
  }).filter((technician: any) => technician.total > 0).sort((a: any, b: any) => b.done - a.done || b.total - a.total).slice(0, 4);
  const periodOptions: { id: Period; label: string }[] = [{ id: 'today', label: 'Today' }, { id: 'week', label: 'This week' }, { id: 'month', label: 'This month' }, { id: 'all', label: 'All time' }, { id: 'custom', label: 'Custom' }];
  const applyMonthPreset = (months: number) => {
    const end = new Date();
    end.setHours(0, 0, 0, 0);
    const start = new Date(end);
    const originalDay = start.getDate();
    start.setDate(1);
    start.setMonth(start.getMonth() - months);
    start.setDate(Math.min(originalDay, new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate()));
    const range = { start_date: dayKey(start), end_date: dayKey(end) };
    setStartDate(range.start_date);
    setEndDate(range.end_date);
    setDateError('');
    setCustomRange(range);
    setPeriod('custom');
  };
  const applyCustomRange = () => {
    if (!isDateKey(startDate) || !isDateKey(endDate) || startDate > endDate) {
      setDateError('Choose a valid start and end date.');
      return;
    }
    const start = new Date(`${startDate}T00:00:00`);
    const end = new Date(`${endDate}T00:00:00`);
    const maximum = new Date(start);
    maximum.setFullYear(maximum.getFullYear() + 1);
    if (end > maximum) {
      setDateError('Custom date ranges can be up to 12 months.');
      return;
    }
    setDateError('');
    setCustomRange({ start_date: startDate, end_date: endDate });
  };

  return <ScreenScroll contentContainerStyle={{ paddingHorizontal: 14, paddingTop: 14, paddingBottom: 34, gap: 16 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
    <ImageBackground source={require('../../../assets/banners/dashboard-banner.jpeg')} resizeMode="cover" style={{ minHeight: 184, borderRadius: 24, overflow: 'hidden', justifyContent: 'flex-end', padding: 22 }}>
      <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(3, 54, 31, 0.72)' }} />
      <Text style={{ color: '#D4F2DE', fontSize: 11, fontWeight: '900', letterSpacing: 1.5 }}>FIELDOPS COMMANDER</Text>
      <Text style={{ color: '#fff', fontSize: 28, lineHeight: 34, fontWeight: '900', marginTop: 8 }}>Good day, {user.first_name || 'Team'}.</Text>
      <Text style={{ color: '#E8F5ED', fontSize: 14, marginTop: 5 }}>{user.organization_name || 'Operations Control'} · Live operations overview</Text>
      <View style={{ alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 15, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 20, backgroundColor: 'rgba(15, 115, 73, 0.58)', borderWidth: 1, borderColor: 'rgba(185, 244, 209, 0.5)' }}><View style={{ width: 8, height: 8, borderRadius: 8, backgroundColor: '#66E29C' }} /><Text style={{ color: '#E8F5ED', fontSize: 10, fontWeight: '800' }}>CONNECTED TO YOUR OPERATIONS WORKSPACE</Text></View>
    </ImageBackground>

    {error ? <Card><Text style={{ color: colors.red, fontSize: 12 }}>{error}</Text></Card> : null}
    <Card style={{ gap: 13, padding: 18, borderRadius: 24 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <View style={{ width: 42, height: 42, borderRadius: 14, backgroundColor: '#DDF5E7', alignItems: 'center', justifyContent: 'center' }}><CalendarClock size={23} color={colors.forest} /></View>
        <Text style={{ color: colors.ink, fontWeight: '900', fontSize: 18 }}>Dashboard date range</Text>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'nowrap', gap: 6 }}>{periodOptions.map(option => <Pressable key={option.id} onPress={() => setPeriod(option.id)} style={{ flex: 1, minWidth: 0, alignItems: 'center', paddingHorizontal: 4, paddingVertical: 10, borderRadius: 14, backgroundColor: period === option.id ? colors.forest : '#F1F5F2' }}><Text numberOfLines={1} adjustsFontSizeToFit style={{ color: period === option.id ? '#fff' : colors.ink, fontWeight: '800', fontSize: 11 }}>{option.label}</Text></Pressable>)}</View>
      {period === 'custom' ? <View style={{ gap: 9 }}>
        <Text style={{ color: colors.muted, fontSize: 10, fontWeight: '800' }}>Quick date ranges</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>{[{ label: '12 months', months: 12 }, { label: '9 months', months: 9 }, { label: '6 months', months: 6 }, { label: '3 months', months: 3 }].map(preset => <Pressable key={preset.months} onPress={() => applyMonthPreset(preset.months)} style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 9, backgroundColor: '#EAF4EE' }}><Text style={{ color: colors.forest, fontWeight: '800', fontSize: 10 }}>{preset.label}</Text></Pressable>)}</View>
        <View style={{ flexDirection: 'row', gap: 8 }}><TextInput value={startDate} onChangeText={value => { setStartDate(value); setDateError(''); }} placeholder="Start YYYY-MM-DD" style={dateInput} placeholderTextColor={colors.muted} /><TextInput value={endDate} onChangeText={value => { setEndDate(value); setDateError(''); }} placeholder="End YYYY-MM-DD" style={dateInput} placeholderTextColor={colors.muted} /></View>
        {dateError ? <Text style={{ color: colors.red, fontSize: 10 }}>{dateError}</Text> : null}
        <Pressable onPress={applyCustomRange} style={{ alignSelf: 'flex-end', paddingHorizontal: 14, paddingVertical: 9, backgroundColor: colors.forest, borderRadius: 10 }}><Text style={{ color: colors.white, fontWeight: '900', fontSize: 11 }}>Apply range</Text></Pressable>
      </View> : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><CalendarClock size={16} color={colors.muted} /><Text style={{ color: period === 'custom' && !customRange ? colors.amber : colors.muted, fontSize: 12 }}>{period === 'all' ? 'Showing all available history' : period === 'custom' ? customRange ? `${customRange.start_date} to ${customRange.end_date}` : 'Enter a valid date range and apply it' : (() => { const range = rangeFor(period); return `${range?.start_date} to ${range?.end_date}`; })()}</Text></View>
    </Card>

    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 11 }}>
      <BarChart3 size={29} color={colors.forest} strokeWidth={2.8} />
      <View style={{ gap: 3 }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 23 }}>Job status</Text><Text style={{ color: colors.muted, fontSize: 12 }}>Status counts from the selected range</Text></View>
    </View>
    {loading ? <View style={{ padding: 20 }}><Text style={{ textAlign: 'center', color: colors.muted }}>Loading operations metrics…</Text></View> : <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 6 }}>{metrics.map(item => <View key={item.label} style={{ width: '23.5%' }}><MetricCard {...item} compact backgroundColor="#FFFFFF" onPress={item.onPress} /></View>)}</View>}

    <Card style={{ padding: 0, overflow: 'hidden' }}>
      <View style={{ paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#EAF1ED', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9, flex: 1 }}>
          <View style={{ width: 34, height: 34, borderRadius: 11, backgroundColor: '#D8F7E8', alignItems: 'center', justifyContent: 'center' }}><Activity size={19} color="#059669" /></View>
          <View style={{ flex: 1 }}><Text style={{ color: '#142238', fontSize: 15, fontWeight: '900' }}>Job Performance</Text><Text numberOfLines={2} style={{ color: '#718096', fontSize: 10, marginTop: 2 }}>Created jobs and their current completion status</Text></View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 9, paddingVertical: 8, borderRadius: 10, backgroundColor: '#F0FBF5', borderWidth: 1, borderColor: '#CDEBDD' }}><Text style={{ color: '#087B50', fontSize: 9, fontWeight: '900' }}>{performance.label}</Text><Text style={{ color: '#799487', fontSize: 8 }}>Auto</Text></View>
      </View>
      <View style={{ padding: 15, gap: 11 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 17, flexWrap: 'wrap' }}>
          <Legend color="#119B65" label="Jobs Created" /><Legend color="#9AE6C3" label="Jobs Completed" />
        </View>
        <View style={{ height: 238, borderWidth: 1, borderColor: '#E4EFE8', borderRadius: 15, backgroundColor: '#F8FCF9', overflow: 'hidden', paddingHorizontal: 10, paddingTop: 14, paddingBottom: 32 }}>
          {[0, 1, 2, 3, 4].map(line => <View key={line} style={{ position: 'absolute', top: 14 + line * 46, left: 10, right: 10, borderTopWidth: 1, borderStyle: line === 4 ? 'solid' : 'dashed', borderColor: line === 4 ? '#D5E4DA' : '#E4EDE7' }} />)}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ width: Math.max(windowWidth - 84, performance.buckets.length * (performance.grouping === 'daily' ? 38 : 32)), height: '100%' }}>
            {performance.buckets.map((bucket, index) => {
              const chartHeight = 160;
              const createdHeight = bucket.created ? Math.max(4, bucket.created / performance.max * chartHeight * 0.82) : 0;
              const completedHeight = bucket.completed ? Math.max(4, bucket.completed / performance.max * chartHeight * 0.82) : 0;
              return <View key={`${bucket.label}-${index}`} style={{ flex: 1, minWidth: performance.grouping === 'daily' ? 38 : 32, height: '100%', justifyContent: 'flex-end', alignItems: 'center' }}>
                <View style={{ height: chartHeight, flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'center', gap: 3, width: '100%' }}>
                  <View style={{ height: '100%', width: 12, justifyContent: 'flex-end', alignItems: 'center' }}>{bucket.created > 0 ? <Text style={{ position: 'absolute', bottom: createdHeight + 4, color: '#087C50', fontSize: 9, fontWeight: '900' }}>{bucket.created}</Text> : null}<View style={{ height: createdHeight, width: '85%', borderTopLeftRadius: 6, borderTopRightRadius: 6, backgroundColor: '#12A66C' }} /></View>
                  <View style={{ height: '100%', width: 12, justifyContent: 'flex-end', alignItems: 'center' }}>{bucket.completed > 0 ? <Text style={{ position: 'absolute', bottom: completedHeight + 4, color: '#50A77E', fontSize: 9, fontWeight: '900' }}>{bucket.completed}</Text> : null}<View style={{ height: completedHeight, width: '85%', borderTopLeftRadius: 6, borderTopRightRadius: 6, backgroundColor: '#9AE6C3' }} /></View>
                </View>
                <Text numberOfLines={1} style={{ height: 22, paddingTop: 5, color: '#526174', fontSize: 8, fontWeight: '700', textAlign: 'center' }}>{bucket.label}</Text>
              </View>;
            })}
          </ScrollView>
        </View>
        <Text style={{ color: '#718096', fontSize: 9, lineHeight: 13 }}>Created bars use creation dates; completed bars use completion/close dates, with legacy date fallbacks when missing.</Text>
        <View style={{ alignSelf: 'flex-start', paddingHorizontal: 11, paddingVertical: 7, borderRadius: 15, backgroundColor: '#EAF8F0', borderWidth: 1, borderColor: '#CDEBDD' }}><Text style={{ color: '#087B50', fontSize: 9, fontWeight: '800' }}>Live dashboard data</Text></View>
      </View>
    </Card>

    <Card style={{ gap: 12 }}>
      <SectionTitle title="Service category breakdown" subtitle="Jobs grouped by service category" />
      {categoryRows.length ? categoryRows.slice(0, 8).map(([label, value]) => { const max = Math.max(...categoryRows.map(([, count]) => Number(count))); return <View key={label} style={{ gap: 6 }}><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.ink, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{label}</Text><Text style={{ color: colors.muted, fontSize: 11, fontWeight: '800' }}>{Number(value)}</Text></View><View style={{ height: 7, borderRadius: 5, backgroundColor: '#EDF1EE', overflow: 'hidden' }}><View style={{ width: `${Math.max(3, Number(value) / max * 100)}%`, height: '100%', backgroundColor: colors.forest, borderRadius: 5 }} /></View></View>; }) : <Text style={{ color: colors.muted, fontSize: 12 }}>No category data available for this period.</Text>}
    </Card>

    <Card style={{ gap: 12 }}>
      <SectionTitle title="SLA & response health" subtitle="Active jobs with an SLA deadline" />
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
        <View style={{ width: 92, height: 92, borderRadius: 50, borderWidth: 8, borderColor: slaRate === null ? '#E8EEEA' : '#37B879', alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 20 }}>{slaRate === null ? '—' : `${slaRate}%`}</Text><Text style={{ color: colors.muted, fontSize: 8 }}>IN SLA</Text></View>
        <View style={{ flex: 1, gap: 9 }}><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 11 }}>Tracked active jobs</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 11 }}>{activeWithSla.length}</Text></View><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 11 }}>Within SLA</Text><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 11 }}>{withinSla}</Text></View><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 11 }}>At risk within 1 hour</Text><Text style={{ color: colors.amber, fontWeight: '900', fontSize: 11 }}>{atRiskSla}</Text></View><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 11 }}>Overdue</Text><Text style={{ color: colors.red, fontWeight: '900', fontSize: 11 }}>{Math.max(0, activeWithSla.length - withinSla)}</Text></View></View>
      </View>
      <Text style={{ color: colors.muted, fontSize: 10 }}>Average assignment time: {(() => { const durations = scopedJobs.filter((job: any) => job.created_at && job.assigned_at).map((job: any) => (new Date(job.assigned_at).getTime() - new Date(job.created_at).getTime()) / 60000).filter((minutes: number) => Number.isFinite(minutes) && minutes >= 0); return durations.length ? `${Math.round(durations.reduce((sum: number, value: number) => sum + value, 0) / durations.length)} min` : '—'; })()}</Text>
    </Card>

    <Card style={{ gap: 11 }}>
      <SectionTitle title="Technician performance" subtitle="Top technicians by completed jobs in this period" action="View team" onAction={() => onNavigate('team')} />
      {topTechnicians.length ? topTechnicians.map((technician: any) => <View key={technician.name} style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}><View style={{ flex: 1, gap: 5 }}><View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text numberOfLines={1} style={{ color: colors.ink, fontSize: 11, fontWeight: '800', flex: 1 }}>{technician.name}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{technician.done}/{technician.total} · {technician.rate}%</Text></View><View style={{ height: 6, borderRadius: 4, backgroundColor: '#EDF1EE', overflow: 'hidden' }}><View style={{ height: '100%', width: `${technician.rate}%`, backgroundColor: colors.forest, borderRadius: 4 }} /></View></View></View>) : <Text style={{ color: colors.muted, fontSize: 11 }}>No technician job history for this period.</Text>}
    </Card>

    <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10 }}>Dashboard figures come from tenant scoped backend statistics. Pull down to refresh.</Text></Card>
  </ScreenScroll>;
}

function Legend({ color, label }: { color: string; label: string }) {
  return <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><View style={{ width: 9, height: 9, borderRadius: 3, backgroundColor: color }} /><Text style={{ color: '#526174', fontSize: 10, fontWeight: '700' }}>{label}</Text></View>;
}

const dateInput = { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 11, color: colors.ink, backgroundColor: '#FBFDFC' } as const;
