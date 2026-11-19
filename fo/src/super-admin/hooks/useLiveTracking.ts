import { useEffect, useRef, useState } from 'react';
import { getAccessToken, getApiBaseUrl } from '../api/client';

function timestampMs(value: unknown): number {
  if (typeof value !== 'string' || !value.trim()) return Number.NaN;
  let normalized = value.trim();
  // Backend timestamps are UTC. Some serializers omit the trailing Z; treat
  // those naive ISO strings as UTC instead of device-local time.
  if (normalized.includes('T') && !/[zZ]$/.test(normalized) && !/[+-]\d{2}:?\d{2}$/.test(normalized)) {
    normalized += 'Z';
  }
  return Date.parse(normalized);
}

export interface LivePosition {
  technician_id: string;
  technician_name?: string;
  latitude: number;
  longitude: number;
  status?: string;
  job_id?: string | number | null;
  timestamp: string;
  accuracy?: number | null;
  eta?: string | null;
  age_seconds?: number | null;
  eta_duration_minutes?: number | null;
}

export function useLiveTracking(tenantId?: string, token?: string | null) {
  const [positions, setPositions] = useState<Record<string, LivePosition>>({});
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'reconnecting' | 'offline'>('offline');
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null);
  const attempts = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!tenantId || !token) { setConnection('offline'); return; }
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    let watchdogTimer: ReturnType<typeof setTimeout> | null = null;

    const clearTimers = () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      if (watchdogTimer) clearTimeout(watchdogTimer);
      reconnectTimer = heartbeatTimer = watchdogTimer = null;
    };
    const armWatchdog = () => {
      if (watchdogTimer) clearTimeout(watchdogTimer);
      watchdogTimer = setTimeout(() => {
        if (disposed) return;
        try { socketRef.current?.close(); } catch { /* no-op */ }
      }, 75000);
    };
    const connect = () => {
      if (disposed) return;
      clearTimers();
      setConnection(attempts.current === 0 ? 'connecting' : 'reconnecting');
      const socketBase = (process.env.EXPO_PUBLIC_SOCKET_URL || getApiBaseUrl()).replace(/\/$/, '').replace(/^http/i, 'ws');
      // Use the latest token after an HTTP refresh before reconnecting.
      const activeToken = getAccessToken() || token;
      if (!activeToken) { setConnection('offline'); return; }
      const url = `${socketBase}/ws/v1/tracking?token=${encodeURIComponent(activeToken)}`;
      const ws = new WebSocket(url);
      socketRef.current = ws;
      ws.onopen = () => {
        if (disposed || socketRef.current !== ws) return;
        attempts.current = 0;
        setConnection('connected');
        ws.send(JSON.stringify({ type: 'subscribe', channel: `tenant:${tenantId}:all` }));
        heartbeatTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'pong', timestamp: new Date().toISOString() }));
        }, 25000);
        armWatchdog();
      };
      ws.onmessage = (event) => {
        if (disposed || socketRef.current !== ws) return;
        armWatchdog();
        setLastFrameAt(Date.now());
        try {
          const frame = typeof event.data === 'string' ? JSON.parse(event.data) : null;
          if (!frame) return;
          if (frame.type === 'ping') {
            if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'pong', timestamp: frame.timestamp || new Date().toISOString() }));
            return;
          }
          if (frame.type !== 'position_update' && frame.latitude === undefined) return;
          const id = String(frame.technician_id ?? frame.id ?? '');
          const lat = Number(frame.latitude), lng = Number(frame.longitude);
          if (!id || !Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
          const timestamp = String(frame.timestamp || frame.gps_timestamp || new Date().toISOString());
          setPositions(previous => {
            const existing = previous[id];
            const incomingMs = timestampMs(timestamp), existingMs = existing ? timestampMs(existing.timestamp) : -1;
            if (Number.isFinite(existingMs) && Number.isFinite(incomingMs) && incomingMs < existingMs) return previous;
            return { ...previous, [id]: {
              technician_id: id, technician_name: frame.technician_name || existing?.technician_name,
              latitude: lat, longitude: lng, status: frame.status || frame.job_status || existing?.status,
              job_id: frame.job_id ?? existing?.job_id ?? null, timestamp,
              accuracy: frame.accuracy == null ? null : Number(frame.accuracy), eta: frame.eta || null,
              age_seconds: frame.age_seconds == null ? null : Number(frame.age_seconds),
              eta_duration_minutes: frame.eta_duration_minutes == null ? null : Number(frame.eta_duration_minutes),
            } };
          });
        } catch { /* ignore malformed frames; keep the stream healthy */ }
      };
      ws.onerror = () => { if (!disposed) setConnection('reconnecting'); };
      ws.onclose = () => {
        if (disposed) return;
        clearTimers();
        setConnection('reconnecting');
        attempts.current += 1;
        const delay = Math.min(15000, 1000 * (2 ** Math.min(attempts.current, 4)));
        reconnectTimer = setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      disposed = true;
      clearTimers();
      try { socketRef.current?.close(); } catch { /* no-op */ }
      socketRef.current = null;
    };
  }, [tenantId, token]);

  return { positions, setPositions, connection, lastFrameAt };
}
