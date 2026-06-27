from __future__ import annotations

import uuid
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError

from app.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitPermit,
    CircuitState,
    CircuitTransition,
)

StoreEventCallback = Callable[[str, str], None]

_ALLOW_PRIMARY_LUA = """
local state_key = KEYS[1]
local probe_key = KEYS[2]

local recovery_timeout_ms = tonumber(ARGV[1])
local probe_lease_ms = tonumber(ARGV[2])
local probe_token = ARGV[3]

local now = redis.call("TIME")
local now_ms = now[1] * 1000 + math.floor(now[2] / 1000)

local state = redis.call("HGET", state_key, "state") or "closed"
local version = tonumber(redis.call("HGET", state_key, "version") or "0")

if state == "closed" then
    return {"allow", "closed", "0", tostring(version), ""}
end

if state == "open" then
    local opened_at_ms = tonumber(
        redis.call("HGET", state_key, "opened_at_ms") or "0"
    )
    local remaining_ms = recovery_timeout_ms - (now_ms - opened_at_ms)

    if remaining_ms > 0 then
        return {
            "block",
            "open",
            tostring(remaining_ms),
            tostring(version),
            "",
        }
    end
end

if state == "open" or state == "half_open" then
    local acquired = redis.call(
        "SET",
        probe_key,
        probe_token,
        "NX",
        "PX",
        probe_lease_ms
    )

    if acquired then
        version = redis.call("HINCRBY", state_key, "version", 1)
        redis.call(
            "HSET",
            state_key,
            "state",
            "half_open",
            "consecutive_failures",
            "0",
            "opened_at_ms",
            "0"
        )
        return {
            "allow",
            "half_open",
            "0",
            tostring(version),
            probe_token,
        }
    end

    local remaining_ms = redis.call("PTTL", probe_key)
    if remaining_ms < 0 then
        remaining_ms = probe_lease_ms
    end

    return {
        "block",
        "half_open",
        tostring(remaining_ms),
        tostring(version),
        "",
    }
end

return {
    "block",
    "open",
    tostring(recovery_timeout_ms),
    tostring(version),
    "",
}
"""

_RECORD_SUCCESS_LUA = """
local state_key = KEYS[1]
local probe_key = KEYS[2]

local permit_state = ARGV[1]
local permit_version = tonumber(ARGV[2])
local probe_token = ARGV[3]

local state = redis.call("HGET", state_key, "state") or "closed"
local version = tonumber(redis.call("HGET", state_key, "version") or "0")

if state ~= permit_state or version ~= permit_version then
    return {"stale", state, state}
end

if permit_state == "half_open" then
    if redis.call("GET", probe_key) ~= probe_token then
        return {"stale", state, state}
    end

    redis.call(
        "HSET",
        state_key,
        "state",
        "closed",
        "consecutive_failures",
        "0",
        "opened_at_ms",
        "0"
    )
    redis.call("HINCRBY", state_key, "version", 1)
    redis.call("DEL", probe_key)
    return {"transition", "half_open", "closed"}
end

if permit_state == "closed" then
    redis.call(
        "HSET",
        state_key,
        "state",
        "closed",
        "consecutive_failures",
        "0",
        "opened_at_ms",
        "0"
    )
    return {"no_transition", "closed", "closed"}
end

return {"stale", state, state}
"""

_RECORD_FAILURE_LUA = """
local state_key = KEYS[1]
local probe_key = KEYS[2]

local permit_state = ARGV[1]
local permit_version = tonumber(ARGV[2])
local probe_token = ARGV[3]
local failure_threshold = tonumber(ARGV[4])

local now = redis.call("TIME")
local now_ms = now[1] * 1000 + math.floor(now[2] / 1000)

local state = redis.call("HGET", state_key, "state") or "closed"
local version = tonumber(redis.call("HGET", state_key, "version") or "0")

if state ~= permit_state or version ~= permit_version then
    return {"stale", state, state}
end

if permit_state == "half_open" then
    if redis.call("GET", probe_key) ~= probe_token then
        return {"stale", state, state}
    end

    redis.call(
        "HSET",
        state_key,
        "state",
        "open",
        "consecutive_failures",
        tostring(failure_threshold),
        "opened_at_ms",
        tostring(now_ms)
    )
    redis.call("HINCRBY", state_key, "version", 1)
    redis.call("DEL", probe_key)
    return {"transition", "half_open", "open"}
end

if permit_state == "closed" then
    local failures = redis.call(
        "HINCRBY",
        state_key,
        "consecutive_failures",
        1
    )

    if failures >= failure_threshold then
        redis.call(
            "HSET",
            state_key,
            "state",
            "open",
            "opened_at_ms",
            tostring(now_ms)
        )
        redis.call("HINCRBY", state_key, "version", 1)
        return {"transition", "closed", "open"}
    end

    redis.call(
        "HSET",
        state_key,
        "state",
        "closed",
        "opened_at_ms",
        "0"
    )
    return {"no_transition", "closed", "closed"}
end

return {"stale", state, state}
"""

_SNAPSHOT_LUA = """
local state_key = KEYS[1]
local recovery_timeout_ms = tonumber(ARGV[1])

local now = redis.call("TIME")
local now_ms = now[1] * 1000 + math.floor(now[2] / 1000)

local state = redis.call("HGET", state_key, "state") or "closed"
local failures = tonumber(
    redis.call("HGET", state_key, "consecutive_failures") or "0"
)
local opened_at_ms = tonumber(
    redis.call("HGET", state_key, "opened_at_ms") or "0"
)

local remaining_ms = 0
if state == "open" then
    remaining_ms = recovery_timeout_ms - (now_ms - opened_at_ms)
    if remaining_ms < 0 then
        remaining_ms = 0
    end
end

return {
    state,
    tostring(failures),
    tostring(remaining_ms),
}
"""


