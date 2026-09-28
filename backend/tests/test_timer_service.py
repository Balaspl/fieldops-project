import pytest
from datetime import datetime, timezone, timedelta
import json

from app.services.timer_service import TimerService

class MockRedis:
    def __init__(self):
        self.data = {}
        
    def setex(self, key, time, value):
        self.data[key] = value
        return True
        
    def delete(self, *keys):
        deleted_count = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                deleted_count += 1
        return deleted_count
        
    def exists(self, key):
        return key in self.data
        
    def get(self, key):
        return self.data.get(key)

def test_timer_starts_on_assigned():
    redis_client = MockRedis()
    job_id = "job-123"
    tech_id = "tech-456"
    
    result = TimerService.start_timer(redis_client, job_id, tech_id, duration_seconds=600)
    
    assert result is True
    assert redis_client.exists(f"job:timer:{job_id}")
    assert redis_client.exists(f"job:timer_warning:{job_id}")
    
    timer_data = json.loads(redis_client.get(f"job:timer:{job_id}"))
    assert timer_data["job_id"] == job_id
    assert timer_data["tech_id"] == tech_id
    
    warning_data = json.loads(redis_client.get(f"job:timer_warning:{job_id}"))
    assert warning_data["job_id"] == job_id
    
def test_timer_cancels_on_accept_reject_reassign():
    redis_client = MockRedis()
    job_id = "job-999"
    
    TimerService.start_timer(redis_client, job_id, "tech-1", duration_seconds=600)
    assert redis_client.exists(f"job:timer:{job_id}")
    
    result = TimerService.cancel_timer(redis_client, job_id)
    assert result is True
    assert not redis_client.exists(f"job:timer:{job_id}")
    assert not redis_client.exists(f"job:timer_warning:{job_id}")
    assert not redis_client.exists(f"job:timer_warned:{job_id}")

def test_timer_service_graceful_with_no_redis():
    result = TimerService.start_timer(None, "1", "2")
    assert result is False
    
    result2 = TimerService.cancel_timer(None, "1")
    assert result2 is False
