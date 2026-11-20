import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Animated, PanResponder, Pressable, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  Activity,
  Bell,
  BriefcaseBusiness,
  Headset,
  LayoutDashboard,
  LogOut,
  Users,
  Wrench,
} from 'lucide-react-native';
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

type Route =
  | 'dashboard'
  | 'planning'
  | 'tracking'
  | 'team'
  | 'services'
  | 'support'
  | 'agents'
  | 'notifications'
  | 'profile';

const MAIN_NAV: { id: Route; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Home', icon: <LayoutDashboard size={20} /> },
  { id: 'planning', label: 'Jobs', icon: <BriefcaseBusiness size={20} /> },
  { id: 'tracking', label: 'Tracking', icon: <Activity size={20} /> },
  { id: 'team', label: 'Team', icon: <Users size={20} /> },
  { id: 'services', label: 'Services', icon: <Wrench size={20} /> },
];

export default function StaffShell() {
  const { user, role, signOut, accessToken } = useAuth();
  const [route, setRoute] = useState<Route>('dashboard');
  const [signingOut, setSigningOut] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationRefreshKey, setNotificationRefreshKey] = useState(0);
  const countRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSuperAdmin = role === 'super_admin';

  const go = (next: string) => {
    if (
      [
        'dashboard',
        'planning',
        'tracking',
        'team',
        'services',
        'support',
        'agents',
        'notifications',
        'profile',
      ].includes(next)
    ) {
      setRoute(next as Route);
    }
  };

  const refreshUnreadCount = useCallback(async () => {
    if (!accessToken || !['super_admin', 'dispatcher'].includes(role || '')) {
      setUnreadCount(0);
      return;
    }

    try {
      const response = await api.get('/admin/notifications', {
        params: { limit: 1, offset: 0 },
      });
      setUnreadCount(Number(response.data?.unread_count || 0));
    } catch {
      // Notification screen handles and displays its own API errors.
    }
  }, [accessToken, role]);

  useEffect(() => {
    void refreshUnreadCount();
    const timer = setInterval(() => void refreshUnreadCount(), 60000);
    return () => clearInterval(timer);
  }, [refreshUnreadCount]);

  useEffect(() => {
    if (!accessToken || !user?.tenant_id) return;

    const socketUrl = (
      process.env.EXPO_PUBLIC_SOCKET_IO_URL || getApiBaseUrl()
    ).replace(/\/$/, '');

    const socket = io(socketUrl, {
      auth: (callback) =>
        callback({ token: getAccessToken() || accessToken }),
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 8,
      reconnectionDelay: 1500,
      timeout: 10000,
    });

    const queueCountRefresh = () => {
      if (countRefreshTimer.current) {
        clearTimeout(countRefreshTimer.current);
      }

      countRefreshTimer.current = setTimeout(() => {
        countRefreshTimer.current = null;
        void refreshUnreadCount();
        setNotificationRefreshKey((value) => value + 1);
      }, 500);
    };

    socket.on('new_notification', queueCountRefresh);
    socket.on('notification', queueCountRefresh);
    socket.on('notification:new', queueCountRefresh);

    socket.on(
      'notification:unread_count',
      (payload: number | { unread_count?: number; count?: number }) => {
        const next =
          typeof payload === 'number'
            ? payload
            : Number(payload?.unread_count ?? payload?.count ?? 0);

        if (Number.isFinite(next)) {
          setUnreadCount(Math.max(0, next));
        }
        setNotificationRefreshKey((value) => value + 1);
      },
    );

    return () => {
      if (countRefreshTimer.current) {
        clearTimeout(countRefreshTimer.current);
        countRefreshTimer.current = null;
      }
      socket.removeAllListeners();
      socket.disconnect();
    };
  }, [accessToken, user?.tenant_id, refreshUnreadCount]);

  const logout = async () => {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <SafeAreaView
      style={{ flex: 1, backgroundColor: '#EAF1EB' }}
      edges={['top', 'left', 'right', 'bottom']}
    >
      <View style={{ flex: 1, backgroundColor: '#EAF1EB' }}>
        {/* Top navigation / app bar */}
        <View
          style={{
            minHeight: 76,
            paddingHorizontal: 17,
            paddingVertical: 10,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#FFFFFF',
            borderBottomWidth: 1,
            borderBottomColor: '#DCE8DF',
          }}
        >
          <View style={{ flex: 1, justifyContent: 'center' }}>
            <BrandMark compact />
            <Text
              style={{
                marginTop: -1,
                marginLeft: 3,
                color: '#668071',
                fontSize: 8,
                fontWeight: '900',
                letterSpacing: 1.5,
              }}
            >
              FIELD OPERATIONS
            </Text>
          </View>

          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <Pressable
              onPress={() => go('notifications')}
              accessibilityRole="button"
              accessibilityLabel={`${unreadCount} unread notifications`}
              style={({ pressed }) => ({
                width: 42,
                height: 42,
                borderRadius: 15,
                backgroundColor: unreadCount ? '#FFF0ED' : '#F0F6F1',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: pressed ? 0.75 : 1,
              })}
            >
              <Bell
                size={19}
                color={unreadCount ? '#C45A4D' : '#476B55'}
                strokeWidth={2.2}
              />
              {unreadCount > 0 ? (
                <View
                  style={{
                    position: 'absolute',
                    top: -3,
                    right: -3,
                    minWidth: 17,
                    height: 17,
                    borderRadius: 9,
                    backgroundColor: '#D94B45',
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingHorizontal: 3,
                    borderWidth: 2,
                    borderColor: '#FFFFFF',
                  }}
                >
                  <Text
                    style={{
                      color: '#FFFFFF',
                      fontSize: 8,
                      fontWeight: '900',
                    }}
                  >
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </Text>
                </View>
              ) : null}
            </Pressable>

            <Pressable
              onPress={() => go('profile')}
              accessibilityRole="button"
              accessibilityLabel="Open profile"
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 8,
                paddingLeft: 2,
              }}
            >
              <View
                style={{
                  width: 41,
                  height: 41,
                  borderRadius: 15,
                  backgroundColor: '#DDEEE2',
                  borderWidth: 1,
                  borderColor: '#C8DFCE',
                  justifyContent: 'center',
                  alignItems: 'center',
                }}
              >
                <Text
                  style={{
                    color: '#245B3B',
                    fontSize: 12,
                    fontWeight: '900',
                  }}
                >
                  {initials(
                    `${user?.first_name || ''} ${user?.last_name || ''}`,
                  )}
                </Text>
              </View>
            </Pressable>

            <Pressable
              onPress={() => void logout()}
              disabled={signingOut}
              accessibilityRole="button"
              accessibilityLabel="Sign out"
              style={({ pressed }) => ({
                width: 42,
                height: 42,
                borderRadius: 15,
                backgroundColor: '#FFF1EF',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: signingOut ? 0.5 : pressed ? 0.7 : 1,
              })}
            >
              <LogOut size={19} color="#B94B43" strokeWidth={2.2} />
            </Pressable>
          </View>
        </View>

        {/* Active screen */}
        <View style={{ flex: 1, backgroundColor: '#EAF1EB' }}>
          {route === 'dashboard' ? (
            <DashboardScreen user={user!} onNavigate={go} />
          ) : null}
          {route === 'planning' ? <PlanningScreen /> : null}
          {route === 'tracking' ? <TrackingScreen /> : null}
          {route === 'team' ? <TeamScreen onNavigate={go} /> : null}
          {route === 'services' ? <ServicesScreen /> : null}
          {route === 'support' ? <SupportScreen /> : null}
          {route === 'agents' && isSuperAdmin ? <AgentTrackingScreen /> : null}
          {route === 'notifications' ? (
            <NotificationScreen
              onUnreadCountChange={setUnreadCount}
              refreshKey={notificationRefreshKey}
            />
          ) : null}
          {route === 'profile' ? <ProfileScreen /> : null}
        </View>

        {/* Floating bottom navigation */}
        <View
          style={{
            paddingHorizontal: 13,
            paddingTop: 8,
            paddingBottom: 5,
            backgroundColor: '#EAF1EB',
          }}
        >
          <View
            style={{
              minHeight: 68,
              paddingHorizontal: 5,
              paddingVertical: 6,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-around',
              backgroundColor: '#FFFFFF',
              borderRadius: 23,
              borderWidth: 1,
              borderColor: '#DCE8DF',
              shadowColor: '#173B2A',
              shadowOffset: { width: 0, height: 5 },
              shadowOpacity: 0.10,
              shadowRadius: 12,
              elevation: 5,
            }}
          >
            {MAIN_NAV.map((item) => {
              const active = route === item.id;
              return (
                <Pressable
                  key={item.id}
                  onPress={() => go(item.id)}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  style={({ pressed }) => ({
                    flex: 1,
                    minHeight: 54,
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 4,
                    borderRadius: 17,
                    backgroundColor: active ? '#E5F2E9' : 'transparent',
                    opacity: pressed ? 0.72 : 1,
                    marginHorizontal: 2,
                  })}
                >
                  {React.cloneElement(
                    item.icon as React.ReactElement<any>,
                    {
                      color: active ? '#236341' : '#829187',
                      strokeWidth: active ? 2.5 : 2,
                    },
                  )}
                  <Text
                    style={{
                      color: active ? '#236341' : '#829187',
                      fontSize: 10,
                      fontWeight: active ? '900' : '700',
                    }}
                  >
                    {item.label}
                  </Text>
                  {active ? (
                    <View
                      style={{
                        position: 'absolute',
                        bottom: 3,
                        width: 14,
                        height: 3,
                        borderRadius: 3,
                        backgroundColor: '#39845A',
                      }}
                    />
                  ) : null}
                </Pressable>
              );
            })}


          </View>
        </View>

        <FloatingSupportButton onPress={() => go('support')} />
      </View>

    </SafeAreaView>
  );
}

