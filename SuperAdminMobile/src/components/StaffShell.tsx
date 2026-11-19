import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Activity, Bell, BriefcaseBusiness, Headset, LayoutDashboard, LogOut, Users, Wrench } from 'lucide-react-native';
import { io } from 'socket.io-client';
import { useAuth } from '../auth/AuthContext';
import DashboardScreen from '../screens/DashboardScreen';
import PlanningScreen from '../screens/PlanningScreen';
import TrackingScreen from '../screens/TrackingScreen';
import TeamScreen from '../screens/TeamScreen';
import ServicesScreen from '../screens/ServicesScreen';
import SupportScreen from '../screens/SupportScreen';
import NotificationScreen from '../screens/NotificationScreen';
import ProfileScreen from '../screens/ProfileScreen';
import { BrandMark } from './UI';
import { colors } from '../theme';
import { api, getAccessToken, getApiBaseUrl } from '../api/client';
import { initials } from '../utils/format';

type Route = 'dashboard' | 'planning' | 'tracking' | 'team' | 'services' | 'support' | 'notifications' | 'profile';
const MAIN_NAV: { id: Route; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Home', icon: <LayoutDashboard size={19} /> },
  { id: 'planning', label: 'Planning', icon: <BriefcaseBusiness size={19} /> },
  { id: 'tracking', label: 'Tracking', icon: <Activity size={19} /> },
  { id: 'team', label: 'Team', icon: <Users size={19} /> },
  { id: 'services', label: 'Services', icon: <Wrench size={19} /> },
];

export default function StaffShell() {
  const { user, role, signOut, accessToken } = useAuth();
  const [route, setRoute] = useState<Route>('dashboard');
  const [signingOut, setSigningOut] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationRefreshKey, setNotificationRefreshKey] = useState(0);
  const [teamDetailsVisible, setTeamDetailsVisible] = useState(false);
  const [teamScreenKey, setTeamScreenKey] = useState(0);
  const countRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSuperAdmin = role === 'super_admin';
  const go = (next: string) => {
    // TeamScreen uses this internal signal while keeping its own directory/detail state.
    if (next === 'technician-details') {
      setTeamDetailsVisible(true);
      return;
    }

    if (['dashboard', 'planning', 'tracking', 'team', 'services', 'support', 'notifications', 'profile'].includes(next)) {
      setRoute(next as Route);
      // Re-entering Team or navigating elsewhere always returns to the normal shell header.
      setTeamDetailsVisible(false);
    }
  };
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
      {!teamDetailsVisible ? <View style={{ minHeight: 62, paddingHorizontal: 15, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.white }}>
        <View style={{ flex: 1, justifyContent: 'center' }}><BrandMark compact /></View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
          <Pressable onPress={() => go('notifications')} accessibilityRole="button" accessibilityLabel={`${unreadCount} unread notifications`} style={{ width: 35, height: 35, borderRadius: 11, backgroundColor: unreadCount ? '#FDECEC' : colors.canvas, alignItems: 'center', justifyContent: 'center' }}><Bell size={17} color={unreadCount ? colors.red : colors.muted} />{unreadCount > 0 ? <View style={{ position: 'absolute', top: -3, right: -3, minWidth: 15, height: 15, borderRadius: 8, backgroundColor: colors.red, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 3 }}><Text style={{ color: '#fff', fontSize: 8, fontWeight: '900' }}>{unreadCount > 99 ? '99+' : unreadCount}</Text></View> : null}</Pressable>
          <Pressable onPress={() => go('support')} accessibilityRole="button" accessibilityLabel="Customer support" style={{ width: 35, height: 35, borderRadius: 11, backgroundColor: colors.canvas, alignItems: 'center', justifyContent: 'center' }}><Headset size={17} color={colors.forest} /></Pressable>
          <View style={{ alignItems: 'flex-end', gap: 2, maxWidth: 90 }}><Text numberOfLines={1} style={{ color: colors.ink, fontSize: 11, fontWeight: '900' }}>{user?.first_name} {user?.last_name}</Text><Text style={{ color: colors.forest, fontSize: 9, fontWeight: '900' }}>{isSuperAdmin ? 'SUPER ADMIN' : 'DISPATCHER'}</Text></View>
          <Pressable onPress={() => go('profile')} accessibilityRole="button" accessibilityLabel="My profile" style={{ width: 35, height: 35, borderRadius: 12, backgroundColor: colors.mint, justifyContent: 'center', alignItems: 'center' }}><Text style={{ color: colors.forest, fontSize: 12, fontWeight: '900' }}>{initials(`${user?.first_name || ''} ${user?.last_name || ''}`)}</Text></Pressable>
          <Pressable onPress={() => void logout()} accessibilityRole="button" accessibilityLabel="Sign out" style={{ width: 35, height: 35, alignItems: 'center', justifyContent: 'center', borderRadius: 11, backgroundColor: '#FEECEC' }}><LogOut size={16} color={colors.red} /></Pressable>
        </View>
      </View> : null}

      <View style={{ flex: 1 }}>
        {route === 'dashboard' ? <DashboardScreen user={user!} onNavigate={go} /> : null}
        {route === 'planning' ? <PlanningScreen /> : null}
        {route === 'tracking' ? <TrackingScreen /> : null}
        {route === 'team' ? <TeamScreen key={teamScreenKey} onNavigate={go} /> : null}
        {route === 'services' ? <ServicesScreen /> : null}
        {route === 'support' ? <SupportScreen /> : null}
        {route === 'notifications' ? <NotificationScreen onUnreadCountChange={setUnreadCount} refreshKey={notificationRefreshKey} /> : null}
        {route === 'profile' ? <ProfileScreen /> : null}
      </View>

      <View style={{ minHeight: 64, paddingHorizontal: 8, paddingTop: 7, paddingBottom: 3, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', backgroundColor: colors.white, borderTopWidth: 1, borderTopColor: colors.border }}>
        {MAIN_NAV.map(item => {
          const active = route === item.id;
          return <Pressable
            key={item.id}
            onPress={() => {
              // Re-selecting Team while a technician detail is open should return to
              // a fresh directory screen, not leave the selected detail mounted.
              if (item.id === 'team' && teamDetailsVisible) {
                setTeamDetailsVisible(false);
                setTeamScreenKey(value => value + 1);
                return;
              }
              go(item.id);
            }}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            style={{ minWidth: 52, alignItems: 'center', justifyContent: 'center', gap: 3, paddingHorizontal: 4, paddingVertical: 4 }}
          >
            <View style={{ width: 36, height: 29, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: active ? '#E5F2EA' : 'transparent' }}>{React.cloneElement(item.icon as React.ReactElement<any>, { color: active ? colors.forest : colors.muted })}</View>
            <Text style={{ color: active ? colors.forest : colors.muted, fontSize: 9, fontWeight: active ? '900' : '700' }}>{item.label}</Text>
          </Pressable>;
        })}
      </View>
    </View>

  </SafeAreaView>;
}
