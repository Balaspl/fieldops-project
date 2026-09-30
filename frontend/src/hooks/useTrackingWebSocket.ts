import { useEffect, useRef, useCallback } from 'react';
import { useTrackingStore } from '../store/trackingStore';
import { useNotificationStore } from '../store/notificationStore';

/**
 * Live tracking WebSocket.
 *
 * What changed
 * ------------
 * 1. position_update frames now store receivedAt / ageAtReceipt / source.
 * 2. Reconnect never gives up (backoff 1 s -> 15 s with jitter).
 * 3. Watchdog: no frame for 75 s -> the socket is treated as dead and replaced
 *    (the server sends a ping every 30 s, so this is ~2 missed heartbeats).
 * 4. Reconnects immediately on `online` and when the tab becomes visible.
 * 5. connect() never opens a second socket while one is OPEN/CONNECTING, and
 *    detaches handlers from the old socket before replacing it.
 * 6. Token: optional 4th argument `authToken` (pass the customer's own JWT).
 *    The 'dev-dispatcher-token' fallback is removed. The tenant is read from the
 *    JWT, the 'tenant-1' fallback is removed, and ?tenant_id= is no longer sent
 *    (the server always takes the tenant from the JWT).
 * 7. Server `error` frames are logged, pings are answered with a pong, and
 *    positions older than the one already stored for the same job are ignored
 *    (a cached snapshot can no longer overwrite a newer live position).
 *
 * Debug: same switch as the map.
 *   localStorage.setItem('trackingDebug', '1')  // on   (reload)
 *   localStorage.setItem('trackingDebug', '0')  // off  (reload)
 *   or open the page with ?trackdebug=1
 */

const WATCHDOG_MS = 75_000;
const BACKOFF_START_MS = 1_000;
const BACKOFF_MAX_MS = 15_000;

function readDebugFlag(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const stored = window.localStorage.getItem('trackingDebug');
    if (stored === '0') return false;
    if (stored === '1') return true;
    if (new URLSearchParams(window.location.search).has('trackdebug')) return true;
  } catch {
    // ignore storage errors
  }
  return Boolean((import.meta as any).env?.DEV);
}

const DEBUG_ENABLED = readDebugFlag();

const dbg = (tag: string, data?: unknown) => {
  if (!DEBUG_ENABLED) return;
  if (data === undefined) console.log(`[WS] ${tag}`);
  else console.log(`[WS] ${tag}`, data);
};

function decodeJwtClaims(token: string): Record<string, any> | null {
  try {
    const part = token.split('.')[1];
    if (!part) return null;
    return JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return null;
  }
}

