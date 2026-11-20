import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  ImageBackground,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import {
  Bell,
  BellRing,
  Check,
  CheckCheck,
  Clock3,
  Filter,
  Inbox,
  Leaf,
  Search,
  ShieldAlert,
  Wifi,
  X,
  Trash2,
} from 'lucide-react-native';
import {
  dismissAdminNotification,
  getAdminNotifications,
  markAdminNotificationRead,
  markAdminNotificationsRead,
} from '../api/operations';
import { ErrorBanner } from '../components/UI';
import { dateTime, statusLabel, text, timeAgo } from '../utils/format';

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

type Filter = 'UNREAD' | 'READ';

export default function NotificationScreen({ onUnreadCountChange, refreshKey }: { onUnreadCountChange: (count: number) => void; refreshKey: number }) {
  const [items, setItems] = useState<NotificationRecord[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [filter, setFilter] = useState<Filter>('UNREAD');
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
      const matchesFilter = filter === 'UNREAD' ? status === 'UNREAD' : status === 'READ';
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



  const readItems = items.filter(row => String(row.status || '').toUpperCase() === 'READ').length;
  const criticalItems = items.filter(row => ['CRITICAL', 'HIGH'].includes(String(row.priority || '').toUpperCase())).length;

  const filterOptions: { label: string; value: Filter; count: number }[] = [
    { label: 'Unread', value: 'UNREAD', count: unreadCount },
    { label: 'Read', value: 'READ', count: readItems },
  ];

  const renderNotification = (item: NotificationRecord) => {
    const isUnread = String(item.status || '').toUpperCase() === 'UNREAD';
    const priority = String(item.priority || 'NORMAL').toUpperCase();
    const urgent = priority === 'CRITICAL' || priority === 'HIGH';
    return (
      <View
        key={item.id}
        style={{
          backgroundColor: 'rgba(255,255,255,0.96)',
          borderRadius: 19,
          borderWidth: 1,
          borderColor: isUnread ? '#C8E2C8' : '#DCE8D8',
          borderLeftWidth: 5,
          borderLeftColor: urgent ? '#D52D2D' : isUnread ? '#16813C' : '#C9D8CA',
          padding: 13,
          marginBottom: 10,
          elevation: 2,
          shadowColor: '#17432B',
          shadowOffset: { width: 0, height: 2 },
          shadowOpacity: 0.07,
          shadowRadius: 5,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
          <View style={{
            width: 40, height: 40, borderRadius: 14,
            backgroundColor: urgent ? '#FBE0D9' : '#E2F3E3',
            alignItems: 'center', justifyContent: 'center',
          }}>
            {urgent ? <ShieldAlert size={21} color="#D52D2D" /> : <Bell size={20} color="#075B36" />}
          </View>
          <View style={{ flex: 1, gap: 4 }}>
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 6 }}>
              <Text style={{ flex: 1, color: '#103F2B', fontSize: 13, lineHeight: 18, fontWeight: '900' }}>
                {text(item.title, 'FieldOps alert')}
              </Text>
              {isUnread ? <View style={{ width: 8, height: 8, borderRadius: 5, backgroundColor: '#16813C', marginTop: 5 }} /> : null}
            </View>
            <Text style={{ color: '#526B5C', fontSize: 11, lineHeight: 17 }}>
              {text(item.body, 'No additional message.')}
            </Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6, marginTop: 11 }}>
          <View style={{ paddingHorizontal: 9, paddingVertical: 5, borderRadius: 18, backgroundColor: '#EAF4EE', borderWidth: 1, borderColor: '#D3E6D5' }}>
            <Text style={{ color: '#245B3B', fontSize: 9, fontWeight: '900' }}>{statusLabel(item.type || 'SYSTEM')}</Text>
          </View>
          <View style={{ paddingHorizontal: 9, paddingVertical: 5, borderRadius: 18, backgroundColor: urgent ? '#FCE7E4' : '#F0F4EF', borderWidth: 1, borderColor: urgent ? '#F0D0C8' : '#DDE7DC' }}>
            <Text style={{ color: urgent ? '#A52222' : '#526B5C', fontSize: 9, fontWeight: '900' }}>{priority} PRIORITY</Text>
          </View>
          {item.job_id ? (
            <View style={{ paddingHorizontal: 9, paddingVertical: 5, borderRadius: 18, backgroundColor: '#EDF4FF', borderWidth: 1, borderColor: '#D5E4FF' }}>
              <Text style={{ color: '#2670D8', fontSize: 9, fontWeight: '900' }}>JOB #{item.job_id}</Text>
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginLeft: 'auto' }}>
            <Clock3 size={11} color="#718277" />
            <Text style={{ color: '#718277', fontSize: 9 }}>
              {item.created_at ? timeAgo(item.created_at) : 'Time unavailable'}
            </Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 11, paddingTop: 9, borderTopWidth: 1, borderTopColor: '#E8EFE8', gap: 8 }}>
          <Text style={{ color: '#718277', fontSize: 9, flex: 1 }}>
            {item.created_at ? dateTime(item.created_at) : 'Date unavailable'}
          </Text>
          <View style={{ flexDirection: 'row', gap: 7 }}>
            {isUnread ? (
              <Pressable
                disabled={workingId === item.id}
                onPress={() => void markRead(item)}
                style={{ minHeight: 34, paddingHorizontal: 11, borderRadius: 18, backgroundColor: '#E6F4E5', borderWidth: 1, borderColor: '#C8E5C5', flexDirection: 'row', alignItems: 'center', gap: 5 }}
              >
                <Check size={12} color="#15582D" />
                <Text style={{ color: '#15582D', fontSize: 10, fontWeight: '900' }}>
                  {workingId === item.id ? 'Saving…' : 'Mark read'}
                </Text>
              </Pressable>
            ) : null}
            <Pressable
              disabled={workingId === item.id}
              onPress={() => dismiss(item)}
              style={{ minHeight: 34, paddingHorizontal: 11, borderRadius: 18, backgroundColor: '#F4F6F3', borderWidth: 1, borderColor: '#E0E7DE', flexDirection: 'row', alignItems: 'center', gap: 5 }}
            >
              <X size={12} color="#718277" />
              <Text style={{ color: '#718277', fontSize: 10, fontWeight: '800' }}>Dismiss</Text>
            </Pressable>
          </View>
        </View>
      </View>
    );
  };

  return (
    <ImageBackground
      source={require('../../../assets/team/nature_team_background.png')}
      resizeMode="cover"
      imageStyle={{ opacity: 1 }}
      style={{ flex: 1, backgroundColor: '#E8F1E6' }}
    >
      <ScrollView
        style={{ flex: 1, backgroundColor: 'transparent' }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#145C3B" />
        }
        contentContainerStyle={{
          paddingHorizontal: 14,
          paddingTop: 14,
          paddingBottom: 34,
          gap: 13,
          backgroundColor: 'transparent',
        }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* Same heading structure and spacing as TeamScreen */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: 3, paddingVertical: 5 }}>
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={{ color: '#103F2B', fontSize: 27, fontWeight: '900', letterSpacing: -0.8 }}>
              Notifications
            </Text>
            <Text style={{ color: '#244F3A', fontSize: 12, fontWeight: '600' }}>
              Operational alerts and dispatch updates
            </Text>
          </View>
          <View style={{ minHeight: 40, paddingHorizontal: 12, borderRadius: 24, borderWidth: 1.4, borderColor: unreadCount ? '#D8AAA2' : '#4F8C59', backgroundColor: unreadCount ? 'rgba(255,235,229,0.96)' : 'rgba(247,252,239,0.94)', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 6 }}>
            <BellRing size={15} color={unreadCount ? '#A52222' : '#174D32'} />
            <Text style={{ color: unreadCount ? '#A52222' : '#174D32', fontSize: 11, fontWeight: '900' }}>{unreadCount} unread</Text>
          </View>
        </View>

        {/* TeamScreen-style summary metrics */}
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 19, borderWidth: 1, borderColor: '#CFE3D0', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
            <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#E2F3E3', alignItems: 'center', justifyContent: 'center' }}>
              <Inbox size={22} color="#075B36" />
            </View>
            <View style={{ flex: 1, gap: 1 }}>
              <Text style={{ color: '#073F27', fontSize: 22, fontWeight: '900' }}>{items.length}</Text>
              <Text style={{ color: '#244F3A', fontSize: 9, fontWeight: '800' }}>In inbox</Text>
            </View>
          </View>
          <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(229,248,220,0.96)', borderRadius: 19, borderWidth: 1, borderColor: '#C7E5B9', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
            <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#D7F0CB', alignItems: 'center', justifyContent: 'center' }}>
              <Bell size={22} color="#16813C" />
            </View>
            <View style={{ flex: 1, gap: 1 }}>
              <Text style={{ color: '#16813C', fontSize: 22, fontWeight: '900' }}>{unreadCount}</Text>
              <Text style={{ color: '#285B35', fontSize: 9, fontWeight: '800' }}>Unread</Text>
            </View>
          </View>
          <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(255,235,229,0.96)', borderRadius: 19, borderWidth: 1, borderColor: '#F0D0C8', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
            <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#FBE0D9', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCheck size={22} color="#D52D2D" />
            </View>
            <View style={{ flex: 1, gap: 1 }}>
              <Text style={{ color: '#A52222', fontSize: 22, fontWeight: '900' }}>{readItems}</Text>
              <Text style={{ color: '#80413C', fontSize: 9, fontWeight: '800' }}>Read</Text>
            </View>
          </View>
        </View>

        {/* Search and mark-all action */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ flex: 1, minHeight: 46, borderRadius: 25, backgroundColor: 'rgba(255,255,255,0.94)', borderWidth: 1, borderColor: '#CFE0CF', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, gap: 8 }}>
            <Search size={17} color="#456B50" />
            <TextInput
              value={search}
              onChangeText={setSearch}
              placeholder="Search title, message or job..."
              placeholderTextColor="#829187"
              style={{ flex: 1, color: '#173D2B', fontSize: 11, paddingVertical: 9 }}
              returnKeyType="search"
            />
            {search ? <Pressable onPress={() => setSearch('')} hitSlop={8}><X size={15} color="#456B50" /></Pressable> : null}
          </View>
          <Pressable
            disabled={!unreadCount || workingId === 'all'}
            onPress={() => void markAllRead()}
            style={{ minHeight: 46, paddingHorizontal: 12, borderRadius: 24, backgroundColor: unreadCount ? '#075B36' : '#B9C8BB', borderWidth: 1, borderColor: unreadCount ? '#2F8B4D' : '#B9C8BB', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 5 }}
          >
            <CheckCheck size={15} color="#FFFFFF" />
            <Text style={{ color: '#FFFFFF', fontSize: 10, fontWeight: '900' }}>{workingId === 'all' ? 'Saving' : 'Read all'}</Text>
          </Pressable>
        </View>

        {/* Availability-style filter chips from TeamScreen */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7, paddingRight: 3 }}>
          {filterOptions.map(option => {
            const active = filter === option.value;
            const chip = option.value === 'UNREAD'
              ? { bg: 'rgba(229,248,220,0.96)', fg: '#15582D', border: '#C7E5B9' }
              : { bg: 'rgba(255,232,229,0.97)', fg: '#962727', border: '#F0D0C8' };
            return (
              <Pressable
                key={option.value}
                onPress={() => setFilter(option.value)}
                style={{ minHeight: 37, paddingHorizontal: 14, borderRadius: 22, backgroundColor: active ? chip.bg : 'rgba(255,255,255,0.9)', borderWidth: 1, borderColor: active ? chip.border : 'rgba(190,216,185,0.85)', flexDirection: 'row', alignItems: 'center', gap: 6, elevation: active ? 2 : 0 }}
              >
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: active ? chip.fg : '#9AA99D' }} />
                <Text style={{ color: active ? chip.fg : '#526B5C', fontSize: 10, fontWeight: '900' }}>{option.label} ({option.count})</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        {/* Directory heading */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 2, paddingTop: 2 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
            <Leaf size={22} color="#3C8A38" fill="#7CBF48" />
            <Text style={{ color: '#103F2B', fontSize: 19, fontWeight: '900' }}>Notification Directory</Text>
          </View>
          <Text style={{ color: '#153F2C', fontSize: 10, fontWeight: '900' }}>{visible.length} alerts</Text>
        </View>

        {error ? <ErrorBanner message={error} /> : null}
        {loading ? (
          <Text style={{ textAlign: 'center', color: '#718277', padding: 24 }}>Loading notifications...</Text>
        ) : visible.length === 0 ? (
          <View style={{ backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 19, borderWidth: 1, borderColor: '#D8E8D4', padding: 24, alignItems: 'center', gap: 8 }}>
            <View style={{ width: 48, height: 48, borderRadius: 16, backgroundColor: '#E2F3E3', alignItems: 'center', justifyContent: 'center' }}>
              <Bell size={23} color="#075B36" />
            </View>
            <Text style={{ color: '#103F2B', fontSize: 15, fontWeight: '900' }}>No notifications found</Text>
            <Text style={{ color: '#526B5C', fontSize: 11, textAlign: 'center' }}>
              {search ? 'Try another search term.' : filter === 'UNREAD' ? 'You are all caught up.' : 'New operational notifications will appear here.'}
            </Text>
            <Pressable onPress={() => void load(true)} style={{ marginTop: 5, paddingHorizontal: 15, paddingVertical: 9, borderRadius: 20, backgroundColor: '#075B36' }}>
              <Text style={{ color: '#FFFFFF', fontSize: 10, fontWeight: '900' }}>Refresh</Text>
            </Pressable>
          </View>
        ) : (
          <View>
            {visible.map(renderNotification)}
          </View>
        )}

        <Text style={{ color: '#526B5C', fontSize: 9, lineHeight: 14, textAlign: 'center', paddingHorizontal: 8, marginTop: 4 }}>
          Notifications are scoped to your staff account and organization. Pull down to refresh.
        </Text>
      </ScrollView>
    </ImageBackground>
  );
}
