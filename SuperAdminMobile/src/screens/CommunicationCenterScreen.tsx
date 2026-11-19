import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshControl, Text, View } from 'react-native';
import { Bell, Mail, MessageSquareText, Smartphone } from 'lucide-react-native';
import { getCommunicationActivity } from '../api/operations';
import { Card, EmptyState, ErrorBanner, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField } from '../components/UI';
import { colors } from '../theme';
import { dateTime, text } from '../utils/format';

const channels = ['all', 'in_app', 'sms', 'email', 'push'];
const states = ['all', 'unread', 'read', 'pending', 'queued', 'sending', 'accepted', 'sent', 'delivered', 'failed', 'permanent_failure'];
const pretty = (value: any) => String(value || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const iconFor = (channel: string) => channel === 'sms' ? <Smartphone size={14} color={colors.forest} /> : channel === 'email' ? <Mail size={14} color={colors.forest} /> : channel === 'push' ? <Bell size={14} color={colors.forest} /> : <MessageSquareText size={14} color={colors.forest} />;

export default function CommunicationCenterScreen() {
  const [data, setData] = useState<any>({ messages: [], total: 0, channel_counts: {}, delivery_counts: {} });
  const [search, setSearch] = useState('');
  const [channel, setChannel] = useState('all');
  const [status, setStatus] = useState('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const messageCount = useRef(0);

  const load = useCallback(async (refresh = false, append = false) => {
    if (refresh) setRefreshing(true); else if (!append) setLoading(true);
    setError('');
    try {
      const offset = append ? messageCount.current : 0;
      const result = await getCommunicationActivity({ search: search.trim() || undefined, channel, status, limit: 50, offset });
      setData((previous: any) => {
        const next = append ? { ...result, messages: [...previous.messages, ...(result.messages || [])] } : result;
        messageCount.current = next.messages.length;
        return next;
      });
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Could not load communication activity.');
    } finally { setLoading(false); setRefreshing(false); }
  }, [search, channel, status]);

  useEffect(() => { void load(); }, [search, channel, status]);

  return <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={colors.forest} />}>
    <ScreenHeading title="Communication center" subtitle="Messages and delivery status from the FieldOps backend" />
    <SearchField value={search} onChangeText={setSearch} placeholder="Search messages, recipient or job…" />
    <Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>CHANNEL</Text>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{channels.map(value => <PrimaryButton key={value} title={pretty(value)} compact variant={channel === value ? 'primary' : 'ghost'} onPress={() => setChannel(value)} />)}</View>
    <Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>DELIVERY STATUS</Text>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{states.map(value => <PrimaryButton key={value} title={pretty(value)} compact variant={status === value ? 'primary' : 'ghost'} onPress={() => setStatus(value)} />)}</View>
    {error ? <ErrorBanner message={error} /> : null}
    <Text style={{ color: colors.muted, fontSize: 11 }}>{loading ? 'Loading activity…' : `${data.total || data.messages.length} messages`}</Text>
    {!loading && !data.messages.length ? <EmptyState title="No communication activity" detail="Try another search, channel or delivery status." onRetry={() => void load()} /> : null}
    {(data.messages || []).map((item: any) => <Card key={String(item.id)} style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.ink, fontSize: 14, fontWeight: '900' }}>{text(item.title, pretty(item.type))}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{pretty(item.recipient_role)}{item.job_id ? ` · Job #${item.job_id}` : ' · Service update'}{item.type ? ` · ${pretty(item.type)}` : ''}</Text></View><Text style={{ color: colors.muted, fontSize: 9 }}>{dateTime(item.updated_at || item.created_at)}</Text></View>
      <Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }}>{text(item.message, 'This automatic update has no message body.')}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{(item.channels || []).map((delivery: any) => <View key={`${item.id}-${delivery.channel}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 6 }}>
        {iconFor(delivery.channel)}<Text style={{ color: colors.text, fontSize: 10, fontWeight: '800' }}>{pretty(delivery.channel)}</Text><Pill label={pretty(delivery.status)} tone={['delivered', 'accepted', 'sent', 'read'].includes(String(delivery.status).toLowerCase()) ? 'green' : ['failed', 'permanent_failure'].includes(String(delivery.status).toLowerCase()) ? 'red' : 'amber'} />{delivery.attempts > 0 ? <Text style={{ color: colors.muted, fontSize: 9 }}>{delivery.attempts}×</Text> : null}
      </View>)}</View>
    </Card>)}
    {data.messages.length < Number(data.total || 0) ? <PrimaryButton title="Load more" variant="secondary" loading={loading && data.messages.length > 0} onPress={() => void load(false, true)} /> : null}
  </ScreenScroll>;
}
