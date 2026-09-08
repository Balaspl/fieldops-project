from datetime import date, datetime
from typing import Literal, Optional, Union
from pydantic import BaseModel, field_validator, ConfigDict, Field
from .services.ai.FieldOpsAI.schemas.prompt_variable import PromptVariableDeclaration


class JobCreate(BaseModel):
    customer_name: str
    location: str
    issue_description: str
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "P1", "P2", "P3", "P4", "P5"] # Merged priorities
    service_type: str
    contact_number: str
    preferred_service_date: date
    required_skill: Optional[str] = None # Made optional to match frontend
    status: str = "active"
    tenant_id: Optional[str] = None
    sla_deadline: Optional[datetime] = None
    attempt_count: Optional[int] = 0

    @field_validator(
        "customer_name",
        "location",
        "issue_description",
        "service_type",
        "contact_number"
    )
    @classmethod
    def not_empty(cls, value, info):
        if info.field_name == "required_skill" and value is None:
            return value
        if not value or not value.strip():
            raise ValueError("Field cannot be empty")
        return value

    @field_validator("contact_number")
    @classmethod
    def validate_contact_number(cls, value):
        if not value.isdigit() or len(value) != 10:
            raise ValueError("Contact number must be 10 digits")
        # Relaxed validation or check if it matches original
        return value


class JobResponse(BaseModel):
    id: int
    customer_name: Optional[str] = None
    location: Optional[str] = None
    issue_description: Optional[str] = None
    priority: Optional[str] = None
    service_type: Optional[str] = None
    contact_number: Optional[str] = None
    preferred_service_date: Optional[date] = None
    status: Optional[str] = None
    required_skill: Optional[str] = None
    assigned_technician_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tenant_id: Optional[str] = None
    sla_deadline: Optional[datetime] = None
    attempt_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class TechnicianCreate(BaseModel):
    tech_id: Optional[str] = None
    technician_name: str
    technician_skill: str
    technician_location: str
    technician_status: str

    @field_validator("technician_name", "technician_skill", "technician_location", "technician_status")
    @classmethod
    def field_must_not_be_empty(cls, value):
        if not value or not value.strip():
            raise ValueError("Field cannot be empty")
        return value.strip()


class TechnicianAvailabilityUpdate(BaseModel):
    technician_status: Literal["Available", "Busy", "Assigned", "Offline", "En Route", "On Site", "On Break", "Suspended", "AVAILABLE", "BUSY", "ASSIGNED", "OFFLINE", "EN_ROUTE", "ON_SITE", "ON_BREAK", "SUSPENDED"]

class TechnicianStatusUpdate(BaseModel):
    technician_id: int
    status: Literal["Available", "Busy", "Assigned", "Offline", "En Route", "On Site", "On Break", "Suspended", "AVAILABLE", "BUSY", "ASSIGNED", "OFFLINE", "EN_ROUTE", "ON_SITE", "ON_BREAK", "SUSPENDED"]

class TechnicianResponse(BaseModel):
    technician_id: int
    tech_id: Optional[str] = None
    technician_name: str
    technician_skill: str
    technician_location: str
    technician_status: str
    current_jobs: int
    max_jobs: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkloadResponse(BaseModel):
    technician: str
    current_jobs: int
    status: str


class WorkloadUpdate(BaseModel):
    technician_id: int
    current_jobs: int


class WorkloadValidationResponse(BaseModel):
    technician: str
    current_jobs: int
    max_jobs: int
    can_assign: bool
    message: str


class AvailableTechnicianResponse(BaseModel):
    technician_id: int
    technician: str
    skill: str
    location: str
    status: str
    current_jobs: int
    max_jobs: int
    eligible_for_assignment: bool

    model_config = ConfigDict(from_attributes=True)


class TechnicianAssignment(BaseModel):
    job_id: Union[int, str]
    technician_id: Optional[Union[int, str]] = None
    job_type: Optional[str] = None



class NearestTechnicianResponse(BaseModel):
    technician: TechnicianResponse
    distance: float

