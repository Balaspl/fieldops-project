import re
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import CustomerProfile, CustomerPreferenceAudit

from app.services.ai.FieldOpsAI.repositories.customer_profile_repository import CustomerProfileRepository
from app.services.ai.FieldOpsAI.schemas.customer_profile import (
    CustomerPreferenceUpdate, 
    CustomerPreferenceResponse, 
    CustomerPreferenceDecision,
    CustomerPreferenceChannel
)
from app.services.ai.FieldOpsAI.services.prompt_locale_service import normalize_locale, InvalidLocaleError

class CustomerPreferenceError(Exception): pass
class InvalidCustomerIdentifierError(CustomerPreferenceError): pass
class CustomerPreferenceConflictError(CustomerPreferenceError): pass
class CustomerPreferencePersistenceError(CustomerPreferenceError): pass
class CustomerPreferenceValidationError(CustomerPreferenceError): pass

class CustomerPreferenceService:
    def __init__(self, repository: CustomerProfileRepository):
        self.repository = repository

    def _validate_identifier(self, identifier: str, field_name: str, max_length: int) -> str:
        if not isinstance(identifier, str):
            raise InvalidCustomerIdentifierError(f"{field_name} must be a string")
        if any(c in identifier for c in ('\x00', '\n', '\r', '..', '/', '\\')):
            raise InvalidCustomerIdentifierError(f"Invalid characters in {field_name}")
        stripped = identifier.strip()
        if not stripped:
            raise InvalidCustomerIdentifierError(f"{field_name} cannot be blank")
        if len(stripped) > max_length:
            raise InvalidCustomerIdentifierError(f"{field_name} cannot exceed {max_length} characters")
        return stripped

    def _response_from_profile(self, profile: CustomerProfile) -> CustomerPreferenceResponse:
        return CustomerPreferenceResponse(
            profile_id=profile.id,
            tenant_id=profile.tenant_id,
            customer_id=profile.customer_id,
            sms_enabled=profile.sms_enabled,
            email_enabled=profile.email_enabled,
            push_enabled=profile.push_enabled,
            portal_enabled=profile.portal_enabled,
            preferred_locale=profile.preferred_locale,
            daily_engagement_enabled=profile.daily_engagement_enabled,
            timezone=profile.timezone,
            quiet_hours_start=profile.quiet_hours_start,
            quiet_hours_end=profile.quiet_hours_end,
            revision=profile.revision,
            source="PROFILE",
            updated_at=profile.updated_at,
            updated_by=profile.updated_by
        )

    def get_preferences(
        self,
        tenant_id: str,
        customer_id: str
    ) -> CustomerPreferenceResponse:
        t_id = self._validate_identifier(tenant_id, "tenant_id", 50)
        c_id = self._validate_identifier(customer_id, "customer_id", 50)
        
        profile = self.repository.get_by_customer(t_id, c_id)
        
        if not profile:
            return CustomerPreferenceResponse(
                profile_id=None,
                tenant_id=t_id,
                customer_id=c_id,
                sms_enabled=True,
                email_enabled=True,
                push_enabled=False,
                portal_enabled=True,
                preferred_locale="en",
                daily_engagement_enabled=False,
                timezone="UTC",
                quiet_hours_start="21:00",
                quiet_hours_end="08:00",
                revision=0,
                source="COMPATIBILITY_DEFAULT",
                updated_at=None,
                updated_by=None
            )
            
        return self._response_from_profile(profile)

    def update_preferences(
        self,
        tenant_id: str,
        customer_id: str,
        payload: CustomerPreferenceUpdate,
        actor_id: str,
        actor_source: str,
        correlation_id: Optional[str] = None
    ) -> CustomerPreferenceResponse:
        t_id = self._validate_identifier(tenant_id, "tenant_id", 50)
        c_id = self._validate_identifier(customer_id, "customer_id", 50)
        a_id = self._validate_identifier(actor_id, "actor_id", 100)
        c_corr_id = None
        if correlation_id is not None:
            c_corr_id = self._validate_identifier(correlation_id, "correlation_id", 100)
        
        if actor_source not in ("CUSTOMER", "ADMIN", "SYSTEM"):
            raise CustomerPreferenceValidationError("Invalid actor source")

        try:
            profile = self.repository.get_by_customer(t_id, c_id, for_update=True)
            
            is_new = False
            previous_revision = 0
            
            if not profile:
                is_new = True
                profile = CustomerProfile(
                    tenant_id=t_id,
                    customer_id=c_id,
                    sms_enabled=True,
                    email_enabled=True,
                    push_enabled=False,
                    portal_enabled=True,
                    preferred_locale="en",
                    daily_engagement_enabled=False,
                    timezone="UTC",
                    quiet_hours_start="21:00",
                    quiet_hours_end="08:00",
                    revision=1,
                    updated_by=a_id
                )
                self.repository.add_profile(profile)
            else:
                previous_revision = profile.revision
            
            changed_fields = {}
            updates = payload.model_dump(exclude_unset=True)
            
            for field, value in updates.items():
                if field == "preferred_locale":
                    try:
                        value = normalize_locale(value)
                    except InvalidLocaleError as e:
                        raise CustomerPreferenceValidationError(str(e))
                
                old_val = getattr(profile, field)
                if old_val != value or is_new:
                    # For a new profile, we record all explicitly supplied fields
                    changed_fields[field] = {"old": old_val, "new": value}
                    setattr(profile, field, value)
            
            if not changed_fields and not is_new:
                # No-op
                response = self._response_from_profile(profile)
                self.repository.db.commit()
                return response
            
            if not is_new:
                profile.revision += 1
                profile.updated_by = a_id
                
            audit = CustomerPreferenceAudit(
                customer_profile_id=profile.id,
                tenant_id=t_id,
                previous_revision=previous_revision,
                new_revision=profile.revision,
                changed_fields=changed_fields,
                actor_id=a_id,
                actor_source=actor_source,
                correlation_id=c_corr_id
            )
            self.repository.add_audit(audit)
            
            self.repository.db.flush()
            self.repository.db.refresh(profile)
            
            response = self._response_from_profile(profile)
            self.repository.db.commit()
            return response
            
        except IntegrityError:
            self.repository.db.rollback()
            raise CustomerPreferenceConflictError("Duplicate profile creation or constraint violation")
        except CustomerPreferenceError:
            self.repository.db.rollback()
            raise
        except Exception as e:
            self.repository.db.rollback()
            raise CustomerPreferencePersistenceError("Failed to persist customer preferences") from e

    def evaluate_channel(
        self,
        tenant_id: str,
        customer_id: str,
        channel: str
    ) -> CustomerPreferenceDecision:
        t_id = self._validate_identifier(tenant_id, "tenant_id", 50)
        c_id = self._validate_identifier(customer_id, "customer_id", 50)
        
        if channel == "IN_APP":
            channel = "PORTAL"
            
        if channel not in ("SMS", "EMAIL", "PUSH", "PORTAL"):
            raise CustomerPreferenceValidationError(f"Invalid channel: {channel}")
            
        channel_attr = f"{channel.lower()}_enabled"
        
        profile = self.repository.get_by_customer(t_id, c_id)
        
        if not profile:
            allowed = True
            if channel == "PUSH":
                allowed = False
                
            return CustomerPreferenceDecision(
                allowed=allowed,
                channel=channel, # type: ignore
                reason_code="CUSTOMER_COMPATIBILITY_DEFAULT_ALLOWED" if allowed else "CUSTOMER_COMPATIBILITY_DEFAULT_BLOCKED",
                source="COMPATIBILITY_DEFAULT",
                revision=0
            )
            
        allowed = getattr(profile, channel_attr)
        
        return CustomerPreferenceDecision(
            allowed=allowed,
            channel=channel, # type: ignore
            reason_code="CUSTOMER_PREFERENCE_ENABLED" if allowed else "CUSTOMER_PREFERENCE_DISABLED",
            source="PROFILE",
            revision=profile.revision
        )
