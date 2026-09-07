from typing import Optional

from sqlalchemy import Boolean,CheckConstraint,Column,Date,DateTime,Float,ForeignKey,Index,Integer,JSON,String, Text,UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from .database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    parent_tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=True)


class Technician(Base):
    __tablename__ = "technicians"

    technician_id = Column(Integer, primary_key=True, index=True)
    tech_id = Column(String(36), unique=True, index=True, nullable=True) # Added for heartbeat UUID
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=True) # Added for tenant isolation
    technician_name = Column(String(100), nullable=False)
    technician_skill = Column(String(100), nullable=False)
    certifications_data = Column(JSON, nullable=True)
    technician_location = Column(String(150), nullable=False)
    technician_status = Column(String(30), default="AVAILABLE")
    current_jobs = Column(Integer, default=0)
    max_jobs = Column(Integer, default=5)
    last_ping = Column(DateTime(timezone=True), nullable=True) # Added for heartbeat
    fcm_token = Column(String(255), nullable=True) # Added for FCM
    device_type = Column(String(20), nullable=True) # 'android' or 'ios'
    phone_number = Column(String(20), nullable=True) # E.164 format
    sms_opt_out = Column(Integer, default=0) # 0 for false, 1 for true
    notification_preferences = Column(JSON, default={
        "sms_enabled": True,
        "push_enabled": True,
        "inapp_enabled": True,
        "email_enabled": False
    })
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    jobs = relationship("Job", back_populates="technician")
    organization=relationship("Organization",back_populates="technicans")


class Job(Base):
    __tablename__ = "jobs"  

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=True) # Added for tenant isolation
    customer_name = Column(String(100), nullable=False)
    location = Column(String(150), nullable=False)
    issue_description = Column(Text, nullable=False)
    priority = Column(String(20), nullable=False)
    service_type = Column(String(50), nullable=False)
    contact_number = Column(String(15), nullable=False)
    preferred_service_date = Column(Date, nullable=False)
    required_skill = Column(String(100), nullable=True) # My addition
    status = Column(String(30), default="CREATED")
    assigned_technician_id = Column(Integer, ForeignKey("technicians.technician_id"), nullable=True) # My addition
    sla_deadline = Column(DateTime(timezone=True), nullable=True) # Added for SLA tracking
    attempt_count = Column(Integer, default=0)
    gps_active = Column(Boolean, default=False, nullable=False)
    work_report = Column(Text, nullable=True)
    customer_id = Column(String(50), nullable=True)
    customer_email = Column(String(100), nullable=True)
    geofence_radius = Column(Float, default=100.0, nullable=False)
    previous_priority = Column(String(20), nullable=True)
    bumped_at = Column(DateTime(timezone=True), nullable=True)
    site_latitude = Column(Float, nullable=True)
    site_longitude = Column(Float, nullable=True)
    site_address = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Transition timestamps
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    en_route_at = Column(DateTime(timezone=True), nullable=True)
    on_site_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Transition actors
    assigned_by = Column(String(50), nullable=True)
    en_route_by = Column(String(50), nullable=True)
    on_site_by = Column(String(50), nullable=True)
    completed_by = Column(String(50), nullable=True)
    cancelled_by = Column(String(50), nullable=True)
    closed_by = Column(String(50), nullable=True)

    # Reason fields
    cancellation_reason = Column(Text, nullable=True)
    closure_reason = Column(Text, nullable=True)

    # Technician rejection fields
    rejection_reason = Column(Text, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by_tech_id = Column(String(50), nullable=True)

    # Share tracking link fields
    share_token = Column(String(36), unique=True, index=True, nullable=True)
    share_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    technician = relationship("Technician", back_populates="jobs")
    organization=relationship("Organization",back_populates="jobs")

    @property
    def technician_id(self) -> Optional[str]:
        return str(self.assigned_technician_id) if self.assigned_technician_id is not None else None

    def transition(self, new_status, actor_id: str, actor_role: str, reason: str = None, is_override: bool = False) -> None:
        from .services.job_status_machine import transition_job
        transition_job(self, new_status, actor_id, actor_role, reason, is_override)



class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    tech_id = Column(String(36), nullable=True, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Fields required for job status transition audit trail
    job_id = Column(String(36), nullable=True, index=True)
    actor_id = Column(String(50), nullable=True)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String(36), nullable=True)
    organization=relationship("Organization",back_populates="audit_events")


class DispatcherNotification(Base):
    __tablename__ = "dispatcher_notifications"

    id = Column(Integer, primary_key=True, index=True)
    tech_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"),nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization=relationship("Organization",back_populates="dispatcher_notifications")

class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    tech_id = Column(String(36),ForeignKey("technicians.tech_id"),nullable=False)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"),nullable=False,index=True)
    job_id = Column(Integer,ForeignKey("jobs.id"),nullable=False,index=True)    
    fcm_message_id = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="sent") # sent, delivered, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


    organization = relationship("Organization",back_populates="notification_deliveries")

