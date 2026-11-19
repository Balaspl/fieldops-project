
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshControl, Text, View } from 'react-native';
import {
  Activity,
  MapPin,
  Navigation,
  Radio,
  Signal,
  SignalZero,
} from 'lucide-react-native';

import { useAuth } from '../auth/AuthContext';
import { getTechnicians } from '../api/operations';
import { useLiveTracking, type LivePosition } from '../hooks/useLiveTracking';
import {
  Card,
  EmptyState,
  Pill,
  PrimaryButton,
  ScreenHeading,
  ScreenScroll,
  SearchField,
} from '../components/UI';
import { colors } from '../theme';
import { statusLabel, text, timeAgo } from '../utils/format';
import OlaTechnicianMap, {
  type OlaTechnician,
} from '../../../fo/src/shared/maps/OlaTechnicianMap';

const ONLINE_WINDOW_MS = 120_000;

type Filter = 'ALL' | 'ONLINE' | 'OFFLINE';

function timestampMs(value?: string | null): number {
  if (!value) return Number.NaN;

  let normalized = value.trim();

  // Treat timezone-naive backend timestamps as UTC.
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

function formatLastSeen(
  value: string | null | undefined,
  currentTime: number,
): string {
  if (!value) return 'No heartbeat received';

  let normalized = value.trim();

  if (
    normalized.includes('T') &&
    !normalized.endsWith('Z') &&
    !/[+-]\d{2}:\d{2}$/.test(normalized)
  ) {
    normalized += 'Z';
  }

  const timestamp = Date.parse(normalized);

  if (!Number.isFinite(timestamp)) {
    return 'No heartbeat received';
  }

  const seconds = Math.max(
    0,
    Math.floor((currentTime - timestamp) / 1000),
  );

  if (seconds < 60) return `Last seen ${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);

  if (minutes < 60) return `Last seen ${minutes}m ago`;
  return `Last seen ${Math.floor(minutes / 60)}h ago`;
}

export default function TrackingScreen() {
  const { user, accessToken } = useAuth();

  const {
    positions,
    setPositions,
    connection,
    lastFrameAt,
  } = useLiveTracking(user?.tenant_id, accessToken);

  const [technicians, setTechnicians] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState('');
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
      const list = await getTechnicians({
        page: 1,
        limit: 200,
      });

      setTechnicians(list);

      setPositions((previous) => {
        const next = { ...previous };

        for (const tech of list) {
          const id = String(
            tech.tech_id ||
            tech.technician_id ||
            tech.id ||
            '',
          );

          const latitude = Number(tech.latitude);
          const longitude = Number(tech.longitude);

          if (!id || !validCoordinates(latitude, longitude)) {
            continue;
          }

          const timestamp = tech.last_ping || null;

          if (!timestamp) {
            continue;
          }

          const incoming = timestampMs(timestamp);
          const existing = next[id]
            ? timestampMs(next[id].timestamp)
            : -1;

          if (
            Number.isFinite(existing) &&
            Number.isFinite(incoming) &&
            incoming < existing
          ) {
            continue;
          }

          next[id] = {
            technician_id: id,
            technician_name: tech.technician_name,
            latitude,
            longitude,
            status: tech.technician_status,
            timestamp,
            accuracy: null,
            job_id: null,
            eta: null,
          };
        }

        return next;
      });
    } catch {
      // Preserve the last successful roster and socket positions
      // during temporary API outages.
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [setPositions]);

  useEffect(() => {
    void load();

    // Refresh the technician roster every 10 seconds.
    const rosterTimer = setInterval(() => {
      void load(true);
    }, 10_000);

    // Refresh online/offline calculations every 10 seconds.
    const clockTimer = setInterval(() => {
      setNow(Date.now());
    }, 10_000);

    return () => {
      clearInterval(rosterTimer);
      clearInterval(clockTimer);
    };
  }, [load]);

  const rows = useMemo(() => {
    return technicians.map((tech) => {
      const keys = [
        String(tech.technician_id ?? ''),
        String(tech.tech_id ?? ''),
        String(tech.id ?? ''),
      ].filter(Boolean);

      const liveCandidates = keys
        .map((key) => positions[key])
        .filter(Boolean) as LivePosition[];

      const live = [...liveCandidates].sort(
        (a, b) =>
          timestampMs(b.timestamp) - timestampMs(a.timestamp),
      )[0];

      const apiPing = tech.last_ping || null;
      const livePing = live?.timestamp || null;

      const useLive = Boolean(
        live &&
        Number.isFinite(timestampMs(livePing)) &&
        (!apiPing || timestampMs(livePing) >= timestampMs(apiPing)),
      );

      const latitude = useLive
        ? live!.latitude
        : Number(tech.latitude);

      const longitude = useLive
        ? live!.longitude
        : Number(tech.longitude);

      const hasLocation = validCoordinates(latitude, longitude);

      const lastPing = useLive
        ? livePing
        : apiPing || livePing;

      const pingTime = timestampMs(lastPing);

      const online =
        Number.isFinite(pingTime) &&
        now >= pingTime - 30_000 &&
        now - pingTime <= ONLINE_WINDOW_MS;

      const id = String(
        tech.technician_id ??
        tech.tech_id ??
        tech.id ??
        '',
      );

      return {
        ...tech,
        mapId: id,
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

    return rows.filter((row) => {
      if (filter === 'ONLINE' && !row.online) {
        return false;
      }

      if (filter === 'OFFLINE' && row.online) {
        return false;
      }

      return (
        !term ||
        [
          row.technician_name,
          row.technician_skill,
          row.technician_location,
          row.email,
          row.phone_number,
        ].some((value) =>
          String(value || '').toLowerCase().includes(term),
        )
      );
    });
  }, [rows, filter, search]);

  const mapped = useMemo(
    () =>
      visible.filter(
        (row) => row.lat !== null && row.lng !== null,
      ),
    [visible],
  );

  const mapTechnicians = useMemo<OlaTechnician[]>(
    () =>
      mapped.map((row) => ({
        id: row.mapId,
        name: text(row.technician_name, 'Technician'),
        latitude: Number(row.lat),
        longitude: Number(row.lng),
        online: row.online,
        status:
          row.technician_status ??
          row.gps?.status ??
          null,
        lastPing: row.lastPing ?? null,
        jobId: row.gps?.job_id ?? null,
      })),
    [mapped],
  );

  const selectedRow = rows.find(
    (row) => row.mapId === selected,
  );

  const onlineCount = rows.filter(
    (row) => row.online,
  ).length;

  const offlineCount = rows.length - onlineCount;
  const mappedRows = useMemo(() => visible.filter(row => row.latitude !== null && row.longitude !== null), [visible]);
  const mapPayload = useMemo(() => mappedRows.map(row => ({
    id: row.trackingId,
    name: row.technician_name || `Technician ${row.trackingId}`,
    online: row.online,
    latitude: row.latitude,
    longitude: row.longitude,
    lastSeen: formatLastSeen(row.lastPing, now),
  })), [mappedRows, now]);

  const connectionLabel =
    connection === 'connected'
      ? 'Live connected'
      : connection;

  return (
    <ScreenScroll
      contentContainerStyle={{ paddingBottom: 30 }}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => void load(true)}
          tintColor={colors.forest}
        />
      }
    >
      <ScreenHeading
        title="Live tracking"
        subtitle="Tenant-scoped technician locations and heartbeat freshness."
        action={
          <Pill
            label={connectionLabel}
            tone={
              connection === 'connected'
                ? 'green'
                : connection === 'reconnecting'
                  ? 'amber'
                  : 'neutral'
            }
          />
        }
      />

      {/* Technician statistics */}
      <View style={{ flexDirection: 'row', gap: 9 }}>
        <Card style={{ flex: 1, padding: 13, gap: 4 }}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Radio size={15} color={colors.forest} />
            <Text style={{ color: colors.muted, fontSize: 10 }}>
              Technicians
            </Text>
          </View>

          <Text
            style={{
              color: colors.ink,
              fontSize: 22,
              fontWeight: '900',
            }}
          >
            {rows.length}
          </Text>
        </Card>

        <Card style={{ flex: 1, padding: 13, gap: 4 }}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Signal size={15} color={colors.forest} />
            <Text style={{ color: colors.muted, fontSize: 10 }}>
              Online
            </Text>
          </View>

          <Text
            style={{
              color: colors.forest,
              fontSize: 22,
              fontWeight: '900',
            }}
          >
            {onlineCount}
          </Text>
        </Card>

        <Card style={{ flex: 1, padding: 13, gap: 4 }}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <SignalZero size={15} color={colors.amber} />
            <Text style={{ color: colors.muted, fontSize: 10 }}>
              Offline
            </Text>
          </View>

          <Text
            style={{
              color: colors.amber,
              fontSize: 22,
              fontWeight: '900',
            }}
          >
            {offlineCount}
          </Text>
        </Card>
      </View>

      {/* Technician search */}
      <SearchField
        value={search}
        onChangeText={setSearch}
        placeholder="Search technician, skill, zone or contact…"
      />

      {/* Online/offline filters */}
      <View
        style={{
          flexDirection: 'row',
          backgroundColor: '#E7EFEA',
          padding: 4,
          borderRadius: 13,
          gap: 4,
        }}
      >
        {(['ALL', 'ONLINE', 'OFFLINE'] as Filter[]).map(
          (value) => (
            <PrimaryButton
              key={value}
              title={
                value === 'ALL'
                  ? `All (${rows.length})`
                  : value === 'ONLINE'
                    ? `Online (${onlineCount})`
                    : `Offline (${offlineCount})`
              }
              compact
              style={{ flex: 1 }}
              variant={
                filter === value ? 'primary' : 'ghost'
              }
              onPress={() => setFilter(value)}
            />
          ),
        )}
      </View>

      {/* Ola Maps */}
      <Card style={{ padding: 8, gap: 7 }}>
        <View
          style={{
            paddingHorizontal: 8,
            paddingTop: 5,
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Text
            style={{
              color: colors.ink,
              fontWeight: '900',
              fontSize: 13,
            }}
          >
            Technician map
          </Text>

          <Text
            style={{
              color: colors.muted,
              fontSize: 10,
            }}
          >
            {mapped.length} mapped / {visible.length} visible
          </Text>
        </View>

        <OlaTechnicianMap
          technicians={mapTechnicians}
          selectedTechnicianId={selected}
          onSelectTechnician={setSelected}
          style={{ height: 350 }}
        />

        <Text
          style={{
            color: colors.muted,
            fontSize: 10,
            paddingHorizontal: 7,
          }}
        >
          All visible technicians with valid GPS coordinates
          appear on this Ola Maps view. Live updates arrive
          through the authenticated tenant-wide WebSocket
          subscription.
        </Text>
      </Card>

      {/* Selected technician details */}
      {selectedRow ? (
        <Card
          style={{
            gap: 8,
            borderColor: colors.forest,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              gap: 8,
            }}
          >
            <View style={{ flex: 1, gap: 3 }}>
              <Text
                style={{
                  color: colors.ink,
                  fontWeight: '900',
                  fontSize: 14,
                }}
              >
                {text(
                  selectedRow.technician_name,
                  'Technician',
                )}
              </Text>

              <Text
                style={{
                  color: colors.muted,
                  fontSize: 10,
                }}
              >
                {text(selectedRow.technician_skill)} ·{' '}
                {text(selectedRow.technician_location)}
              </Text>
            </View>

            <Pill
              label={
                selectedRow.online ? 'Online' : 'Offline'
              }
              tone={
                selectedRow.online ? 'green' : 'amber'
              }
            />
          </View>

          <Text style={{ color: colors.text, fontSize: 11 }}>
            Work status:{' '}
            {statusLabel(selectedRow.technician_status)}
          </Text>

          <Text style={{ color: colors.muted, fontSize: 11 }}>
            Last heartbeat:{' '}
            {selectedRow.lastPing
              ? timeAgo(selectedRow.lastPing)
              : 'No heartbeat received'}
          </Text>

          {selectedRow.lat !== null &&
          selectedRow.lng !== null ? (
            <Text
              style={{ color: colors.text, fontSize: 11 }}
            >
              GPS: {selectedRow.lat.toFixed(5)},{' '}
              {selectedRow.lng.toFixed(5)}
            </Text>
          ) : (
            <Text
              style={{ color: colors.amber, fontSize: 11 }}
            >
              No valid GPS location recorded.
            </Text>
          )}

          {selectedRow.gps?.job_id ? (
            <Text
              style={{ color: colors.text, fontSize: 11 }}
            >
              Job: #{selectedRow.gps.job_id}
            </Text>
          ) : null}

          {selectedRow.gps?.eta ? (
            <Text
              style={{ color: colors.text, fontSize: 11 }}
            >
              Live ETA: {selectedRow.gps.eta}
            </Text>
          ) : null}

          {selectedRow.gps?.eta_duration_minutes != null &&
          Number.isFinite(
            Number(selectedRow.gps.eta_duration_minutes),
          ) ? (
            <Text
              style={{ color: colors.text, fontSize: 11 }}
            >
              ETA duration:{' '}
              {Math.max(
                0,
                Math.round(
                  Number(
                    selectedRow.gps.eta_duration_minutes,
                  ),
                ),
              )}{' '}
              min
            </Text>
          ) : null}

          {selectedRow.phone_number ||
          selectedRow.email ? (
            <Text
              style={{ color: colors.muted, fontSize: 11 }}
            >
              {[
                selectedRow.phone_number,
                selectedRow.email,
              ]
                .filter(Boolean)
                .join(' · ')}
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

      {/* WebSocket status */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <Activity size={13} color={colors.muted} />

        <Text
          style={{
            color: colors.muted,
            fontSize: 10,
          }}
        >
          Last WebSocket frame:{' '}
          {lastFrameAt
            ? new Date(lastFrameAt).toLocaleTimeString()
            : 'Waiting for server frame'}
        </Text>
      </View>

      {/* Technician list */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Text
          style={{
            color: colors.ink,
            fontWeight: '900',
            fontSize: 16,
          }}
        >
          Technicians
        </Text>

        <Text
          style={{
            color: colors.muted,
            fontSize: 10,
          }}
        >
          {visible.length} shown · roster refresh 10s
        </Text>
      </View>

      {visible.length === 0 ? (
        <EmptyState
          title={
            loading
              ? 'Loading technicians…'
              : 'No matching technicians'
          }
          detail="Change the online filter or search, then refresh the roster."
          onRetry={() => void load(true)}
        />
      ) : (
        visible.map((row) => (
          <Card
            key={row.mapId}
            onPress={() => setSelected(row.mapId)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 11,
            }}
          >
            <View
              style={{
                width: 38,
                height: 38,
                borderRadius: 13,
                backgroundColor: row.online
                  ? colors.mint
                  : '#FFF1DF',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {row.online ? (
                <Navigation
                  size={17}
                  color={colors.forest}
                />
              ) : (
                <MapPin
                  size={17}
                  color={colors.amber}
                />
              )}
            </View>

            <View style={{ flex: 1, gap: 4 }}>
              <Text
                style={{
                  color: colors.ink,
                  fontSize: 13,
                  fontWeight: '900',
                }}
              >
                {text(
                  row.technician_name,
                  'Technician',
                )}
              </Text>

              <Text
                style={{
                  color: colors.muted,
                  fontSize: 10,
                }}
              >
                {text(row.technician_skill)} ·{' '}
                {row.lastPing
                  ? timeAgo(row.lastPing)
                  : 'No heartbeat'}
              </Text>

              <Text
                style={{
                  color: colors.muted,
                  fontSize: 10,
                }}
              >
                {row.lat !== null && row.lng !== null
                  ? 'GPS available'
                  : 'No GPS position'}
              </Text>
            </View>

            <Pill
              label={row.online ? 'Online' : 'Offline'}
              tone={row.online ? 'green' : 'amber'}
            />
          </Card>
        ))
      )}
    </ScreenScroll>
  );
}

function buildOlaMapHtml(apiKey: string) {
  const escapedKey = JSON.stringify(apiKey);
  return `<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<style>
html,body,#map{width:100%;height:100%;margin:0;padding:0;overflow:hidden;background:#eaf0ed}
.tech-marker{border:0;background:transparent;padding:0;display:flex;flex-direction:column;align-items:center;gap:4px;white-space:nowrap;font-family:Arial,sans-serif}
.tech-dot{width:32px;height:32px;border:3px solid white;border-radius:50%;display:grid;place-items:center;color:white;font-size:11px;font-weight:800;box-shadow:0 2px 8px rgba(15,23,42,.3)}
.tech-label{max-width:170px;overflow:hidden;text-overflow:ellipsis;padding:3px 6px;border-radius:6px;color:#1f2937;background:rgba(255,255,255,.96);border:1px solid #dde7e1;font-size:10px;font-weight:700;box-shadow:0 1px 4px rgba(15,23,42,.12)}
</style><script src="https://unpkg.com/olamaps-web-sdk@1.4.0/dist/olamaps-web-sdk.umd.js"></script></head>
<body><div id="map"></div><script>
(function(){
  var markers = new Map();
  var map = null;
  var fitted = false;
  var key = ${escapedKey};
  function send(message){try{if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(JSON.stringify(message));}catch(e){}}
  window.onerror=function(message){send({type:'error',message:String(message||'Ola Maps failed to load.')});};
  window.__updateTechnicians=function(serialized){
    if(!map)return;
    var items=[];
    try{items=JSON.parse(serialized)||[];}catch(e){return;}
    var valid=items.filter(function(t){return Number.isFinite(Number(t.latitude))&&Number.isFinite(Number(t.longitude))&&Number(t.latitude)>=-90&&Number(t.latitude)<=90&&Number(t.longitude)>=-180&&Number(t.longitude)<=180&&!(Number(t.latitude)===0&&Number(t.longitude)===0);});
    var wanted=new Set(valid.map(function(t){return String(t.id);}));
    markers.forEach(function(entry,id){if(!wanted.has(id)){try{entry.marker.remove();}catch(e){}markers.delete(id);}});
    valid.forEach(function(t){
      var id=String(t.id),lng=Number(t.longitude),lat=Number(t.latitude),entry=markers.get(id);
      if(!entry){
        var el=document.createElement('div');el.className='tech-marker';
        var dot=document.createElement('div');dot.className='tech-dot';
        var label=document.createElement('div');label.className='tech-label';
        el.appendChild(dot);el.appendChild(label);
        el.addEventListener('click',function(){send({type:'select',id:id});});
        var marker=window.__ola.addMarker({element:el,anchor:'bottom'}).setLngLat([lng,lat]).addTo(map);
        entry={marker:marker,element:el};markers.set(id,entry);
      }else{entry.marker.setLngLat([lng,lat]);}
      var initials=String(t.name||'').split(/\\s+/).filter(Boolean).slice(0,2).map(function(part){return part.charAt(0).toUpperCase();}).join('')||'?';
      entry.element.querySelector('.tech-dot').style.background=t.online?'#059669':'#64748b';
      entry.element.querySelector('.tech-dot').textContent=initials;
      entry.element.querySelector('.tech-label').textContent=String(t.name||'Technician')+' · '+(t.online?'Online':'Offline');
      entry.element.title=String(t.name||'Technician')+' — '+(t.online?'Online':'Offline')+'\\n'+String(t.lastSeen||'No heartbeat received');
    });
    if(valid.length&&!fitted){
      fitted=true;
      if(valid.length===1){map.flyTo({center:[Number(valid[0].longitude),Number(valid[0].latitude)],zoom:14});}
      else{var lngs=valid.map(function(t){return Number(t.longitude);}),lats=valid.map(function(t){return Number(t.latitude);});map.fitBounds([[Math.min.apply(null,lngs),Math.min.apply(null,lats)],[Math.max.apply(null,lngs),Math.max.apply(null,lats)]],{padding:44,maxZoom:14});}
    }
  };
  window.__focusTechnician=function(id){var entry=markers.get(String(id));if(!entry)return;var p=entry.marker.getLngLat();map.flyTo({center:[p.lng,p.lat],zoom:15,essential:true});};
  if(!key){send({type:'error',message:'Ola Maps API key is not configured.'});return;}
  if(typeof window.OlaMaps!=='function'){send({type:'error',message:'Ola Maps Web SDK could not be loaded.'});return;}
  (async function(){try{
    window.__ola=new window.OlaMaps({apiKey:key});
    map=await window.__ola.init({style:'https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json',container:'map',center:[80.2707,13.0827],zoom:11});
    if(!map)throw new Error('Ola Maps did not return a map instance.');
    try{map.addControl(window.__ola.addNavigationControls({showCompass:true}),'top-right');}catch(e){}
    send({type:'ready'});
  }catch(error){send({type:'error',message:error&&error.message?error.message:'Unable to initialize Ola Maps.'});}})();
})();
</script></body></html>`;
}
