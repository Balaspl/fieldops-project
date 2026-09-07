import os
import re
import asyncio
import uuid
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from sqlalchemy.orm import Session
from ..logger import logger
from ..models import Technician, SMSDelivery
from ..redis_client import get_redis_client
from .preferences import get_technician_preferences

# Environment variables
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', 'AC_dummy_account_sid')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', 'dummy_auth_token')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', '+1234567890')

# Initialize Twilio Client
# Uses dummy values if env vars are missing for local dev to not crash on startup
twilio_client = None
if 'AC' in TWILIO_ACCOUNT_SID:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("Twilio client initialized.")
    except Exception as e:
        logger.error("Failed to initialize Twilio client.")

def validate_phone_number(phone_number: str) -> bool:
    """Validate E.164 phone number format (e.g., +919876543210)"""
    if not phone_number:
        return False
    # Regex: '+' followed by 7 to 15 digits (min 7 digits to avoid too short formats like +123)
    pattern = r"^\+[1-9]\d{6,14}$"
    return bool(re.match(pattern, phone_number))

def generate_sms_template(job_title: str, address: str, priority: str, job_id: str) -> str:
    """
    Generate SMS text strictly under 160 chars.
    Template:
    FieldOps: New job '{title}' at {address}.
    Priority: {priority}.
    Accept: {short_url}
    Expires in 10 min.
    Reply STOP to opt out.
    """
    # Max length budget: 
    # Base text is ~80 chars. We need to truncate title and address if they are too long.
    short_url = f"api.fieldops.io/j/{str(job_id)[:8]}" # using short url mock
    
    # Trim title to 15 chars, address to 20 chars max to be safe.
    t_title = (job_title[:12] + '...') if len(job_title) > 15 else job_title
    t_address = (address[:17] + '...') if len(address) > 20 else address
    
    message = (
        f"FieldOps: New job '{t_title}' at {t_address}. "
        f"Priority: {priority}. "
        f"Accept: {short_url} "
        f"Expires in 10 min. "
        f"Reply STOP to opt out."
    )
    return message

from .ai.FieldOpsAI.schemas.communication_configuration import CommunicationMessageCategory, CommunicationChannelDisabledError
from .ai.FieldOpsAI.services.communication_configuration_service import CommunicationConfigurationService
from .ai.FieldOpsAI.repositories.communication_configuration_repository import CommunicationConfigurationRepository
from .ai.FieldOpsAI.services.customer_preference_service import CustomerPreferenceService
from .ai.FieldOpsAI.repositories.customer_profile_repository import CustomerProfileRepository
from .ai.FieldOpsAI.services.communication_delivery_policy_service import CommunicationDeliveryPolicyService

def dispatch_twilio_message(to_phone: str, body: str) -> str:
    """
    The single authoritative Twilio transport boundary for both technicians and customers.
    """
    if not twilio_client:
        return f"SMmock_{uuid.uuid4().hex[:12]}"
        
    response = twilio_client.messages.create(
        body=body,
        from_=TWILIO_PHONE_NUMBER,
        to=to_phone,
        status_callback="https://api.fieldops.io/v1/webhooks/twilio-status"
    )
    return response.sid

def check_rate_limit(redis_client, tech_id: str) -> bool:
    """Check if the technician has exceeded 10 SMS per minute."""
    if not redis_client:
        return True # pass if no redis
    
    key = f"rate_limit:sms:{tech_id}"
    try:
        count = redis_client.get(key)
        if count and int(count) >= 10:
            return False
            
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60) # 60 seconds
        pipe.execute()
        return True
    except Exception as e:
        logger.error("Redis rate limiting error occurred.")
        return True # fail open