class SMSDelivery(Base):
    __tablename__ = "sms_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    tech_id = Column(String(36), nullable=False, index=True)
    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    job_id = Column(String(36), nullable=False, index=True)
    sms_sid = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="queued") # queued, sent, delivered, failed, undelivered
    cost = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class InAppNotification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True) # Using UUID string for portability
    tech_id = Column(String(36), ForeignKey("technicians.tech_id"), nullable=False)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True) 
    job_id = Column(String(36), nullable=True) # Assuming jobs use string UUIDs in some contexts, or int
    type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    status = Column(String(20), default="UNREAD")
    action_url = Column(String(500), nullable=True)
    action_type = Column(String(50), nullable=True)
    priority = Column(String(20), default="NORMAL")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    notification_metadata = Column(JSON, default=dict)

    organization=relationship("Organization",back_populates="InApp_Notification")

    __table_args__ = (
        CheckConstraint("status IN ('UNREAD', 'READ', 'DISMISSED')", name="valid_status"),
        Index("idx_notifications_tech_status", "tech_id", "status"),
        Index("idx_notifications_created_at", "created_at"),
        Index("idx_notifications_type", "type"),
    )

class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String(100),
        nullable=False,
    )

    type = Column(
        String(50),
        nullable=False,
    )

    channel = Column(
        String(20),
        nullable=False,
    )

    locale = Column(
        String(10),
        nullable=False,
        default="en",
    )

    format = Column(
        String(20),
        nullable=False,
        default="text",
    )

    title_template = Column(
        Text,
        nullable=True,
    )

    body_template = Column(
        Text,
        nullable=False,
    )

    variables = Column(
        JSON,
        nullable=False,
        default=list,
    )

    version = Column(
        Integer,
        nullable=False,
        default=1,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    tenant_id = Column(
    String(50),
    ForeignKey("organizations.id", ondelete="RESTRICT"),
    nullable=False,
    index=True,
    default="**platform**",
    )

    agent_type = Column(
        String(50),
        nullable=False,
        index=True,
        default="CommsAgent",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    is_deleted = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    deleted_by = Column(
        String(100),
        nullable=True,
    )

    versions = relationship(
        "TemplateVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by=(
            "TemplateVersion.version_number.desc()"
        ),
    )

    organization = relationship(
    "Organization",
    back_populates="notification_templates",
)

    __table_args__ = (
        Index(
            "idx_template_lookup",
            "type",
            "channel",
            "locale",
            "is_active",
        ),
        Index(
            "idx_managed_prompt_lookup",
            "tenant_id",
            "agent_type",
            "channel",
            "locale",
            "type",
            "is_active",
        ),
        UniqueConstraint(
            "tenant_id",
            "agent_type",
            "channel",
            "locale",
            "type",
            "version",
            name=(
                "uq_notification_templates_lookup"
            ),
        ),
    )
class TemplateVersion(Base):
    __tablename__ = "template_versions"

    id = Column(Integer, primary_key=True, index=True)

    template_id = Column(
        Integer,
        ForeignKey("notification_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_number = Column(Integer, nullable=False)

    name = Column(String(100), nullable=True)
    type = Column(String(50), nullable=True)
    channel = Column(String(20), nullable=True)
    locale = Column(String(10), nullable=True)
    format = Column(String(20), nullable=True)
    agent_type = Column(String(50), nullable=True)
    variables = Column(JSON, nullable=True)

    title_template = Column(Text, nullable=True)
    body_template = Column(Text, nullable=False)

    created_by = Column(String(100), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    change_summary = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    template_is_active = Column(Boolean, nullable=True)
    restored_from_version = Column(Integer, nullable=True)

    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String(100), nullable=True)

    template = relationship(
        "NotificationTemplate",
        back_populates="versions",
    )

    __table_args__ = (
        Index(
            "idx_template_version",
            "template_id",
            "version_number",
        ),
        UniqueConstraint(
            "template_id",
            "version_number",
            name="uq_template_version"
        ),                                                                                      
        Index(
            "idx_active_template_version",
            "template_id",
            unique=True,
            postgresql_where=(is_active == True) & (is_deleted == False),
            sqlite_where=(is_active == True) & (is_deleted == False),
        ),
    )
    

class PreferenceAuditLog(Base):
    __tablename__ = "preference_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    tech_id = Column(String(36), nullable=False, index=True)
    updated_by = Column(String(50), nullable=False)
    old_preferences = Column(JSON, nullable=True)
    new_preferences = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization=relationship("Organization",back_populates="preference_audit_logs")

class SkillTaxonomy(Base):
    __tablename__ = "skill_taxonomy"

    id = Column(String(50), primary_key=True, default="default")
    taxonomy_data = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScoringConfiguration(Base):
    __tablename__ = "scoring_configurations"
    id = Column(Integer, primary_key=True,autoincrement=True, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    proximity_weight = Column(Float, default=0.4)
    skill_weight = Column(Float, default=0.4)
    workload_weight = Column(Float, default=0.2)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    organization=relationship("Organization",back_populates="scoring_configurations")


from sqlalchemy import event

@event.listens_for(AuditEvent, "before_update")
def prevent_audit_event_update(mapper, connection, target):
    raise ValueError("AuditEvent is immutable")

@event.listens_for(AuditEvent, "before_delete")
def prevent_audit_event_delete(mapper, connection, target):
    raise ValueError("AuditEvent is immutable")

class AIBrandSafetyRule(Base):
    """
    Tenant-specific brand-safety rule configured by an
    administrator.

    These rules are loaded by the database/Redis brand-safety
    provider and used by BrandSafetyValidator.
    """

    __tablename__ = "ai_brand_safety_rules"

    id = Column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()),)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    rule_id = Column(String(100),nullable=False,)
    category = Column(String(30),nullable=False,)
    match_type = Column(String(20),nullable=False,)
    pattern = Column(String(200),nullable=False,)
    severity = Column(String(20),nullable=False,default="ERROR",)
    active = Column(Boolean,nullable=False,default=True,)
    case_sensitive = Column(Boolean,nullable=False,default=False,)
    created_by = Column(String(100),nullable=False,)
    updated_by = Column(String(100),nullable=True,)
    created_at = Column(DateTime(timezone=True),server_default=func.now(),nullable=False,)
    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False,)
    organization=relationship("Organization",back_populates="ai_brand_safety_rules")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "rule_id",
            name="uq_ai_brand_safety_tenant_rule",
        ),
        CheckConstraint(
            "category IN ("
            "'COMPETITOR', "
            "'POLITICAL', "
            "'OFF_BRAND', "
            "'BLOCKED_PHRASE'"
            ")",
            name="ck_ai_brand_safety_category",
        ),
        CheckConstraint(
            "match_type IN ('WORD', 'PHRASE')",
            name="ck_ai_brand_safety_match_type",
        ),
        CheckConstraint(
            "severity IN ("
            "'INFO', "
            "'WARNING', "
            "'ERROR', "
            "'CRITICAL'"
            ")",
            name="ck_ai_brand_safety_severity",
        ),
        Index(
            "idx_ai_brand_safety_tenant_active",
            "tenant_id",
            "active",
        ),
        Index(
            "idx_ai_brand_safety_tenant_category",
            "tenant_id",
            "category",
        ),
    )