class PlannedAssignmentResponse(BaseModel):
    job_id: int
    technician: str
    skill: str
    customer: str
    location: str
    priority: str
    status: str
    current_jobs: int
    max_jobs: int

    model_config = ConfigDict(from_attributes=True)


class HeartbeatPayload(BaseModel):
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None


class AvailabilityResponse(BaseModel):
    tech_id: str
    status: str
    last_ping: datetime
    active_jobs: int
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None

class DisqualifiedTechnician(BaseModel):
    tech_id: str
    name: str
    reason: str
    details: Optional[list[str]] = None
    message: str
    cooldown_expires_at: Optional[str] = None
    remaining_seconds: Optional[int] = None
    rejected_at: Optional[str] = None
    rejection_reason: Optional[str] = None

class RankedTechnician(BaseModel):
    rank: int
    tech_id: str
    name: str
    proximity_score: float
    skill_score: float
    workload_score: float
    composite_score: float
    score_breakdown: Optional[dict] = None
    warnings: Optional[list[str]] = None
    distance_km: Optional[float] = None
    active_jobs: int
    max_capacity: int = 3
    is_top_3: bool = False
    is_recommended: bool = False
    estimated_arrival: Optional[str] = None

class ScoringWeights(BaseModel):
    proximity: float
    skill: float
    workload: float

class PlanResponse(BaseModel):
    job_id: str
    job_title: str
    status: str
    ranked_technicians: list[RankedTechnician]
    disqualified_technicians: list[DisqualifiedTechnician]
    scoring_weights: ScoringWeights
    cache_ttl_seconds: int

class FCMTokenRegistration(BaseModel):
    token: str
    device_type: Literal["android", "ios"]

class NotificationSendRequest(BaseModel):
    job_id: str
    tech_ids: list[str]

class NotificationSendResponse(BaseModel):
    sent: int
    failed: int
    delivery_ids: list[int]

class SMSSendRequest(BaseModel):
    job_id: str
    tech_ids: list[str]

class SMSPreviewRequest(BaseModel):
    # Recipient number and message to validate without sending.
    to_number: str
    body: str


class SMSSendDirectRequest(BaseModel):
    # Single SMS request that will be processed asynchronously.
    to_number: str
    body: str
    from_number: str | None = None


class SMSBulkSendRequest(BaseModel):
    # Bulk SMS request processed by the Celery worker.
    recipients: list[str]
    body: str
    from_number: str | None = None

    
class InAppNotificationResponse(BaseModel):
    id: str
    tech_id: str
    job_id: Optional[str] = None
    type: str
    title: str
    body: Optional[str] = None
    status: str
    action_url: Optional[str] = None
    action_type: Optional[str] = None
    priority: str
    created_at: datetime
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    notification_metadata: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)

class PaginatedNotificationsResponse(BaseModel):
    notifications: list[InAppNotificationResponse]
    unread_count: int
    total: int

class BatchReadRequest(BaseModel):
    notification_ids: list[str]

class TemplateCreate(BaseModel):
    name: str
    type: str
    channel: str
    locale: Optional[str] = "en"
    format: Optional[Literal["text", "html"]] = "text"
    title_template: Optional[str] = None
    body_template: str

    @field_validator(
        "format",
        mode="before",
    )
    @classmethod
    def validate_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return "text"
        if not isinstance(value, str):
            raise ValueError("Format must be 'text' or 'html'.")
        val = value.strip().lower()
        if val not in ("text", "html"):
            raise ValueError("Format must be 'text' or 'html'.")
        return val

class TemplateResponse(TemplateCreate):
    id: int
    version: int
    is_active: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TemplatePreviewRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    title_template: Optional[str] = None
    body_template: str
    mock_context: dict
    variables: Optional[
        list[PromptVariableDeclaration]
    ] = None

    format: Literal["text", "html"] = "text"

    @field_validator(
        "format",
        mode="before",
    )
    @classmethod
    def validate_format(
        cls,
        value,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                "Format must be 'text' or 'html'."
            )

        normalized = value.strip().lower()

        if normalized not in {
            "text",
            "html",
        }:
            raise ValueError(
                "Format must be 'text' or 'html'."
            )

        return normalized
