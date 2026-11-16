import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, RefreshControl, Text, View } from 'react-native';
import MapView, { Callout, Marker, PROVIDER_GOOGLE, type Region } from 'react-native-maps';
import { Activity, MapPin, Navigation, Radio, Search, Signal, SignalZero } from 'lucide-react-native';
import { useAuth } from '../auth/AuthContext';
import { getTechnicians } from '../api/operations';
import { useLiveTracking, type LivePosition } from '../hooks/useLiveTracking';
import { Card, EmptyState, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField } from '../components/UI';
import { colors } from '../theme';
import { statusLabel, statusTone, text, timeAgo } from '../utils/format';

const DEFAULT_REGION: Region = { latitude: 13.0827, longitude: 80.2707, latitudeDelta: 0.28, longitudeDelta: 0.28 };
const ONLINE_WINDOW_MS = 120_000;
type Filter = 'ALL' | 'ONLINE' | 'OFFLINE';

function timestampMs(value?: string | null): number {
  if (!value) return Number.NaN;
  let normalized = value.trim();
  // The web live-tracking page treats timezone-naive server timestamps as UTC.
  if (normalized.includes('T') && !normalized.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(normalized)) normalized += 'Z';
  return Date.parse(normalized);
}

function validCoordinates(latitude: number, longitude: number) {
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    && latitude >= -90 && latitude <= 90
    && longitude >= -180 && longitude <= 180
    && !(latitude === 0 && longitude === 0);
}

