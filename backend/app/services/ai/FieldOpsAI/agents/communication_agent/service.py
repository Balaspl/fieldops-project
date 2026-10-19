
"""Entry point for the LangGraph Communication Agent.

Responsibilities:
- Validate job ID and persisted event version.
- Execute the communication graph.
- Return persisted notification IDs to the caller.
- Allow graph failures to propagate so the caller can handle them.

The event producer must allocate and persist event_version.
Never generate a new event version here.
"""

import logging

from .events import JobEvent
from .graph import communication_graph

logger = logging.getLogger(__name__)


def handle(
    db,
    job_id: int,
    event: JobEvent,
    technician_id: int | None = None,
    version: int | None = None,
    correlation_id: str | None = None,
) -> list[str]:
    """Execute the Communication Agent graph for one job event."""

    # Validate the job ID.
    if (
        not isinstance(job_id, int)
        or isinstance(job_id, bool)
        or job_id < 1
    ):
        raise ValueError(
            "Communication Agent requires a valid positive job_id"
        )

    # Validate the persisted event version.
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise ValueError(
            "Communication Agent requires a persisted positive event_version"
        )

    # Accept either a JobEvent enum or its string value.
    try:
        normalized_event = (
            event if isinstance(event, JobEvent) else JobEvent(event)
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Communication Agent received an invalid event: {event!r}"
        ) from exc

    if technician_id is not None and (
        not isinstance(technician_id, int)
        or isinstance(technician_id, bool)
        or technician_id < 1
    ):
        raise ValueError(
            "Communication Agent received an invalid technician_id"
        )

    logger.info(
        "Communication Agent starting",
        extra={
            "job_id": str(job_id),
            "event_type": normalized_event.value,
            "event_version": version,
            "technician_id": technician_id,
            "correlation_id": correlation_id,
        },
    )

    # Run the existing LangGraph pipeline.
    # The same SQLAlchemy session is supplied to the graph.
    result = communication_graph.invoke(
        {
            "job_id": job_id,
            "event": normalized_event.value,
            "event_version": version,
            "technician_id": technician_id,
            "correlation_id": correlation_id,
        },
        config={
            "configurable": {
                "db": db,
            }
        },
    )

    notification_ids = result.get("notification_ids", [])

    if not isinstance(notification_ids, list):
        raise RuntimeError(
            "Communication Agent returned an invalid notification_ids value"
        )

    logger.info(
        "Communication Agent finished",
        extra={
            "job_id": str(job_id),
            "event_type": normalized_event.value,
            "event_version": version,
            "notification_count": len(notification_ids),
            "correlation_id": correlation_id,
        },
    )

    return notification_ids