class SLAEscalation(Base):
    __tablename__ = "sla_escalations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    manager_notified_at = Column(DateTime(timezone=True), nullable=True)
    manager_responded_at = Column(DateTime(timezone=True), nullable=True)
    cto_notified_at = Column(DateTime(timezone=True), nullable=True)
    action_taken = Column(String(100), nullable=True)
    status = Column(String(50), default="ESCALATED")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization=relationship("Organization",back_populates="sla_escalations")

class DispatcherAlert(Base):
    __tablename__ = "dispatcher_alerts"
    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"),nullable=False, index=True)
    type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    attempt_count = Column(Integer, nullable=False)
    max_attempts = Column(Integer, nullable=False)
    excluded_technicians = Column(JSON, nullable=True)
    recommended_action = Column(Text, nullable=True)
    acknowledged = Column(Integer, default=0) # 0 for false, 1 for true
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="dispatcher_alerts")
    
class OverrideAuditEvent(Base):
    __tablename__ = "override_audit_events"

    id = Column(String(36), primary_key=True)
    event_type = Column(String(50), nullable=False, default="manual_override")
    actor_id = Column(String(36), nullable=False, index=True)
    actor_role = Column(String(50), nullable=False)
    actor_name = Column(String(200), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    
    before_state = Column(JSON, nullable=False)
    after_state = Column(JSON, nullable=False)
    
    justification = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    correlation_id = Column(String(36), nullable=True)
    
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization=relationship("Organization",back_populates="override_audit_events")

@event.listens_for(OverrideAuditEvent, "before_update")
def prevent_override_audit_event_update(mapper, connection, target):
    raise ValueError("OverrideAuditEvent is immutable (BR-009)")

@event.listens_for(OverrideAuditEvent, "before_delete")
def prevent_override_audit_event_delete(mapper, connection, target):
    raise ValueError("OverrideAuditEvent is immutable (BR-009)")

class AIGuardrailViolation(Base):
    """
    Immutable audit record for one AI guardrail violation.

    The table stores audit-safe metadata only.

    Raw prompts, generated communication, customer PII, and
    matched prohibited text must never be stored here.
    """

    __tablename__ = "ai_guardrail_violations"

    id = Column(String(36),primary_key=True,default=lambda: str(uuid.uuid4()),)

    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)

    correlation_id = Column(String(100),nullable=True,index=True,)

    job_id = Column(String(100),nullable=True,index=True,)

    agent_name = Column(String(100),nullable=False,index=True,)

    notification_type = Column(String(100),nullable=True,index=True,)

    channel = Column(String(20),nullable=False,index=True,)

    checker_name = Column(String(100),nullable=False,index=True,)

    violation_code = Column(String(100),nullable=False,index=True,)

    category = Column(String(50),nullable=False,index=True,)

    severity = Column(String(20),nullable=False,index=True,)

    affected_field = Column(String(50),nullable=True,)

    safe_message = Column(Text,nullable=False,)

    safe_metadata = Column(JSON,nullable=False,default=dict,)

    pipeline_decision = Column(String(20),nullable=False,index=True,)

    fallback_triggered = Column(Boolean,nullable=False,default=False,index=True,)

    prompt_hash = Column(String(64),nullable=False,index=True,)

    output_hash = Column(String(64),nullable=False,index=True,)

    checker_latency_ms = Column(Float,nullable=False,default=0.0,)

    total_latency_ms = Column(Float,nullable=False,default=0.0,)

    created_at = Column(DateTime(timezone=True),server_default=func.now(),nullable=False,index=True,)

    organization=relationship("Organization",back_populates="ai_guardrail_violations")

    __table_args__ = (
        Index("idx_ai_guardrail_tenant_created","tenant_id","created_at",),
        Index("idx_ai_guardrail_job_created","job_id","created_at",),
        Index("idx_ai_guardrail_code_created","violation_code","created_at",),
    )


