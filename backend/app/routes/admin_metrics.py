from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permission
from app.auth.rbac import Permission
from app.runtime.metrics import MetricsCollector
from app.services.kafka.consumer import DEFAULT_CONSUMER_GROUPS
from app.services.kafka.monitoring import kafka_monitoring

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

    return {
        "broker": broker,
        "topics": topics,
        "consumer_lag": consumer_lag,
        "operations": kafka_monitoring.snapshot(),
    }