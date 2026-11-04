"""
app/sentiment/dashboard.py

SentimentDashboardService — read-only aggregation layer over the
existing sentiment pipeline (SentimentThreadMessage, SentimentEscalation).

Does NOT write sentiment data. Real-time scoring, escalation
creation, and manager notification are handled by
RealTimeSentimentScorer / SentimentEscalationService — this
service only reads and aggregates for the operations dashboard.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db  # adjust if your get_db lives elsewhere
from app.models import Job, Technician
from app.models.sentiment import SentimentThreadMessage
from app.models.sentiment_escalation import SentimentEscalation
from app.sentiment.escalation import SentimentEscalationService
from app.services.socket_manager import ws_manager

# --- Auth: adjust these imports to match your actual auth module ---
# `get_current_user` should return an object/dict exposing at least
# `tenant_id` (and ideally a role/permission for admin dashboard access).
# `require_admin` should raise HTTPException(403) if the caller isn't
# authorized to view admin dashboards for their tenant.
from app.auth.dependencies import get_current_user  # noqa: E402

try:
    from app.redis_client import get_redis_client  # adjust to your Redis client
except ImportError:  # pragma: no cover - allows this file to import even
    redis_client = None  # if a Redis client module isn't wired up yet


# Sentiment -> numeric score, matching the convention already
# established in RealTimeSentimentScorer.get_job_sentiment_summary()
SENTIMENT_SCORES = {
    "POSITIVE": 1.0,
    "MIXED": 0.5,
    "NEUTRAL": 0.0,
    "NEGATIVE": -1.0,
}

VALID_GRANULARITIES = {"hourly", "daily", "weekly", "monthly"}

# Postgres date_trunc field per granularity
_TRUNC_FIELD = {
    "hourly": "hour",
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
}

# Short cache TTL for the bundled dashboard payload. It's recomputed
# from scratch on a cache miss and invalidated naturally by TTL expiry —
# this keeps the <500ms target realistic under auto-refresh load
# without introducing explicit invalidation-on-write complexity.
DASHBOARD_CACHE_TTL_SECONDS = 45

# CSV-injection guard: Excel/Sheets treats a leading '=', '+', '-', '@'
# as the start of a formula, so any string field that could contain
# user- or technician-supplied text gets a leading apostrophe prefixed
# before being written to a CSV cell.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _csv_safe(value):
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


class SentimentDashboardService:
    """
    Aggregates sentiment data for the operations dashboard.

    All queries are tenant-scoped — every method requires
    tenant_id and never returns cross-tenant data.
    """

    def __init__(self, db: Session):
        self.db = db
        self.escalation_service = SentimentEscalationService(db)

    # ============================================================
    # Helpers
    # ============================================================

    def _base_query(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
        """
        Base tenant-scoped, date-filtered query over
        SentimentThreadMessage.
        """

        query = self.db.query(SentimentThreadMessage).filter(
            SentimentThreadMessage.tenant_id == tenant_id
        )

        if start_date is not None:
            query = query.filter(
                SentimentThreadMessage.created_at >= start_date
            )

        if end_date is not None:
            query = query.filter(
                SentimentThreadMessage.created_at <= end_date
            )

        return query

    def _default_date_range(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        default_days: int = 30,
    ) -> tuple[datetime, datetime]:
        """
        Fill in a sensible default date range when the caller
        doesn't supply one — last 30 days.
        """

        now = datetime.now(timezone.utc)

        if end_date is None:
            end_date = now

        if start_date is None:
            start_date = end_date - timedelta(days=default_days)

        return start_date, end_date

    # ============================================================
    # CORE METRICS (Requirement: total replies, distribution,
    # average confidence)
    # ============================================================

    def get_core_metrics(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Returns:
        {
            "total_replies": int,
            "sentiment_distribution": {
                "POSITIVE": {"count": int, "percentage": float},
                "NEGATIVE": {"count": int, "percentage": float},
                "NEUTRAL":  {"count": int, "percentage": float},
                "MIXED":    {"count": int, "percentage": float},
            },
            "average_confidence": float,
        }
        """

        start_date, end_date = self._default_date_range(
            start_date, end_date
        )

        base = self._base_query(tenant_id, start_date, end_date)

        total_replies = base.count()

        if total_replies == 0:
            return {
                "total_replies": 0,
                "sentiment_distribution": {
                    label: {"count": 0, "percentage": 0.0}
                    for label in SENTIMENT_SCORES
                },
                "average_confidence": 0.0,
            }

        # Distribution — grouped count per sentiment label
        distribution_rows = (
            base.with_entities(
                SentimentThreadMessage.sentiment,
                func.count(SentimentThreadMessage.id),
            )
            .group_by(SentimentThreadMessage.sentiment)
            .all()
        )

        counts = {label: 0 for label in SENTIMENT_SCORES}

        for sentiment_label, count in distribution_rows:
            normalized = (sentiment_label or "").upper()
            if normalized in counts:
                counts[normalized] = count
            # Unknown/unexpected labels are intentionally
            # excluded from the fixed 4-category breakdown
            # rather than silently inflating a bucket.

        distribution = {
            label: {
                "count": count,
                "percentage": round(
                    (count / total_replies) * 100, 2
                ),
            }
            for label, count in counts.items()
        }

        # Average confidence
        avg_confidence = base.with_entities(
            func.avg(SentimentThreadMessage.confidence)
        ).scalar()

        return {
            "total_replies": total_replies,
            "sentiment_distribution": distribution,
            "average_confidence": round(
                float(avg_confidence or 0.0), 3
            ),
        }

    # ============================================================
    # TREND CALCULATION (Requirement: hourly/daily/weekly/monthly
    # sentiment over time, moving averages, change detection)
    # ============================================================

    def get_sentiment_trend(
        self,
        tenant_id: str,
        granularity: str = "daily",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        moving_average_window: int = 7,
    ) -> dict:
        """
        Returns time-bucketed sentiment trend data.

        {
            "granularity": "daily",
            "buckets": [
                {
                    "period": "2026-08-20T00:00:00+00:00",
                    "total_replies": int,
                    "average_score": float,   # -1.0 .. 1.0
                    "moving_average": float | None,
                    "sentiment_counts": {"POSITIVE": n, ...},
                },
                ...
            ],
            "change": {
                "current_period_avg": float,
                "previous_period_avg": float,
                "delta": float,
                "direction": "IMPROVING" | "DECLINING" | "STABLE",
            },
        }
        """

        _validate_granularity(granularity)

        start_date, end_date = self._default_date_range(
            start_date, end_date
        )

        trunc_field = _TRUNC_FIELD[granularity]

        base = self._base_query(tenant_id, start_date, end_date)

        period_col = func.date_trunc(
            trunc_field, SentimentThreadMessage.created_at
        ).label("period")

        rows = (
            base.with_entities(
                period_col,
                SentimentThreadMessage.sentiment,
                func.count(SentimentThreadMessage.id),
            )
            .group_by(period_col, SentimentThreadMessage.sentiment)
            .order_by(period_col)
            .all()
        )

        # Aggregate raw rows into per-period sentiment counts
        periods: dict[datetime, dict[str, int]] = {}

        for period, sentiment_label, count in rows:
            normalized = (sentiment_label or "").upper()
            periods.setdefault(
                period, {label: 0 for label in SENTIMENT_SCORES}
            )
            if normalized in periods[period]:
                periods[period][normalized] = count

        sorted_periods = sorted(periods.keys())

        buckets = []
        raw_scores: list[float] = []

        for period in sorted_periods:
            counts = periods[period]
            total = sum(counts.values())

            if total == 0:
                weighted_score = 0.0
            else:
                weighted_score = (
                    sum(
                        SENTIMENT_SCORES[label] * count
                        for label, count in counts.items()
                    )
                    / total
                )

            raw_scores.append(weighted_score)

            buckets.append(
                {
                    "period": period.isoformat(),
                    "total_replies": total,
                    "average_score": round(weighted_score, 3),
                    "sentiment_counts": counts,
                }
            )

        # Moving average — simple rolling mean over the window,
        # computed left-to-right so early buckets use however
        # many prior points are actually available.
        for i, bucket in enumerate(buckets):
            window_start = max(0, i - moving_average_window + 1)
            window_scores = raw_scores[window_start : i + 1]

            bucket["moving_average"] = (
                round(sum(window_scores) / len(window_scores), 3)
                if window_scores
                else None
            )

        # Change detection — compare the most recent period
        # against the one before it.
        change = self._detect_change(raw_scores)

        return {
            "granularity": granularity,
            "buckets": buckets,
            "change": change,
        }

    def _detect_change(self, raw_scores: list[float]) -> dict:
        """
        Compares the latest bucket's score against the
        previous bucket's score.
        """

        if len(raw_scores) < 2:
            return {
                "current_period_avg": (
                    round(raw_scores[-1], 3) if raw_scores else 0.0
                ),
                "previous_period_avg": 0.0,
                "delta": 0.0,
                "direction": "STABLE",
            }

        current = raw_scores[-1]
        previous = raw_scores[-2]
        delta = current - previous

        # Small deltas are treated as noise, not a real trend.
        if abs(delta) < 0.05:
            direction = "STABLE"
        elif delta > 0:
            direction = "IMPROVING"
        else:
            direction = "DECLINING"

        return {
            "current_period_avg": round(current, 3),
            "previous_period_avg": round(previous, 3),
            "delta": round(delta, 3),
            "direction": direction,
        }

    # ============================================================
    # TECHNICIAN LEADERBOARD (Requirement: avg sentiment per
    # technician, ranked)
    # ============================================================

    def get_technician_leaderboard(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Ranks technicians by average sentiment score across
        all customer replies tied to their assigned jobs.

        There is no direct technician_id on SentimentThreadMessage,
        so this joins through Job.assigned_technician_id.

        Returns, best-first:
        [
            {
                "technician_id": int,
                "technician_name": str,
                "total_replies": int,
                "average_score": float,       # -1.0 .. 1.0
                "sentiment_counts": {"POSITIVE": n, ...},
                "rank": int,
            },
            ...
        ]
        """

        start_date, end_date = self._default_date_range(
            start_date, end_date
        )

        rows = (
            self.db.query(
                Job.assigned_technician_id,
                Technician.technician_name,
                SentimentThreadMessage.sentiment,
                func.count(SentimentThreadMessage.id),
            )
            .join(
                Job,
                Job.id == SentimentThreadMessage.job_id,
            )
            .join(
                Technician,
                Technician.technician_id
                == Job.assigned_technician_id,
            )
            .filter(
                SentimentThreadMessage.tenant_id == tenant_id,
                SentimentThreadMessage.created_at >= start_date,
                SentimentThreadMessage.created_at <= end_date,
                Job.assigned_technician_id.isnot(None),
            )
            .group_by(
                Job.assigned_technician_id,
                Technician.technician_name,
                SentimentThreadMessage.sentiment,
            )
            .all()
        )

        # Aggregate rows into a per-technician structure
        technicians: dict[int, dict] = {}

        for tech_id, tech_name, sentiment_label, count in rows:
            normalized = (sentiment_label or "").upper()

            if tech_id not in technicians:
                technicians[tech_id] = {
                    "technician_id": tech_id,
                    "technician_name": tech_name,
                    "sentiment_counts": {
                        label: 0 for label in SENTIMENT_SCORES
                    },
                }

            if normalized in technicians[tech_id]["sentiment_counts"]:
                technicians[tech_id]["sentiment_counts"][
                    normalized
                ] = count

        leaderboard = []

        for tech_id, data in technicians.items():
            counts = data["sentiment_counts"]
            total = sum(counts.values())

            weighted_score = (
                sum(
                    SENTIMENT_SCORES[label] * count
                    for label, count in counts.items()
                )
                / total
                if total > 0
                else 0.0
            )

            leaderboard.append(
                {
                    "technician_id": tech_id,
                    "technician_name": data["technician_name"],
                    "total_replies": total,
                    "average_score": round(weighted_score, 3),
                    "sentiment_counts": counts,
                }
            )

        # Rank best (highest average_score) first, using total
        # replies as a tiebreaker so a single lucky reply doesn't
        # outrank a technician with a consistent strong record.
        leaderboard.sort(
            key=lambda t: (-t["average_score"], -t["total_replies"])
        )

        for i, entry in enumerate(leaderboard, start=1):
            entry["rank"] = i

        return leaderboard[:limit]

    # ============================================================
    # JOB TYPE BREAKDOWN (Requirement: sentiment by service
    # category)
    # ============================================================

    def get_job_type_breakdown(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Sentiment distribution grouped by Job.service_type.

        There is no service_type column on SentimentThreadMessage,
        so this joins through Job.

        Returns:
        [
            {
                "service_type": "AC Repair",
                "total_replies": int,
                "average_score": float,
                "sentiment_counts": {"POSITIVE": n, ...},
                "sentiment_percentages": {"POSITIVE": pct, ...},
            },
            ...
        ]
        """

        start_date, end_date = self._default_date_range(
            start_date, end_date
        )

        rows = (
            self.db.query(
                Job.service_type,
                SentimentThreadMessage.sentiment,
                func.count(SentimentThreadMessage.id),
            )
            .join(
                Job,
                Job.id == SentimentThreadMessage.job_id,
            )
            .filter(
                SentimentThreadMessage.tenant_id == tenant_id,
                SentimentThreadMessage.created_at >= start_date,
                SentimentThreadMessage.created_at <= end_date,
            )
            .group_by(
                Job.service_type,
                SentimentThreadMessage.sentiment,
            )
            .all()
        )

        return self._build_grouped_breakdown(
            rows, group_key_label="service_type"
        )

    # ============================================================
    # CHANNEL BREAKDOWN (Requirement: sentiment by SMS vs email
    # vs portal)
    # ============================================================

    def get_channel_breakdown(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Sentiment distribution grouped by channel
        (SMS / EMAIL / PORTAL).

        channel lives directly on SentimentThreadMessage,
        so no join is needed here.

        Returns:
        [
            {
                "channel": "SMS",
                "total_replies": int,
                "average_score": float,
                "sentiment_counts": {"POSITIVE": n, ...},
                "sentiment_percentages": {"POSITIVE": pct, ...},
            },
            ...
        ]
        """

        start_date, end_date = self._default_date_range(
            start_date, end_date
        )

        rows = (
            self._base_query(tenant_id, start_date, end_date)
            .with_entities(
                SentimentThreadMessage.channel,
                SentimentThreadMessage.sentiment,
                func.count(SentimentThreadMessage.id),
            )
            .group_by(
                SentimentThreadMessage.channel,
                SentimentThreadMessage.sentiment,
            )
            .all()
        )

        return self._build_grouped_breakdown(
            rows, group_key_label="channel"
        )

    # ============================================================
    # Shared aggregation helper for the two breakdowns above
    # ============================================================

    def _build_grouped_breakdown(
        self,
        rows,
        group_key_label: str,
    ) -> list[dict]:
        """
        Turns (group_key, sentiment, count) rows into a list of
        per-group breakdown dicts with counts, weighted average
        score, and percentages that sum to 100% within each group.
        """

        groups: dict[str, dict] = {}

        for group_key, sentiment_label, count in rows:
            if group_key is None:
                continue

            normalized = (sentiment_label or "").upper()

            if group_key not in groups:
                groups[group_key] = {
                    label: 0 for label in SENTIMENT_SCORES
                }

            if normalized in groups[group_key]:
                groups[group_key][normalized] = count

        breakdown = []

        for group_key, counts in groups.items():
            total = sum(counts.values())

            if total == 0:
                continue

            weighted_score = (
                sum(
                    SENTIMENT_SCORES[label] * count
                    for label, count in counts.items()
                )
                / total
            )

            percentages = {
                label: round((count / total) * 100, 2)
                for label, count in counts.items()
            }

            breakdown.append(
                {
                    group_key_label: group_key,
                    "total_replies": total,
                    "average_score": round(weighted_score, 3),
                    "sentiment_counts": counts,
                    "sentiment_percentages": percentages,
                }
            )

        # Highest volume first — most-discussed category leads.
        breakdown.sort(key=lambda g: -g["total_replies"])

        return breakdown

    # ============================================================
    # ALERT FEED (Requirement: recent escalations, unresolved
    # issues)
    # ============================================================

    def get_alert_feed(
        self,
        tenant_id: str,
        limit: int = 50,
        status_filter: Optional[str] = None,
        include_resolved: bool = False,
    ) -> list[dict]:
        """
        Returns recent sentiment escalations for the alert feed,
        most recent first.

        Reuses SentimentEscalationService.check_sla_breach() so
        the dashboard flags the exact same SLA violations the
        escalation pipeline itself tracks — no separate SLA
        logic is reimplemented here.

        Args:
            status_filter: "OPEN" | "ACKNOWLEDGED" | "RESOLVED",
                or None for all statuses (subject to
                include_resolved below).
            include_resolved: when status_filter is None,
                whether to include RESOLVED escalations in the
                feed. Defaults to False — the feed is meant to
                surface things needing attention, not history.

        Returns:
        [
            {
                "escalation_id": int,
                "job_id": int,
                "customer_name": str,
                "technician_name": str | None,
                "sentiment_label": str,
                "sentiment_score": float,
                "trigger_reason": str,
                "status": str,
                "assigned_manager_id": str | None,
                "created_at": str (isoformat),
                "acknowledge_deadline": str (isoformat),
                "resolve_deadline": str (isoformat),
                "sla_breach": "ACKNOWLEDGE_SLA_BREACHED"
                    | "RESOLVE_SLA_BREACHED" | None,
            },
            ...
        ]
        """

        query = self.db.query(SentimentEscalation).filter(
            SentimentEscalation.tenant_id == tenant_id
        )

        if status_filter is not None:
            query = query.filter(
                SentimentEscalation.status == status_filter.upper()
            )
        elif not include_resolved:
            query = query.filter(
                SentimentEscalation.status != "RESOLVED"
            )

        escalations = (
            query.order_by(SentimentEscalation.created_at.desc())
            .limit(limit)
            .all()
        )

        feed = []

        for escalation in escalations:
            sla_breach = self.escalation_service.check_sla_breach(
                escalation
            )

            feed.append(
                {
                    "escalation_id": escalation.id,
                    "job_id": escalation.job_id,
                    "customer_name": escalation.customer_name,
                    "technician_name": escalation.technician_name,
                    "sentiment_label": escalation.sentiment_label,
                    "sentiment_score": escalation.sentiment_score,
                    "trigger_reason": escalation.trigger_reason,
                    "suggested_action": getattr(escalation, "suggested_action", None),
                    "status": escalation.status,
                    "assigned_manager_id": (
                        escalation.assigned_manager_id
                    ),
                    "created_at": escalation.created_at.isoformat(),
                    "acknowledge_deadline": (
                        escalation.acknowledge_deadline.isoformat()
                    ),
                    "resolve_deadline": (
                        escalation.resolve_deadline.isoformat()
                    ),
                    "sla_breach": sla_breach,
                }
            )

        return feed

    def get_alert_summary_counts(self, tenant_id: str) -> dict:
        """
        Quick counts for a dashboard summary widget — how many
        escalations are open, breaching SLA, etc.

        Returns:
        {
            "open": int,
            "acknowledged": int,
            "resolved_last_24h": int,
            "sla_breached": int,
        }
        """

        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)

        open_count = (
            self.db.query(func.count(SentimentEscalation.id))
            .filter(
                SentimentEscalation.tenant_id == tenant_id,
                SentimentEscalation.status == "OPEN",
            )
            .scalar()
        )

        acknowledged_count = (
            self.db.query(func.count(SentimentEscalation.id))
            .filter(
                SentimentEscalation.tenant_id == tenant_id,
                SentimentEscalation.status == "ACKNOWLEDGED",
            )
            .scalar()
        )

        resolved_last_24h = (
            self.db.query(func.count(SentimentEscalation.id))
            .filter(
                SentimentEscalation.tenant_id == tenant_id,
                SentimentEscalation.status == "RESOLVED",
                SentimentEscalation.resolved_at >= last_24h,
            )
            .scalar()
        )

        # SLA breach requires evaluating each open/acknowledged
        # escalation's deadlines, so it can't be a pure SQL count
        # without duplicating check_sla_breach()'s logic in SQL.
        # (This is the ONLY place that logic runs — the standalone
        # duplicate that used to live on this class was removed.)
        active_escalations = (
            self.db.query(SentimentEscalation)
            .filter(
                SentimentEscalation.tenant_id == tenant_id,
                SentimentEscalation.status.in_(
                    ["OPEN", "ACKNOWLEDGED"]
                ),
            )
            .all()
        )

        sla_breached = sum(
            1
            for escalation in active_escalations
            if self.escalation_service.check_sla_breach(escalation)
            is not None
        )

        return {
            "open": open_count or 0,
            "acknowledged": acknowledged_count or 0,
            "resolved_last_24h": resolved_last_24h or 0,
            "sla_breached": sla_breached,
        }

    # ============================================================
    # Bundled payload (used by GET /admin/sentiment/dashboard and
    # by the periodic WebSocket broadcast)
    # ============================================================

    def get_dashboard_bundle(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        granularity: str = "daily",
    ) -> dict:
        return {
            "metrics": self.get_core_metrics(tenant_id, start_date, end_date),
            "trend": self.get_sentiment_trend(
                tenant_id, granularity, start_date, end_date
            ),
            "technician_leaderboard": self.get_technician_leaderboard(
                tenant_id, start_date, end_date
            ),
            "job_type_breakdown": self.get_job_type_breakdown(
                tenant_id, start_date, end_date
            ),
            "channel_breakdown": self.get_channel_breakdown(
                tenant_id, start_date, end_date
            ),
            "alert_feed": self.get_alert_feed(tenant_id),
            "alert_summary": self.get_alert_summary_counts(tenant_id),
        }


# ============================================================
# Shared validation helpers
# ============================================================


def _validate_granularity(granularity: str) -> None:
    if granularity not in VALID_GRANULARITIES:
        raise HTTPException(
            status_code=422,
            detail=f"granularity must be one of {sorted(VALID_GRANULARITIES)}",
        )


def _parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parses optional ISO date query params into datetimes.
    Raises HTTPException(422) on malformed input rather than
    letting a bad string reach the service layer.

    Naive datetimes (no UTC offset in the input string) are
    assumed to be UTC and made timezone-aware, since created_at
    columns are stored tz-aware and a naive/aware comparison
    mismatch would otherwise behave inconsistently across drivers.
    """

    parsed_start = None
    parsed_end = None

    try:
        if start_date:
            parsed_start = datetime.fromisoformat(start_date)
            if parsed_start.tzinfo is None:
                parsed_start = parsed_start.replace(tzinfo=timezone.utc)
        if end_date:
            parsed_end = datetime.fromisoformat(end_date)
            if parsed_end.tzinfo is None:
                parsed_end = parsed_end.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                "start_date and end_date must be ISO 8601 "
                "formatted (e.g. 2026-08-01T00:00:00+00:00)."
            ),
        )

    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before end_date.",
        )

    return parsed_start, parsed_end


