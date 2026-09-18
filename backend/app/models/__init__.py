"""
Models package.

Re-exports all models from the original models_legacy.py
(renamed from models.py) plus the new multi-tenant models.

All existing `from app.models import X` imports continue to work.
"""

# Original models — backward compatible re-export
# This imports everything from the renamed models_legacy.py
from ..models_legacy import (  # noqa: F401
    Base,
    Tenant,
    Technician,
    Job,
    AuditEvent,
    DispatcherNotification,
    NotificationDelivery,
    SMSDelivery,
    InAppNotification,
    NotificationTemplate,
    TemplateVersion,
    PreferenceAuditLog,
    SkillTaxonomy,
    ScoringConfiguration,
    AIBrandSafetyRule,
    SLAEscalation,
    DispatcherAlert,
    OverrideAuditEvent,
    AIGuardrailViolation,
    AssignmentOverride,
    GPSPing,
    TenantGPSConfiguration,
    GPSPurgeAuditLog,
    GPSRejectedPingLog,
    CommunicationChannelConfiguration,
    CommunicationConfigurationAudit,
    ETAHistory,
    SecurityAuditLog,
    JobAssignment,
    AgentStateRecord,
    CustomerProfile,
    CustomerPreferenceAudit,
)

from ..prompts.analytics_models import PromptAnalyticsAggregate, PromptUsageEvent  # noqa: F401

# New multi-tenant & job closure models
from .user import User, RefreshToken  # noqa: F401
from .organization import Organization  # noqa: F401
from .enterprise_audit import EnterpriseAuditLog  # noqa: F401
from .job_closure import JobClosure  # noqa: F401

# Portal models
from .technician_profile import TechnicianProfile  # noqa: F401
from .customer_profile import CustomerProfileModel  # noqa: F401
from .service_request import ServiceRequest  # noqa: F401
from .organization_onboarding import OrganizationOnboarding  # noqa: F401
from .dead_letter_task import DeadLetterTask  # noqa: F401
from .sentiment import SentimentThreadMessage  # noqa: F401
from .retention import (
    RetentionWorkflow,
    RetentionDiscountCode,
    RetentionCRMTask,
    RetentionServiceCredit,

)

from .sentiment_audit import SentimentAuditRecord
from .sentiment_escalation import SentimentEscalation
from .runtime_metrics import RuntimeMetricRollup  # noqa: F401
from .oidc_identity import OIDCIdentity
from .mfa import MFA  # noqa: F401
from .mfa_recovery_code import MFARecoveryCode  # noqa: F401
from .password_reset_token import PasswordResetToken
from .trust_device import TrustedDevice