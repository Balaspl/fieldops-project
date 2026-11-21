import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ImageBackground, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import {
  MapPin,
  Navigation,
  ChevronRight,
  Users,
  Wifi,
  WifiOff,
  Crosshair,
  Leaf,
  Wrench,
  Clock3,
} from 'lucide-react-native';
import { useAuth } from '../auth/AuthContext';
import { getTechnicians } from '../api/operations';
import { useLiveTracking, type LivePosition } from '../hooks/useLiveTracking';
import {
  Card,
  EmptyState,
  Pill,
  PrimaryButton,
  SearchField,
} from '../components/UI';
import OlaTechnicianMap, {
  type OlaTechnician,
} from '../../shared/maps/OlaTechnicianMap';
import { colors } from '../theme';
import { statusLabel, text } from '../utils/format';

const ONLINE_WINDOW_MS = 120_000;
const FUTURE_CLOCK_TOLERANCE_MS = 30_000;
const ROSTER_REFRESH_MS = 10_000;
const CLOCK_REFRESH_MS = 10_000;

type Filter = 'ALL' | 'ONLINE' | 'OFFLINE';
type Technician = Record<string, any>;
type TrackingRow = Technician & {
  mapId: string;
  gps?: LivePosition;
  lat: number | null;
  lng: number | null;
  lastPing: string | null;
  online: boolean;
};

/** Parse server timestamps consistently. Naive ISO timestamps are treated as UTC. */
function timestampMs(value?: string | null): number {
  if (!value || typeof value !== 'string') return Number.NaN;

  let normalized = value.trim();
  if (!normalized) return Number.NaN;

  if (
    normalized.includes('T') &&
    !/[zZ]$/.test(normalized) &&
    !/[+-]\d{2}:?\d{2}$/.test(normalized)
  ) {
    normalized += 'Z';
  }

  return Date.parse(normalized);
}

function validCoordinates(latitude: number, longitude: number): boolean {
  return (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180 &&
    !(latitude === 0 && longitude === 0)
  );
}

/** Human-readable heartbeat age, including protection against invalid dates. */
function formatLastSeen(
  value: string | null | undefined,
  currentTime: number,
): string {
  if (!value) return 'No heartbeat received';

  const timestamp = timestampMs(value);
  if (!Number.isFinite(timestamp)) return 'No heartbeat received';

  const seconds = Math.max(0, Math.floor((currentTime - timestamp) / 1000));
  if (seconds < 60) return `Last seen ${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Last seen ${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Last seen ${hours}h ago`;

  return `Last seen ${Math.floor(hours / 24)}d ago`;
}

function getTechnicianId(tech: Technician): string {
  const candidate = [tech.technician_id, tech.tech_id, tech.id].find(
    value => value !== null && value !== undefined && String(value).trim() !== '',
  );
  return candidate === undefined ? '' : String(candidate);
}