@event.listens_for(
    AIGuardrailViolation,
    "before_update",
)
def prevent_ai_guardrail_violation_update(
    mapper,
    connection,
    target,
):
    """
    Prevent modification of an existing guardrail audit record.
    """

    raise ValueError(
        "AIGuardrailViolation is immutable."
    )


@event.listens_for(
    AIGuardrailViolation,
    "before_delete",
)
def prevent_ai_guardrail_violation_delete(
    mapper,
    connection,
    target,
):
    """
    Prevent deletion of an existing guardrail audit record.
    """

    raise ValueError(
        "AIGuardrailViolation is immutable."
    )


class AssignmentOverride(Base):
    __tablename__ = "assignment_overrides"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    actor_name = Column(String(100), nullable=False)
    actor_role = Column(String(30), nullable=False)
    justification = Column(Text, nullable=False)
    previous_technician_id = Column(Integer, ForeignKey("technicians.technician_id"), nullable=True)
    previous_technician_name = Column(String(100), nullable=True)
    new_technician_id = Column(Integer, ForeignKey("technicians.technician_id"), nullable=False)
    new_technician_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization=relationship("Organization",back_populates="assignment_overrides")


class GPSPing(Base):
    __tablename__ = "gps_pings"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    technician_id = Column(String(36), ForeignKey("technicians.tech_id"), nullable=False, index=True)
    job_id = Column(String(36), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    accuracy = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    correlation_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization=relationship("Organization",back_populates="gps_pings")


class TenantGPSConfiguration(Base):
    __tablename__ = "tenant_gps_configurations"
    
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key= True)
    retention_days = Column(Integer, nullable=False, default=30)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    organization=relationship("Organization",back_populates="tenant_gps_configurations")

    __table_args__ = (
        CheckConstraint("retention_days BETWEEN 1 AND 90", name="valid_retention_days"),
    )


