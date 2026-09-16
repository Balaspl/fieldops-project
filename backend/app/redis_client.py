import redis
from redis.exceptions import ConnectionError, TimeoutError
import os
import time
from typing import Optional

class RedisCacheManager:
    def __init__(self):
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        
        self.pool = redis.ConnectionPool(
            host=redis_host, 
            port=redis_port, 
            decode_responses=True,
            socket_timeout=0.3,
            socket_connect_timeout=0.3
        )
        self.client = redis.Redis(connection_pool=self.pool)
        self._was_connected = True

    def _execute_with_retry(self, operation, *args, **kwargs):
        retries = 1
        for i in range(retries):
            try:
                result = operation(*args, **kwargs)
                if not self._was_connected:
                    print("Redis connection restored.")
                    self._was_connected = True
                return result
            except (ConnectionError, TimeoutError) as e:
                if i == retries - 1:
                    if self._was_connected:
                        print(f"Redis connection failed: {e} (subsequent connection warnings will be suppressed)")
                        self._was_connected = False
                    return None
                time.sleep(0.1)
        return None

    def get(self, key: str) -> Optional[str]:
        return self._execute_with_retry(self.client.get, key)

    def setex(self, key: str, time_seconds: int, value: str) -> bool:
        result = self._execute_with_retry(self.client.setex, key, time_seconds, value)
        return result is not None

    def delete(self, key: str) -> bool:
        result = self._execute_with_retry(self.client.delete, key)
        return result is not None
    def get_and_delete(self, key: str) -> Optional[str]:
        """
        Atomically get and delete a Redis key.

        Used for one-time MFA challenges to prevent replay attacks.
        """
        script = """
        local value = redis.call('GET', KEYS[1])
        if value then
            redis.call('DEL', KEYS[1])
        end
        return value
        """

        return self._execute_with_retry(
            self.client.eval,
            script,
            1,
            key,
        )

    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        return self._execute_with_retry(self.client.incrby, key, amount)

    def expire(self, key: str, time_seconds: int) -> bool:
        result = self._execute_with_retry(self.client.expire, key, time_seconds)
        return result is not None

    def __getattr__(self, name):
        if name == "client":
            raise AttributeError("client attribute not initialized")
        attr = getattr(self.client, name)
        if callable(attr):
            def wrapper(*args, **kwargs):
                return self._execute_with_retry(attr, *args, **kwargs)
            return wrapper
        return attr

redis_manager = None

def get_redis_client():
    global redis_manager
    if redis_manager is None:
        redis_manager = RedisCacheManager()
    return redis_manager
