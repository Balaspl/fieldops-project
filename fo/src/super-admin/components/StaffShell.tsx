import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Activity, Bell, Bot, BriefcaseBusiness, ChevronRight, Headset, LayoutDashboard, LogOut, MoreHorizontal, Shield, UserRound, Users, Wrench, X } from 'lucide-react-native';
import { io } from 'socket.io-client';
import { useAuth } from '../auth/AuthContext';
import DashboardScreen from '../screens/DashboardScreen';
import PlanningScreen from '../screens/PlanningScreen';
import TrackingScreen from '../screens/TrackingScreen';
import TeamScreen from '../screens/TeamScreen';
import ServicesScreen from '../screens/ServicesScreen';
import SupportScreen from '../screens/SupportScreen';
import AgentTrackingScreen from '../screens/AgentTrackingScreen';
import NotificationScreen from '../screens/NotificationScreen';
import ProfileScreen from '../screens/ProfileScreen';
import { BrandMark } from './UI';
import { colors } from '../theme';
import { api, getAccessToken, getApiBaseUrl } from '../api/client';
import { initials } from '../utils/format';

type Route = 'dashboard' | 'planning' | 'tracking' | 'team' | 'services' | 'support' | 'agents' | 'notifications' | 'profile';
const MAIN_NAV: { id: Route; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Home', icon: <LayoutDashboard size={19} /> },
  { id: 'planning', label: 'Planning', icon: <BriefcaseBusiness size={19} /> },
  { id: 'tracking', label: 'Tracking', icon: <Activity size={19} /> },
  { id: 'team', label: 'Team', icon: <Users size={19} /> },
];

