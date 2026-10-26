from sqlalchemy.orm import Session
from . import models

def sync_technician_status(technician: models.Technician):
    """
    Retained for compatibility. Workload changes do not control availability.
    """
    return technician

def update_workload_count(db: Session, technician_id: int, delta: int):
    """
    Update workload count and sync status.
    delta can be positive or negative.
    """
    tech = db.query(models.Technician).filter(models.Technician.technician_id == technician_id).first()
    if tech:
        tech.current_jobs = max(0, tech.current_jobs + delta)
        db.add(tech)
        return tech
    return None