class TemplatePreviewResponse(BaseModel):
    rendered_title: Optional[str] = None
    rendered_body: str

class TemplateVersionResponse(BaseModel):
    id: int
    template_id: int
    version_number: int
    name: Optional[str] = None
    type: Optional[str] = None
    channel: Optional[str] = None
    locale: Optional[str] = None
    format: Optional[str] = None
    agent_type: Optional[str] = None
    variables: Optional[list] = None
    title_template: Optional[str] = None
    body_template: str
    created_by: str
    created_at: datetime
    change_summary: Optional[str] = None
    is_active: bool
    template_is_active: Optional[bool] = None
    restored_from_version: Optional[int] = None
    is_deleted: bool

    model_config = ConfigDict(from_attributes=True)

class TemplateVersionCreate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    channel: Optional[str] = None
    locale: Optional[str] = None
    format: Optional[str] = None
    agent_type: Optional[str] = None
    variables: Optional[list] = None
    title_template: Optional[str] = None
    body_template: str
    change_summary: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class TemplateRollbackRequest(BaseModel):
    change_summary: Optional[str] = Field(None, max_length=500)
    
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class TemplateRestoreRequest(BaseModel):
    version_number: int = Field(..., ge=1)

    model_config = ConfigDict(
        extra="forbid",
    )
class TemplateRestoreResponse(BaseModel):
    template_id: int
    previous_version: int
    restored_version: int
    new_active_version: int
    restored_by: str
    restored_at: datetime

class TemplateVersionHistoryResponse(BaseModel):
    template_id: int
    current_version: int
    versions: list[TemplateVersionResponse] 

class TemplateCompareRequest(BaseModel):
    old_version: int
    new_version: int

class TemplateCompareResponse(BaseModel):
    template_id: int
    old_version: int
    new_version: int
    changes: dict = Field(default_factory=dict)

class NotificationPreferences(BaseModel):
    sms_enabled: bool = True
    push_enabled: bool = True
    inapp_enabled: bool = True
    email_enabled: bool = False

    @field_validator('sms_enabled', 'push_enabled', 'inapp_enabled', 'email_enabled', mode='before')
    @classmethod
    def require_at_least_one(cls, v, info):
        # We will do a model_validator for the whole object instead
        return v

    @classmethod
    def validate_minimum_channels(cls, values):
        if not values.get('sms_enabled') and not values.get('push_enabled') and not values.get('inapp_enabled'):
            raise ValueError("At least one notification channel must be enabled")
        return values

from pydantic import model_validator

class NotificationPreferencesInput(BaseModel):
    sms_enabled: bool
    push_enabled: bool
    inapp_enabled: bool
    email_enabled: Optional[bool] = False

    @model_validator(mode='after')
    def check_at_least_one(self) -> 'NotificationPreferencesInput':
        if not self.sms_enabled and not self.push_enabled and not self.inapp_enabled:
            raise ValueError("At least one notification channel must be enabled")
        return self

class PreferencesUpdateResponse(BaseModel):
    tech_id: str
    preferences: dict
    updated_at: datetime
    updated_by: str


class TechnicianAcceptResponse(BaseModel):
    tech_id: str
    name: str
    status: str

class JobAcceptResponse(BaseModel):
    job_id: str
    status: str
    previous_status: str
    technician: TechnicianAcceptResponse
    accepted_at: datetime
    eta_to_customer: Optional[datetime] = None
    tracking_enabled: bool = True

from pydantic import Field

class JobRejectRequest(BaseModel):
    reason: str = Field(..., min_length=10)

class RejectionDetail(BaseModel):
    reason: str
    rejected_at: datetime
    rejected_by: str

class CooldownDetail(BaseModel):
    tech_id: str
    expires_at: datetime
    duration_seconds: int

