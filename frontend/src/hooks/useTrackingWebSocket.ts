import { useEffect, useRef, useCallback } from 'react';
import { useTrackingStore } from '../store/trackingStore';
import { useNotificationStore } from '../store/notificationStore';

export const useTrackingWebSocket = (tenantId: string) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  
  const {
    connectionStatus,
    updateTechnicianLocation,
    setConnectionStatus,
    setReconnectAttempt,
    updateJobStatus,
    updateJobETA,
  } = useTrackingStore();

  const connect = useCallback(() => {
    // Clean up existing connections
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (e) {}
      wsRef.current = null;
    }

    setConnectionStatus(reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'disconnected');
    setReconnectAttempt(reconnectAttemptsRef.current);

    const socketUrl = (import.meta as any).env?.VITE_SOCKET_URL || 'http://localhost:8000';
    const wsUrl = socketUrl.replace(/^http/, 'ws') + '/ws/v1/tracking';
    const token = localStorage.getItem('token') || localStorage.getItem('access_token') || (import.meta as any).env?.VITE_AUTH_TOKEN || 'dev-dispatcher-token';
    const finalTenant = tenantId || localStorage.getItem('tenant_id') || 'tenant-1';

    const fullWsUrl = `${wsUrl}?token=${token}&tenant_id=${finalTenant}`;
    
    try {
      const ws = new WebSocket(fullWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnectionStatus('connected');
        reconnectAttemptsRef.current = 0;
        setReconnectAttempt(0);
        
        // Subscribe to updates
        ws.send(
          JSON.stringify({
            type: 'subscribe',
            channel: `tenant:${finalTenant}:all`,
          })
        );

        // Subscribe to geofence alerts
        ws.send(
          JSON.stringify({
            type: 'subscribe',
            channel: `tenant:${finalTenant}:events:geofence`,
          })
        );
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Check if it's a geofence alert event
          const isGeofenceEvent = 
            data.type === 'geofence' || 
            data.event === 'ENTRY' || 
            data.event === 'EXIT' ||
            (data.channel && String(data.channel).endsWith('events:geofence'));

          if (isGeofenceEvent) {
            const techId = String(data.technician_id || data.tech_id || data.technician?.tech_id || 'unknown');
            const storedTech = useTrackingStore.getState().technicians[techId];
            const techName = String(data.technician_name || data.technician?.name || data.tech_name || storedTech?.name || 'Technician');
            const jobId = String(data.job_id || data.job?.id || 'unknown');
            const jobTitle = String(data.job_title || data.job?.title || 'Job');
            const jobLocation = String(data.job_location || data.job?.location || 'Job Site');
            const eventType = data.event === 'EXIT' ? 'EXIT' : 'ENTRY';
            
            useNotificationStore.getState().addAlert({
              techId,
              techName,
              jobId,
              jobTitle,
              jobLocation,
              eventType,
              timestamp: data.timestamp || new Date().toISOString(),
            });
            return;
          }
          
          if (data.type === 'position_update' || data.latitude !== undefined) {
            const techId = String(data.technician_id || data.id);
            const rawStatus = data.status || data.job_status || 'Available';

            if (data.job_id) {
              const jobIdStr = String(data.job_id);
              if (data.job_status) {
                updateJobStatus(jobIdStr, String(data.job_status));
              }
              updateJobETA(jobIdStr, {
                eta: data.eta || null,
                duration_minutes: data.eta_duration_minutes !== undefined ? Number(data.eta_duration_minutes) : null,
                traffic_delay_minutes: data.traffic_delay_minutes !== undefined ? Number(data.traffic_delay_minutes) : null,
                source: data.eta_source || (data.fallback ? 'estimated' : 'calculated'),
              });
            }
            
            updateTechnicianLocation(techId, {
              latitude: Number(data.latitude),
              longitude: Number(data.longitude),
              status: rawStatus,
              ...(data.technician_name ? { name: String(data.technician_name) } : {}),
              accuracy: data.accuracy !== undefined ? Number(data.accuracy) : null,
              altitude: data.altitude !== undefined ? Number(data.altitude) : null,
              eta: data.eta || null,
              eta_duration_minutes: data.eta_duration_minutes !== undefined ? Number(data.eta_duration_minutes) : null,
              job_id: data.job_id ? String(data.job_id) : null,
              lastPing: data.timestamp || new Date().toISOString(),
            });
          }
        } catch (err) {
          console.error('[useTrackingWebSocket] Error parsing message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('[useTrackingWebSocket] Error:', err);
        ws.close();
      };

      ws.onclose = () => {
        setConnectionStatus('disconnected');
        
        // Retry connection with exponential backoff (max 5 retries)
        if (reconnectAttemptsRef.current < 5) {
          reconnectAttemptsRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 15000);
          
          setConnectionStatus('reconnecting');
          setReconnectAttempt(reconnectAttemptsRef.current);
          
          console.log(`[useTrackingWebSocket] Reconnecting in ${delay}ms... (Attempt ${reconnectAttemptsRef.current}/5)`);
          
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect();
          }, delay);
        } else {
          console.error('[useTrackingWebSocket] Max reconnection attempts reached.');
        }
      };

    } catch (e) {
      console.error('[useTrackingWebSocket] Failed to instantiate WebSocket:', e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    connect();
  }, [connect]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        // Remove close listener to prevent auto-reconnect on unmount
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    ws: wsRef.current,
    status: connectionStatus,
    reconnect,
  };
};
