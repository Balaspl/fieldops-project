import React, { useCallback, useEffect, useState } from 'react';
import { ImageBackground, RefreshControl, Text, View } from 'react-native';
import { Activity, AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, Users, Wrench } from 'lucide-react-native';
import { api } from '../api/client';
import { getDashboardData } from '../api/operations';
import { Card, EmptyState, MetricCard, Pill, ScreenScroll, ScreenHeading, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { statusLabel, statusTone, text, dateTime } from '../utils/format';
import type { AuthUser } from '../types';

export default function DashboardScreen({ user, onNavigate }: { user: AuthUser; onNavigate: (tab: string) => void }) {
  const [data, setData] = useState<any>({ stats: {}, kpi: {}, jobs: [], technicians: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try { setData(await getDashboardData()); }
    catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Unable to load operations dashboard.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => { void load(true); }, 45000);
    return () => clearInterval(timer);
  }, [load]);

  const stats = data.stats || {};
  const cards = stats.job_cards || {};
  const jobs = stats.jobs || {};
  const tech = stats.technicians || data.kpi.technicians || {};
  const total = cards.total ?? jobs.total ?? ((Number(data.kpi.jobs_dispatched) || 0) + (Number(data.kpi.jobs_pending) || 0));
  const metrics = [
    { label: 'Total Jobs', value: total, icon: <ClipboardList size={18} color={colors.forest} />, tone: 'green' as const, caption: 'All visible jobs' },
    { label: 'Unassigned', value: cards.unassigned ?? jobs.pending ?? data.kpi.jobs_pending ?? 0, icon: <CalendarClock size={18} color={colors.amber} />, tone: 'amber' as const, caption: 'Awaiting dispatch' },
    { label: 'Active Jobs', value: jobs.active ?? 0, icon: <Activity size={18} color={colors.blue} />, tone: 'blue' as const, caption: 'In field / assigned' },
    { label: 'Completed', value: cards.completed ?? jobs.completed ?? 0, icon: <CheckCircle2 size={18} color={colors.forest} />, tone: 'green' as const, caption: 'Completed or closed' },
    { label: 'Available Techs', value: tech.available ?? 0, icon: <Users size={18} color={colors.forest} />, tone: 'green' as const, caption: `${tech.busy ?? 0} currently busy` },
    { label: 'SLA Expired', value: data.kpi.jobs_expired ?? 0, icon: <AlertTriangle size={18} color={colors.red} />, tone: 'red' as const, caption: 'Needs attention' },
  ];

  return <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
    <ImageBackground source={require('../../../assets/banners/dashboard-banner.jpeg')} resizeMode="cover" style={{ minHeight: 172, borderRadius: 20, overflow: 'hidden', justifyContent: 'flex-end', padding: 18 }}>
      <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(3, 54, 31, 0.72)' }} />
      <Text style={{ color: '#D4F2DE', fontSize: 10, fontWeight: '900', letterSpacing: 1.3 }}>FIELDOPS COMMANDER</Text>
      <Text style={{ color: '#fff', fontSize: 25, lineHeight: 31, fontWeight: '900', marginTop: 7 }}>Good day, {user.first_name || 'Team'}.</Text>
      <Text style={{ color: '#E8F5ED', fontSize: 12, marginTop: 4 }}>{user.organization_name || 'Operations Control'} · Live operations overview</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 14 }}><View style={{ width: 7, height: 7, borderRadius: 8, backgroundColor: '#66E29C' }} /><Text style={{ color: '#E8F5ED', fontSize: 10, fontWeight: '800' }}>CONNECTED TO YOUR OPERATIONS WORKSPACE</Text></View>
    </ImageBackground>

    <ScreenHeading title="Operations overview" subtitle="Live data from your FieldOps backend." />
    {error ? <Card><Text style={{ color: colors.red, fontSize: 12 }}>{error}</Text></Card> : null}
    {loading ? <View style={{ padding: 20 }}><Text style={{ textAlign: 'center', color: colors.muted }}>Loading operations metrics…</Text></View> : <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
      {metrics.map(item => <MetricCard key={item.label} {...item} onPress={() => onNavigate(item.label === 'Available Techs' ? 'team' : 'planning')} />)}
    </View>}

    <SectionTitle title="Quick operations" subtitle="Open a workspace" />
    <View style={{ flexDirection: 'row', gap: 10 }}>
      <Card onPress={() => onNavigate('planning')} style={{ flex: 1, gap: 8, backgroundColor: '#EAF4EE' }}>
        <View style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: '#D5EBDD', alignItems: 'center', justifyContent: 'center' }}><ClipboardList size={19} color={colors.forest} /></View>
        <Text style={{ fontWeight: '900', color: colors.ink, fontSize: 13 }}>Dispatch queue</Text>
        <Text style={{ color: colors.muted, fontSize: 10 }}>Review, plan and assign jobs</Text>
      </Card>
      <Card onPress={() => onNavigate('tracking')} style={{ flex: 1, gap: 8, backgroundColor: '#EEF4FF' }}>
        <View style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: '#DCE8FF', alignItems: 'center', justifyContent: 'center' }}><Activity size={19} color={colors.blue} /></View>
        <Text style={{ fontWeight: '900', color: colors.ink, fontSize: 13 }}>Live tracking</Text>
        <Text style={{ color: colors.muted, fontSize: 10 }}>View technician locations</Text>
      </Card>
    </View>
    <View style={{ flexDirection: 'row', gap: 10 }}>
      <Card onPress={() => onNavigate('team')} style={{ flex: 1, gap: 8 }}>
        <Users size={20} color={colors.forest} /><Text style={{ fontWeight: '900', color: colors.ink, fontSize: 13 }}>Technicians</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Accounts, skills and availability</Text>
      </Card>
      <Card onPress={() => onNavigate('services')} style={{ flex: 1, gap: 8 }}>
        <Wrench size={20} color={colors.forest} /><Text style={{ fontWeight: '900', color: colors.ink, fontSize: 13 }}>Services catalog</Text><Text style={{ color: colors.muted, fontSize: 10 }}>Manage service coverage</Text>
      </Card>
    </View>

    <SectionTitle title="Recent jobs" action="View planning" onAction={() => onNavigate('planning')} subtitle="Latest records visible to your organization" />
    {data.jobs.length === 0 ? <EmptyState title="No recent jobs found" detail="Jobs will appear here when available in your organization." onRetry={() => load(true)} /> : data.jobs.slice(0, 8).map((job: any) => <Card key={String(job.id ?? job.job_id)} style={{ gap: 9 }} onPress={() => onNavigate('planning')}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 12 }}>JOB #{job.id ?? job.job_id}</Text><Pill label={statusLabel(job.status)} tone={statusTone(job.status)} /></View>
      <Text style={{ color: colors.ink, fontWeight: '800', fontSize: 14 }}>{text(job.service_type, 'Service request')}</Text>
      <Text style={{ color: colors.muted, fontSize: 11 }}>{text(job.customer_name)} · {text(job.location)}</Text>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ fontSize: 10, color: colors.muted }}>Priority: {text(job.priority)}</Text><Text style={{ fontSize: 10, color: colors.muted }}>{dateTime(job.created_at)}</Text></View>
    </Card>)}
    <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10 }}>Dashboard numbers are supplied by the backend’s tenant-scoped job statistics and planning KPI endpoints. Pull down to refresh.</Text></Card>
  </ScreenScroll>;
}
