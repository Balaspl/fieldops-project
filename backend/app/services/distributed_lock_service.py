import os
import time
import secrets
import logging
from contextlib import contextmanager
from fastapi import HTTPException
from app.redis_client import get_redis_client

try:
    from redlock import Redlock
except ImportError:
    Redlock = None

logger = logging.getLogger(__name__)

# Initialize redlock instances
def get_redlock_manager():
    if not Redlock:
        logger.warning("Redlock library not found. Falling back to single instance lock.")
        return None
        
    redis_nodes_env = os.getenv("REDIS_NODES", "localhost:6379")
    nodes = []
    for node in redis_nodes_env.split(","):
        parts = node.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 6379
        nodes.append({"host": host, "port": port})
    
    return Redlock(nodes)

dlm = get_redlock_manager()

@contextmanager
def with_job_lock(job_id: str):
    """
    Context manager to acquire a distributed lock for a job.
    Raises HTTPException 409 if lock cannot be acquired.
    """
    lock_key = f"job:lock:{job_id}"
    ttl_ms = 30000 # 30s TTL
    
    start_time = time.time()
    lock = None
    
    try:
        if dlm:
            # Redlock will attempt to acquire lock from majority of nodes
            lock = dlm.lock(lock_key, ttl_ms)
            if not lock:
                redis_client = get_redis_client()
                if redis_client:
                    redis_client.incr("metrics:lock_contention")
                raise HTTPException(status_code=409, detail="Concurrent modification detected")
        else:
            # Give each Redis lock a unique ownership token.
            redis_client = get_redis_client()
            lock_token = secrets.token_urlsafe(32)
            if not redis_client or not redis_client.client.set(lock_key, lock_token, nx=True, px=ttl_ms):
                if redis_client:
                    redis_client.incr("metrics:lock_contention")
                raise HTTPException(status_code=409, detail="Concurrent modification detected")
            lock = lock_token
            
        acquire_time = (time.time() - start_time) * 1000
        logger.debug(f"Lock acquired for job {job_id} in {acquire_time:.2f}ms")
        
        # Log metrics
        rc = get_redis_client()
        if rc:
            try:
                rc.client.lpush("metrics:lock_acquire_time_ms", int(acquire_time))
                rc.client.ltrim("metrics:lock_acquire_time_ms", 0, 999) # keep last 1000
            except Exception as e:
                logger.warning(f"Failed to record lock metrics: {e}")
            
        yield lock
        
    finally:
        if lock:
            if dlm:
                dlm.unlock(lock)
            else:
                redis_client = get_redis_client()
                if redis_client:
                    try:
                        redis_client.client.eval(
                            """
                            if redis.call('get', KEYS[1]) == ARGV[1] then
                                return redis.call('del', KEYS[1])
                            end
                            return 0
                            """,
                            1,
                            lock_key,
                            lock,
                        )
                    except Exception as e:
                        logger.warning("Failed to release lock for job %s: %s", job_id, e)
            logger.debug(f"Lock released for job {job_id}")