export const useTrackingWebSocket = (
  tenantId: string,
  jobId?: string,
  channelTenantId?: string,
  authToken?: string,
) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const watchdogRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const disposedRef = useRef<boolean>(false);
  const connectRef = useRef<((force?: boolean) => void) | null>(null);

  const connectionStatus = useTrackingStore((s) => s.connectionStatus);
  const updateTechnicianLocation = useTrackingStore((s) => s.updateTechnicianLocation);
  const setConnectionStatus = useTrackingStore((s) => s.setConnectionStatus);
  const setReconnectAttempt = useTrackingStore((s) => s.setReconnectAttempt);
  const updateJobStatus = useTrackingStore((s) => s.updateJobStatus);
  const updateJobETA = useTrackingStore((s) => s.updateJobETA);

  const clearReconnectTimer = () => {
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  };

  const clearWatchdog = () => {
    if (watchdogRef.current !== null) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
  };

  /** Detach every handler, then close. Prevents duplicate reconnect loops. */
  const discardSocket = (ws: WebSocket | null) => {
    if (!ws) return;
    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    try {
      ws.close();
    } catch {
      // ignore
    }
    if (wsRef.current === ws) wsRef.current = null;
  };

  const scheduleReconnect = useCallback(() => {
    if (disposedRef.current) return;

    reconnectAttemptsRef.current += 1;
    const attempt = reconnectAttemptsRef.current;

    const base = Math.min(BACKOFF_START_MS * Math.pow(2, attempt - 1), BACKOFF_MAX_MS);
    const delay = Math.round(base * (0.75 + Math.random() * 0.5)); // +-25 % jitter

    setConnectionStatus('reconnecting');
    setReconnectAttempt(attempt);
    dbg(`reconnecting in ${delay} ms (attempt ${attempt})`);

    clearReconnectTimer();
    reconnectTimeoutRef.current = window.setTimeout(() => {
      reconnectTimeoutRef.current = null;
      connectRef.current?.(true);
    }, delay);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = useCallback(
    (force = false) => {
      if (disposedRef.current) return;

      const existing = wsRef.current;
      if (
        !force &&
        existing &&
        (existing.readyState === WebSocket.OPEN ||
          existing.readyState === WebSocket.CONNECTING)
      ) {
        return; // already connected / connecting: never open a second socket
      }

      discardSocket(existing);
      clearReconnectTimer();
      clearWatchdog();

      // ── Token: explicit prop first, then storage. No dev fallback. ──────
      const token =
        authToken ||
        localStorage.getItem('token') ||
        localStorage.getItem('access_token') ||
        (import.meta as any).env?.VITE_AUTH_TOKEN ||
        '';

      if (!token) {
        console.error(
          '[useTrackingWebSocket] No auth token found. Pass the logged-in user\'s JWT ' +
            'as the 4th argument, or store it as "token" / "access_token".',
        );
        setConnectionStatus('disconnected');
        return;
      }

      // ── Tenant: the JWT is the source of truth ─────────────────────────
      const claims = decodeJwtClaims(token);
      const jwtTenant: string = claims?.tenant_id ? String(claims.tenant_id) : '';
      const finalTenant = jwtTenant || tenantId || localStorage.getItem('tenant_id') || '';
      const trackingTenant = channelTenantId || finalTenant;

      if (jwtTenant && tenantId && jwtTenant !== tenantId) {
        dbg('tenant prop differs from JWT tenant (JWT wins for dispatcher channels)', {
          tenantProp: tenantId,
          jwtTenant,
        });
      }

      if (!finalTenant && !jobId) {
        console.error('[useTrackingWebSocket] Cannot determine tenant for dispatcher channel.');
        setConnectionStatus('disconnected');
        return;
      }

      setConnectionStatus(reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'disconnected');
      setReconnectAttempt(reconnectAttemptsRef.current);

      const socketUrl = (import.meta as any).env?.VITE_SOCKET_URL || 'http://localhost:8000';
      const wsUrl = socketUrl.replace(/^http/, 'ws') + '/ws/v1/tracking';
      // No &tenant_id=... : the server takes the tenant from the JWT.
      const fullWsUrl = `${wsUrl}?token=${encodeURIComponent(token)}`;

      dbg('connecting', {
        url: wsUrl,
        role: claims?.role,
        jwtTenant,
        finalTenant,
        trackingTenant,
        jobId: jobId ?? null,
      });

      const armWatchdog = (ws: WebSocket) => {
        clearWatchdog();
        watchdogRef.current = window.setTimeout(() => {
          console.warn(
            `[useTrackingWebSocket] No frames for ${WATCHDOG_MS / 1000}s; replacing socket.`,
          );
          discardSocket(ws);
          scheduleReconnect();
        }, WATCHDOG_MS);
      };

      try {
        const ws = new WebSocket(fullWsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (wsRef.current !== ws) return;

          setConnectionStatus('connected');
          reconnectAttemptsRef.current = 0;
          setReconnectAttempt(0);
          armWatchdog(ws);

          const send = (channel: string) => {
            dbg('subscribe', channel);
            ws.send(JSON.stringify({ type: 'subscribe', channel }));
          };

          if (jobId) {
            // Customer / technician job tracking uses the narrow job channel.
            send(`tenant:${trackingTenant}:job:${jobId}`);
          } else {
            send(`tenant:${finalTenant}:all`);
            send(`tenant:${finalTenant}:events:geofence`);
          }
        };

        ws.onmessage = (event) => {
          if (wsRef.current !== ws) return;
          armWatchdog(ws); // any frame proves the connection is alive

          try {
            const data = JSON.parse(event.data);

            // ── Control frames ───────────────────────────────────────────
            if (data.type === 'ping') {
              try {
                ws.send(JSON.stringify({ type: 'pong', timestamp: data.timestamp }));
              } catch {
                // ignore
              }
              return;
            }
            if (data.type === 'heartbeat' || data.type === 'unsubscribed') {
              return;
            }
            if (data.type === 'subscribed') {
              dbg('subscribed', data.channel);
              return;
            }
            if (data.type === 'error') {
              console.error('[useTrackingWebSocket] Server error frame:', data);
              return;
            }

            // ── Geofence alert ───────────────────────────────────────────
            const isGeofenceEvent =
              data.type === 'geofence' ||
              data.event === 'ENTRY' ||
              data.event === 'EXIT' ||
              (data.channel && String(data.channel).endsWith('events:geofence'));

            if (isGeofenceEvent) {
              const techId = String(
                data.technician_id || data.tech_id || data.technician?.tech_id || 'unknown',
              );
              const storedTech = useTrackingStore.getState().technicians[techId];
              const techName = String(
                data.technician_name ||
                  data.technician?.name ||
                  data.tech_name ||
                  storedTech?.name ||
                  'Technician',
              );
              const geoJobId = String(data.job_id || data.job?.id || 'unknown');
              const jobTitle = String(data.job_title || data.job?.title || 'Job');
              const jobLocation = String(data.job_location || data.job?.location || 'Job Site');
              const eventType = data.event === 'EXIT' ? 'EXIT' : 'ENTRY';

              useNotificationStore.getState().addAlert({
                techId,
                techName,
                jobId: geoJobId,
                jobTitle,
                jobLocation,
                eventType,
                timestamp: data.timestamp || new Date().toISOString(),
              });
              return;
            }

            // ── Position update ──────────────────────────────────────────
            if (data.type === 'position_update' || data.latitude !== undefined) {
              const techId = String(data.technician_id || data.id);
              const rawStatus = data.status || data.job_status || 'Available';
              const jobIdStr = data.job_id ? String(data.job_id) : null;

              // Ignore a position older than the one already stored for the same job
              // (e.g. a cached snapshot arriving after a newer live update).
              const incomingTs = Date.parse(data.timestamp || '');
              const existing = useTrackingStore.getState().technicians[techId];
              if (
                existing &&
                jobIdStr &&
                String(existing.job_id ?? '') === jobIdStr &&
                Number.isFinite(incomingTs)
              ) {
                const existingTs = Date.parse(existing.lastPing || '');
                if (Number.isFinite(existingTs) && incomingTs < existingTs) {
                  dbg('ignored older position', {
                    incoming: data.timestamp,
                    stored: existing.lastPing,
                    source: data.source,
                  });
                  return;
                }
              }

              if (jobIdStr) {
                if (data.job_status) {
                  updateJobStatus(jobIdStr, String(data.job_status));
                }
                updateJobETA(jobIdStr, {
                  eta: data.eta || null,
                  duration_minutes:
                    data.eta_duration_minutes !== undefined && data.eta_duration_minutes !== null
                      ? Number(data.eta_duration_minutes)
                      : null,
                  traffic_delay_minutes:
                    data.traffic_delay_minutes !== undefined && data.traffic_delay_minutes !== null
                      ? Number(data.traffic_delay_minutes)
                      : null,
                  source: data.eta_source || (data.fallback ? 'estimated' : 'calculated'),
                });
              }

              dbg('position_update', {
                tech: techId,
                job: jobIdStr,
                lat: data.latitude,
                lng: data.longitude,
                source: data.source,
                age_seconds: data.age_seconds,
              });

              updateTechnicianLocation(techId, {
                latitude: Number(data.latitude),
                longitude: Number(data.longitude),
                status: rawStatus,
                ...(data.technician_name ? { name: String(data.technician_name) } : {}),
                accuracy: data.accuracy == null ? null : Number(data.accuracy),
                altitude:
                  data.altitude !== undefined && data.altitude !== null
                    ? Number(data.altitude)
                    : null,
                eta: data.eta || null,
                eta_duration_minutes:
                  data.eta_duration_minutes !== undefined && data.eta_duration_minutes !== null
                    ? Number(data.eta_duration_minutes)
                    : null,
                job_id: jobIdStr,
                lastPing: data.timestamp || new Date().toISOString(),

                // freshness (read by JobLiveTrackingMap)
                receivedAt: Date.now(),
                ageAtReceipt: data.age_seconds != null ? Number(data.age_seconds) : 0,
                source: data.source ? String(data.source) : undefined,
              });
            }
          } catch (err) {
            console.error('[useTrackingWebSocket] Error parsing message:', err);
          }
        };

        ws.onerror = (err) => {
          console.error('[useTrackingWebSocket] Error:', err);
          // onclose always follows an error; reconnect is scheduled there.
        };

        ws.onclose = (ev) => {
          if (wsRef.current !== ws) return; // an old, already replaced socket
          wsRef.current = null;
          clearWatchdog();
          setConnectionStatus('disconnected');

          if (ev.code === 1008) {
            console.error(
              `[useTrackingWebSocket] Closed by server (1008): ${ev.reason || 'policy violation'}. ` +
                'Usually a wrong/expired token or a tenant mismatch.',
            );
          } else {
            dbg('closed', { code: ev.code, reason: ev.reason });
          }

          scheduleReconnect();
        };
      } catch (e) {
        console.error('[useTrackingWebSocket] Failed to instantiate WebSocket:', e);
        scheduleReconnect();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tenantId, jobId, channelTenantId, authToken],
  );

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    connect(true);
  }, [connect]);

  // ── Mount / unmount ───────────────────────────────────────────────────────
  useEffect(() => {
    disposedRef.current = false;
    connectRef.current = connect;
    connect(true);

    const onOnline = () => {
      dbg('browser online; reconnecting');
      reconnectAttemptsRef.current = 0;
      connectRef.current?.(true);
    };

    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        dbg('tab visible and socket not open; reconnecting');
        reconnectAttemptsRef.current = 0;
        connectRef.current?.(false);
      }
    };

    window.addEventListener('online', onOnline);
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      disposedRef.current = true;
      window.removeEventListener('online', onOnline);
      document.removeEventListener('visibilitychange', onVisible);
      clearReconnectTimer();
      clearWatchdog();
      discardSocket(wsRef.current); // handlers detached first: no auto-reconnect on unmount
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connect]);

  return {
    ws: wsRef.current,
    status: connectionStatus,
    reconnect,
  };
};