def _verify_tenant_access(current_user, tenant_id: str) -> None:
    """
    Ensure the authenticated caller can access the requested tenant.

    Super admins may access any tenant.
    Regular users may only access their own tenant.
    """

    if current_user.is_super_admin:
        return

    if str(current_user.tenant_id) != str(tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view this tenant's dashboard.",
        )


# ============================================================
# API
# ============================================================

router = APIRouter(prefix="/admin/sentiment/dashboard", tags=["sentiment-dashboard"])


@router.get("")
async def get_dashboard(
    tenant_id: str = Query(..., description="Tenant to scope the dashboard to"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    granularity: str = Query("daily"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Aggregate admin dashboard payload — bundles metrics, trend,
    leaderboard, breakdowns, and alert feed in a single response.

    Cached briefly per (tenant, date range, granularity) so
    60-second auto-refresh polling from multiple managers on the
    same tenant doesn't recompute the full bundle on every hit.
    """

    _verify_tenant_access(current_user, tenant_id)

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)
    _validate_granularity(granularity)

    cache_key = (
        f"sentiment_dashboard:{tenant_id}:{granularity}:"
        f"{start_date or 'default'}:{end_date or 'default'}"
    )

    if redis_client is not None:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)

    service = SentimentDashboardService(db)
    payload = service.get_dashboard_bundle(
        tenant_id, parsed_start, parsed_end, granularity
    )

    if redis_client is not None:
        redis_client.setex(
            cache_key, DASHBOARD_CACHE_TTL_SECONDS, json.dumps(payload, default=str)
        )

    return payload


@router.get("/metrics")
async def get_metrics(
    tenant_id: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    granularity: str = Query("daily"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Lighter-weight endpoint for chart-data consumers that only
    need metrics + trend, not the full dashboard bundle.
    """

    _verify_tenant_access(current_user, tenant_id)

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)
    _validate_granularity(granularity)

    service = SentimentDashboardService(db)

    return {
        "metrics": service.get_core_metrics(tenant_id, parsed_start, parsed_end),
        "trend": service.get_sentiment_trend(
            tenant_id, granularity, parsed_start, parsed_end
        ),
    }


@router.get("/analyses")
async def get_recent_analyses(
    tenant_id: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return recent tenant-scoped customer message assessments for staff."""
    _verify_tenant_access(current_user, tenant_id)
    role = str(getattr(current_user.role, "value", current_user.role)).lower()
    if role not in {"head", "super_admin", "dispatcher", "admin"}:
        raise HTTPException(status_code=403, detail="Staff access is required.")
    records = (
        db.query(SentimentThreadMessage)
        .filter(SentimentThreadMessage.tenant_id == tenant_id)
        .order_by(SentimentThreadMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": item.id,
                "job_id": item.job_id,
                "source_type": item.source_type,
                "channel": item.channel,
                "message": item.message,
                "sentiment": item.sentiment,
                "emotion": item.emotion,
                "urgency": item.urgency,
                "severity": item.severity,
                "confidence": item.confidence,
                "issue_categories": item.issue_categories or [],
                "requires_human": str(item.requires_human or "").lower() in {"true", "yes", "1"},
                "summary": item.summary,
                "recommended_action": item.recommended_action,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in records
        ]
    }


@router.get("/export")
async def export_dashboard_data(
    tenant_id: str = Query(...),
    format: str = Query("csv", pattern="^(csv|png)$"),
    export_type: str = Query(
        "trend",
        pattern="^(trend|leaderboard|job_type|channel)$",
    ),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    granularity: str = Query("daily"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Exports dashboard data as CSV or a rendered PNG chart.
    """

    _verify_tenant_access(current_user, tenant_id)

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)
    _validate_granularity(granularity)

    service = SentimentDashboardService(db)

    rows, headers, label_index, value_index = _get_export_rows(
        service, export_type, tenant_id, parsed_start, parsed_end, granularity
    )

    if format == "csv":
        return _export_csv(rows, headers, export_type)

    return _export_png(rows, headers, export_type, label_index, value_index)


def _get_export_rows(
    service: "SentimentDashboardService",
    export_type: str,
    tenant_id: str,
    start_date,
    end_date,
    granularity: str,
):
    """
    Returns (rows, headers, label_index, value_index) where
    label_index/value_index tell the PNG renderer which columns
    to use for the x-axis labels and y-axis values for this
    export_type — each export type has a different row shape,
    so this can't be inferred generically from row length.
    """

    if export_type == "trend":
        trend = service.get_sentiment_trend(
            tenant_id, granularity, start_date, end_date
        )
        headers = ["period", "total_replies", "average_score", "moving_average"]
        rows = [
            [b["period"], b["total_replies"], b["average_score"], b["moving_average"]]
            for b in trend["buckets"]
        ]
        return rows, headers, 0, 2

    if export_type == "leaderboard":
        leaderboard = service.get_technician_leaderboard(
            tenant_id, start_date, end_date
        )
        headers = ["rank", "technician_name", "total_replies", "average_score"]
        rows = [
            [t["rank"], t["technician_name"], t["total_replies"], t["average_score"]]
            for t in leaderboard
        ]
        return rows, headers, 1, 3

    if export_type == "job_type":
        breakdown = service.get_job_type_breakdown(tenant_id, start_date, end_date)
        headers = ["service_type", "total_replies", "average_score"]
        rows = [
            [b["service_type"], b["total_replies"], b["average_score"]]
            for b in breakdown
        ]
        return rows, headers, 0, 2

    breakdown = service.get_channel_breakdown(tenant_id, start_date, end_date)
    headers = ["channel", "total_replies", "average_score"]
    rows = [[b["channel"], b["total_replies"], b["average_score"]] for b in breakdown]
    return rows, headers, 0, 2


def _export_csv(rows: list, headers: list, export_type: str) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([[_csv_safe(v) for v in row] for row in rows])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=sentiment_{export_type}.csv"
            )
        },
    )