class RedisCircuitBreaker:
    """
    Redis-backed circuit breaker with a process-local availability fallback.

    Redis is the authoritative state store when reachable. If Redis is
    unavailable, this Gateway falls back to its own local breaker so the
    request path remains available, while losing cross-Pod consistency.
    """

    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_timeout_seconds: float,
        redis_url: str,
        key_prefix: str,
        socket_timeout_seconds: float,
        probe_lease_ms: int,
        client: Redis | None = None,
        fallback_breaker: CircuitBreaker | None = None,
        on_store_event: StoreEventCallback | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")

        if recovery_timeout_seconds <= 0:
            raise ValueError(
                "recovery_timeout_seconds must be positive"
            )

        if socket_timeout_seconds <= 0:
            raise ValueError(
                "socket_timeout_seconds must be positive"
            )

        if probe_lease_ms <= 0:
            raise ValueError("probe_lease_ms must be positive")

        if not key_prefix:
            raise ValueError("key_prefix must not be empty")

        self._failure_threshold = failure_threshold
        self._recovery_timeout_ms = max(
            1,
            int(round(recovery_timeout_seconds * 1000)),
        )
        self._probe_lease_ms = probe_lease_ms
        self._on_store_event = on_store_event

        self._state_key = f"{{{key_prefix}}}:circuit"
        self._probe_key = f"{{{key_prefix}}}:probe"

        self._client = client or Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=socket_timeout_seconds,
            socket_timeout=socket_timeout_seconds,
        )
        self._fallback_breaker = fallback_breaker or CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout_seconds,
        )

    @property
    def state(self) -> CircuitState:
        return CircuitState(str(self.snapshot()["state"]))

    def allow_primary_call(self) -> CircuitPermit:
        response = self._eval(
            operation="allow_primary_call",
            script=_ALLOW_PRIMARY_LUA,
            keys=(self._state_key, self._probe_key),
            args=(
                self._recovery_timeout_ms,
                self._probe_lease_ms,
                uuid.uuid4().hex,
            ),
        )

        if response is None:
            return self._local_fallback_permit()

        decision, state, remaining_ms, version, probe_token = response

        if decision != "allow":
            raise CircuitOpenError(float(remaining_ms) / 1000)

        return CircuitPermit(
            state=CircuitState(state),
            version=int(version),
            probe_token=probe_token or None,
            store="redis",
        )

    def record_success(
        self,
        permit: CircuitPermit | None = None,
    ) -> CircuitTransition | None:
        if permit is None or permit.store != "redis":
            return self._fallback_breaker.record_success()

        response = self._eval(
            operation="record_success",
            script=_RECORD_SUCCESS_LUA,
            keys=(self._state_key, self._probe_key),
            args=(
                permit.state.value,
                permit.version if permit.version is not None else 0,
                permit.probe_token or "",
            ),
        )

        if response is None:
            return self._fallback_breaker.record_success()

        return self._transition_from_response(response)

    def record_failure(
        self,
        permit: CircuitPermit | None = None,
    ) -> CircuitTransition | None:
        if permit is None or permit.store != "redis":
            return self._fallback_breaker.record_failure()

        response = self._eval(
            operation="record_failure",
            script=_RECORD_FAILURE_LUA,
            keys=(self._state_key, self._probe_key),
            args=(
                permit.state.value,
                permit.version if permit.version is not None else 0,
                permit.probe_token or "",
                self._failure_threshold,
            ),
        )

        if response is None:
            return self._fallback_breaker.record_failure()

        return self._transition_from_response(response)

    def snapshot(self) -> dict[str, float | int | str]:
        response = self._eval(
            operation="snapshot",
            script=_SNAPSHOT_LUA,
            keys=(self._state_key,),
            args=(self._recovery_timeout_ms,),
        )

        if response is None:
            snapshot = self._fallback_breaker.snapshot()
            snapshot["store"] = "local_fallback"
            return snapshot

        state, failures, remaining_ms = response
        return {
            "state": state,
            "consecutive_failures": int(failures),
            "retry_after_seconds": round(
                float(remaining_ms) / 1000,
                6,
            ),
            "store": "redis",
        }

    def _local_fallback_permit(self) -> CircuitPermit:
        permit = self._fallback_breaker.allow_primary_call()
        return CircuitPermit(
            state=permit.state,
            version=permit.version,
            probe_token=permit.probe_token,
            store="local_fallback",
        )

    def _eval(
        self,
        *,
        operation: str,
        script: str,
        keys: tuple[str, ...],
        args: tuple[object, ...],
    ) -> list[str] | None:
        try:
            result = self._client.eval(
                script,
                len(keys),
                *keys,
                *args,
            )
        except RedisError:
            self._emit_store_event(operation, "local_fallback")
            return None

        self._emit_store_event(operation, "redis")
        return [str(value) for value in result]

    def _emit_store_event(
        self,
        operation: str,
        result: str,
    ) -> None:
        if self._on_store_event is not None:
            self._on_store_event(operation, result)

    @staticmethod
    def _transition_from_response(
        response: list[str],
    ) -> CircuitTransition | None:
        result, from_state, to_state = response

        if result != "transition":
            return None

        return CircuitTransition(
            from_state=CircuitState(from_state),
            to_state=CircuitState(to_state),
        )