class ReDispatchDetail(BaseModel):
    triggered: bool
    priority_bump: bool
    estimated_dispatch_time: Optional[datetime] = None

class JobRejectResponse(BaseModel):
    job_id: str
    status: str
    previous_status: str
    rejection: RejectionDetail
    cooldown: CooldownDetail
    re_dispatch: ReDispatchDetail

class JobReassignRequest(BaseModel):
    new_tech_id: str
    reason: str

class PreviousTechnicianDetail(BaseModel):
    tech_id: str
    name: str

class NewTechnicianDetail(BaseModel):
    tech_id: str
    name: str
    notified_at: datetime

class ReassignmentDetail(BaseModel):
    reason: str
    reassigned_at: datetime

class AcceptanceWindowDetail(BaseModel):
    expires_at: datetime
    duration_minutes: int

class JobReassignResponse(BaseModel):
    job_id: str
    status: str
    previous_technician: PreviousTechnicianDetail
    new_technician: NewTechnicianDetail
    reassignment: ReassignmentDetail
    acceptance_window: AcceptanceWindowDetail

class ExcludedTechDetail(BaseModel):
    name: str
    reason: str

class DispatcherAlertResponse(BaseModel):
    alert_id: str
    type: str
    severity: str
    job_id: str
    job_title: str
    attempt_count: int
    max_attempts: int
    excluded_technicians: list[ExcludedTechDetail]
    recommended_action: str
    created_at: datetime
    acknowledged: bool

class AlertAcknowledgeRequest(BaseModel):
    acknowledged: bool = True

class DirectAssignRequest(BaseModel):
    tech_id: str
    justification: str
    skip_skill_check: bool = False
    skip_workload_check: bool = False

class AssignmentDetail(BaseModel):
    tech_id: str
    name: str
    assigned_at: datetime
    assigned_by: str
    assigned_by_name: str

class OverrideDetail(BaseModel):
    justification: str
    planning_agent_bypassed: bool = True
    cooldown_bypassed: bool = True
    skill_check_enforced: bool
    workload_check_enforced: bool

class NotificationDetail(BaseModel):
    channels: list[str]
    sent_at: datetime

class DirectAssignResponse(BaseModel):
    job_id: str
    status: str
    previous_status: str
    assignment: AssignmentDetail
    override: OverrideDetail
    acceptance_window: AcceptanceWindowDetail
    notification: NotificationDetail

class OverrideAuditResponse(BaseModel):
    id: str
    event_type: str
    actor_id: str
    actor_role: str
    actor_name: Optional[str] = None
    job_id: int
    action: str
    before_state: dict
    after_state: dict
    justification: str
    reason: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    correlation_id: Optional[str] = None
    tenant_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SLADetail(BaseModel):
    deadline: Optional[datetime]
    minutes_remaining: Optional[float]
    risk_level: str

class QueueTechnicianDetail(BaseModel):
    tech_id: str
    name: str
    status: str

class DispatchQueueJob(BaseModel):
    job_id: str
    title: str
    status: str
    priority: str
    customer: str
    location: str
    technician: Optional[QueueTechnicianDetail] = None
    sla: SLADetail
    assigned_at: Optional[datetime] = None
    acceptance_expires_at: Optional[datetime] = None

class DispatchQueuePagination(BaseModel):
    next_cursor: Optional[str]
    has_more: bool

class DispatchQueueResponse(BaseModel):
    data: list[DispatchQueueJob]
    pagination: DispatchQueuePagination

class TodayMetrics(BaseModel):
    jobs_dispatched: int
    avg_acceptance_time_minutes: float
    re_dispatch_rate: float
    sla_compliance_rate: float

class DispatchTrend(BaseModel):
    yesterday: int
    change_pct: Optional[float]

class DispatchTrends(BaseModel):
    dispatched: DispatchTrend
    pending: DispatchTrend
    expired: DispatchTrend
    redispatched: DispatchTrend

class DispatchSparklines(BaseModel):
    dispatched: list[int]
    pending: list[int]
    expired: list[int]
    redispatched: list[int]

