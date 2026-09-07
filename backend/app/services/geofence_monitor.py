import logging
import math
import json
from sqlalchemy.orm import Session
from ..redis_client import get_redis_client
from ..models import GPSPing, Job
from ..database import SessionLocal

logger = logging.getLogger(__name__)

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Radius of the Earth in meters
    R = 6371000.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    return R * c


class GeofenceMonitor:
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()

    def process_ping(self, db: Session, ping: GPSPing) -> None:
        if not self.redis:
            return
            
        # Resolve tech UUID to integer ID
        tech_id = getattr(ping, "technician_id", None) or getattr(ping, "tech_id", None)
        if not tech_id:
            return

        from ..models import Technician
        tech = db.query(Technician).filter(Technician.tech_id == str(tech_id)).first()
        if tech:
            tech_int_id = tech.technician_id
        elif str(tech_id).isdigit():
            tech_int_id = int(tech_id)
        else:
            return

        # Find active EN_ROUTE jobs assigned to this technician
        jobs = db.query(Job).filter(
            Job.assigned_technician_id == tech_int_id,
            Job.status == "EN_ROUTE"
        ).all()
        
        for job in jobs:
            job_id = str(job.id)
            
            # Check Cooldown (5 minutes)
            cooldown_key = f"geofence:cooldown:{job_id}"
            if self.redis.exists(cooldown_key):
                logger.info(f"Geofence skip: Cooldown active for job {job_id}")
                continue
                
            # Verify coordinates exist
            if job.site_latitude is None or job.site_longitude is None:
                continue
                
            distance = calculate_haversine_distance(
                ping.latitude, ping.longitude,
                job.site_latitude, job.site_longitude
            )
            
            radius = getattr(job, "geofence_radius", 100.0) or 100.0
            
            counter_key = f"geofence:entry:{job_id}"
            
            if distance <= radius:
                # Increment counter
                try:
                    count = self.redis.incr(counter_key)
                    if count == 1:
                        # Set 60s TTL on first ping inside
                        self.redis.expire(counter_key, 60)
                        
                    logger.info(f"Technician {tech_id} inside geofence for job {job_id}. Distance: {distance:.2f}m. Count: {count}/3")
                    
                    if count >= 3:
                        # Set Cooldown
                        self.redis.setex(cooldown_key, 300, "active")
                        # Delete counter
                        self.redis.delete(counter_key)
                        
                        logger.info(f"Triggering auto-transition EN_ROUTE -> ON_SITE for job {job_id} on geofence entry (Distance: {distance:.2f}m)")
                        
                        # Trigger Celery Task
                        from ..tasks import auto_transition_on_geofence
                        auto_transition_on_geofence.delay(job_id, ping.id, distance)
                except Exception as e:
                    logger.error(f"Error in geofence processing: {e}")
            else:
                # Reset counter if ping falls outside
                try:
                    if self.redis.exists(counter_key):
                        self.redis.delete(counter_key)
                        logger.info(f"Technician {tech_id} moved outside geofence for job {job_id}. Distance: {distance:.2f}m. Counter reset.")
                except Exception as e:
                    logger.error(f"Error resetting geofence counter: {e}")