type SupportCorner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';

function FloatingSupportButton({ onPress }: { onPress: () => void }) {
  const { width, height } = useWindowDimensions();
  const [corner, setCorner] = useState<SupportCorner>('bottom-right');

  const panResponder = React.useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => false,
        onMoveShouldSetPanResponder: (_event, gesture) =>
          Math.abs(gesture.dx) > 6 || Math.abs(gesture.dy) > 6,
        onPanResponderRelease: (_event, gesture) => {
          const x = gesture.moveX || gesture.x0 + gesture.dx;
          const y = gesture.moveY || gesture.y0 + gesture.dy;
          const horizontal = x < width / 2 ? 'left' : 'right';
          const vertical = y < height / 2 ? 'top' : 'bottom';
          setCorner(`${vertical}-${horizontal}` as SupportCorner);
        },
      }),
    [width, height],
  );

  const position =
    corner === 'top-left'
      ? { top: 88, left: 14 }
      : corner === 'top-right'
        ? { top: 88, right: 14 }
        : corner === 'bottom-left'
          ? { bottom: 94, left: 14 }
          : { bottom: 94, right: 14 };

  return (
    <View
      pointerEvents="box-none"
      style={{
        position: 'absolute',
        ...position,
        zIndex: 1000,
        elevation: 12,
      }}
      {...panResponder.panHandlers}
    >
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel="Open customer support"
        style={({ pressed }) => ({
          width: 54,
          height: 54,
          borderRadius: 27,
          backgroundColor: '#176B43',
          alignItems: 'center',
          justifyContent: 'center',
          borderWidth: 2,
          borderColor: '#FFFFFF',
          shadowColor: '#123B27',
          shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.24,
          shadowRadius: 7,
          elevation: 8,
          opacity: pressed ? 0.82 : 1,
        })}
      >
        <Headset size={23} color="#FFFFFF" strokeWidth={2.2} />
        <View
          style={{
            position: 'absolute',
            right: -1,
            top: -1,
            width: 13,
            height: 13,
            borderRadius: 7,
            backgroundColor: '#F6B94A',
            borderWidth: 2,
            borderColor: '#FFFFFF',
          }}
        />
      </Pressable>
    </View>
  );
}