export default function StaffShell() {
  const { user, role, signOut, accessToken } = useAuth();
  const [route, setRoute] = useState<Route>('dashboard');
  const [moreOpen, setMoreOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationRefreshKey, setNotificationRefreshKey] = useState(0);
  const countRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSuperAdmin = role === 'super_admin';
  const go = (next: string) => { if (['dashboard', 'planning', 'tracking', 'team', 'services', 'support', 'agents', 'notifications', 'profile'].includes(next)) setRoute(next as Route); setMoreOpen(false); };
  const refreshUnreadCount = useCallback(async () => {
    if (!accessToken || !['super_admin', 'dispatcher'].includes(role || '')) { setUnreadCount(0); return; }
    try { const response = await api.get('/admin/notifications', { params: { limit: 1, offset: 0 } }); setUnreadCount(Number(response.data?.unread_count || 0)); } catch { /* The notification screen reports the detailed API error. */ }
  }, [accessToken, role]);
  useEffect(() => {
    void refreshUnreadCount();
    const timer = setInterval(() => { void refreshUnreadCount(); }, 60000);
    return () => clearInterval(timer);
  }, [refreshUnreadCount]);
  useEffect(() => {
    if (!accessToken || !user?.tenant_id) return;
    const socketUrl = (process.env.EXPO_PUBLIC_SOCKET_IO_URL || getApiBaseUrl()).replace(/\/$/, '');
    const socket = io(socketUrl, {
      auth: (callback) => callback({ token: getAccessToken() || accessToken }),
      transports: ['websocket', 'polling'],
      reconnection: true, reconnectionAttempts: 8, reconnectionDelay: 1500, timeout: 10000,
    });
    const queueCountRefresh = () => {
      if (countRefreshTimer.current) clearTimeout(countRefreshTimer.current);
      countRefreshTimer.current = setTimeout(() => { countRefreshTimer.current = null; void refreshUnreadCount(); setNotificationRefreshKey(value => value + 1); }, 500);
    };
    socket.on('new_notification', queueCountRefresh);
    socket.on('notification', queueCountRefresh);
    socket.on('notification:new', queueCountRefresh);
    socket.on('notification:unread_count', (payload: number | { unread_count?: number; count?: number }) => {
      const next = typeof payload === 'number' ? payload : Number(payload?.unread_count ?? payload?.count ?? 0);
      if (Number.isFinite(next)) setUnreadCount(Math.max(0, next));
      setNotificationRefreshKey(value => value + 1);
    });
    return () => {
      if (countRefreshTimer.current) { clearTimeout(countRefreshTimer.current); countRefreshTimer.current = null; }
      socket.removeAllListeners(); socket.disconnect();
    };
  }, [accessToken, user?.tenant_id, refreshUnreadCount]);
  const logout = async () => { if (signingOut) return; setSigningOut(true); try { await signOut(); } finally { setSigningOut(false); } };

  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }} edges={['top', 'left', 'right', 'bottom']}>
    <View style={{ flex: 1 }}>
      <View style={{ minHeight: 62, paddingHorizontal: 15, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.white }}>
        <View style={{ flex: 1, justifyContent: 'center' }}><BrandMark compact /></View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
          <Pressable onPress={() => go('notifications')} accessibilityRole="button" accessibilityLabel={`${unreadCount} unread notifications`} style={{ width: 35, height: 35, borderRadius: 11, backgroundColor: unreadCount ? '#FDECEC' : colors.canvas, alignItems: 'center', justifyContent: 'center' }}><Bell size={17} color={unreadCount ? colors.red : colors.muted} />{unreadCount > 0 ? <View style={{ position: 'absolute', top: -3, right: -3, minWidth: 15, height: 15, borderRadius: 8, backgroundColor: colors.red, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 3 }}><Text style={{ color: '#fff', fontSize: 8, fontWeight: '900' }}>{unreadCount > 99 ? '99+' : unreadCount}</Text></View> : null}</Pressable>
          <View style={{ alignItems: 'flex-end', gap: 2, maxWidth: 145 }}><Text numberOfLines={1} style={{ color: colors.ink, fontSize: 11, fontWeight: '900' }}>{user?.first_name} {user?.last_name}</Text><Text style={{ color: colors.forest, fontSize: 9, fontWeight: '900' }}>{isSuperAdmin ? 'SUPER ADMIN' : 'DISPATCHER'}</Text></View>
          <View style={{ width: 35, height: 35, borderRadius: 12, backgroundColor: colors.mint, justifyContent: 'center', alignItems: 'center' }}><Text style={{ color: colors.forest, fontSize: 12, fontWeight: '900' }}>{initials(`${user?.first_name || ''} ${user?.last_name || ''}`)}</Text></View>
          <Pressable onPress={() => void logout()} accessibilityRole="button" accessibilityLabel="Sign out" style={{ width: 35, height: 35, alignItems: 'center', justifyContent: 'center', borderRadius: 11, backgroundColor: '#FEECEC' }}><LogOut size={16} color={colors.red} /></Pressable>
        </View>
      </View>

      <View style={{ flex: 1 }}>
        {route === 'dashboard' ? <DashboardScreen user={user!} onNavigate={go} /> : null}
        {route === 'planning' ? <PlanningScreen /> : null}
        {route === 'tracking' ? <TrackingScreen /> : null}
        {route === 'team' ? <TeamScreen onNavigate={go} /> : null}
        {route === 'services' ? <ServicesScreen /> : null}
        {route === 'support' ? <SupportScreen /> : null}
        {route === 'agents' && isSuperAdmin ? <AgentTrackingScreen /> : null}
        {route === 'notifications' ? <NotificationScreen onUnreadCountChange={setUnreadCount} refreshKey={notificationRefreshKey} /> : null}
        {route === 'profile' ? <ProfileScreen /> : null}
      </View>

      <View style={{ minHeight: 64, paddingHorizontal: 8, paddingTop: 7, paddingBottom: 3, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', backgroundColor: colors.white, borderTopWidth: 1, borderTopColor: colors.border }}>
        {MAIN_NAV.map(item => {
          const active = route === item.id;
          return <Pressable key={item.id} onPress={() => go(item.id)} accessibilityRole="button" accessibilityState={{ selected: active }} style={{ minWidth: 58, alignItems: 'center', justifyContent: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 4 }}>
            <View style={{ width: 36, height: 29, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: active ? '#E5F2EA' : 'transparent' }}>{React.cloneElement(item.icon as React.ReactElement<any>, { color: active ? colors.forest : colors.muted })}</View>
            <Text style={{ color: active ? colors.forest : colors.muted, fontSize: 9, fontWeight: active ? '900' : '700' }}>{item.label}</Text>
          </Pressable>;
        })}
        <Pressable onPress={() => setMoreOpen(true)} accessibilityRole="button" style={{ minWidth: 58, alignItems: 'center', justifyContent: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 4 }}>
          <View style={{ width: 36, height: 29, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: ['services', 'support', 'agents', 'notifications', 'profile'].includes(route) ? '#E5F2EA' : 'transparent' }}><MoreHorizontal size={20} color={['services', 'support', 'agents', 'notifications', 'profile'].includes(route) ? colors.forest : colors.muted} /></View>
          <Text style={{ color: ['services', 'support', 'agents', 'notifications', 'profile'].includes(route) ? colors.forest : colors.muted, fontSize: 9, fontWeight: '800' }}>More</Text>
        </Pressable>
      </View>
    </View>

    <Modal visible={moreOpen} transparent animationType="fade" onRequestClose={() => setMoreOpen(false)}>
      <Pressable onPress={() => setMoreOpen(false)} style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.48)', justifyContent: 'flex-end' }}>
        <Pressable onPress={() => undefined} style={{ backgroundColor: colors.white, borderTopLeftRadius: 25, borderTopRightRadius: 25, padding: 20, paddingBottom: 28, gap: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><View style={{ gap: 3 }}><Text style={{ color: colors.ink, fontSize: 18, fontWeight: '900' }}>Operations workspace</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{user?.organization_name || 'FieldOps Commander'}</Text></View><Pressable onPress={() => setMoreOpen(false)} style={{ width: 34, height: 34, borderRadius: 11, backgroundColor: colors.canvas, alignItems: 'center', justifyContent: 'center' }}><X size={17} color={colors.ink} /></Pressable></View>
          <MenuRow icon={<Bell size={18} color={colors.forest} />} title={`Notifications${unreadCount ? ` (${unreadCount})` : ''}`} subtitle="Dispatch alerts and operational updates" onPress={() => go('notifications')} />
          <MenuRow icon={<UserRound size={18} color={colors.forest} />} title="My profile" subtitle="Update personal information and password" onPress={() => go('profile')} />
          <MenuRow icon={<Wrench size={18} color={colors.forest} />} title="Services catalog" subtitle={isSuperAdmin ? 'Create and manage service offerings' : 'Browse your organization’s services'} onPress={() => go('services')} />
          <MenuRow icon={<Headset size={18} color={colors.forest} />} title="Customer support" subtitle="Review cases, triage and resolve" onPress={() => go('support')} />
          {isSuperAdmin ? <MenuRow icon={<Bot size={18} color={colors.purple} />} title="Agent Tracking" subtitle="Inspect Planning, Communication, Sentiment and Closure stages" onPress={() => go('agents')} /> : null}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4, padding: 12, borderRadius: 13, backgroundColor: '#F3F8F5' }}><Shield size={15} color={colors.forest} /><Text style={{ flex: 1, color: colors.muted, fontSize: 10, lineHeight: 15 }}>Your role permissions are enforced by the backend API. Navigation visibility is an additional UI restriction, not a replacement for server authorization.</Text></View>
        </Pressable>
      </Pressable>
    </Modal>
  </SafeAreaView>;
}

function MenuRow({ icon, title, subtitle, onPress }: { icon: React.ReactNode; title: string; subtitle: string; onPress: () => void }) {
  return <Pressable onPress={onPress} style={({ pressed }) => ({ borderWidth: 1, borderColor: colors.border, borderRadius: 15, padding: 13, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: pressed ? '#F3F8F5' : colors.white })}>
    <View style={{ width: 40, height: 40, borderRadius: 13, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center' }}>{icon}</View>
    <View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.ink, fontSize: 13, fontWeight: '900' }}>{title}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{subtitle}</Text></View>
    <ChevronRight size={17} color={colors.muted} />
  </Pressable>;
}
