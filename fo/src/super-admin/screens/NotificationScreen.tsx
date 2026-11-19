import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, RefreshControl, Text, View } from 'react-native';
import { Bell, CheckCheck, Clock3, ShieldAlert } from 'lucide-react-native';
import {
  dismissAdminNotification,
  getAdminNotifications,
  markAdminNotificationRead,
  markAdminNotificationsRead,
} from '../api/operations';
import { Card, EmptyState, ErrorBanner, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField, SectionTitle } from '../components/UI';
import { colors } from '../theme';
import { dateTime, statusLabel, statusTone, text, timeAgo } from '../utils/format';

type NotificationRecord = {
  id: string;
  type?: string;
  title?: string;
  body?: string;
  status?: string;
  priority?: string;
  created_at?: string;
  job_id?: string | number | null;
  action_type?: string | null;
  action_url?: string | null;
  notification_metadata?: Record<string, any> | null;
};

type Filter = 'ALL' | 'UNREAD' | 'READ';

export default function NotificationScreen({ onUnreadCountChange, refreshKey }: { onUnreadCountChange: (count: number) => void; refreshKey: number }) {
  const [items, setItems] = useState<NotificationRecord[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [workingId, setWorkingId] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const data = await getAdminNotifications({ limit: 50, offset: 0 });
      const rows = Array.isArray(data?.notifications) ? data.notifications : [];
      setItems(rows);
      const count = Number(data?.unread_count ?? 0);
      setUnreadCount(count);
      onUnreadCountChange(count);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Could not load notifications.');
    } finally { setLoading(false); setRefreshing(false); }
  }, [onUnreadCountChange]);

  useEffect(() => { void load(refreshKey > 0); }, [load, refreshKey]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return items.filter(item => {
      const status = String(item.status || '').toUpperCase();
      const matchesFilter = filter === 'ALL' || (filter === 'UNREAD' ? status === 'UNREAD' : status === 'READ');
      const matchesSearch = !term || [item.title, item.body, item.type, item.job_id, item.priority].some(value => String(value ?? '').toLowerCase().includes(term));
      return matchesFilter && matchesSearch;
    });
  }, [items, filter, search]);

  const markRead = async (item: NotificationRecord) => {
    if (String(item.status).toUpperCase() !== 'UNREAD') return;
    setWorkingId(item.id);
    try {
      await markAdminNotificationRead(item.id);
      setItems(previous => previous.map(row => row.id === item.id ? { ...row, status: 'READ' } : row));
      const count = Math.max(0, unreadCount - 1);
      setUnreadCount(count); onUnreadCountChange(count);
    } catch (e: any) {
      Alert.alert('Could not update notification', e?.response?.data?.detail || e?.message || 'Please try again.');
    } finally { setWorkingId(null); }
  };

  const markAllRead = async () => {
    if (!unreadCount) return;
    setWorkingId('all');
    try {
      // The API caps each page and each batch at 100 IDs. Walk every unread
      // page and submit bounded batches so this really means all inbox items.
      const allIds: string[] = [];
      let offset = 0;
      while (true) {
        const page = await getAdminNotifications({ limit: 100, offset, status: 'UNREAD' });
        const rows: NotificationRecord[] = Array.isArray(page?.notifications) ? page.notifications : [];
        allIds.push(...rows.map(row => row.id));
        offset += rows.length;
        if (!rows.length || rows.length < 100 || offset >= Number(page?.total ?? 0)) break;
      }
      for (let index = 0; index < allIds.length; index += 100) {
        await markAdminNotificationsRead(allIds.slice(index, index + 100));
      }
      setItems(previous => previous.map(row => ({ ...row, status: String(row.status).toUpperCase() === 'UNREAD' ? 'READ' : row.status })));
      setUnreadCount(0); onUnreadCountChange(0);
      await load(true);
    } catch (e: any) {
      Alert.alert('Could not mark all as read', e?.response?.data?.detail || e?.message || 'Please try again.');
    } finally { setWorkingId(null); }
  };

  const dismiss = (item: NotificationRecord) => {
    Alert.alert('Dismiss notification?', 'This will remove the notification from your active inbox.', [
      { text: 'Keep', style: 'cancel' },
      { text: 'Dismiss', style: 'destructive', onPress: async () => {
        setWorkingId(item.id);
        try {
          await dismissAdminNotification(item.id);
          setItems(previous => previous.filter(row => row.id !== item.id));
          if (String(item.status).toUpperCase() === 'UNREAD') {
            const count = Math.max(0, unreadCount - 1);
            setUnreadCount(count); onUnreadCountChange(count);
          }
        } catch (e: any) {
          Alert.alert('Could not dismiss notification', e?.response?.data?.detail || e?.message || 'Please try again.');
        } finally { setWorkingId(null); }
      } },
    ]);
  };

  return <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
    <ScreenHeading title="Notifications" subtitle="Operational alerts and dispatch updates delivered to your staff account." action={<Pill label={`${unreadCount} unread`} tone={unreadCount ? 'red' : 'green'} />} />
    <View style={{ flexDirection: 'row', gap: 8 }}>
      <Card style={{ flex: 1, padding: 13, gap: 4 }}><Bell size={16} color={colors.forest} /><Text style={{ color: colors.muted, fontSize: 10 }}>In inbox</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 22 }}>{items.length}</Text></Card>
      <Card style={{ flex: 1, padding: 13, gap: 4 }}><ShieldAlert size={16} color={colors.red} /><Text style={{ color: colors.muted, fontSize: 10 }}>Unread</Text><Text style={{ color: colors.red, fontWeight: '900', fontSize: 22 }}>{unreadCount}</Text></Card>
      <Card style={{ flex: 1, padding: 13, gap: 4 }}><CheckCheck size={16} color={colors.blue} /><Text style={{ color: colors.muted, fontSize: 10 }}>Read</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 22 }}>{items.filter(row => String(row.status).toUpperCase() === 'READ').length}</Text></Card>
    </View>
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
      <SectionTitle title="Your inbox" subtitle="Newest server notifications first" />
      <PrimaryButton title="Mark all read" compact variant="secondary" disabled={!unreadCount || workingId === 'all'} loading={workingId === 'all'} onPress={() => void markAllRead()} />
    </View>
    <View style={{ flexDirection: 'row', gap: 5, backgroundColor: '#E7EFEA', padding: 4, borderRadius: 13 }}>
      {(['ALL', 'UNREAD', 'READ'] as const).map(value => <PrimaryButton key={value} title={value === 'ALL' ? 'All' : value === 'UNREAD' ? `Unread ${unreadCount}` : 'Read'} compact style={{ flex: 1 }} variant={filter === value ? 'primary' : 'ghost'} onPress={() => setFilter(value)} />)}
    </View>
    <SearchField value={search} onChangeText={setSearch} placeholder="Search notification, job or type…" />
    {error ? <ErrorBanner message={error} /> : null}
    {loading ? <Text style={{ color: colors.muted, textAlign: 'center', padding: 24 }}>Loading notifications…</Text> : visible.length === 0 ? <EmptyState title="No notifications here" detail={search ? 'Try another search.' : filter === 'UNREAD' ? 'You are all caught up.' : 'New operational notifications will appear here.'} onRetry={() => load(true)} /> : visible.map(item => {
      const isUnread = String(item.status).toUpperCase() === 'UNREAD';
      const priority = String(item.priority || 'NORMAL').toUpperCase();
      return <Card key={item.id} style={{ gap: 9, borderColor: isUnread ? '#B9DCC7' : colors.border, backgroundColor: isUnread ? '#FBFEFC' : colors.white }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 9 }}>
          <View style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: priority === 'CRITICAL' || priority === 'HIGH' ? '#FDECEC' : '#EAF4EE', alignItems: 'center', justifyContent: 'center' }}><Bell size={17} color={priority === 'CRITICAL' || priority === 'HIGH' ? colors.red : colors.forest} /></View>
          <View style={{ flex: 1, gap: 4 }}><View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}><Text style={{ flex: 1, minWidth: 130, color: colors.ink, fontSize: 13, fontWeight: '900' }}>{text(item.title, 'FieldOps alert')}</Text>{isUnread ? <Pill label="Unread" tone="green" /> : <Pill label="Read" tone="neutral" />}</View><Text style={{ color: colors.text, fontSize: 11, lineHeight: 17 }}>{text(item.body, 'No additional message.')}</Text></View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
          <Pill label={statusLabel(item.type || 'SYSTEM')} tone={statusTone(item.type || 'SYSTEM')} />
          <Pill label={`${priority} priority`} tone={priority === 'CRITICAL' || priority === 'HIGH' ? 'red' : 'neutral'} />
          {item.job_id ? <Pill label={`Job #${item.job_id}`} tone="blue" /> : null}
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1 }}><Clock3 size={12} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 9 }}>{item.created_at ? `${timeAgo(item.created_at)} · ${dateTime(item.created_at)}` : 'Time unavailable'}</Text></View><View style={{ flexDirection: 'row', gap: 6 }}>
          {isUnread ? <PrimaryButton title="Mark read" compact variant="secondary" loading={workingId === item.id} onPress={() => void markRead(item)} /> : null}
          <PrimaryButton title="Dismiss" compact variant="ghost" disabled={workingId === item.id} onPress={() => dismiss(item)} />
        </View></View>
      </Card>;
    })}
    <Text style={{ color: colors.muted, fontSize: 10, lineHeight: 15 }}>Notifications are read from the authenticated admin notification API and scoped to your staff account and organization by the backend. Pull down to refresh.</Text>
  </ScreenScroll>;
}
