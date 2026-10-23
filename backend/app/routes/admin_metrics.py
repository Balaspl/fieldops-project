from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permission
from app.auth.rbac import Permission
from app.runtime.metrics import MetricsCollector
from app.services.kafka.consumer import DEFAULT_CONSUMER_GROUPS
from app.services.kafka.monitoring import kafka_monitoring
from app.services.consumer_health_checks import ConsumerHealthChecks
from app.services.consumer_dead_letter_topics import ConsumerDeadLetterTopics

router = APIRouter(prefix="/admin/metrics", tags=["Admin Metrics"])
collector = MetricsCollector()


@router.get("")
def get_metrics() -> dict:
    return collector.snapshot()


@router.get("/agents")
def get_agent_metrics() -> dict:
    return collector.agent_snapshot()


@router.get("/tenants")
def get_tenant_metrics() -> dict:
    return collector.tenant_snapshot()


@router.get(
    "/kafka",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_metrics() -> dict:
    broker = await kafka_monitoring.broker_health()
    topics = await kafka_monitoring.topic_health()

    consumer_lag = {}

    for topic, group_id in DEFAULT_CONSUMER_GROUPS.items():
        consumer_lag[topic] = await kafka_monitoring.consumer_lag(
            topic,
            group_id,
        )

    consumers_health = await ConsumerHealthChecks.get_all_consumers_health_summary()

    return {
        "broker": broker,
        "topics": topics,
        "consumer_lag": consumer_lag,
        "consumer_health": consumers_health,
        "operations": kafka_monitoring.snapshot(),
    }


@router.get(
    "/kafka/consumers",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_consumers_health() -> dict:
    return await ConsumerHealthChecks.get_all_consumers_health_summary()


@router.get(
    "/kafka/dlq",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_dlq_metrics() -> dict:
    dlq_service = ConsumerDeadLetterTopics()
    return dlq_service.get_dlq_metrics()


@router.get(
    "/kafka/idempotency",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_idempotency_metrics() -> dict:
    from app.services.consumer_idempotency import ConsumerIdempotency
    return ConsumerIdempotency.get_idempotency_metrics()


@router.get(
    "/kafka/ordering",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_ordering_metrics() -> dict:
    from app.services.consumer_event_ordering import ConsumerEventOrdering
    return ConsumerEventOrdering.get_ordering_metrics()


@router.get(
    "/kafka/replay",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_replay_metrics() -> dict:
    from app.services.consumer_event_replay import ConsumerEventReplay
    return ConsumerEventReplay.get_replay_metrics()


@router.post(
    "/kafka/replay",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def trigger_kafka_event_replay(request_data: dict) -> dict:
    from app.services.consumer_event_replay import ConsumerEventReplay
    consumer = ConsumerEventReplay()
    event_payload = request_data.get("event") or request_data.get("payload") or request_data
    operator_role = request_data.get("operator_role", "admin")
    operator_id = request_data.get("operator_id", "admin_operator")
    force = bool(request_data.get("force", False))
    reason = request_data.get("reason", "Admin API triggered replay")

    result = await consumer.replay_event(
        event_or_payload=event_payload,
        operator_role=operator_role,
        operator_id=operator_id,
        force=force,
        reason=reason,
    )
    return dict(result)


@router.get(
    "/kafka/offsets",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_offset_metrics() -> dict:
    from app.services.consumer_offset_management import ConsumerOffsetManagement
    return ConsumerOffsetManagement.get_offset_metrics()


@router.get(
    "/kafka/idempotency-keys",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_idempotency_key_metrics() -> dict:
    from app.services.idempotency_keys import ConsumerIdempotencyKeys
    return ConsumerIdempotencyKeys.get_idempotency_metrics()


@router.get(
    "/kafka/failed-events",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_failed_event_metrics() -> dict:
    from app.services.failed_event_storage import FailedEventStorage
    return FailedEventStorage.get_storage_metrics()


@router.get(
    "/kafka/schemas",
    dependencies=[
        Depends(
            require_permission(
                Permission.PLATFORM_HEALTH
            )
        )
    ],
)
async def get_kafka_schema_metrics() -> dict:
    from app.services.event_schema_versioning import EventSchemaVersioning
    return EventSchemaVersioning.get_schema_metrics()




