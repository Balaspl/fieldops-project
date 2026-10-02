import { useEffect, useRef, useCallback } from 'react';
import { useTrackingStore } from '../store/trackingStore';
import { useNotificationStore } from '../store/notificationStore';

/**
 * Live tracking WebSocket.
 *
 * Responsibilities:
 *  - Connect using the authenticated user's JWT.
 *  - Subscribe to the correct tenant/job tracking channel.
 *  - Reconnect automatically after connection loss.
 *  - Detect silent/dead sockets with a watchdog.
 *  - Respond to server heartbeat ping frames.
 *  - Ignore stale/cached positions that are older than the latest stored fix.
 *  - Store freshness metadata for the live tracking map.
 *  - Process geofence and ETA events.
 *  - Preserve the optional sendLocation() capability for technician-side
 *    callers that need to send an explicit WebSocket location frame.
 *
 * Authentication:
 *  - authToken argument has highest priority.
 *  - localStorage token/access_token are supported as fallback.
 *  - VITE_AUTH_TOKEN is supported as a final development/configuration fallback.
 *  - No fake/dev-dispatcher token is generated.
 *  - The JWT tenant is authoritative for the WebSocket connection.
 *  - tenant_id is NOT appended to the WebSocket URL.
 *
 * Debug:
 *   localStorage.setItem('trackingDebug', '1') // on
 *   localStorage.setItem('trackingDebug', '0') // off
 *   or open with ?trackdebug=1
 */

const WATCHDOG_MS = 75_000;
const BACKOFF_START_MS = 1_000;
const BACKOFF_MAX_MS = 15_000;

function readDebugFlag(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const stored =
      window.localStorage.getItem(
        'trackingDebug',
      );

    if (stored === '0') {
      return false;
    }

    if (stored === '1') {
      return true;
    }

    if (
      new URLSearchParams(
        window.location.search,
      ).has('trackdebug')
    ) {
      return true;
    }
  } catch {
    // Ignore storage/query-string errors.
  }

  return Boolean(
    (import.meta as any).env?.DEV,
  );
}

const DEBUG_ENABLED = readDebugFlag();

const dbg = (
  tag: string,
  data?: unknown,
) => {
  if (!DEBUG_ENABLED) {
    return;
  }

  if (data === undefined) {
    console.log(`[WS] ${tag}`);
  } else {
    console.log(
      `[WS] ${tag}`,
      data,
    );
  }
};

