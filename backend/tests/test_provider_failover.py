"""
test_provider_failover.py

Unit test suite for ProviderFailoverExecutor, FailoverAttempt, FailoverExecutionResult,
ProviderFailoverMetrics, and ProviderFailoverExhaustedError (Task 4.4B Hardening Corrections).
"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from pydantic import ValidationError

from app.services.ai.FieldOpsAI.config.config_loader import ConfigLoader
from app.services.ai.FieldOpsAI.providers.base_provider import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderExecutionError,
)
from app.services.ai.FieldOpsAI.providers.provider_failover import (
    FailoverAttempt,
    FailoverExecutionResult,
    ProviderFailoverExecutor,
    ProviderFailoverExhaustedError,
    ProviderFailoverMetrics,
)
from app.services.ai.FieldOpsAI.providers.provider_health import (
    ProviderHealthConfig,
    ProviderHealthInfrastructureError,
    ProviderHealthMonitor,
    ProviderHealthSnapshot,
)
from app.services.ai.FieldOpsAI.schemas.provider import GenerationResult, ProviderHealth, UsageStats


class FakeClock:
    def __init__(self, start_dt: datetime | None = None) -> None:
        self._dt = start_dt or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._dt


class FakeProvider(BaseAIProvider):
    def __init__(self, name: str = "groq") -> None:
        self._name = name

    def generate_completion(self, messages, temperature=None, max_tokens=None) -> str:
        return "ok"

    def provider_name(self) -> str:
        return self._name

    def model_name(self) -> str:
        return "fake-model"

    def health_check(self) -> bool:
        return True


class FakeProviderFactory:
    @classmethod
    def create_provider(cls, name: str, config=None, provider_kwargs=None) -> BaseAIProvider:
        norm = name.strip().lower()
        if norm == "unknown_p":
            raise ProviderConfigurationError("Unknown provider")
        if norm == "bad_p":
            raise RuntimeError("Secret constructor crash gsk_12345")
        return FakeProvider(norm)

    @classmethod
    def registered_names(cls) -> list[str]:
        return ["groq", "openai"]


def make_gen_result(provider_name: str = "groq", text: str = "Hello world") -> GenerationResult:
    return GenerationResult(
        text=text,
        provider_name=provider_name,
        model_name="fake-model",
        usage=UsageStats(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_count=1,
            latency_ms=50.0,
            cost_usd=0.0,
        ),
    )


# 1. Primary provider succeeds
def test_primary_provider_succeeds() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    runner = lambda name, provider: make_gen_result(name, "Success response")

    res = executor.execute(runner)
    assert res.selected_provider == "groq"
    assert res.generation_result.text == "Success response"


# 2. Primary success produces one attempt
def test_primary_success_produces_one_attempt() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    runner = lambda name, provider: make_gen_result(name)

    res = executor.execute(runner)
    assert len(res.attempts) == 1
    assert res.attempts[0].provider_name == "groq"
    assert res.attempts[0].succeeded is True


# 3. Primary success sets failover_occurred=False
def test_primary_success_sets_failover_occurred_false() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    runner = lambda name, provider: make_gen_result(name)

    res = executor.execute(runner)
    assert res.failover_occurred is False


# 4. Retryable primary failure tries secondary
def test_retryable_primary_failure_tries_secondary() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Groq 429 Rate limit", is_retryable=True, status_code=429)
        return make_gen_result(name, "OpenAI success")

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(runner)

    assert res.selected_provider == "openai"
    assert len(res.attempts) == 2
    assert res.attempts[0].provider_name == "groq"
    assert res.attempts[0].retryable is True
    assert res.attempts[1].provider_name == "openai"
    assert res.attempts[1].succeeded is True


# 5. Secondary success sets failover_occurred=True
def test_secondary_success_sets_failover_occurred_true() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Groq error", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(runner)
    assert res.failover_occurred is True


# 6. Configured order is preserved
def test_configured_order_is_preserved() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["openai", "groq"]

    called_order = []

    def runner(name, provider):
        called_order.append(name)
        if name == "openai":
            raise ProviderExecutionError("OpenAI error", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(runner)
    assert called_order == ["openai", "groq"]
    assert res.selected_provider == "groq"


# 7. Non-retryable primary failure stops immediately
def test_non_retryable_primary_failure_stops_immediately() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Groq 401 Unauthorized", is_retryable=False, status_code=401)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderExecutionError) as exc_info:
        executor.execute(runner)

    assert exc_info.value.is_retryable is False
    assert exc_info.value.status_code == 401


# 8. Secondary is not called after non-retryable failure
def test_secondary_not_called_after_non_retryable_failure() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    called = []

    def runner(name, provider):
        called.append(name)
        if name == "groq":
            raise ProviderExecutionError("Fatal auth error", is_retryable=False)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderExecutionError):
        executor.execute(runner)

    assert called == ["groq"]


# 9. Unexpected exception stops safely
def test_unexpected_exception_stops_safely() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    def runner(name, provider):
        raise ValueError("Unexpected library bug!")

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderExecutionError) as exc_info:
        executor.execute(runner)

    assert exc_info.value.is_retryable is False
    assert "AI provider execution failed." in str(exc_info.value)


# 10. Raw exception absent from public errors
def test_raw_exception_absent_from_public_errors() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq"]

    secret = "gsk_SECRET_API_KEY_12345"

    def runner(name, provider):
        raise RuntimeError(f"Crash with secret {secret}")

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderExecutionError) as exc_info:
        executor.execute(runner)

    assert secret not in str(exc_info.value)


# 11. Raw exception absent from logs
def test_raw_exception_absent_from_logs(caplog) -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq"]

    secret = "gsk_SECRET_LOG_KEY_67890"

    def runner(name, provider):
        raise ProviderExecutionError(
            f"Error Authorization: Bearer {secret}",
            is_retryable=True,
        )

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)

    with caplog.at_level(logging.INFO):
        with pytest.raises(ProviderFailoverExhaustedError):
            executor.execute(runner)

    assert secret not in caplog.text


# 12. HEALTHY provider is eligible
def test_healthy_provider_is_eligible() -> None:
    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_health.get_snapshot.return_value = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.HEALTHY, checked_at=dt
    )

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health)
    res = executor.execute(lambda name, p: make_gen_result(name))
    assert res.selected_provider == "groq"


# 13. DEGRADED provider is eligible
def test_degraded_provider_is_eligible() -> None:
    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_health.get_snapshot.return_value = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.DEGRADED, checked_at=dt
    )

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health)
    res = executor.execute(lambda name, p: make_gen_result(name))
    assert res.selected_provider == "groq"


# 14. UNHEALTHY provider not due is skipped
def test_unhealthy_provider_not_due_is_skipped() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    next_dt = dt + timedelta(seconds=300)

    def get_snap(name):
        if name == "groq":
            return ProviderHealthSnapshot(
                provider_name="groq",
                status=ProviderHealth.UNHEALTHY,
                checked_at=dt,
                next_recovery_probe_at=next_dt,
            )
        return ProviderHealthSnapshot(
            provider_name="openai", status=ProviderHealth.HEALTHY, checked_at=dt
        )

    mock_health.get_snapshot.side_effect = get_snap
    mock_health.should_probe.return_value = False

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health, config=mock_config)
    res = executor.execute(lambda name, p: make_gen_result(name))

    assert res.selected_provider == "openai"
    assert res.attempts[0].provider_name == "groq"
    assert res.attempts[0].skipped is True


# 15. UNHEALTHY provider due is probed
def test_unhealthy_provider_due_is_probed() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq"]

    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    unhealthy_snap = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.UNHEALTHY, checked_at=dt
    )
    recovered_snap = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.HEALTHY, checked_at=dt
    )

    mock_health.get_snapshot.return_value = unhealthy_snap
    mock_health.should_probe.return_value = True
    mock_health.check_provider.return_value = recovered_snap

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health, config=mock_config)
    res = executor.execute(lambda name, p: make_gen_result(name))

    assert res.selected_provider == "groq"
    mock_health.check_provider.assert_called_once()


# 16. Recovered provider becomes eligible
def test_recovered_provider_becomes_eligible() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq"]

    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    unhealthy_snap = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.UNHEALTHY, checked_at=dt
    )
    healthy_snap = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.HEALTHY, checked_at=dt
    )

    mock_health.get_snapshot.return_value = unhealthy_snap
    mock_health.should_probe.return_value = True
    mock_health.check_provider.return_value = healthy_snap

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health, config=mock_config)
    res = executor.execute(lambda name, p: make_gen_result(name))
    assert res.selected_provider == "groq"


# 17. Failed recovery probe is skipped
def test_failed_recovery_probe_is_skipped() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    unhealthy_snap = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.UNHEALTHY, checked_at=dt
    )

    def get_snap(name):
        if name == "groq":
            return unhealthy_snap
        return ProviderHealthSnapshot(
            provider_name="openai", status=ProviderHealth.HEALTHY, checked_at=dt
        )

    mock_health.get_snapshot.side_effect = get_snap
    mock_health.should_probe.return_value = True
    mock_health.check_provider.return_value = unhealthy_snap

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health, config=mock_config)
    res = executor.execute(lambda name, p: make_gen_result(name))

    assert res.selected_provider == "openai"
    assert res.attempts[0].skipped is True


# 18. Missing snapshot triggers one health check
def test_missing_snapshot_triggers_one_health_check() -> None:
    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    healthy_snap = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.HEALTHY, checked_at=dt
    )

    mock_health.get_snapshot.return_value = None
    mock_health.check_provider.return_value = healthy_snap

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health)
    res = executor.execute(lambda name, p: make_gen_result(name))

    assert res.selected_provider == "groq"
    mock_health.check_provider.assert_called_once()


# 19. Health infrastructure error propagates
def test_health_infrastructure_error_propagates() -> None:
    mock_health = MagicMock()
    mock_health.get_snapshot.side_effect = ProviderHealthInfrastructureError("Redis down")

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health)
    with pytest.raises(ProviderHealthInfrastructureError):
        executor.execute(lambda name, p: make_gen_result(name))


# 20. Malformed fallback configuration propagates
def test_malformed_fallback_configuration_propagates() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = None
    type(mock_config).provider_fallback_order = PropertyMock(
        side_effect=ProviderConfigurationError("Malformed config")
    )

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderConfigurationError):
        executor.execute(lambda name, p: make_gen_result(name))


# 21. Unknown provider is skipped
def test_unknown_provider_is_skipped() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["unknown_p", "groq"]

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(lambda name, p: make_gen_result(name))

    assert res.selected_provider == "groq"
    assert res.attempts[0].provider_name == "unknown_p"
    assert res.attempts[0].skipped is True


# 22. Provider constructor failure is skipped safely
def test_provider_constructor_failure_is_skipped_safely() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["bad_p", "groq"]

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(lambda name, p: make_gen_result(name))

    assert res.selected_provider == "groq"
    assert res.attempts[0].skipped is True


# 23. All retryable failures produce ProviderFailoverExhaustedError
def test_all_retryable_failures_produce_exhausted_error() -> None:
    def runner(name, provider):
        raise ProviderExecutionError("Retryable failure", is_retryable=True)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    with pytest.raises(ProviderFailoverExhaustedError) as exc_info:
        executor.execute(runner)

    assert exc_info.value.is_retryable is True
    assert "All configured AI providers are unavailable." in str(exc_info.value)


# 24. No eligible provider produces ProviderFailoverExhaustedError
def test_no_eligible_provider_produces_exhausted_error() -> None:
    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_health.get_snapshot.return_value = ProviderHealthSnapshot(
        provider_name="groq", status=ProviderHealth.UNHEALTHY, checked_at=dt
    )
    mock_health.should_probe.return_value = False

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health)
    with pytest.raises(ProviderFailoverExhaustedError):
        executor.execute(lambda name, p: make_gen_result(name))


# 25. Exhausted error has fixed safe text
def test_exhausted_error_fixed_safe_text() -> None:
    err = ProviderFailoverExhaustedError()
    assert str(err) == "All configured AI providers are unavailable."
    assert err.is_retryable is True


# 26. GenerationResult validation
def test_generation_result_validation() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq"]

    def runner_invalid(name, provider):
        return "not a generation result"  # type: ignore[return-value]

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderExecutionError):
        executor.execute(runner_invalid)


# 27. Selected provider matches successful attempt
def test_selected_provider_matches_successful_attempt() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    res = executor.execute(lambda name, p: make_gen_result(name))

    successful_attempts = [a for a in res.attempts if a.succeeded]
    assert len(successful_attempts) == 1
    assert res.selected_provider == successful_attempts[0].provider_name


# 28. Attempt records contain no response text
def test_attempt_records_contain_no_response_text() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    res = executor.execute(lambda name, p: make_gen_result(name, "Secret prompt text response"))

    for attempt in res.attempts:
        payload = attempt.model_dump_json()
        assert "Secret prompt text response" not in payload


# 29. Attempt records contain no raw errors
def test_attempt_records_contain_no_raw_errors() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Secret API error gsk_55555", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(runner)

    for attempt in res.attempts:
        payload = attempt.model_dump_json()
        assert "gsk_55555" not in payload


# 30. Failover alert called once
def test_failover_alert_called_once() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    alert_mock = MagicMock()

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Retryable fail", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config, alert_callback=alert_mock)
    executor.execute(runner)

    alert_mock.assert_called_once()
    payload = alert_mock.call_args[0][0]
    assert payload["event_type"] == "failover_success"
    assert payload["selected_provider"] == "openai"


# 31. Exhausted alert called once
def test_exhausted_alert_called_once() -> None:
    alert_mock = MagicMock()

    def runner(name, provider):
        raise ProviderExecutionError("Retryable fail", is_retryable=True)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, alert_callback=alert_mock)
    with pytest.raises(ProviderFailoverExhaustedError):
        executor.execute(runner)

    alert_mock.assert_called_once()
    payload = alert_mock.call_args[0][0]
    assert payload["event_type"] == "failover_exhausted"


# 32. Alert callback exception is harmless
def test_alert_callback_exception_is_harmless() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    bad_alert = MagicMock(side_effect=Exception("Alert crash"))

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Retryable fail", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config, alert_callback=bad_alert)
    res = executor.execute(runner)
    assert res.selected_provider == "openai"


# 33. Metrics primary success
def test_metrics_primary_success() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    executor.execute(lambda name, p: make_gen_result(name))

    metrics = executor.get_metrics()
    assert metrics.total_executions == 1
    assert metrics.primary_successes == 1
    assert metrics.failover_successes == 0


# 34. Metrics failover success
def test_metrics_failover_success() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    def runner(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Fail", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    executor.execute(runner)

    metrics = executor.get_metrics()
    assert metrics.total_executions == 1
    assert metrics.primary_successes == 0
    assert metrics.failover_successes == 1


# 35. Metrics exhaustion
def test_metrics_exhaustion() -> None:
    def runner(name, provider):
        raise ProviderExecutionError("Fail", is_retryable=True)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    with pytest.raises(ProviderFailoverExhaustedError):
        executor.execute(runner)

    metrics = executor.get_metrics()
    assert metrics.total_executions == 1
    assert metrics.exhausted_executions == 1


# 36. Metrics retryable and non-retryable failure counts
def test_metrics_retryable_and_non_retryable_failure_counts() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    # 1. Retryable failure
    def runner_retryable(name, provider):
        if name == "groq":
            raise ProviderExecutionError("Fail", is_retryable=True)
        return make_gen_result(name)

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    executor.execute(runner_retryable)
    assert executor.get_metrics().retryable_failures == 1

    # 2. Non-retryable failure
    def runner_non_retryable(name, provider):
        raise ProviderExecutionError("Fatal", is_retryable=False)

    executor2 = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    with pytest.raises(ProviderExecutionError):
        executor2.execute(runner_non_retryable)
    assert executor2.get_metrics().non_retryable_failures == 1


# 37. Average attempts and latency
def test_average_attempts_and_latency() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)
    executor.execute(lambda name, p: make_gen_result(name))

    metrics = executor.get_metrics()
    assert metrics.average_attempts == 1.0
    assert metrics.average_latency_ms >= 0.0


# 38. Concurrent metric updates remain accurate
def test_concurrent_metric_updates_remain_accurate() -> None:
    import threading

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)

    def run_exec():
        executor.execute(lambda name, p: make_gen_result(name))

    threads = [threading.Thread(target=run_exec) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    metrics = executor.get_metrics()
    assert metrics.total_executions == 10
    assert metrics.primary_successes == 10


# 39. provider_kwargs_by_name passed to the correct provider only
def test_provider_kwargs_by_name_passed_correctly() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["groq", "openai"]

    mock_factory = MagicMock()
    mock_factory.create_provider.side_effect = lambda name, config=None, provider_kwargs=None: FakeProvider(name)

    executor = ProviderFailoverExecutor(provider_factory=mock_factory, config=mock_config)
    kwargs_map = {"groq": {"groq_param": 123}, "openai": {"openai_param": 456}}

    executor.execute(lambda name, p: make_gen_result(name), provider_kwargs_by_name=kwargs_map)

    mock_factory.create_provider.assert_called_with(
        name="groq", config=mock_config, provider_kwargs={"groq_param": 123}
    )


# 40. No module-import side effects
def test_no_module_import_side_effects() -> None:
    with patch("asyncio.create_task") as mock_create_task:
        import app.services.ai.FieldOpsAI.providers.provider_failover as pf
        importlib.reload(pf)
        mock_create_task.assert_not_called()


# --- HARDENING CORRECTION TESTS ---

# CORRECTION 1: Completed Execution Metrics
def test_completed_execution_metrics_non_retryable_and_unexpected() -> None:
    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory)

    # 1. Non-retryable failure increments total_executions once
    def runner_non_retryable(name, provider):
        raise ProviderExecutionError("Fatal", is_retryable=False)

    with pytest.raises(ProviderExecutionError):
        executor.execute(runner_non_retryable)

    metrics = executor.get_metrics()
    assert metrics.total_executions == 1
    assert metrics.non_retryable_failures == 1
    assert metrics.primary_successes == 0
    assert metrics.failover_successes == 0
    assert metrics.exhausted_executions == 0
    assert metrics.average_attempts == 1.0

    # 2. Unexpected exception increments total_executions once
    def runner_unexpected(name, provider):
        raise RuntimeError("Bug")

    with pytest.raises(ProviderExecutionError):
        executor.execute(runner_unexpected)

    metrics2 = executor.get_metrics()
    assert metrics2.total_executions == 2
    assert metrics2.non_retryable_failures == 2
    assert metrics2.primary_successes == 0
    assert metrics2.exhausted_executions == 0


# CORRECTION 2: Strict Fallback Validation
def test_strict_fallback_validation() -> None:
    # Non-list/tuple raw fallback order
    mock_cfg1 = MagicMock()
    mock_cfg1.provider_fallback_order = "groq"  # String instead of list
    executor1 = ProviderFailoverExecutor(config=mock_cfg1)
    with pytest.raises(ProviderConfigurationError):
        executor1.execute(lambda n, p: make_gen_result(n))

    # Element is integer
    mock_cfg2 = MagicMock()
    mock_cfg2.provider_fallback_order = ["groq", 123]
    executor2 = ProviderFailoverExecutor(config=mock_cfg2)
    with pytest.raises(ProviderConfigurationError):
        executor2.execute(lambda n, p: make_gen_result(n))

    # Element is None
    mock_cfg3 = MagicMock()
    mock_cfg3.provider_fallback_order = ["groq", None]
    executor3 = ProviderFailoverExecutor(config=mock_cfg3)
    with pytest.raises(ProviderConfigurationError):
        executor3.execute(lambda n, p: make_gen_result(n))

    # Element is blank string
    mock_cfg4 = MagicMock()
    mock_cfg4.provider_fallback_order = ["groq", "   "]
    executor4 = ProviderFailoverExecutor(config=mock_cfg4)
    with pytest.raises(ProviderConfigurationError):
        executor4.execute(lambda n, p: make_gen_result(n))


# CORRECTION 3: Skipped Unhealthy Metric Rules
def test_skipped_unhealthy_metric_rules() -> None:
    mock_config = MagicMock()
    mock_config.provider_fallback_order = ["unknown_p", "bad_p", "groq"]

    executor = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, config=mock_config)
    res = executor.execute(lambda n, p: make_gen_result(n))

    assert res.selected_provider == "groq"
    # Unknown provider and constructor failure should NOT increment skipped_unhealthy_providers
    metrics = executor.get_metrics()
    assert metrics.skipped_unhealthy_providers == 0

    # Unhealthy provider MUST increment skipped_unhealthy_providers
    mock_config2 = MagicMock()
    mock_config2.provider_fallback_order = ["unhealthy_p", "groq"]
    mock_health = MagicMock()
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_health.get_snapshot.side_effect = lambda name: (
        ProviderHealthSnapshot(provider_name="unhealthy_p", status=ProviderHealth.UNHEALTHY, checked_at=dt)
        if name == "unhealthy_p" else ProviderHealthSnapshot(provider_name="groq", status=ProviderHealth.HEALTHY, checked_at=dt)
    )
    mock_health.should_probe.return_value = False

    executor2 = ProviderFailoverExecutor(provider_factory=FakeProviderFactory, health_monitor=mock_health, config=mock_config2)
    res2 = executor2.execute(lambda n, p: make_gen_result(n))
    assert res2.selected_provider == "groq"
    assert executor2.get_metrics().skipped_unhealthy_providers == 1


# CORRECTION 4: Failover Attempt Consistency & Status Code Validation
def test_failover_attempt_consistency_and_status_code() -> None:
    # Contradictory states
    with pytest.raises(ValidationError):
        FailoverAttempt(
            provider_name="groq", attempted=True, skipped=True, succeeded=False, retryable=False
        )

    with pytest.raises(ValidationError):
        FailoverAttempt(
            provider_name="groq", attempted=False, skipped=False, succeeded=True, retryable=False
        )

    with pytest.raises(ValidationError):
        FailoverAttempt(
            provider_name="groq", attempted=False, skipped=True, succeeded=True, retryable=False
        )

    # Boolean status code rejected
    with pytest.raises(ValidationError):
        FailoverAttempt(
            provider_name="groq", attempted=True, skipped=False, succeeded=False, retryable=False, status_code=True  # type: ignore[arg-type]
        )

    # Out of range status code rejected
    with pytest.raises(ValidationError):
        FailoverAttempt(
            provider_name="groq", attempted=True, skipped=False, succeeded=False, retryable=False, status_code=99
        )

    with pytest.raises(ValidationError):
        FailoverAttempt(
            provider_name="groq", attempted=True, skipped=False, succeeded=False, retryable=False, status_code=600
        )

    # Valid status code accepted
    att = FailoverAttempt(
        provider_name="groq", attempted=True, skipped=False, succeeded=False, retryable=True, status_code=429
    )
    assert att.status_code == 429
