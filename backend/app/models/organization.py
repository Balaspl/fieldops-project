"""
Organization (Tenant) model for multi-tenant SaaS.

This extends the existing Tenant model with enterprise features:
- Organization status management (active/suspended/deleted)
- Subscription plan tracking
- Resource limits (max users, technicians)
- Soft delete support
"""

import uuid
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, JSON, Float,
    Index, CheckConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base


class Organization(Base):
    """
    Organization (tenant/company) in the platform.

    Every piece of data in the system belongs to exactly one Organization,
    except global platform tables (SkillTaxonomy, etc.).

    The `id` column matches the existing `tenant_id` values used throughout
    the codebase for backward compatibility.
    """
    __tablename__ = "organizations"

    id = Column(String(50), primary_key=True, default=lambda: f"org-{uuid.uuid4().hex[:12]}")
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    
    # Status management
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    # ACTIVE, SUSPENDED, DELETED
    
    # Subscription
    subscription_plan = Column(String(50), nullable=False, default="FREE")
    # FREE, STARTER, PROFESSIONAL, ENTERPRISE
    
    # Resource limits
    max_users = Column(Integer, nullable=False, default=10)
    max_technicians = Column(Integer, nullable=False, default=50)
    max_jobs_per_month = Column(Integer, nullable=False, default=500)
    
    # Organization settings (JSON for flexibility)
    settings = Column(JSON, nullable=False, default=dict)
    
    # Contact info
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)

    # Organization location
    site_latitude = Column(Float, nullable=True)
    site_longitude = Column(Float, nullable=True)
    
    # Branding
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), nullable=True)  # hex color
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String(36), nullable=True)

    #relationship
    users = relationship("User",back_populates="organization")
    jobs = relationship("Job",back_populates="organization")
    technicans=relationship("Technician",back_populates="organization")
    technician_profile=relationship("TechnicianProfile",back_populates="organization")
    customer_profiles_extended=relationship("CustomerProfileModel",back_populates="organization")
    InApp_Notification=relationship("InAppNotification",back_populates="organization")

    # Suspension tracking
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_by = Column(String(36), nullable=True)
    suspension_reason = Column(String(500), nullable=True)
    
    dispatcher_notifications = relationship("DispatcherNotification", back_populates="organization")
    job_assignments = relationship("JobAssignment", back_populates="organization")
    dispatcher_alerts = relationship("DispatcherAlert", back_populates="organization")
    jobs = relationship("Job", back_populates="organization")
    communication_channel_configurations = relationship("CommunicationChannelConfiguration", back_populates="organization")
    communication_configuration_audits = relationship("CommunicationConfigurationAudit", back_populates="organization")
    tenant_gps_configurations = relationship("TenantGPSConfiguration", back_populates="organization")
    scoring_configurations = relationship("ScoringConfiguration", back_populates="organization")
    assignment_overrides = relationship("AssignmentOverride", back_populates="organization")
    override_audit_events = relationship("OverrideAuditEvent", back_populates="organization")
    customer_preference_audits = relationship("CustomerPreferenceAudit", back_populates="organization")
    preference_audit_logs = relationship("PreferenceAuditLog", back_populates="organization")
    security_audit_logs = relationship("SecurityAuditLog", back_populates="organization")
    enterprise_audit_logs = relationship("EnterpriseAuditLog", back_populates="organization")
    audit_events = relationship("AuditEvent", back_populates="organization")
    ai_guardrail_violations = relationship("AIGuardrailViolation", back_populates="organization")
    ai_brand_safety_rules = relationship("AIBrandSafetyRule", back_populates="organization")
    agent_state_records = relationship("AgentStateRecord", back_populates="organization")
    gps_purge_audit_logs = relationship("GPSPurgeAuditLog", back_populates="organization")
    gps_rejected_ping_logs = relationship("GPSRejectedPingLog", back_populates="organization")
    sla_escalations = relationship("SLAEscalation", back_populates="organization")
    job_closures = relationship("JobClosure", back_populates="organization")
    eta_history = relationship("ETAHistory", back_populates="organization")
    gps_pings = relationship("GPSPing", back_populates="organization")
    service_requests = relationship("ServiceRequest", back_populates="organization")
    notification_templates = relationship("NotificationTemplate",back_populates="organization")
    notification_deliveries = relationship("NotificationDelivery",back_populates="organization")

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DELETED')",
            name="ck_organizations_status",
        ),
        CheckConstraint(
            "subscription_plan IN ('FREE', 'STARTER', 'PROFESSIONAL', 'ENTERPRISE')",
            name="ck_organizations_plan",
        ),
        Index("idx_organizations_status", "status"),
        Index("idx_organizations_active", "status", "deleted_at"),
    )

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE" and self.deleted_at is None

    @property
    def is_suspended(self) -> bool:
        return self.status == "SUSPENDED"
