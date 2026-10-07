"""
app/services/broadcast_scheduler.py
────────────────────────────────────
BroadcastScheduler — FALLBACK position broadcaster.

The live path is:  technician /ping  ->  Redis gps:latest + gps:updates
                   ->  redis_gps_listener  ->  WebSocket clients.

This scheduler only covers gaps in that path (Redis publish failed, batch
uploads, a technician whose live pings are being throttled, etc.).

Design:
  • Every 5 s load the LATEST ping per (technician, job) from the last 60 s
    (ROW_NUMBER() window, not GROUP BY lat/lng).
  • Skip a job when gps:latest:{tenant}:{job} exists -> live path is healthy.
  • Dedup per job AND per ping: broadcast:last:{tech}:{job} = ping timestamp.
  • Only ONE worker runs a cycle (scheduler:leader lock).
  • Publish a single msgpack batch to Redis `gps:updates`. The listener fans it
    out, so we do NOT also broadcast locally (that delivered every update
    twice). Local fan-out is used only if the Redis publish itself fails.
  • The blocking DB query runs in a thread (asyncio.to_thread).

Recommended index:
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_gps_pings_tenant_tech_ts
      ON gps_pings (tenant_id, technician_id, timestamp DESC);
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import msgpack
from sqlalchemy import bindparam, text
from ..logger import logger
from ..utils import iso_utc

if TYPE_CHECKING:
    from ..services.tracking_manager import ConnectionManager

# ── Constants ─────────────────────────────────────────────────────────────────
BROADCAST_INTERVAL_S = 5.0
DEDUP_TTL_S = 120                   # dedup on the ping itself, so a long TTL is safe
GPS_STALENESS_S = 60                # pings older than this are ignored
LEADER_LOCK_KEY = "scheduler:leader"
LEADER_LOCK_PX = 4000               # < BROADCAST_INTERVAL_S so the lock never outlives a cycle
REDIS_GPS_CHANNEL = "gps:updates"

# Keep in sync with the statuses accepted by gps.py /ping.
ACTIVE_JOB_STATUSES = ("ASSIGNED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "ACTIVE")

# Ignore junk fallback locations (e.g. 50 000 m IP-based fixes).
SCHEDULER_MAX_ACCURACY_M = float(os.getenv("SCHEDULER_MAX_ACCURACY_METERS", "200"))


def _decode(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


# ─────────────────────────────────────────────────────────────────────────────
# BroadcastScheduler
# ─────────────────────────────────────────────────────────────────────────────
class BroadcastScheduler:
    """
    Parameters
    ----------
    db_factory : callable
        Zero-argument callable returning a new SQLAlchemy Session.
    redis_async :
        A ``redis.asyncio.Redis`` instance.
    manager : ConnectionManager
        Module-level ConnectionManager singleton (used only if Redis publish fails).
    """

    def __init__(self, db_factory, redis_async, manager: "ConnectionManager") -> None:
        self.db_factory = db_factory
        self.redis = redis_async
        self.manager = manager
        self.running: bool = False
        self._task: asyncio.Task | None = None

        # Metrics
        self.total_broadcasts: int = 0
        self.total_skipped: int = 0
        self.total_live_path_skips: int = 0
        self.total_not_leader: int = 0
        self.last_batch_size: int = 0
        self.last_latency_ms: float = 0.0

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info("[scheduler] BroadcastScheduler started (fallback mode, interval=5 s)")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[scheduler] BroadcastScheduler stopped")

    # ── Core loop ─────────────────────────────────────────────────────────────

    async def _broadcast_loop(self) -> None:
        while self.running:
            t0 = time.monotonic()
            try:
                await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[scheduler] broadcast_cycle_failed: {exc}", exc_info=True)
            finally:
                elapsed = time.monotonic() - t0
                await asyncio.sleep(max(0.0, BROADCAST_INTERVAL_S - elapsed))

    async def _acquire_leader(self) -> bool:
        """Only one worker runs the fallback cycle. Redis down -> allow."""
        try:
            return bool(await self.redis.set(LEADER_LOCK_KEY, "1", nx=True, px=LEADER_LOCK_PX))
        except Exception:
            return True

    async def _run_cycle(self) -> None:
        if not await self._acquire_leader():
            self.total_not_leader += 1
            return

        t0 = time.monotonic()

        rows = await asyncio.to_thread(self._load_rows)
        if not rows:
            self._record(0, 0, t0)
            return

        # ── Phase A: one pipeline round-trip for dedup + live-path checks ──
        dedup_keys = [f"broadcast:last:{r.tech_id}:{r.job_id}" for r in rows]
        latest_keys = [f"gps:latest:{r.tenant_id}:{r.job_id}" for r in rows]
        last_sent: list = [None] * len(rows)
        live_exists: list = [False] * len(rows)
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                for dk, lk in zip(dedup_keys, latest_keys):
                    pipe.get(dk)
                    pipe.exists(lk)
                res = await pipe.execute()
            last_sent = [_decode(v) for v in res[0::2]]
            live_exists = [bool(v) for v in res[1::2]]
        except Exception as exc:
            logger.warning(f"[scheduler] redis pre-check failed, broadcasting anyway: {exc}")

        survivors = []
        skipped = 0
        live_skips = 0
        for row, prev, live in zip(rows, last_sent, live_exists):
            if live:
                live_skips += 1          # live path is delivering this job
                continue
            ping_ts = iso_utc(row.last_ping)
            if prev is not None and prev == ping_ts:
                skipped += 1             # this exact ping was already sent
                continue
            survivors.append((row, ping_ts))

        self.total_live_path_skips += live_skips

        if not survivors:
            self._record(0, skipped, t0)
            return

        # ── Phase B: ETA cache lookups in one pipeline ──
        etas = [None] * len(survivors)
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                for row, _ in survivors:
                    pipe.get(f"eta:{row.tech_id}:{row.job_id}")
                etas = await pipe.execute()
        except Exception:
            pass

        now_iso = iso_utc(datetime.now(timezone.utc))
        batch: list[dict] = []
        for (row, ping_ts), eta_raw in zip(survivors, etas):
            eta, eta_minutes = "calculating...", None
            try:
                if eta_raw:
                    data = json.loads(_decode(eta_raw))
                    eta = data.get("eta", eta)
                    eta_minutes = data.get("duration_minutes")
            except Exception:
                pass

            tech_id = str(row.tech_id)
            batch.append({
                "type": "position_update",
                "technician_id": tech_id,
                "technician_name": row.technician_name or f"Technician #{tech_id[:8]}",
                "job_id": str(row.job_id),
                "tenant_id": str(row.tenant_id),
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "accuracy": float(row.accuracy) if row.accuracy is not None else None,
                "altitude": float(row.altitude) if row.altitude is not None else None,
                "job_status": row.job_status,
                "eta": eta,
                "eta_duration_minutes": eta_minutes,
                "timestamp": ping_ts,
                "server_ts": now_iso,
                "broadcast_at": now_iso,
                "source": "scheduler",
            })

        # ── Phase C: publish, then remember what we sent ──
        await self._dispatch_batch(batch)

        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                for u in batch:
                    pipe.setex(
                        f"broadcast:last:{u['technician_id']}:{u['job_id']}",
                        DEDUP_TTL_S,
                        u["timestamp"],
                    )
                await pipe.execute()
        except Exception:
            pass

        self._record(len(batch), skipped, t0)

    def _record(self, sent: int, skipped: int, t0: float) -> None:
        self.last_latency_ms = round((time.monotonic() - t0) * 1000, 2)
        self.total_broadcasts += sent
        self.total_skipped += skipped
        self.last_batch_size = sent
        if sent:
            logger.info(
                f"[scheduler] cycle: batch_size={sent} skipped={skipped} "
                f"latency_ms={self.last_latency_ms}"
            )
        else:
            logger.debug(
                f"[scheduler] cycle_empty: skipped={skipped} latency_ms={self.last_latency_ms}"
            )

    # ── DB query (runs in a worker thread) ────────────────────────────────────

    def _load_rows(self):
        db = self.db_factory()
        try:
            return self._query_active_technicians(db)
        finally:
            db.close()

    def _query_active_technicians(self, db):
        """
        Latest ping per (tenant, technician, job) inside the staleness window,
        joined to the technician's active jobs.

        Joining the ping to its own job (p.job_id = j.id) means a technician's
        stale EN_ROUTE jobs no longer receive the position of a different job.
        """
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError, ProgrammingError

        threshold = datetime.now(timezone.utc) - timedelta(seconds=GPS_STALENESS_S)
        dialect = getattr(getattr(db, "bind", None), "dialect", None)
        if dialect is not None and dialect.name == "sqlite":
            # SQLite stores naive text timestamps; compare like with like.
            threshold = threshold.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

        statuses = ", ".join(f"'{s}'" for s in ACTIVE_JOB_STATUSES)  # constants, not user input



        sql = text("""
            WITH latest AS (
                SELECT p.technician_id, p.tenant_id, p.job_id,
                       p.latitude, p.longitude, p.accuracy, p.altitude, p.timestamp,
                       ROW_NUMBER() OVER (
                           PARTITION BY p.tenant_id, p.technician_id, p.job_id
                           ORDER BY p.timestamp DESC
                       ) AS rn
                FROM gps_pings p
                WHERE p.timestamp >= :threshold
                  AND (p.accuracy IS NULL OR p.accuracy <= :max_accuracy)
            )
            SELECT t.tech_id, t.technician_name, t.tenant_id,
                   j.id AS job_id, j.status AS job_status,
                   j.service_type AS job_title, j.location AS job_location,
                   l.latitude, l.longitude, l.accuracy, l.altitude,
                   l.timestamp AS last_ping
            FROM technicians t
            JOIN jobs j
              ON j.assigned_technician_id = t.technician_id
             AND UPPER(j.status) IN :statuses
             AND CAST(j.tenant_id AS VARCHAR) = CAST(t.tenant_id AS VARCHAR)
            JOIN latest l
              ON l.technician_id = CAST(t.tech_id AS VARCHAR)
             AND l.tenant_id = CAST(t.tenant_id AS VARCHAR)
             AND l.job_id = CAST(j.id AS VARCHAR)
             AND l.rn = 1
            WHERE t.tech_id IS NOT NULL
        """).bindparams(
            bindparam("statuses", expanding=True)
        )
        try:
            return db.execute(
            sql,
            {
                "threshold": threshold,
                "max_accuracy": SCHEDULER_MAX_ACCURACY_M,
                "statuses": [s.upper() for s in ACTIVE_JOB_STATUSES],
            },
        ).fetchall()
        except (ProgrammingError, OperationalError) as exc:
            msg = str(exc).lower()
            if "gps_pings" in msg or "does not exist" in msg or "no such table" in msg:
                logger.warning(f"[scheduler] Table 'gps_pings' does not exist yet: {exc}")
                return []
            raise

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def _dispatch_batch(self, batch: list[dict]) -> None:
        """
        Publish to Redis; the redis_gps_listener fans it out to every worker.
        Local fan-out happens ONLY when Redis publish fails (then the listener
        would never see the batch).
        """
        envelope = {
            "type": "position_batch",
            "count": len(batch),
            "updates": batch,
            "broadcast_cycle_at": iso_utc(datetime.now(timezone.utc)),
        }
        try:
            compressed = msgpack.packb(envelope, use_bin_type=True)
            await self.redis.publish(REDIS_GPS_CHANNEL, compressed)
            return
        except Exception as e:
            logger.warning(f"[scheduler] Redis publish failed, falling back to local fan-out: {e}")

        await self._local_fan_out(batch)

    async def _local_fan_out(self, batch: list[dict]) -> None:
        coros = []
        for u in batch:
            t, tech, job = u["tenant_id"], u["technician_id"], u["job_id"]
            coros.append(self.manager.broadcast(f"tenant:{t}:job:{job}", u))          # customers
            coros.append(self.manager.broadcast(f"tenant:{t}:technician:{tech}", u))
            coros.append(self.manager.broadcast(f"tenant:{t}:all", u))                # dispatchers
        await asyncio.gather(*coros, return_exceptions=True)

    def get_metrics(self) -> dict:
        return {
            "total_broadcasts": self.total_broadcasts,
            "total_skipped": self.total_skipped,
            "total_live_path_skips": self.total_live_path_skips,
            "total_not_leader": self.total_not_leader,
            "last_batch_size": self.last_batch_size,
            "last_latency_ms": self.last_latency_ms,
            "broadcast_interval_s": BROADCAST_INTERVAL_S,
        }