def _export_png(
    rows: list,
    headers: list,
    export_type: str,
    label_index: int,
    value_index: int,
) -> StreamingResponse:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not rows:
        raise HTTPException(status_code=404, detail="No data to export.")

    labels = [str(r[label_index]) for r in rows]
    values = [r[value_index] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, values)
    ax.set_title(f"Sentiment {export_type.replace('_', ' ').title()}")
    ax.set_ylabel(headers[value_index].replace("_", " ").title())
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f"attachment; filename=sentiment_{export_type}.png"
            )
        },
    )


# ============================================================
# WebSocket / periodic real-time updates
# ============================================================


async def broadcast_metrics_update(
    tenant_id: str,
    service: "SentimentDashboardService",
) -> None:
    """
    Pushes a fresh metrics snapshot to any Socket.IO clients
    connected to this tenant's room.

    Reuses the existing tenant room ("tenant_{tenant_id}") that
    clients already join via the connect() handler in
    socket_manager.py — no new connection/subscription mechanism
    needed.
    """

    payload = {
        "type": "dashboard_metrics_update",
        "metrics": service.get_core_metrics(tenant_id),
        "alert_summary": service.get_alert_summary_counts(tenant_id),
    }

    await ws_manager.broadcast_to_tenant(tenant_id, payload)


async def broadcast_all_tenants(db: Session) -> None:
    """
    Iterates every tenant with sentiment activity and pushes a
    metrics snapshot to each one's room. This is the function a
    scheduler should call every 60 seconds to satisfy the
    "auto-refresh" requirement server-side (in addition to any
    client-side polling fallback).

    Wire this into your existing Celery beat schedule, e.g.:

        # celeryconfig.py / celery_app.conf.beat_schedule
        "broadcast-sentiment-dashboard": {
            "task": "app.sentiment.tasks.broadcast_dashboard_updates",
            "schedule": 60.0,
        }

    and in app/sentiment/tasks.py:

        from app.celery_app import celery_app
        from app.database import SessionLocal
        from app.sentiment.dashboard import broadcast_all_tenants
        import asyncio

        @celery_app.task
        def broadcast_dashboard_updates():
            db = SessionLocal()
            try:
                asyncio.run(broadcast_all_tenants(db))
            finally:
                db.close()
    """

    service = SentimentDashboardService(db)

    tenant_ids = [
        row[0]
        for row in db.query(SentimentThreadMessage.tenant_id).distinct().all()
    ]

    for tenant_id in tenant_ids:
        await broadcast_metrics_update(tenant_id, service)