function decodeJwtClaims(
  token: string,
): Record<string, any> | null {
  try {
    const parts = token.split('.');

    if (parts.length < 2) {
      return null;
    }

    let payload = parts[1]
      .replace(/-/g, '+')
      .replace(/_/g, '/');

    /*
     * Base64url JWT payloads are commonly unpadded.
     * atob() expects correct 4-character padding.
     */
    while (payload.length % 4 !== 0) {
      payload += '=';
    }

    return JSON.parse(
      atob(payload),
    );
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
  const wsRef =
    useRef<WebSocket | null>(null);

  const reconnectTimeoutRef =
    useRef<number | null>(null);

  const watchdogRef =
    useRef<number | null>(null);

  const reconnectAttemptsRef =
    useRef<number>(0);

  const disposedRef =
    useRef<boolean>(false);

  const connectRef =
    useRef<
      ((force?: boolean) => void) | null
    >(null);

  const connectionStatus =
    useTrackingStore(
      (s) => s.connectionStatus,
    );

  const updateTechnicianLocation =
    useTrackingStore(
      (s) =>
        s.updateTechnicianLocation,
    );

  const setConnectionStatus =
    useTrackingStore(
      (s) => s.setConnectionStatus,
    );

  const setReconnectAttempt =
    useTrackingStore(
      (s) => s.setReconnectAttempt,
    );

  const updateJobStatus =
    useTrackingStore(
      (s) => s.updateJobStatus,
    );

  const updateJobETA =
    useTrackingStore(
      (s) => s.updateJobETA,
    );

  // --------------------------------------------------------------------------
  // TIMER HELPERS
  // --------------------------------------------------------------------------

  const clearReconnectTimer =
    useCallback(() => {
      if (
        reconnectTimeoutRef.current !==
        null
      ) {
        clearTimeout(
          reconnectTimeoutRef.current,
        );

        reconnectTimeoutRef.current =
          null;
      }
    }, []);

  const clearWatchdog =
    useCallback(() => {
      if (
        watchdogRef.current !==
        null
      ) {
        clearTimeout(
          watchdogRef.current,
        );

        watchdogRef.current = null;
      }
    }, []);

  // --------------------------------------------------------------------------
  // SOCKET CLEANUP
  // --------------------------------------------------------------------------

  /**
   * Detach every handler before closing the socket.
   *
   * This is important when a connection is being forcibly replaced. Without
   * detaching handlers first, the old socket can fire onclose and start a
   * second reconnect chain while the new socket is already active.
   */
  const discardSocket =
    useCallback(
      (ws: WebSocket | null) => {
        if (!ws) {
          return;
        }

        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;

        try {
          ws.close();
        } catch {
          // Ignore sockets that are already closed.
        }

        if (
          wsRef.current === ws
        ) {
          wsRef.current = null;
        }
      },
      [],
    );

  // --------------------------------------------------------------------------
  // RECONNECT
  // --------------------------------------------------------------------------

  const scheduleReconnect =
    useCallback(() => {
      if (
        disposedRef.current
      ) {
        return;
      }

      /*
       * Avoid scheduling a second reconnect timer if one is already pending.
       */
      if (
        reconnectTimeoutRef.current !==
        null
      ) {
        return;
      }

      reconnectAttemptsRef.current +=
        1;

      const attempt =
        reconnectAttemptsRef.current;

      const base = Math.min(
        BACKOFF_START_MS *
          Math.pow(
            2,
            attempt - 1,
          ),
        BACKOFF_MAX_MS,
      );

      // ±25% jitter prevents synchronized reconnect storms.
      const delay = Math.round(
        base *
          (0.75 +
            Math.random() *
              0.5),
      );

      setConnectionStatus(
        'reconnecting',
      );

      setReconnectAttempt(
        attempt,
      );

      dbg(
        `reconnecting in ${delay} ms (attempt ${attempt})`,
      );

      reconnectTimeoutRef.current =
        window.setTimeout(() => {
          reconnectTimeoutRef.current =
            null;

          connectRef.current?.(
            true,
          );
        }, delay);
    }, [
      setConnectionStatus,
      setReconnectAttempt,
    ]);

  // --------------------------------------------------------------------------
  // CONNECT
  // --------------------------------------------------------------------------

  const connect = useCallback(
    (
      force = false,
    ) => {
      if (
        disposedRef.current
      ) {
        return;
      }

      const existing =
        wsRef.current;

      /*
       * Normal connect:
       * never create a second socket if one is OPEN/CONNECTING.
       *
       * Forced connect:
       * replace the current socket intentionally, for example after watchdog
       * expiry or an explicit reconnect().
       */
      if (
        !force &&
        existing &&
        (
          existing.readyState ===
            WebSocket.OPEN ||
          existing.readyState ===
            WebSocket.CONNECTING
        )
      ) {
        return;
      }

      if (existing) {
        discardSocket(
          existing,
        );
      }

      clearReconnectTimer();
      clearWatchdog();

      // ----------------------------------------------------------------------
      // AUTHENTICATION
      // ----------------------------------------------------------------------

      const token =
        authToken ||
        localStorage.getItem(
          'token',
        ) ||
        localStorage.getItem(
          'access_token',
        ) ||
        (import.meta as any).env
          ?.VITE_AUTH_TOKEN ||
        '';

      if (!token) {
        console.error(
          '[useTrackingWebSocket] No auth token found. ' +
            'Pass the logged-in user\'s JWT as the 4th argument, ' +
            'or store it as "token" / "access_token".',
        );

        setConnectionStatus(
          'disconnected',
        );

        return;
      }

      // ----------------------------------------------------------------------
      // TENANT RESOLUTION
      // ----------------------------------------------------------------------

      const claims =
        decodeJwtClaims(
          token,
        );

      const jwtTenant: string =
        claims?.tenant_id
          ? String(
              claims.tenant_id,
            )
          : '';

      /*
       * JWT tenant is authoritative.
       * The prop/localStorage values remain useful as fallback for legacy
       * dispatcher contexts where the token itself may not expose tenant_id.
       */
      const finalTenant =
        jwtTenant ||
        tenantId ||
        localStorage.getItem(
          'tenant_id',
        ) ||
        '';

      const trackingTenant =
        channelTenantId ||
        finalTenant;

      if (
        jwtTenant &&
        tenantId &&
        jwtTenant !== tenantId
      ) {
        dbg(
          'tenant prop differs from JWT tenant (JWT wins)',
          {
            tenantProp:
              tenantId,
            jwtTenant,
          },
        );
      }

      if (
        !finalTenant &&
        !jobId
      ) {
        console.error(
          '[useTrackingWebSocket] Cannot determine tenant ' +
            'for dispatcher channel.',
        );

        setConnectionStatus(
          'disconnected',
        );

        return;
      }

      setConnectionStatus(
        reconnectAttemptsRef.current >
          0
          ? 'reconnecting'
          : 'disconnected',
      );

      setReconnectAttempt(
        reconnectAttemptsRef.current,
      );

      // ----------------------------------------------------------------------
      // SOCKET URL
      // ----------------------------------------------------------------------

      const socketUrl =
        (import.meta as any).env
          ?.VITE_SOCKET_URL ||
        'http://localhost:8000';

      const wsUrl =
        socketUrl.replace(
          /^http/,
          'ws',
        ) +
        '/ws/v1/tracking';

      /*
       * Do not append tenant_id to the WebSocket query string.
       *
       * The server validates the tenant from the JWT and validates the
       * requested channel separately.
       */
      const fullWsUrl =
        `${wsUrl}?token=${encodeURIComponent(
          token,
        )}`;

      dbg(
        'connecting',
        {
          url: wsUrl,
          role: claims?.role,
          jwtTenant,
          finalTenant,
          trackingTenant,
          jobId:
            jobId ?? null,
        },
      );

      // ----------------------------------------------------------------------
      // WATCHDOG
      // ----------------------------------------------------------------------

      const armWatchdog =
        (
          ws: WebSocket,
        ) => {
          clearWatchdog();

          watchdogRef.current =
            window.setTimeout(() => {
              if (
                wsRef.current !==
                ws
              ) {
                return;
              }

              console.warn(
                `[useTrackingWebSocket] No frames for ${
                  WATCHDOG_MS / 1000
                }s; replacing socket.`,
              );

              discardSocket(
                ws,
              );

              scheduleReconnect();
            }, WATCHDOG_MS);
        };

      // ----------------------------------------------------------------------
      // CREATE SOCKET
      // ----------------------------------------------------------------------

      try {
        const ws =
          new WebSocket(
            fullWsUrl,
          );

        wsRef.current =
          ws;

        // --------------------------------------------------------------------
        // OPEN
        // --------------------------------------------------------------------

        ws.onopen =
          () => {
            if (
              wsRef.current !==
              ws
            ) {
              return;
            }

            setConnectionStatus(
              'connected',
            );

            reconnectAttemptsRef.current =
              0;

            setReconnectAttempt(
              0,
            );

            armWatchdog(
              ws,
            );

            const send =
              (
                channel: string,
              ) => {
                if (
                  ws.readyState !==
                  WebSocket.OPEN
                ) {
                  return;
                }

                dbg(
                  'subscribe',
                  channel,
                );

                ws.send(
                  JSON.stringify(
                    {
                      type: 'subscribe',
                      channel,
                    },
                  ),
                );
              };

            if (jobId) {
              /*
               * Customer / technician job tracking:
               * narrow job channel only.
               */
              send(
                `tenant:${trackingTenant}:job:${jobId}`,
              );
            } else {
              /*
               * Dispatcher/internal tracking:
               * tenant-wide position events and geofence events.
               */
              send(
                `tenant:${finalTenant}:all`,
              );

              send(
                `tenant:${finalTenant}:events:geofence`,
              );
            }
          };

        // --------------------------------------------------------------------
        // MESSAGE
        // --------------------------------------------------------------------

        ws.onmessage =
          (
            event,
          ) => {
            if (
              wsRef.current !==
              ws
            ) {
              return;
            }

            /*
             * Any server frame proves the socket is still alive.
             * This includes heartbeat, subscribed, error, snapshot and position
             * frames.
             */
            armWatchdog(
              ws,
            );

            try {
              const data =
                JSON.parse(
                  event.data,
                );

              // --------------------------------------------------------------
              // HEARTBEAT / CONTROL FRAMES
              // --------------------------------------------------------------

              if (
                data.type ===
                'ping'
              ) {
                try {
                  if (
                    ws.readyState ===
                    WebSocket.OPEN
                  ) {
                    ws.send(
                      JSON.stringify(
                        {
                          type: 'pong',
                          timestamp:
                            data.timestamp,
                        },
                      ),
                    );
                  }
                } catch {
                  // onclose/watchdog will recover the socket.
                }

                return;
              }

              if (
                data.type ===
                  'heartbeat' ||
                data.type ===
                  'unsubscribed'
              ) {
                return;
              }

              if (
                data.type ===
                'subscribed'
              ) {
                dbg(
                  'subscribed',
                  data.channel,
                );

                return;
              }

              if (
                data.type ===
                'error'
              ) {
                console.error(
                  '[useTrackingWebSocket] Server error frame:',
                  data,
                );

                return;
              }

              // --------------------------------------------------------------
              // GEOFENCE EVENT
              // --------------------------------------------------------------

              const isGeofenceEvent =
                data.type ===
                  'geofence' ||
                data.event ===
                  'ENTRY' ||
                data.event ===
                  'EXIT' ||
                (
                  data.channel &&
                  String(
                    data.channel,
                  ).endsWith(
                    'events:geofence',
                  )
                );

              if (
                isGeofenceEvent
              ) {
                const techId =
                  String(
                    data.technician_id ||
                      data.tech_id ||
                      data.technician
                        ?.tech_id ||
                      'unknown',
                  );

                const storedTech =
                  useTrackingStore
                    .getState()
                    .technicians[
                      techId
                    ];

                const techName =
                  String(
                    data.technician_name ||
                      data.technician
                        ?.name ||
                      data.tech_name ||
                      storedTech?.name ||
                      'Technician',
                  );

                const geoJobId =
                  String(
                    data.job_id ||
                      data.job?.id ||
                      'unknown',
                  );

                const jobTitle =
                  String(
                    data.job_title ||
                      data.job?.title ||
                      'Job',
                  );

                const jobLocation =
                  String(
                    data.job_location ||
                      data.job?.location ||
                      'Job Site',
                  );

                const eventType =
                  data.event ===
                  'EXIT'
                    ? 'EXIT'
                    : 'ENTRY';

                useNotificationStore
                  .getState()
                  .addAlert({
                    techId,
                    techName,
                    jobId:
                      geoJobId,
                    jobTitle,
                    jobLocation,
                    eventType,
                    timestamp:
                      data.timestamp ||
                      new Date().toISOString(),
                  });

                return;
              }

              // --------------------------------------------------------------
              // POSITION UPDATE
              // --------------------------------------------------------------

              if (
                data.type ===
                  'position_update' ||
                data.latitude !==
                  undefined
              ) {
                const techId =
                  String(
                    data.technician_id ||
                      data.id ||
                      '',
                  );

                if (!techId) {
                  dbg(
                    'position_update missing technician id',
                    data,
                  );

                  return;
                }

                const rawStatus =
                  data.status ||
                  data.job_status ||
                  'Available';

                const jobIdStr =
                  data.job_id
                    ? String(
                        data.job_id,
                      )
                    : null;

                // ------------------------------------------------------------
                // STALE POSITION PROTECTION
                // ------------------------------------------------------------

                /*
                 * A latest cached snapshot may arrive after a newer live
                 * position. Never overwrite a newer stored position with an
                 * older one for the same job.
                 */
                const incomingTs =
                  Date.parse(
                    data.timestamp ||
                      data.gps_timestamp ||
                      '',
                  );

                const existing =
                  useTrackingStore
                    .getState()
                    .technicians[
                      techId
                    ];

                if (
                  existing &&
                  jobIdStr &&
                  String(
                    existing.job_id ??
                      '',
                  ) ===
                    jobIdStr &&
                  Number.isFinite(
                    incomingTs,
                  )
                ) {
                  const existingTs =
                    Date.parse(
                      existing.lastPing ||
                        '',
                    );

                  if (
                    Number.isFinite(
                      existingTs,
                    ) &&
                    incomingTs <
                      existingTs
                  ) {
                    dbg(
                      'ignored older position',
                      {
                        incoming:
                          data.timestamp,
                        stored:
                          existing.lastPing,
                        source:
                          data.source,
                      },
                    );

                    return;
                  }
                }

                // ------------------------------------------------------------
                // JOB STATUS
                // ------------------------------------------------------------

                if (jobIdStr) {
                  if (
                    data.job_status
                  ) {
                    updateJobStatus(
                      jobIdStr,
                      String(
                        data.job_status,
                      ),
                    );
                  }

                  // ----------------------------------------------------------
                  // ETA
                  // ----------------------------------------------------------

                  updateJobETA(
                    jobIdStr,
                    {
                      eta:
                        data.eta ||
                        null,

                      duration_minutes:
                        data.eta_duration_minutes !==
                          undefined &&
                        data.eta_duration_minutes !==
                          null
                          ? Number(
                              data.eta_duration_minutes,
                            )
                          : null,

                      traffic_delay_minutes:
                        data.eta_traffic_delay_minutes !==
                          undefined &&
                        data.eta_traffic_delay_minutes !==
                          null
                          ? Number(
                              data.eta_traffic_delay_minutes,
                            )
                          : (
                              data.traffic_delay_minutes !==
                                undefined &&
                              data.traffic_delay_minutes !==
                                null
                                ? Number(
                                    data.traffic_delay_minutes,
                                  )
                                : null
                            ),

                      source:
                        data.eta_source ||
                        (
                          data.fallback
                            ? 'estimated'
                            : 'calculated'
                        ),
                    },
                  );
                }

                // ------------------------------------------------------------
                // DEBUG
                // ------------------------------------------------------------

                dbg(
                  'position_update',
                  {
                    tech:
                      techId,
                    job:
                      jobIdStr,
                    lat:
                      data.latitude,
                    lng:
                      data.longitude,
                    source:
                      data.source,
                    age_seconds:
                      data.age_seconds,
                  },
                );

                // ------------------------------------------------------------
                // STORE LOCATION
                // ------------------------------------------------------------

                const latitude =
                  Number(
                    data.latitude,
                  );

                const longitude =
                  Number(
                    data.longitude,
                  );

                if (
                  !Number.isFinite(
                    latitude,
                  ) ||
                  !Number.isFinite(
                    longitude,
                  )
                ) {
                  console.warn(
                    '[useTrackingWebSocket] Ignoring position with invalid coordinates.',
                    data,
                  );

                  return;
                }

                updateTechnicianLocation(
                  techId,
                  {
                    latitude,
                    longitude,

                    status:
                      rawStatus,

                    ...(data.technician_name
                      ? {
                          name: String(
                            data.technician_name,
                          ),
                        }
                      : {}),

                    accuracy:
                      data.accuracy ===
                        undefined ||
                      data.accuracy ===
                        null
                        ? null
                        : Number(
                            data.accuracy,
                          ),

                    altitude:
                      data.altitude !==
                        undefined &&
                      data.altitude !==
                        null
                        ? Number(
                            data.altitude,
                          )
                        : null,

                    eta:
                      data.eta ||
                      null,

                    eta_duration_minutes:
                      data.eta_duration_minutes !==
                        undefined &&
                      data.eta_duration_minutes !==
                        null
                        ? Number(
                            data.eta_duration_minutes,
                          )
                        : null,

                    job_id:
                      jobIdStr,

                    lastPing:
                      data.timestamp ||
                      data.gps_timestamp ||
                      new Date().toISOString(),

                    /*
                     * Freshness metadata consumed by JobLiveTrackingMap.
                     */
                    receivedAt:
                      Date.now(),

                    ageAtReceipt:
                      data.age_seconds !==
                        undefined &&
                      data.age_seconds !==
                        null
                        ? Number(
                            data.age_seconds,
                          )
                        : 0,

                    source:
                      data.source
                        ? String(
                            data.source,
                          )
                        : undefined,
                  },
                );
              }
            } catch (err) {
              console.error(
                '[useTrackingWebSocket] Error parsing message:',
                err,
              );
            }
          };

        // --------------------------------------------------------------------
        // ERROR
        // --------------------------------------------------------------------

        ws.onerror =
          (
            err,
          ) => {
            console.error(
              '[useTrackingWebSocket] Error:',
              err,
            );

            /*
             * Do not schedule another reconnect here.
             *
             * Browsers normally fire onclose after onerror. Reconnect is
             * centralized in onclose so one failure creates one reconnect
             * chain instead of two.
             */
          };

        // --------------------------------------------------------------------
        // CLOSE
        // --------------------------------------------------------------------

        ws.onclose =
          (
            ev,
          ) => {
            if (
              wsRef.current !==
              ws
            ) {
              /*
               * Old socket already replaced by another connection.
               */
              return;
            }

            wsRef.current =
              null;

            clearWatchdog();

            setConnectionStatus(
              'disconnected',
            );

            if (
              ev.code ===
              1008
            ) {
              console.error(
                `[useTrackingWebSocket] Closed by server (1008): ${
                  ev.reason ||
                  'policy violation'
                }. Usually a wrong/expired token or tenant mismatch.`,
              );
            } else {
              dbg(
                'closed',
                {
                  code:
                    ev.code,
                  reason:
                    ev.reason,
                },
              );
            }

            scheduleReconnect();
          };
      } catch (error) {
        console.error(
          '[useTrackingWebSocket] Failed to instantiate WebSocket:',
          error,
        );

        scheduleReconnect();
      }
    },
    [
      tenantId,
      jobId,
      channelTenantId,
      authToken,
      clearReconnectTimer,
      clearWatchdog,
      discardSocket,
      scheduleReconnect,
      setConnectionStatus,
      setReconnectAttempt,
      updateTechnicianLocation,
      updateJobStatus,
      updateJobETA,
    ],
  );

  // Keep a stable imperative reconnect reference for the reconnect timer.
  useEffect(() => {
    connectRef.current =
      connect;

    return () => {
      if (
        connectRef.current ===
        connect
      ) {
        connectRef.current =
          null;
      }
    };
  }, [connect]);

  // --------------------------------------------------------------------------
  // EXPLICIT RECONNECT
  // --------------------------------------------------------------------------

  const reconnect =
    useCallback(() => {
      if (
        disposedRef.current
      ) {
        return;
      }

      reconnectAttemptsRef.current =
        0;

      clearReconnectTimer();
      clearWatchdog();

      connect(true);
    }, [
      connect,
      clearReconnectTimer,
      clearWatchdog,
    ]);

  // --------------------------------------------------------------------------
  // OPTIONAL EXPLICIT LOCATION SENDER
  // --------------------------------------------------------------------------

  /**
   * Send an explicit technician location frame over the currently open socket.
   *
   * This does not replace the normal backend /api/v1/gps/ping endpoint.
   * It preserves the existing WebSocket-side location_update capability from
   * the conflicting branch for callers that already depend on it.
   */
  const sendLocation =
    useCallback(
      (location: {
        latitude: number;
        longitude: number;
        accuracy?: number | null;
        altitude?: number | null;
        job_id?: string | null;
        status?: string | null;
      }) => {
        const ws =
          wsRef.current;

        if (
          !ws ||
          ws.readyState !==
            WebSocket.OPEN
        ) {
          return false;
        }

        if (
          !Number.isFinite(
            location.latitude,
          ) ||
          !Number.isFinite(
            location.longitude,
          )
        ) {
          console.warn(
            '[useTrackingWebSocket] Refusing to send invalid coordinates.',
            location,
          );

          return false;
        }

        try {
          ws.send(
            JSON.stringify(
              {
                type:
                  'location_update',

                latitude:
                  location.latitude,

                longitude:
                  location.longitude,

                accuracy:
                  location.accuracy ??
                  null,

                altitude:
                  location.altitude ??
                  null,

                job_id:
                  location.job_id ??
                  null,

                status:
                  location.status ??
                  null,

                timestamp:
                  new Date().toISOString(),
              },
            ),
          );

          return true;
        } catch (error) {
          console.warn(
            '[useTrackingWebSocket] Failed to send location frame:',
            error,
          );

          return false;
        }
      },
      [],
    );

  // --------------------------------------------------------------------------
  // MOUNT / UNMOUNT
  // --------------------------------------------------------------------------

  useEffect(() => {
    disposedRef.current =
      false;

    reconnectAttemptsRef.current =
      0;

    connectRef.current =
      connect;

    connect(true);

    // --------------------------------------------------------------
    // Browser comes back online.
    // --------------------------------------------------------------
    const onOnline =
      () => {
        if (
          disposedRef.current
        ) {
          return;
        }

        dbg(
          'browser online; reconnecting',
        );

        reconnectAttemptsRef.current =
          0;

        clearReconnectTimer();
        clearWatchdog();

        connectRef.current?.(
          true,
        );
      };

    // --------------------------------------------------------------
    // Tab becomes visible again.
    // --------------------------------------------------------------
    const onVisible =
      () => {
        if (
          document.visibilityState !==
          'visible'
        ) {
          return;
        }

        if (
          disposedRef.current
        ) {
          return;
        }

        const ws =
          wsRef.current;

        if (
          !ws ||
          ws.readyState !==
            WebSocket.OPEN
        ) {
          dbg(
            'tab visible and socket not open; reconnecting',
          );

          reconnectAttemptsRef.current =
            0;

          clearReconnectTimer();
          clearWatchdog();

          connectRef.current?.(
            false,
          );
        }
      };

    window.addEventListener(
      'online',
      onOnline,
    );

    document.addEventListener(
      'visibilitychange',
      onVisible,
    );

    return () => {
      disposedRef.current =
        true;

      window.removeEventListener(
        'online',
        onOnline,
      );

      document.removeEventListener(
        'visibilitychange',
        onVisible,
      );

      clearReconnectTimer();
      clearWatchdog();

      const socket =
        wsRef.current;

      /*
       * Detach handlers before closing so unmount does not start a reconnect
       * cycle.
       */
      discardSocket(
        socket,
      );

      if (
        connectRef.current ===
        connect
      ) {
        connectRef.current =
          null;
      }
    };
  }, [
    connect,
    clearReconnectTimer,
    clearWatchdog,
    discardSocket,
  ]);

  return {
    ws:
      wsRef.current,

    status:
      connectionStatus,

    reconnect,

    sendLocation,
  };
};