class GPSPurgeAuditLog(Base):
    __tablename__ = "gps_purge_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    job_id = Column(String(36), nullable=True, index=True)
    purge_type = Column(String(20), nullable=False)  # 'age_based', 'event_based', 'manual'
    deleted_count = Column(Integer, nullable=False)
    correlation_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    organization=relationship("Organization",back_populates="gps_purge_audit_logs")


class GPSRejectedPingLog(Base):
    __tablename__ = "gps_rejected_ping_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    technician_id = Column(String(50), nullable=True, index=True)
    job_id = Column(String(36), nullable=True, index=True)
    reason = Column(String(200), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    organization=relationship("Organization",back_populates="gps_rejected_ping_logs")


@event.listens_for(Job, 'after_update')
def on_job_status_changed(mapper, connection, target):
    from sqlalchemy import inspect
    from sqlalchemy.orm import object_session
    from sqlalchemy import event as sa_event
    state = inspect(target)
    history = state.get_history('status', True)
    if history.has_changes():
        new_status = history.added[0] if history.added else None
        old_status = history.deleted[0] if history.deleted else None
        
        from .redis_client import get_redis_client
        from .context import correlation_id_ctx
        import time

        job_id = target.id
        tenant_id = target.tenant_id or "tenant-1"
        correlation_id = correlation_id_ctx.get() or None

        # Store transition start time in Redis for SLA tracking
        try:
            redis_client = get_redis_client()
            if redis_client:
                redis_client.set(f"gps_purge_start_time:{job_id}", str(time.time()), ex=3600)
        except Exception:
            pass

        def dispatch_tasks():
            # Trigger GPS Purge if terminal
            if new_status and str(new_status).upper().strip() in ["CLOSED", "CANCELLED", "CANCELED"]:
                from .tasks import purge_job_gps_data_task, execute_job_gps_purge_sync
                from .database import SessionLocal
                import threading
                try:
                    purge_job_gps_data_task.delay(job_id, tenant_id, "event_based", correlation_id)
                except Exception:
                    def run_purge_in_thread():
                        db = SessionLocal()
                        try:
                            execute_job_gps_purge_sync(db, job_id, tenant_id, "event_based", correlation_id)
                        finally:
                            db.close()
                    threading.Thread(target=run_purge_in_thread).start()

            # Trigger transition processing (notifications, SLA, events)
            from .tasks import process_job_status_transition_task
            from .database import SessionLocal
            import threading
            actor_id = getattr(target, "_actor_id", "system")
            actor_role = getattr(target, "_actor_role", "system")
            reason = getattr(target, "_transition_reason", None)
            try:
                process_job_status_transition_task.delay(
                    job_id, old_status, new_status, actor_id, actor_role, reason, correlation_id
                )
            except Exception:
                def run_transition_in_thread():
                    db = SessionLocal()
                    try:
                        process_job_status_transition_task(
                            job_id, old_status, new_status, actor_id, actor_role, reason, correlation_id
                        )
                    finally:
                        db.close()
                threading.Thread(target=run_transition_in_thread).start()

        session = object_session(target)
        if session:
            @sa_event.listens_for(session, "after_commit", once=True)
            def do_after_commit(session_arg):
                dispatch_tasks()
        else:
            dispatch_tasks()


class CommunicationChannelConfiguration(Base):
    __tablename__ = "communication_channel_configurations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)
    state = Column(String(20), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    organization=relationship("Organization",back_populates="communication_channel_configurations")

    __table_args__ = (
        UniqueConstraint("tenant_id","channel", name="uq_communication_channel_configuration_channel"),
        CheckConstraint("state IN ('ENABLED', 'DISABLED', 'EMERGENCY_ONLY')", name="ck_communication_channel_state"),
        CheckConstraint("revision >= 1", name="ck_communication_channel_revision"),
    )

class CommunicationConfigurationAudit(Base):
    __tablename__ = "communication_configuration_audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    channel = Column(String(50), nullable=False, index=True)
    previous_state = Column(String(20), nullable=True)
    new_state = Column(String(20), nullable=False)
    previous_revision = Column(Integer, nullable=True)
    new_revision = Column(Integer, nullable=False)
    actor_id = Column(String(100), nullable=False)
    actor_tenant_id = Column(String(50), nullable=False)
    reason = Column(String(500), nullable=False)
    correlation_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    organization=relationship("Organization",back_populates="communication_configuration_audits")

@event.listens_for(CommunicationConfigurationAudit, "before_update")
def prevent_communication_audit_update(mapper, connection, target):
    raise ValueError("CommunicationConfigurationAudit is immutable")

@event.listens_for(CommunicationConfigurationAudit, "before_delete")
def prevent_communication_audit_delete(mapper, connection, target):
    raise ValueError("CommunicationConfigurationAudit is immutable")



class ETAHistory(Base):
    __tablename__ = "eta_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    eta = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Float, nullable=False)
    distance_km = Column(Float, nullable=False)
    traffic_delay_minutes = Column(Float, default=0.0)
    source_ping_id = Column(String(36), ForeignKey("gps_pings.id"), nullable=False, index=True)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)

    organization=relationship("Organization",back_populates="eta_history")


@event.listens_for(GPSPing, "after_insert")
def on_new_gps_ping(mapper, connection, target):
    job_id_int = int(target.job_id) if str(target.job_id).isdigit() else None
    if not job_id_int:
        return

    from sqlalchemy import select
    from sqlalchemy.orm import object_session
    from sqlalchemy import event as sa_event

    # Check job status using the event connection (safe, no new session needed)
    job = connection.execute(
        select(Job).where(Job.id == job_id_int)
    ).fetchone()

    # Check throttle
    throttle_key = f"eta:throttle:{job_id_int}"
    from .redis_client import get_redis_client
    redis = get_redis_client()
    if redis:
        try:
            if redis.get(throttle_key):
                return
            # Set throttle key with 30s TTL
            redis.setex(throttle_key, 30, "1")
            
            # Invalidate old ETA cache
            redis.delete(f"eta:{target.technician_id}:{job_id_int}")
            redis.delete(f"eta:fallback:{target.technician_id}:{job_id_int}")
        except Exception:
            pass

    def dispatch_gps_tasks():
        # Run geofence check
        from .services.geofence_monitor import GeofenceMonitor
        from .database import SessionLocal
        db = SessionLocal()
        try:
            monitor = GeofenceMonitor()
            monitor.process_ping(db, target)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to check geofence on new GPS ping: {e}")
        finally:
            db.close()

        if job and str(job.status).upper().strip() in ["ASSIGNED", "EN_ROUTE", "ON_SITE"]:
            from .tasks import update_eta_task
            from .context import correlation_id_ctx
            correlation_id = correlation_id_ctx.get() or None
            try:
                update_eta_task.delay(
                    technician_id=target.technician_id,
                    job_id=job_id_int,
                    ping_id=target.id,
                    correlation_id=correlation_id
                )
            except Exception:
                import threading
                from .database import SessionLocal
                def run_in_thread():
                    db = SessionLocal()
                    try:
                        update_eta_task(target.technician_id, job_id_int, target.id, correlation_id)
                    finally:
                        db.close()
                threading.Thread(target=run_in_thread).start()

    session = object_session(target)
    if session:
        @sa_event.listens_for(session, "after_commit", once=True)
        def do_after_commit_gps(session_arg):
            dispatch_gps_tasks()
    else:
        dispatch_gps_tasks()


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id = Column(String(36), primary_key=True)
    event = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    severity = Column(String(20), nullable=False)
    user_tenant = Column(String(50), nullable=True, index=True)
    attempted_channel = Column(String(200), nullable=True)
    ip_address = Column(String(50), nullable=True)
    websocket_id = Column(String(50), nullable=True)
    action_taken = Column(String(50), nullable=True)
    payload_tenant = Column(String(50), nullable=True, index=True)
    target_tenant = Column(String(50), nullable=True, index=True)
    technician_id = Column(String(50), nullable=True)
    job_id = Column(String(50), nullable=True)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    organization=relationship("Organization",back_populates="security_audit_logs")

class JobAssignment(Base):
    """
    Stores the AI-ranked technician recommendations for a job.

    One row represents one recommended technician.
    """
    __tablename__ = "job_assignments"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer,ForeignKey("jobs.id"),nullable=False,index=True,)
    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"),nullable=False, index=True)
    technician_id = Column(Integer,ForeignKey("technicians.technician_id"),nullable=False,index=True,)
    rank = Column(Integer,nullable=False,)  
    status = Column(String(30),nullable=False,default="PENDING",)
    assigned_at = Column(DateTime(timezone=True),nullable=True,)
    responded_at = Column(DateTime(timezone=True),nullable=True,)
    is_current = Column(Boolean,nullable=False,default=False,)  
    created_at = Column(DateTime(timezone=True),server_default=func.now(),)

    organization = relationship("Organization", back_populates="job_assignments")

