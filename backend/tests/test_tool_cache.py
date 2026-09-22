from app.tools.cache import ToolResultCache


class FakeRedis:
    def get(self, key):
        return None


def test_cache_miss():
    cache = ToolResultCache(FakeRedis())

    result = cache.get(
        "test_tool",
        {"value": 1},
    )

    assert result is None
    assert cache.get_metrics("test_tool") == {
        "hits": 0,
        "misses": 1,
    }

def test_cache_hit():
    class FakeRedis:
        def __init__(self):
            self.data = {}

        def get(self, key):
            return self.data.get(key)

        def setex(self, key, ttl, value):
            self.data[key] = value

    cache = ToolResultCache(FakeRedis())

    cache.set(
        "test_tool",
        {"value": 1},
        {"result": "cached"},
    )

    result = cache.get(
        "test_tool",
        {"value": 1},
    )

    assert result == {"result": "cached"}
    assert cache.get_metrics("test_tool") == {
        "hits": 1,
        "misses": 0,
    }


def test_cache_ttl():
    class FakeRedis:
        def __init__(self):
            self.ttl_value = None

        def setex(self, key, ttl, value):
            self.ttl_value = ttl

        def get(self, key):
            return None

    redis = FakeRedis()
    cache = ToolResultCache(redis)

    result = cache.set(
        "ttl_tool",
        {"value": 1},
        {"result": "cached"},
        ttl=120,
    )

    assert result is True
    assert redis.ttl_value == 120


def test_cache_rejects_result_over_1mb():
    class FakeRedis:
        def __init__(self):
            self.saved = False

        def setex(self, key, ttl, value):
            self.saved = True

    redis = FakeRedis()
    cache = ToolResultCache(redis)

    large_result = "x" * (1024 * 1024 + 1)

    result = cache.set(
        "large_tool",
        {"value": 1},
        large_result,
    )

    assert result is False
    assert redis.saved is False


def test_non_cacheable_tool_skips_cache():
    class FakeCache:
        def get(self, tool_id, parameters):
            raise AssertionError("Cache get should not be called")

        def set(self, tool_id, parameters, result, ttl=60):
            raise AssertionError("Cache set should not be called")

    class FakeSchema:
        def generate_json_schema(self):
            return {"parameters": {}}

    def fake_handler(**kwargs):
        return {"result": "fresh"}

    class FakeTool:
        cacheable = False
        cache_ttl = 60
        fallback_tool_id = None
        fallback_value = None
        has_fallback_value = False
        schema = FakeSchema()
        handler = staticmethod(fake_handler)

    class FakeRegistry:
        def get_tool(self, tool_id):
            return FakeTool()

    from app.tools.executor import ToolExecutor
    from unittest.mock import patch

    with patch.object(
    ToolExecutor,
    "_run_in_subprocess",
    return_value={
        "success": True,
        "result": {"result": "fresh"},
    },
), patch.object(
    ToolExecutor,
    "_validate_output",
    return_value=(True, None),
):
        executor = ToolExecutor(
        registry=FakeRegistry(),
        cache=FakeCache(),
    )

        result = executor.execute(
        "live_gps",
        {},
        "tenant-1",
    )
        
        assert result.success is True
        assert result.result == {"result": "fresh"}
        assert result.cached is False

def test_cache_metrics():
    class FakeRedis:
        def __init__(self):
            self.data = {}

        def get(self, key):
            return self.data.get(key)

        def setex(self, key, ttl, value):
            self.data[key] = value

    cache = ToolResultCache(FakeRedis())

    # Miss
    cache.get("metrics_tool", {"id": 1})

    # Cache result
    cache.set(
        "metrics_tool",
        {"id": 1},
        {"status": "ok"},
    )

    # Two hits
    cache.get("metrics_tool", {"id": 1})
    cache.get("metrics_tool", {"id": 1})

    # Another miss
    cache.get("metrics_tool", {"id": 2})

    assert cache.get_metrics("metrics_tool") == {
        "hits": 2,
        "misses": 2,
    }

def test_cache_clear():
    class FakeRedis:
        def __init__(self):
            self.data = {}

        def get(self, key):
            return self.data.get(key)

        def setex(self, key, ttl, value):
            self.data[key] = value

        def delete(self, key):
            if key in self.data:
                del self.data[key]
                return 1
            return 0

    cache = ToolResultCache(FakeRedis())

    cache.set(
        "clear_tool",
        {"id": 1},
        {"status": "cached"},
    )

    assert cache.get(
        "clear_tool",
        {"id": 1},
    ) == {"status": "cached"}

    assert cache.clear(
        "clear_tool",
        {"id": 1},
    ) is True

    assert cache.get(
        "clear_tool",
        {"id": 1},
    ) is None

def test_cache_get_decodes_bytes():
    class FakeRedis:
        def get(self, key):
            return b'{"status":"cached"}'

    cache = ToolResultCache(FakeRedis())

    result = cache.get(
        "bytes_tool",
        {"id": 1},
    )

    assert result == {"status": "cached"}
    assert cache.get_metrics("bytes_tool") == {
        "hits": 1,
        "misses": 0,
    }