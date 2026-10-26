import pytest
from unittest.mock import patch, MagicMock, ANY
from fastapi import HTTPException
import time

from app.services.distributed_lock_service import with_job_lock

def test_lock_acquires_successfully():
    with patch("app.services.distributed_lock_service.dlm", None):
        with patch("app.services.distributed_lock_service.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.client.set.return_value = True
            mock_redis.return_value = mock_client
            
            with with_job_lock("test-job-1") as lock:
                assert lock is not None

def test_409_returned_on_lock_conflict():
    with patch("app.services.distributed_lock_service.dlm", None):
        with patch("app.services.distributed_lock_service.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.client.set.return_value = False
            mock_redis.return_value = mock_client
            
            with pytest.raises(HTTPException) as excinfo:
                with with_job_lock("test-job-1"):
                    pass
                    
            assert excinfo.value.status_code == 409
            assert "Concurrent modification" in excinfo.value.detail
            
            mock_client.incr.assert_called_with("metrics:lock_contention")

def test_lock_released_on_exception():
    with patch("app.services.distributed_lock_service.dlm", None):
        with patch("app.services.distributed_lock_service.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.client.set.return_value = True
            mock_redis.return_value = mock_client
            
            try:
                with with_job_lock("test-job-2"):
                    raise ValueError("Some internal error")
            except ValueError:
                pass
                
            mock_client.client.eval.assert_called_once()
            set_call = mock_client.client.set.call_args
            eval_call = mock_client.client.eval.call_args
            assert eval_call.args[2] == "job:lock:test-job-2"
            assert eval_call.args[3] == set_call.args[1]
            assert "if redis.call('get', KEYS[1]) == ARGV[1] then" in eval_call.args[0]

def test_metrics_recorded():
    with patch("app.services.distributed_lock_service.dlm", None):
        with patch("app.services.distributed_lock_service.get_redis_client") as mock_redis:
            mock_client = MagicMock()
            mock_client.client.set.return_value = True
            mock_redis.return_value = mock_client
            
            with with_job_lock("test-job-3"):
                time.sleep(0.01)
                
            mock_client.client.lpush.assert_called_with("metrics:lock_acquire_time_ms", ANY)