class DispatchMetricsResponse(BaseModel):
    jobs_dispatched: int
    jobs_pending: int
    jobs_expired: int
    jobs_redispatched: int
    trends: DispatchTrends
    sparklines: DispatchSparklines
    # Legacy fields for backward compat
    today: Optional[TodayMetrics] = None
    status_breakdown: Optional[dict[str, int]] = None
    priority_breakdown: Optional[dict[str, int]] = None
    technician_utilization: Optional[float] = None


class GPSPingRequest(BaseModel):
    technician_id: str
    job_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    accuracy: Optional[float] = None
    altitude: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def validate_coordinates(cls, data):
        import json
        if not isinstance(data, dict):
            return data
            
        errors = []
        
        # Check latitude presence/null
        lat_missing = "latitude" not in data
        lat_val = data.get("latitude")
        
        if lat_missing or lat_val is None:
            errors.append(("latitude", "Coordinates are required"))
        else:
            # Check type (Pydantic naturally allows bool, lists, dicts; we reject them here)
            if isinstance(lat_val, bool):
                errors.append(("latitude", "Coordinates must be numeric"))
            elif not isinstance(lat_val, (int, float)):
                if isinstance(lat_val, str):
                    try:
                        lat_val = float(lat_val)
                        data["latitude"] = lat_val
                    except ValueError:
                        errors.append(("latitude", "Coordinates must be numeric"))
                else:
                    errors.append(("latitude", "Coordinates must be numeric"))
            else:
                # Range check
                if lat_val < -90.0 or lat_val > 90.0:
                    errors.append(("latitude", "Latitude must be between -90 and 90"))

        # Check longitude presence/null
        lng_missing = "longitude" not in data
        lng_val = data.get("longitude")
        
        if lng_missing or lng_val is None:
            errors.append(("longitude", "Coordinates are required"))
        else:
            # Check type
            if isinstance(lng_val, bool):
                errors.append(("longitude", "Coordinates must be numeric"))
            elif not isinstance(lng_val, (int, float)):
                if isinstance(lng_val, str):
                    try:
                        lng_val = float(lng_val)
                        data["longitude"] = lng_val
                    except ValueError:
                        errors.append(("longitude", "Coordinates must be numeric"))
                else:
                    errors.append(("longitude", "Coordinates must be numeric"))
            else:
                # Range check
                if lng_val < -180.0 or lng_val > 180.0:
                    errors.append(("longitude", "Longitude must be between -180 and 180"))

        if errors:
            raise ValueError(json.dumps(errors))

        return data



class GPSPingResponse(BaseModel):
    status: str
    ping_id: str
    timestamp: datetime
    technician_id: str
    job_id: str

    model_config = ConfigDict(from_attributes=True)


class GPSBatchRequest(BaseModel):
    pings: list[dict]

    @field_validator("pings")
    @classmethod
    def check_pings_limit(cls, v):
        if not v:
            raise ValueError("Pings array cannot be empty")
        if len(v) > 100:
            raise ValueError("Maximum 100 pings per batch")
        return v


class JobClosureCreate(BaseModel):
    work_summary: str
    before_images: Optional[list[str]] = Field(default_factory=list)
    after_images: list[str] = Field(..., min_length=1)
    labour_cost: float = Field(default=0.0, ge=0.0)
    material_cost: float = Field(default=0.0, ge=0.0)

    @field_validator("work_summary")
    @classmethod
    def validate_work_summary(cls, v):
        if not v or not v.strip():
            raise ValueError("Work summary cannot be empty")
        return v.strip()

    @field_validator("after_images")
    @classmethod
    def validate_after_images(cls, v):
        if not v or len(v) < 1:
            raise ValueError("Minimum one after image is required")
        return v


class JobClosureResponse(BaseModel):
    id: int
    job_id: int
    technician_id: str
    work_summary: str
    before_images: list[str] = Field(default_factory=list)
    after_images: list[str] = Field(default_factory=list)
    labour_cost: float
    material_cost: float
    subtotal: float
    completed_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)