export default function TrackingScreen() {
  const { user, accessToken } = useAuth();
  const { positions, setPositions, connection, lastFrameAt } = useLiveTracking(user?.tenant_id, accessToken);
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [search, setSearch] = useState('');
  const [now, setNow] = useState(Date.now());
  const mapRef = useRef<MapView>(null);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    try {
      const list = await getTechnicians({ page: 1, limit: 200 });
      setTechnicians(list);
      setPositions(previous => {
        const next = { ...previous };
        for (const tech of list) {
          const id = String(tech.tech_id || tech.technician_id || tech.id || '');
          const lat = Number(tech.latitude), lng = Number(tech.longitude);
          if (!id || !validCoordinates(lat, lng)) continue;
          const timestamp = tech.last_ping || null;
          if (!timestamp) continue;
          const incoming = timestampMs(timestamp), existing = next[id] ? timestampMs(next[id].timestamp) : -1;
          if (Number.isFinite(existing) && Number.isFinite(incoming) && incoming < existing) continue;
          next[id] = {
            technician_id: id,
            technician_name: tech.technician_name,
            latitude: lat,
            longitude: lng,
            status: tech.technician_status,
            timestamp: timestamp || new Date().toISOString(),
            accuracy: null,
            job_id: null,
            eta: null,
          };
        }
        return next;
      });
    } catch {
      // Keep the last good snapshot and current socket positions during a transient API outage.
    } finally { setLoading(false); setRefreshing(false); }
  }, [setPositions]);

  useEffect(() => {
    void load();
    // The web workspace refreshes the technician roster every 3 seconds. Use a
    // gentler 10-second roster refresh on mobile; GPS itself remains socket-driven.
    const timer = setInterval(() => { void load(true); }, 10000);
    const clock = setInterval(() => setNow(Date.now()), 10000);
    return () => { clearInterval(timer); clearInterval(clock); };
  }, [load]);

  const rows = useMemo(() => technicians.map(tech => {
    const keys = [String(tech.technician_id ?? ''), String(tech.tech_id ?? ''), String(tech.id ?? '')].filter(Boolean);
    const liveCandidates = keys.map(key => positions[key]).filter(Boolean) as LivePosition[];
    const live = [...liveCandidates].sort((a, b) => timestampMs(b.timestamp) - timestampMs(a.timestamp))[0];
    const apiPing = tech.last_ping || null;
    const livePing = live?.timestamp || null;
    const useLive = !!live && Number.isFinite(timestampMs(livePing))
      && (!apiPing || timestampMs(livePing) >= timestampMs(apiPing));
    const latitude = useLive ? live!.latitude : Number(tech.latitude);
    const longitude = useLive ? live!.longitude : Number(tech.longitude);
    const hasLocation = validCoordinates(latitude, longitude);
    const lastPing = useLive ? livePing : apiPing || livePing;
    const pingTime = timestampMs(lastPing);
    const online = Number.isFinite(pingTime) && now >= pingTime - 30000 && now - pingTime <= ONLINE_WINDOW_MS;
    const id = String(tech.technician_id ?? tech.tech_id ?? tech.id ?? '');
    return {
      ...tech,
      mapId: id,
      gps: useLive ? live : undefined,
      lat: hasLocation ? latitude : null,
      lng: hasLocation ? longitude : null,
      lastPing,
      online,
    };
  }), [technicians, positions, now]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter(row => {
      if (filter === 'ONLINE' && !row.online) return false;
      if (filter === 'OFFLINE' && row.online) return false;
      return !term || [row.technician_name, row.technician_skill, row.technician_location, row.email, row.phone_number]
        .some(value => String(value || '').toLowerCase().includes(term));
    });
  }, [rows, filter, search]);

  const mapped = useMemo(() => visible.filter(row => row.lat !== null && row.lng !== null), [visible]);
  const mapRegion = useMemo<Region>(() => mapped.length ? {
    latitude: mapped[0].lat as number,
    longitude: mapped[0].lng as number,
    latitudeDelta: 0.12,
    longitudeDelta: 0.12,
  } : DEFAULT_REGION, [mapped]);

  useEffect(() => {
    if (mapped.length > 0) mapRef.current?.animateToRegion(mapRegion, 350);
  }, [mapRegion, mapped.length]);

  const selectedRow = rows.find(row => row.mapId === selected);
  const centerOn = (row: any) => {
    setSelected(row.mapId);
    if (row.lat !== null && row.lng !== null) {
      mapRef.current?.animateToRegion({ latitude: row.lat, longitude: row.lng, latitudeDelta: 0.035, longitudeDelta: 0.035 }, 500);
    }
  };
  const onlineCount = rows.filter(row => row.online).length;
  const offlineCount = rows.length - onlineCount;

  return <ScreenScroll contentContainerStyle={{ paddingBottom: 30 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
    <ScreenHeading title="Live tracking" subtitle="Tenant-scoped technician locations and heartbeat freshness." action={<Pill label={connection === 'connected' ? 'Live connected' : connection} tone={connection === 'connected' ? 'green' : connection === 'reconnecting' ? 'amber' : 'neutral'} />} />
    <View style={{ flexDirection: 'row', gap: 9 }}>
      <Card style={{ flex: 1, padding: 13, gap: 4 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Radio size={15} color={colors.forest} /><Text style={{ color: colors.muted, fontSize: 10 }}>Technicians</Text></View><Text style={{ color: colors.ink, fontSize: 22, fontWeight: '900' }}>{rows.length}</Text></Card>
      <Card style={{ flex: 1, padding: 13, gap: 4 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Signal size={15} color={colors.forest} /><Text style={{ color: colors.muted, fontSize: 10 }}>Online</Text></View><Text style={{ color: colors.forest, fontSize: 22, fontWeight: '900' }}>{onlineCount}</Text></Card>
      <Card style={{ flex: 1, padding: 13, gap: 4 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><SignalZero size={15} color={colors.amber} /><Text style={{ color: colors.muted, fontSize: 10 }}>Offline</Text></View><Text style={{ color: colors.amber, fontSize: 22, fontWeight: '900' }}>{offlineCount}</Text></Card>
    </View>
    <SearchField value={search} onChangeText={setSearch} placeholder="Search technician, skill, zone or contact…" />
    <View style={{ flexDirection: 'row', backgroundColor: '#E7EFEA', padding: 4, borderRadius: 13, gap: 4 }}>
      {(['ALL', 'ONLINE', 'OFFLINE'] as Filter[]).map(value => <PrimaryButton key={value} title={value === 'ALL' ? `All (${rows.length})` : value === 'ONLINE' ? `Online (${onlineCount})` : `Offline (${offlineCount})`} compact style={{ flex: 1 }} variant={filter === value ? 'primary' : 'ghost'} onPress={() => setFilter(value)} />)}
    </View>
    <Card style={{ padding: 8, gap: 7 }}>
      <View style={{ paddingHorizontal: 8, paddingTop: 5, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 13 }}>Technician map</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{mapped.length} mapped / {visible.length} visible</Text></View>
      <View style={{ height: 350, borderRadius: 15, overflow: 'hidden' }}>
        <MapView ref={mapRef} provider={Platform.OS === 'android' ? PROVIDER_GOOGLE : undefined} style={{ flex: 1 }} initialRegion={DEFAULT_REGION} onMapReady={() => { if (mapped.length > 0) mapRef.current?.animateToRegion(mapRegion, 350); }} showsUserLocation={false} showsCompass showsScale>
          {mapped.map(row => <Marker key={row.mapId} coordinate={{ latitude: row.lat as number, longitude: row.lng as number }} pinColor={row.online ? '#168653' : '#D97706'} onPress={() => setSelected(row.mapId)}>
            <Callout onPress={() => setSelected(row.mapId)}><View style={{ width: 190, gap: 4 }}><Text style={{ fontWeight: '900', color: '#17231D' }}>{text(row.technician_name)}</Text><Text style={{ color: '#536159', fontSize: 11 }}>{row.online ? 'Online' : 'Offline'} · {statusLabel(row.technician_status)}</Text><Text style={{ color: '#536159', fontSize: 10 }}>Last GPS: {timeAgo(row.lastPing)}</Text>{row.gps?.job_id ? <Text style={{ color: '#536159', fontSize: 10 }}>Job #{row.gps.job_id}</Text> : null}</View></Callout>
          </Marker>)}
        </MapView>
      </View>
      <Text style={{ color: colors.muted, fontSize: 10, paddingHorizontal: 7 }}>GPS coordinates are accepted only when valid and non-zero. Live updates arrive through the backend’s authenticated tenant-wide WebSocket subscription.</Text>
    </Card>
    {selectedRow ? <Card style={{ gap: 8, borderColor: colors.forest }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 14 }}>{text(selectedRow.technician_name, 'Technician')}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{text(selectedRow.technician_skill)} · {text(selectedRow.technician_location)}</Text></View><Pill label={selectedRow.online ? 'Online' : 'Offline'} tone={selectedRow.online ? 'green' : 'amber'} /></View>
      <Text style={{ color: colors.text, fontSize: 11 }}>Work status: {statusLabel(selectedRow.technician_status)}</Text>
      <Text style={{ color: colors.muted, fontSize: 11 }}>Last heartbeat: {selectedRow.lastPing ? timeAgo(selectedRow.lastPing) : 'No heartbeat received'}</Text>
      {selectedRow.lat !== null && selectedRow.lng !== null ? <Text style={{ color: colors.text, fontSize: 11 }}>GPS: {selectedRow.lat.toFixed(5)}, {selectedRow.lng.toFixed(5)}</Text> : <Text style={{ color: colors.amber, fontSize: 11 }}>No valid GPS location recorded.</Text>}
      {selectedRow.gps?.job_id ? <Text style={{ color: colors.text, fontSize: 11 }}>Job: #{selectedRow.gps.job_id}</Text> : null}
      {selectedRow.gps?.eta ? <Text style={{ color: colors.text, fontSize: 11 }}>Live ETA: {selectedRow.gps.eta}</Text> : null}
      {selectedRow.gps?.eta_duration_minutes != null && Number.isFinite(Number(selectedRow.gps.eta_duration_minutes)) ? <Text style={{ color: colors.text, fontSize: 11 }}>ETA duration: {Math.max(0, Math.round(Number(selectedRow.gps.eta_duration_minutes)))} min</Text> : null}
      {selectedRow.phone_number || selectedRow.email ? <Text style={{ color: colors.muted, fontSize: 11 }}>{[selectedRow.phone_number, selectedRow.email].filter(Boolean).join(' · ')}</Text> : null}
      <PrimaryButton title="Clear selection" compact variant="ghost" onPress={() => setSelected(null)} />
    </Card> : null}
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Activity size={13} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 10 }}>Last WebSocket frame: {lastFrameAt ? new Date(lastFrameAt).toLocaleTimeString() : 'Waiting for server frame'}</Text></View>
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 16 }}>Technicians</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{visible.length} shown · roster refresh 10s</Text></View>
    {visible.length === 0 ? <EmptyState title={loading ? 'Loading technicians…' : 'No matching technicians'} detail="Change the online filter or search, then refresh the roster." onRetry={() => load(true)} /> : visible.map(row => <Card key={row.mapId} onPress={() => centerOn(row)} style={{ flexDirection: 'row', alignItems: 'center', gap: 11 }}>
      <View style={{ width: 38, height: 38, borderRadius: 13, backgroundColor: row.online ? colors.mint : '#FFF1DF', alignItems: 'center', justifyContent: 'center' }}>{row.online ? <Navigation size={17} color={colors.forest} /> : <MapPin size={17} color={colors.amber} />}</View>
      <View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.ink, fontSize: 13, fontWeight: '900' }}>{text(row.technician_name, 'Technician')}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{text(row.technician_skill)} · {row.lastPing ? timeAgo(row.lastPing) : 'No heartbeat'}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{row.lat !== null && row.lng !== null ? 'GPS available' : 'No GPS position'}</Text></View>
      <Pill label={row.online ? 'Online' : 'Offline'} tone={row.online ? 'green' : 'amber'} />
    </Card>)}
  </ScreenScroll>;
}