export default function TrackingScreen() {
  const { user, accessToken } = useAuth();
  const {
    positions,
    setPositions,
    connection,
    lastFrameAt,
  } = useLiveTracking(user?.tenant_id, accessToken);

  const [technicians, setTechnicians] = useState<Technician[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [search, setSearch] = useState('');
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const list = await getTechnicians({ page: 1, limit: 200 });
      const safeList = Array.isArray(list) ? list : [];

      setTechnicians(safeList);
      setLoadError('');

      // Merge roster GPS into the live-position cache without allowing an
      // older API heartbeat to replace a newer WebSocket position.
      setPositions(previous => {
        const next = { ...previous };

        for (const tech of safeList) {
          const id = getTechnicianId(tech);
          const latitude = Number(tech.latitude);
          const longitude = Number(tech.longitude);

          if (!id || !validCoordinates(latitude, longitude)) continue;

          const timestamp = tech.last_ping || null;
          if (!timestamp) continue;

          const incoming = timestampMs(timestamp);
          if (!Number.isFinite(incoming)) continue;

          const existing = next[id]
            ? timestampMs(next[id].timestamp)
            : Number.NEGATIVE_INFINITY;

          if (
            Number.isFinite(existing) &&
            Number.isFinite(incoming) &&
            incoming < existing
          ) {
            continue;
          }

          next[id] = {
            ...(next[id] || {}),
            technician_id: id,
            technician_name: tech.technician_name,
            latitude,
            longitude,
            status: tech.technician_status,
            timestamp,
            accuracy: next[id]?.accuracy ?? null,
            job_id: next[id]?.job_id ?? null,
            eta: next[id]?.eta ?? null,
            eta_duration_minutes:
              next[id]?.eta_duration_minutes ?? null,
          };
        }

        return next;
      });
    } catch {
      // Keep the last successful roster and WebSocket positions on failure.
      setLoadError('Unable to refresh technicians. Showing the last available data.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [setPositions]);

  useEffect(() => {
    void load();

    const rosterTimer = setInterval(() => {
      void load(true);
    }, ROSTER_REFRESH_MS);

    const clockTimer = setInterval(() => {
      setNow(Date.now());
    }, CLOCK_REFRESH_MS);

    return () => {
      clearInterval(rosterTimer);
      clearInterval(clockTimer);
    };
  }, [load]);

  const rows = useMemo<TrackingRow[]>(() => {
    return technicians.map(tech => {
      const keys = [
        String(tech.technician_id ?? ''),
        String(tech.tech_id ?? ''),
        String(tech.id ?? ''),
      ].filter(Boolean);

      const liveCandidates = keys
        .map(key => positions[key])
        .filter(Boolean) as LivePosition[];

      const live = [...liveCandidates].sort((a, b) => {
        return timestampMs(b.timestamp) - timestampMs(a.timestamp);
      })[0];

      const apiPing = tech.last_ping || null;
      const livePing = live?.timestamp || null;
      const apiPingMs = timestampMs(apiPing);
      const livePingMs = timestampMs(livePing);

      const useLive = Boolean(
        live &&
        Number.isFinite(livePingMs) &&
        (!Number.isFinite(apiPingMs) || livePingMs >= apiPingMs),
      );

      const latitude = useLive ? Number(live?.latitude) : Number(tech.latitude);
      const longitude = useLive ? Number(live?.longitude) : Number(tech.longitude);
      const hasLocation = validCoordinates(latitude, longitude);
      const lastPing = useLive ? livePing : apiPing || livePing;
      const pingTime = timestampMs(lastPing);

      const online =
        Number.isFinite(pingTime) &&
        now >= pingTime - FUTURE_CLOCK_TOLERANCE_MS &&
        now - pingTime <= ONLINE_WINDOW_MS;

      return {
        ...tech,
        mapId: getTechnicianId(tech),
        gps: useLive ? live : undefined,
        lat: hasLocation ? latitude : null,
        lng: hasLocation ? longitude : null,
        lastPing,
        online,
      };
    });
  }, [technicians, positions, now]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();

    return rows.filter(row => {
      if (filter === 'ONLINE' && !row.online) return false;
      if (filter === 'OFFLINE' && row.online) return false;

      return (
        !term ||
        [
          row.technician_name,
          row.technician_skill,
          row.technician_location,
          row.email,
          row.phone_number,
        ].some(value => String(value || '').toLowerCase().includes(term))
      );
    });
  }, [rows, filter, search]);

  const mapped = useMemo(
    () => visible.filter(row => row.lat !== null && row.lng !== null),
    [visible],
  );

  const mapTechnicians = useMemo<OlaTechnician[]>(() => {
    return mapped.map(row => ({
      id: row.mapId,
      name: text(row.technician_name, 'Technician'),
      latitude: row.lat as number,
      longitude: row.lng as number,
      online: row.online,
      status: row.technician_status
        ? String(row.technician_status)
        : row.gps?.status != null
          ? String(row.gps.status)
          : null,
      lastPing: row.lastPing,
      jobId: row.gps?.job_id ?? null,
    }));
  }, [mapped]);

  const selectedRow = rows.find(row => row.mapId === selected);
  const onlineCount = rows.filter(row => row.online).length;
  const offlineCount = rows.length - onlineCount;

  const connectionLabel =
    connection === 'connected' ? 'Live connected' : connection;

  const centerOn = (row: TrackingRow) => {
    setSelected(row.mapId);
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
      contentContainerStyle={{ paddingHorizontal: 14, paddingTop: 14, paddingBottom: 34, gap: 13, backgroundColor: 'transparent' }}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => void load(true)}
          tintColor={colors.forest}
        />
      }
    >
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          paddingHorizontal: 3,
          paddingVertical: 5,
        }}
      >
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={{ color: '#103F2B', fontSize: 27, fontWeight: '900', letterSpacing: -0.8 }}>
            Live Tracking
          </Text>
          <Text style={{ color: '#244F3A', fontSize: 12, fontWeight: '600' }}>
            Monitor your field team in real time
          </Text>
        </View>
        <View
          style={{
            minHeight: 40,
            paddingHorizontal: 12,
            borderRadius: 24,
            borderWidth: 1.2,
            borderColor: connection === 'connected' ? '#9BCFA9' : '#E7D2A9',
            backgroundColor: connection === 'connected' ? 'rgba(232,248,228,0.96)' : 'rgba(255,246,226,0.96)',
            alignItems: 'center',
            justifyContent: 'center',
            flexDirection: 'row',
            gap: 6,
          }}
        >
          <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: connection === 'connected' ? '#16813C' : '#D08713' }} />
          <Text style={{ color: connection === 'connected' ? '#15582D' : '#92510A', fontSize: 10, fontWeight: '900' }}>
            {connectionLabel}
          </Text>
        </View>
      </View>

      {/* Team metrics styled to match the Team directory screen */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 19, borderWidth: 1, borderColor: '#CFE3D0', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
          <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#E2F3E3', alignItems: 'center', justifyContent: 'center' }}>
            <Users size={22} color="#075B36" />
          </View>
          <View style={{ flex: 1, gap: 1 }}>
            <Text style={{ color: '#073F27', fontSize: 23, fontWeight: '900' }}>{rows.length}</Text>
            <Text style={{ color: '#244F3A', fontSize: 10, fontWeight: '800' }}>Total team</Text>
          </View>
        </View>
        <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(229,248,220,0.96)', borderRadius: 19, borderWidth: 1, borderColor: '#C7E5B9', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
          <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#D7F0CB', alignItems: 'center', justifyContent: 'center' }}>
            <Wifi size={22} color="#16813C" />
          </View>
          <View style={{ flex: 1, gap: 1 }}>
            <Text style={{ color: '#16813C', fontSize: 23, fontWeight: '900' }}>{onlineCount}</Text>
            <Text style={{ color: '#285B35', fontSize: 10, fontWeight: '800' }}>Online</Text>
          </View>
        </View>
        <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(255,235,229,0.96)', borderRadius: 19, borderWidth: 1, borderColor: '#F0D0C8', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
          <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#FBE0D9', alignItems: 'center', justifyContent: 'center' }}>
            <WifiOff size={22} color="#D52D2D" />
          </View>
          <View style={{ flex: 1, gap: 1 }}>
            <Text style={{ color: '#A52222', fontSize: 23, fontWeight: '900' }}>{offlineCount}</Text>
            <Text style={{ color: '#80413C', fontSize: 10, fontWeight: '800' }}>Offline</Text>
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <View style={{ flex: 1 }}>
          <SearchField
            value={search}
            onChangeText={setSearch}
            placeholder="Search name, skill, zone or contact..."
          />
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7, paddingRight: 3 }}>
        {([
          { key: 'ALL', label: `All (${rows.length})`, dot: '#075B36', bg: '#075B36', fg: '#FFFFFF' },
          { key: 'ONLINE', label: `Online (${onlineCount})`, dot: '#20A83B', bg: 'rgba(234,249,225,0.96)', fg: '#15582D' },
          { key: 'OFFLINE', label: `Offline (${offlineCount})`, dot: '#E32929', bg: 'rgba(255,232,229,0.97)', fg: '#962727' },
        ] as const).map(item => {
          const active = filter === item.key;
          return (
            <Pressable
              key={item.key}
              onPress={() => setFilter(item.key)}
              style={{
                minHeight: 37,
                paddingHorizontal: 13,
                borderRadius: 22,
                backgroundColor: active && item.key === 'ALL' ? '#075B36' : item.bg,
                borderWidth: 1,
                borderColor: active ? '#2C8B45' : 'rgba(190,216,185,0.85)',
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                elevation: active ? 2 : 0,
              }}
            >
              {item.key !== 'ALL' ? <View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: item.dot }} /> : null}
              <Text style={{ color: item.fg, fontSize: 10, fontWeight: '900' }}>{item.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <Card style={{ padding: 11, gap: 9, backgroundColor: 'rgba(255,255,255,0.95)', borderColor: '#D8E8D4', borderRadius: 21, shadowColor: '#17432B', shadowOpacity: 0.10, shadowRadius: 6, shadowOffset: { width: 0, height: 3 }, elevation: 3 }}>
        <View
          style={{
            paddingHorizontal: 8,
            paddingTop: 5,
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 34, height: 34, borderRadius: 12, backgroundColor: '#E2F3E3', alignItems: 'center', justifyContent: 'center' }}>
              <Crosshair size={17} color="#075B36" />
            </View>
            <View style={{ gap: 2 }}>
              <Text style={{ color: colors.ink, fontWeight: '900', fontSize: 13 }}>
                Live technician map
              </Text>
              <Text style={{ color: '#607367', fontSize: 9 }}>
                Real-time GPS positions
              </Text>
            </View>
          </View>
          <View style={{ backgroundColor: '#E5F0E4', paddingHorizontal: 9, paddingVertical: 6, borderRadius: 10 }}>
            <Text style={{ color: '#175334', fontSize: 10, fontWeight: '800' }}>
              {mapped.length} / {visible.length}
            </Text>
          </View>
        </View>

        <View style={{ height: 360, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: '#CFE1D0' }}>
          <OlaTechnicianMap
            technicians={mapTechnicians}
            selectedTechnicianId={selected}
            onSelectTechnician={setSelected}
            style={{ flex: 1 }}
          />
        </View>

        <Text style={{ color: '#607367', fontSize: 10, paddingHorizontal: 7, lineHeight: 15 }}>
          Live technician positions update through the secure tenant connection.
        </Text>
      </Card>

      {selectedRow ? (
        <Card style={{ gap: 10, padding: 14, backgroundColor: 'rgba(255,255,255,0.96)', borderColor: '#D8E8D4', borderLeftWidth: 5, borderLeftColor: '#3ABF32', borderRadius: 21, shadowColor: '#17432B', shadowOpacity: 0.10, shadowRadius: 6, shadowOffset: { width: 0, height: 3 }, elevation: 3 }}>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              gap: 8,
            }}
          >
            <View style={{ flex: 1, gap: 3 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Leaf size={14} color="#3C8A38" fill="#7CBF48" />
                <Text style={{ color: colors.ink, fontWeight: '900', fontSize: 14 }}>
                  {text(selectedRow.technician_name, 'Technician')}
                </Text>
              </View>
              <Text style={{ color: colors.muted, fontSize: 10 }}>
                {text(selectedRow.technician_skill)} · {text(selectedRow.technician_location)}
              </Text>
            </View>
            <Pill
              label={selectedRow.online ? 'Online' : 'Offline'}
              tone={selectedRow.online ? 'green' : 'amber'}
            />
          </View>

          <Text style={{ color: colors.text, fontSize: 11 }}>
            Work status: {statusLabel(selectedRow.technician_status)}
          </Text>
          <Text style={{ color: colors.muted, fontSize: 11 }}>
            {formatLastSeen(selectedRow.lastPing, now)}
          </Text>

          {selectedRow.lat !== null && selectedRow.lng !== null ? (
            <Text style={{ color: colors.text, fontSize: 11 }}>
              GPS: {selectedRow.lat.toFixed(5)}, {selectedRow.lng.toFixed(5)}
            </Text>
          ) : (
            <Text style={{ color: colors.amber, fontSize: 11 }}>
              No valid GPS location recorded.
            </Text>
          )}

          {selectedRow.gps?.job_id ? (
            <Text style={{ color: colors.text, fontSize: 11 }}>
              Job: #{selectedRow.gps.job_id}
            </Text>
          ) : null}
          {selectedRow.gps?.eta ? (
            <Text style={{ color: colors.text, fontSize: 11 }}>
              Live ETA: {selectedRow.gps.eta}
            </Text>
          ) : null}
          {selectedRow.gps?.eta_duration_minutes != null &&
          Number.isFinite(Number(selectedRow.gps.eta_duration_minutes)) ? (
            <Text style={{ color: colors.text, fontSize: 11 }}>
              ETA duration:{' '}
              {Math.max(0, Math.round(Number(selectedRow.gps.eta_duration_minutes)))} min
            </Text>
          ) : null}
          {selectedRow.phone_number || selectedRow.email ? (
            <Text style={{ color: colors.muted, fontSize: 11 }}>
              {[selectedRow.phone_number, selectedRow.email].filter(Boolean).join(' · ')}
            </Text>
          ) : null}

          <PrimaryButton
            title="Clear selection"
            compact
            variant="ghost"
            onPress={() => setSelected(null)}
          />
        </Card>
      ) : null}

      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          padding: 12,
          borderRadius: 14,
          backgroundColor: 'rgba(255,255,255,0.90)',
          borderWidth: 1,
          borderColor: '#D8E8D4',
        }}
      >
        <Clock3 size={14} color="#668072" />
        <Text style={{ color: colors.muted, fontSize: 10 }}>
          Last WebSocket frame:{' '}
          {lastFrameAt
            ? new Date(lastFrameAt).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true })
            : 'Waiting for server frame'}
        </Text>
      </View>

      {loadError ? (
        <Text style={{ color: colors.amber, fontSize: 11 }}>{loadError}</Text>
      ) : null}

      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: 3,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
          <Leaf size={22} color="#3C8A38" fill="#7CBF48" />
          <View style={{ gap: 2 }}>
            <Text style={{ color: '#103F2B', fontWeight: '900', fontSize: 19 }}>
              Technicians
            </Text>
            <Text style={{ color: '#607367', fontSize: 10 }}>
              Select a technician to view live details
            </Text>
          </View>
        </View>
        <View style={{ backgroundColor: 'rgba(231,247,215,0.96)', borderRadius: 20, borderWidth: 1, borderColor: '#CFE1C8', paddingHorizontal: 10, paddingVertical: 7 }}>
          <Text style={{ color: '#164C2F', fontSize: 10, fontWeight: '900' }}>
            {visible.length} SHOWN
          </Text>
        </View>
      </View>

      {visible.length === 0 ? (
        <EmptyState
          title={loading ? 'Loading technicians…' : 'No matching technicians'}
          detail="Change the online filter or search, then refresh the roster."
          onRetry={() => void load(true)}
        />
      ) : (
        visible.map(row => (
          <Card
            key={row.mapId}
            onPress={() => centerOn(row)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 12,
              padding: 12,
              borderRadius: 21,
              backgroundColor: 'rgba(255,255,255,0.95)',
              borderColor: selected === row.mapId ? '#9CCB7F' : '#D8E8D4',
              borderLeftWidth: 5,
              borderLeftColor: selected === row.mapId ? '#075B36' : row.online ? '#3ABF32' : '#F05B61',
              shadowColor: '#17432B',
              shadowOpacity: 0.10,
              shadowRadius: 6,
              shadowOffset: { width: 0, height: 3 },
              elevation: 3,
            }}
          >
            <View
              style={{
                width: 48,
                height: 48,
                borderRadius: 16,
                backgroundColor: row.online ? '#DDF4C9' : '#FBE0D9',
                borderWidth: 1,
                borderColor: row.online ? '#C7E5B9' : '#F0D0C8',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {row.online ? (
                <Navigation size={19} color={row.online ? '#075B36' : '#D52D2D'} />
              ) : (
                <MapPin size={19} color="#D52D2D" />
              )}
            </View>

            <View style={{ flex: 1, gap: 4 }}>
              <Text style={{ color: colors.ink, fontSize: 13, fontWeight: '900' }}>
                {text(row.technician_name, 'Technician')}
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <Wrench size={11} color="#315C45" />
                <Text numberOfLines={1} style={{ color: '#30483A', fontSize: 10, flex: 1 }}>
                  {text(row.technician_skill, 'Skill not set')}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <MapPin size={11} color="#315C45" />
                <Text numberOfLines={1} style={{ color: '#607367', fontSize: 10, flex: 1 }}>
                  {text(row.technician_location, row.lat !== null && row.lng !== null ? 'GPS available' : 'No GPS position')}
                </Text>
              </View>
              <Text style={{ color: '#718277', fontSize: 9, fontWeight: '700' }}>
                {row.lastPing ? formatLastSeen(row.lastPing, now) : 'No heartbeat received'}
              </Text>
            </View>

            <View style={{ alignItems: 'flex-end', gap: 7 }}>
              <Pill
                label={row.online ? 'Online' : 'Offline'}
                tone={row.online ? 'green' : 'amber'}
              />
              <ChevronRight size={16} color="#91A399" />
            </View>
          </Card>
        ))
      )}
    </ScrollView>
    </ImageBackground>
  );
}