async def send_job_assignment_sms(
    db: Session,
    job_id: str,
    job_title: str,
    location: str,
    priority: str,
    tech_ids: list[str],
    correlation_id: str = None,
    max_retries: int = 3,
    effective_message: str | None = None,
    category: CommunicationMessageCategory = CommunicationMessageCategory.STANDARD,
) -> dict:
    correlation_id = correlation_id or str(uuid.uuid4())
    log_extra = {"correlation_id": correlation_id, "job_id": job_id}
    
    techs = db.query(Technician).filter(Technician.tech_id.in_(tech_ids)).all()
    
    redis_client = get_redis_client()
    
    sent_count = 0
    failed_count = 0
    delivery_ids = []
    blocked_count = 0
    blocked_reasons: dict[str, int] = {}
    
    if effective_message is None:
        effective_message = generate_sms_template(
            job_title,
            location,
            priority,
            job_id,
        )

    else:
        if not isinstance(
            effective_message,
            str,
        ):
            raise TypeError(
                "effective_message must be text."
            )

        effective_message = (
            effective_message.strip()
        )

    if not effective_message:
        raise ValueError(
            "SMS message must not be empty."
        )

    # Final transport-level validation after real placeholder
    # values have been restored.
    if len(effective_message) > 160:
        raise ValueError(
            "SMS message exceeds 160 characters."
        )
    
    # Enforce delivery policy before iterating over technicians
    repo = CommunicationConfigurationRepository(db)
    config_service = CommunicationConfigurationService(repo, db, redis_client=redis_client)
    pref_repo = CustomerProfileRepository(db)
    pref_service = CustomerPreferenceService(pref_repo)
    policy_service = CommunicationDeliveryPolicyService(config_service, pref_service)

    for tech in techs:
        # Check Opt-out
        if tech.sms_opt_out:
            logger.info(f"Skipping tech {tech.tech_id} (opted out of SMS)", extra=log_extra)
            failed_count += 1
            continue
            
        # Check explicit preference
        prefs = get_technician_preferences(db, tech.tech_id)
        if not prefs.get("sms_enabled", True):
            logger.info(f"Skipping tech {tech.tech_id} (SMS notifications disabled via preferences)", extra=log_extra)
            failed_count += 1
            continue
            
        # Check Valid Phone Number
        if not validate_phone_number(tech.phone_number):
            logger.warning(
                    "Technician SMS skipped because the phone "
                    "number is invalid or missing.",
                    extra=log_extra,
                )
            failed_count += 1
            continue
            
        # Check Rate Limit
        if not check_rate_limit(redis_client, tech.tech_id):
            logger.warning("Rate limit exceeded. Skipping SMS.", extra=log_extra)
            failed_count += 1
            continue
            
        # Ready to send
        delivery = SMSDelivery(
            tenant_id=tech.tenant_id or "tenant-1",
            tech_id=tech.tech_id,
            job_id=str(job_id),
            status="queued"
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        
        # We process sends individually per tech to respect rate limits and individual tracking
        success = False
        
        for attempt in range(max_retries):
            # Enforce delivery policy before every attempt
            decision = policy_service.evaluate(
                channel="SMS", 
                category=category, 
                recipient_type="TECHNICIAN",
            )
            if not decision.allowed:
                delivery.error_message = (
                    decision.final_reason_code
                )

                blocked_count += 1

                blocked_reasons[
                    decision.final_reason_code
                ] = (
                    blocked_reasons.get(
                        decision.final_reason_code,
                        0,
                    )
                    + 1
                )

                break
                
            try:
                sms_sid = dispatch_twilio_message(to_phone=tech.phone_number, body=effective_message)
                
                if sms_sid.startswith("SMmock_"):
                    logger.info(
                            "Technician SMS delivery simulated.",
                            extra={**log_extra, "delivery_id": delivery.id, "attempt": attempt, "operation": "simulate_sms"}
                        )
                else:
                    logger.info("Sent SMS successfully", extra={**log_extra, "delivery_id": delivery.id, "attempt": attempt, "operation": "send_sms"})

                delivery.status = "sent"
                delivery.sms_sid = sms_sid
                success = True
                break
                
            except TwilioRestException as e:
                logger.error("Twilio API Error", extra={**log_extra, "delivery_id": delivery.id, "attempt": attempt, "operation": "send_sms", "status": e.status})
                # If it's a 4xx error (like invalid number), don't retry
                if e.status and 400 <= e.status < 500:
                    delivery.error_message = f"Provider error: HTTP {e.status}"
                    break
                # Otherwise backoff and retry
                await asyncio.sleep(2 ** attempt)
            except Exception:
                logger.error("Unexpected error sending SMS", extra={**log_extra, "delivery_id": delivery.id, "attempt": attempt, "operation": "send_sms"})
                await asyncio.sleep(2 ** attempt)

        if success:
            sent_count += 1
        else:
            failed_count += 1
            delivery.status = "failed"
            if not delivery.error_message:
                delivery.error_message = "Max retries exceeded or unexpected error."

        db.commit()
        delivery_ids.append(delivery.id)
        
    return {
        "sent": sent_count,
        "failed": failed_count,
        "blocked": blocked_count,
        "blocked_reasons": blocked_reasons,
        "delivery_ids": delivery_ids,
}