class AgentStateRecord(Base):
    """
    Persistent snapshot of a FieldOps AI agent's runtime state.

    Story 1.5 — Persistent Agent State.

    Privacy rules
    -------------
    Only operational metadata is stored here.  The following are
    strictly forbidden:
    - API keys
    - Prompts
    - AI provider responses
    - Customer names, addresses, or contact details
    - Technician GPS or private information
    - Message contents or full job payloads
    - Authentication tokens

    Constraints
    -----------
    - At most one record per (tenant_id, agent_id) pair.
    - agent_id is stored as a String(36) UUID.
    - state stores the AgentState string value.
    - agent_type stores the AITask string value.
    - metadata is a JSON column (safe operational counters only).
    """

    __tablename__ = "agent_state_records"

    id = Column(Integer, primary_key=True, index=True)

    agent_id = Column(
        String(36),
        nullable=False,
        comment="UUID4 agent instance identifier.",
    )

    agent_type = Column(
        String(50),
        nullable=False,
        comment="AITask value for this agent.",
    )

    tenant_id = Column(
        String(50),
        ForeignKey("organizations.id", 
        ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant that owns this agent."
    )

    agent_version = Column(
        String(50),
        nullable=False,
        default="1.0",
        comment="Agent implementation version.",
    )

    state = Column(
        String(30),
        nullable=False,
        comment="AgentState string value.",
    )

    correlation_id = Column(
        String(100),
        nullable=True,
        comment="Correlation ID from the last lifecycle event.",
    )

    last_error = Column(
        String(500),
        nullable=True,
        comment="Safe error summary only — no stack traces or secrets.",
    )

    safe_metadata = Column(
        JSON,
        nullable=True,
        default=dict,
        comment="Safe operational metadata — no customer data or secrets.",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization=relationship("Organization",back_populates="agent_state_records")


    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_id",
            name="uq_agent_state_tenant_agent",
        ),
        Index(
            "idx_agent_state_tenant",
            "tenant_id",
        ),
        Index(
            "idx_agent_state_agent_id",
            "agent_id",
        ),
        Index(
            "idx_agent_state_tenant_state",
            "tenant_id",
            "state",
        ),
    )


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    __table_args__ = (
        UniqueConstraint('tenant_id', 'customer_id', name='uq_customer_profiles_tenant_customer'),
        CheckConstraint('revision >= 1', name='chk_customer_profiles_revision_positive'),
        Index('ix_customer_profiles_tenant_id', 'tenant_id'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), nullable=False)
    customer_id = Column(String(50), nullable=False)
    preferred_locale = Column(String(10), nullable=False, default="en")

    sms_enabled = Column(Boolean, nullable=False, default=True)
    email_enabled = Column(Boolean, nullable=False, default=True)
    push_enabled = Column(Boolean, nullable=False, default=False)
    portal_enabled = Column(Boolean, nullable=False, default=True)

    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CustomerPreferenceAudit(Base):
    __tablename__ = "customer_preference_audits"

    __table_args__ = (
        CheckConstraint("actor_source IN ('CUSTOMER', 'ADMIN', 'SYSTEM')", name="chk_audit_actor_source"),
        CheckConstraint("previous_revision >= 0", name="chk_audit_prev_revision"),
        CheckConstraint("new_revision >= 1", name="chk_audit_new_revision"),
        CheckConstraint("new_revision > previous_revision", name="chk_audit_revision_progression"),
        Index('ix_customer_preference_audits_profile_id', 'customer_profile_id'),
        Index('ix_customer_preference_audits_tenant_profile', 'tenant_id', 'customer_profile_id'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_profile_id = Column(String(36), ForeignKey("customer_profiles.id"), nullable=False)

    tenant_id = Column(String(50),ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    previous_revision = Column(Integer, nullable=False)
    new_revision = Column(Integer, nullable=False)
    changed_fields = Column(JSON, nullable=False)
    actor_id = Column(String(100), nullable=False)
    actor_source = Column(String(50), nullable=False)
    correlation_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    organization=relationship("Organization",back_populates="customer_preference_audits")

class RedispatchAttempt(Base):
    __tablename__ = "redispatch_attempts"

    id = Column(Integer, primary_key=True)

    job_id = Column(
        Integer,
        nullable=False,
    )

    attempt_number = Column(
        Integer,
        nullable=False,
    )

    technician_id = Column(
        Integer,
        nullable=True,
    )

    technician_name = Column(
        String(100),
        nullable=True,
    )

    event_type = Column(
        String(30),
        nullable=False,
    )

    reason = Column(
        String(255),
        nullable=True,
    )

    queue_position = Column(
        Integer,
        nullable=True,
        default=1,
    )

    next_dispatch_eta = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "idx_redispatch_attempts_job_id",
            "job_id",
        ),
    )

# class Organization(Base):
#     __tablename__ = "organizations"

#     id = Column(String(50), primary_key=True, index=True)
#     name = Column(String(150), nullable=True)
#     slug = Column(String(100), nullable=True)
#     status = Column(String(30), nullable=True)
#     subscription_plan = Column(String(50), nullable=True)
#     max_users = Column(Integer, nullable=True)
#     max_technicians = Column(Integer, nullable=True)
#     max_jobs_per_month = Column(Integer, nullable=True)
#     settings = Column(JSON, nullable=True)
#     contact_email = Column(String(150), nullable=True)
#     contact_phone = Column(String(20), nullable=True)
#     address = Column(Text, nullable=True)
#     logo_url = Column(String(500), nullable=True)
#     primary_color = Column(String(20), nullable=True)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
#     deleted_at = Column(DateTime(timezone=True), nullable=True)
#     deleted_by = Column(String(100), nullable=True)
#     suspended_at = Column(DateTime(timezone=True), nullable=True)
#     suspended_by = Column(String(100), nullable=True)
#     suspension_reason = Column(Text, nullable=True)



@event.listens_for(CustomerPreferenceAudit, "before_update")
def prevent_customer_preference_audit_update(mapper, connection, target):
    raise ValueError("CustomerPreferenceAudit is immutable")

@event.listens_for(CustomerPreferenceAudit, "before_delete")
def prevent_customer_preference_audit_delete(mapper, connection, target):
    raise ValueError("CustomerPreferenceAudit is immutable")
