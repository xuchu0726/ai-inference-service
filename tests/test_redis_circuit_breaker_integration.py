from __future__ import annotations

import os
import time
import uuid

import pytest
from redis import Redis
from redis.exceptions import RedisError

from app.redis_circuit_breaker import RedisCircuitBreaker
from app.resilience import CircuitOpenError, CircuitState


@pytest.fixture
def redis_client():
    client = Redis.from_url(
        os.getenv(
            "TEST_REDIS_URL",
            "redis://127.0.0.1:6379/0",
        ),
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )

    try:
        client.ping()
    except RedisError:
        pytest.skip("local Redis integration service is unavailable")

    return client


def _breakers(redis_client, **kwargs):
    prefix = f"test:redis-breaker:{uuid.uuid4().hex}"
    common = {
        "failure_threshold": 2,
        "recovery_timeout_seconds": 1,
        "redis_url": "redis://127.0.0.1:6379/0",
        "key_prefix": prefix,
        "socket_timeout_seconds": 0.2,
        "probe_lease_ms": 1_000,
        "client": redis_client,
    }
    common.update(kwargs)

    first = RedisCircuitBreaker(**common)
    second = RedisCircuitBreaker(**common)

    state_key = f"{{{prefix}}}:circuit"
    probe_key = f"{{{prefix}}}:probe"

    return first, second, state_key, probe_key


def test_instances_share_open_state(redis_client):
    first, second, state_key, probe_key = _breakers(redis_client)

    try:
        permit = first.allow_primary_call()
        assert permit.state == CircuitState.CLOSED
        assert first.record_failure(permit) is None

        permit = first.allow_primary_call()
        transition = first.record_failure(permit)

        assert transition is not None
        assert transition.from_state == CircuitState.CLOSED
        assert transition.to_state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            second.allow_primary_call()

        assert second.state == CircuitState.OPEN
        assert second.snapshot()["store"] == "redis"
    finally:
        redis_client.delete(state_key, probe_key)


def test_only_one_instance_gets_half_open_probe(redis_client):
    first, second, state_key, probe_key = _breakers(
        redis_client,
        failure_threshold=1,
        recovery_timeout_seconds=0.05,
    )

    try:
        permit = first.allow_primary_call()
        transition = first.record_failure(permit)

        assert transition is not None
        assert transition.to_state == CircuitState.OPEN

        time.sleep(0.08)

        half_open_permit = first.allow_primary_call()
        assert half_open_permit.state == CircuitState.HALF_OPEN

        with pytest.raises(CircuitOpenError):
            second.allow_primary_call()

        transition = first.record_success(half_open_permit)

        assert transition is not None
        assert transition.from_state == CircuitState.HALF_OPEN
        assert transition.to_state == CircuitState.CLOSED
        assert second.allow_primary_call().state == CircuitState.CLOSED
    finally:
        redis_client.delete(state_key, probe_key)


def test_redis_unavailable_falls_back_to_local_breaker():
    breaker = RedisCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=1,
        redis_url="redis://127.0.0.1:6399/0",
        key_prefix=f"test:redis-unavailable:{uuid.uuid4().hex}",
        socket_timeout_seconds=0.05,
        probe_lease_ms=1_000,
    )

    permit = breaker.allow_primary_call()

    assert permit.store == "local_fallback"
    assert permit.state == CircuitState.CLOSED

    transition = breaker.record_failure(permit)

    assert transition is not None
    assert transition.to_state == CircuitState.OPEN
    assert breaker.snapshot()["store"] == "local_fallback"

def test_stale_success_cannot_close_newer_open_state(redis_client):
    first, second, state_key, probe_key = _breakers(
        redis_client,
        failure_threshold=1,
        recovery_timeout_seconds=60,
    )

    try:
        first_permit = first.allow_primary_call()
        second_permit = second.allow_primary_call()

        transition = second.record_failure(second_permit)

        assert transition is not None
        assert transition.from_state == CircuitState.CLOSED
        assert transition.to_state == CircuitState.OPEN

        assert first.record_success(first_permit) is None
        assert first.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            first.allow_primary_call()
    finally:
        redis_client.delete(state_key, probe_key)
