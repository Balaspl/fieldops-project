from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from ..models_legacy import Base


class SentimentEscalation(Base):
    """
    Stores manager escalations triggered by negative customer sentiment.
    """

    __tablename__ = "sentiment_escalations"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
    )

    tenant_id = Column(
        String(50),
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    job_id = Column(
        Integer,
        ForeignKey(
            "jobs.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    customer_id = Column(
        String(36),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    customer_name = Column(
        String(200),
        nullable=False,
    )

    technician_name = Column(
        String(200),
        nullable=True,
    )

    # Original customer reply that caused the escalation.
    reply_text = Column(
        Text,
        nullable=False,
    )

    # NEGATIVE / etc.
    sentiment_label = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Sentiment confidence/score used for escalation.
    sentiment_score = Column(
        Float,
        nullable=False,
    )

    # Why the escalation was triggered.
    # Examples:
    # "NEGATIVE_SENTIMENT"
    # "COMPLAINT_KEYWORD"
    # "REPEATED_NEGATIVE"
    # "HUMAN_REQUEST"
    trigger_reason = Column(
        String(100),
        nullable=False,
        index=True,
    )

    suggested_action = Column(
        Text,
        nullable=True,
    )

    # Assigned manager.
    assigned_manager_id = Column(
        String(36),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # OPEN -> ACKNOWLEDGED -> RESOLVED
    status = Column(
        String(20),
        nullable=False,
        default="OPEN",
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    acknowledged_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Manager must acknowledge within 15 minutes.
    acknowledge_deadline = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Escalation must be resolved within 2 hours.
    resolve_deadline = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    resolution_notes = Column(
        Text,
        nullable=True,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_sentiment_escalations_tenant_job_created",
            "tenant_id",
            "job_id",
            "created_at",
        ),
        Index(
            "idx_sentiment_escalations_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "idx_sentiment_escalations_tenant_manager",
            "tenant_id",
            "assigned_manager_id",
        ),
    )
