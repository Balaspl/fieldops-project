import json
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from ..models import Technician, PreferenceAuditLog
from ..logger import logger
from ..redis_client import get_redis_client

DEFAULT_PREFS = {
    "sms_enabled": True,
    "push_enabled": True,
    "inapp_enabled": True,
    "email_enabled": False
}

def get_technician_preferences(db: Session, tech_id: str) -> dict:
    redis_client = get_redis_client()
    cache_key = f"tech:prefs:{tech_id}"
    
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.error(f"Redis get error for {cache_key}: {e}")

    tech = db.query(Technician).filter(Technician.tech_id == tech_id).first()
    prefs = DEFAULT_PREFS
    if tech and tech.notification_preferences:
        prefs = tech.notification_preferences

    if redis_client:
        try:
            redis_client.setex(cache_key, 60, json.dumps(prefs))
        except Exception as e:
            logger.error(f"Redis set error for {cache_key}: {e}")
            
    return prefs

def update_technician_preferences(db: Session, tech_id: str, new_prefs: dict, updated_by: str) -> dict:
    tech = db.query(Technician).filter(Technician.tech_id == tech_id).first()
    if not tech:
        return None

    old_prefs = tech.notification_preferences or DEFAULT_PREFS
    
    # Audit log
    audit = PreferenceAuditLog(
        tenant_id=tech.tenant_id or "tenant-1",
        tech_id=tech_id,
        updated_by=updated_by,
        old_preferences=old_prefs,
        new_preferences=new_prefs
    )
    db.add(audit)
    
    tech.notification_preferences = new_prefs
    tech.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Invalidate cache
    redis_client = get_redis_client()
    cache_key = f"tech:prefs:{tech_id}"
    if redis_client:
        try:
            redis_client.delete(cache_key)
            # Re-cache immediately
            redis_client.setex(cache_key, 60, json.dumps(new_prefs))
        except Exception as e:
            logger.error(f"Redis delete/set error for {cache_key}: {e}")
            
    return new_prefs
