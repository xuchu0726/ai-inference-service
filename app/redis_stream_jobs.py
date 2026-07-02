from __future__ import annotations

from dataclasses import dataclass
import json
import time
import uuid
from typing import Any, Mapping

import redis
from redis.exceptions import RedisError, ResponseError


class JobQueueUnavailableError(RuntimeError):
    """Redis Stream 队列不可用。"""


class JobQueueProtocolError(RuntimeError):
    """Stream 消息字段不符合队列协议。"""


@dataclass(frozen=True)
class JobMessage:
    stream_id: str
    job_id: str
    payload: dict[str, Any]
    created_at_ms: int
    reclaimed: bool = False


@dataclass(frozen=True)
class JobLease:
    message: JobMessage
    worker_name: str
    delivery_token: str


class RedisStreamJobQueue:
    """基于 Redis Stream 的异步推理任务队列。

    语义为 at-least-once：worker 在 XACK 前异常退出时，消息保留在
    Pending Entries List 中，并可由其他 worker 通过 XAUTOCLAIM 接管；
    对不支持 XAUTOCLAIM 的 Redis 6，回退到 XPENDING + XCLAIM。
    """

    _MARK_RUNNING_LUA = """
local pending = redis.call(
    "XPENDING", KEYS[2], ARGV[1], ARGV[2], ARGV[2], 1
)

if #pending == 0 or pending[1][2] ~= ARGV[3] then
    return 0
end

redis.call("SET", KEYS[1], ARGV[4], "EX", ARGV[5])
return 1
"""

    _FINALIZE_LUA = """
local pending = redis.call(
    "XPENDING", KEYS[2], ARGV[4], ARGV[5], ARGV[5], 1
)

if #pending == 0 or pending[1][2] ~= ARGV[6] then
    return 0
end

local current = redis.call("GET", KEYS[1])
if not current then
    return 0
end

local ok, decoded = pcall(cjson.decode, current)
if not ok then
    return 0
end

if decoded["delivery_token"] ~= ARGV[1] then
    return 0
end

redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
redis.call("XACK", KEYS[2], ARGV[4], ARGV[5])
redis.call("XDEL", KEYS[2], ARGV[5])
return 1
"""

    def __init__(
        self,
        *,
        redis_url: str,
        key_prefix: str,
        consumer_group: str,
        socket_timeout_seconds: float,
        job_ttl_seconds: int,
        client: redis.Redis | None = None,
    ) -> None:
        key_prefix = key_prefix.strip().rstrip(":")
        consumer_group = consumer_group.strip()

        if not key_prefix:
            raise ValueError("key_prefix must not be empty")
        if not consumer_group:
            raise ValueError("consumer_group must not be empty")
        if socket_timeout_seconds <= 0:
            raise ValueError("socket_timeout_seconds must be positive")
        if job_ttl_seconds <= 0:
            raise ValueError("job_ttl_seconds must be positive")

        self._key_prefix = key_prefix
        self._consumer_group = consumer_group
        self._job_ttl_seconds = job_ttl_seconds

        hash_tag = f"{{{key_prefix}}}"
        self._stream_key = f"{hash_tag}:stream"
        self._job_key_prefix = f"{hash_tag}:job:"

        self._client = client or redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=socket_timeout_seconds,
            socket_timeout=socket_timeout_seconds,
        )

    @property
    def stream_key(self) -> str:
        return self._stream_key

    @property
    def consumer_group(self) -> str:
        return self._consumer_group

    def job_key(self, job_id: str) -> str:
        return f"{self._job_key_prefix}{job_id}"

    def ensure_consumer_group(self) -> None:
        try:
            self._client.xgroup_create(
                self._stream_key,
                self._consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise JobQueueUnavailableError(
                    f"failed to create consumer group: {exc}"
                ) from exc
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to create consumer group: {exc}"
            ) from exc

    def enqueue(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now_ms = self._now_ms()

        state = {
            "job_id": job_id,
            "status": "queued",
            "created_at_ms": now_ms,
            "updated_at_ms": now_ms,
            "attempt_count": 0,
        }

        try:
            payload_json = self._encode_json(dict(payload))
            state_json = self._encode_json(state)

            pipeline = self._client.pipeline(transaction=True)
            pipeline.set(
                self.job_key(job_id),
                state_json,
                ex=self._job_ttl_seconds,
            )
            pipeline.xadd(
                self._stream_key,
                {
                    "job_id": job_id,
                    "payload": payload_json,
                    "created_at_ms": str(now_ms),
                },
            )
            pipeline.execute()
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to enqueue job: {exc}"
            ) from exc

        return state

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            raw_state = self._client.get(self.job_key(job_id))
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to read job status: {exc}"
            ) from exc

        if raw_state is None:
            return None

        state = self._decode_json(raw_state)
        if not isinstance(state, dict):
            raise JobQueueProtocolError("job state must be a JSON object")

        return state

    def read_new(
        self,
        *,
        consumer_name: str,
        count: int,
        block_ms: int,
    ) -> list[JobMessage]:
        if count <= 0:
            raise ValueError("count must be positive")
        if block_ms < 0:
            raise ValueError("block_ms must not be negative")

        try:
            records = self._client.xreadgroup(
                self._consumer_group,
                consumer_name,
                {self._stream_key: ">"},
                count=count,
                block=block_ms,
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to read new jobs: {exc}"
            ) from exc

        return self._decode_records(records, reclaimed=False)

    def reclaim_idle(
        self,
        *,
        consumer_name: str,
        min_idle_time_ms: int,
        start_id: str,
        count: int,
    ) -> tuple[str, list[JobMessage]]:
        if min_idle_time_ms < 0:
            raise ValueError("min_idle_time_ms must not be negative")
        if count <= 0:
            raise ValueError("count must be positive")

        try:
            claimed = self._client.xautoclaim(
                self._stream_key,
                self._consumer_group,
                consumer_name,
                min_idle_time=min_idle_time_ms,
                start_id=start_id,
                count=count,
            )
        except ResponseError as exc:
            if not self._is_xautoclaim_unsupported(exc):
                raise JobQueueUnavailableError(
                    f"failed to reclaim pending jobs: {exc}"
                ) from exc
            return self._reclaim_idle_legacy(
                consumer_name=consumer_name,
                min_idle_time_ms=min_idle_time_ms,
                start_id=start_id,
                count=count,
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to reclaim pending jobs: {exc}"
            ) from exc

        if not isinstance(claimed, (list, tuple)) or len(claimed) != 3:
            raise JobQueueProtocolError(
                f"unexpected XAUTOCLAIM response: {claimed!r}"
            )

        next_start_id, records, _deleted_message_ids = claimed
        messages = self._decode_records(
            [(self._stream_key, records)],
            reclaimed=True,
        )
        return str(next_start_id), messages

    @staticmethod
    def _is_xautoclaim_unsupported(exc: ResponseError) -> bool:
        message = str(exc).lower()
        return "unknown command" in message and "xautoclaim" in message

    def _reclaim_idle_legacy(
        self,
        *,
        consumer_name: str,
        min_idle_time_ms: int,
        start_id: str,
        count: int,
    ) -> tuple[str, list[JobMessage]]:
        scan_start = "-" if start_id == "0-0" else f"({start_id}"

        try:
            pending = self._client.xpending_range(
                self._stream_key,
                self._consumer_group,
                min=scan_start,
                max="+",
                count=count,
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to inspect pending jobs for legacy reclaim: {exc}"
            ) from exc

        if not pending:
            return "0-0", []

        candidate_ids: list[str] = []
        for entry in pending:
            if not isinstance(entry, Mapping):
                raise JobQueueProtocolError(
                    f"unexpected XPENDING entry: {entry!r}"
                )

            message_id = entry.get("message_id")
            idle_ms = entry.get("time_since_delivered")

            if not isinstance(message_id, str) or not isinstance(idle_ms, int):
                raise JobQueueProtocolError(
                    f"unexpected XPENDING entry fields: {entry!r}"
                )

            if idle_ms >= min_idle_time_ms:
                candidate_ids.append(message_id)

        next_start_id = (
            "0-0"
            if len(pending) <= count
            else str(pending[-1]["message_id"])
        )

        if not candidate_ids:
            return next_start_id, []

        try:
            records = self._client.xclaim(
                self._stream_key,
                self._consumer_group,
                consumer_name,
                min_idle_time=min_idle_time_ms,
                message_ids=candidate_ids,
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to legacy-claim pending jobs: {exc}"
            ) from exc

        messages = self._decode_records(
            [(self._stream_key, records)],
            reclaimed=True,
        )
        return next_start_id, messages

    def mark_running(
        self,
        *,
        message: JobMessage,
        worker_name: str,
    ) -> JobLease | None:
        state = self.get_job(message.job_id)

        if state is None:
            state = {
                "job_id": message.job_id,
                "status": "queued",
                "created_at_ms": message.created_at_ms,
                "updated_at_ms": message.created_at_ms,
                "attempt_count": 0,
            }

        delivery_token = uuid.uuid4().hex
        state.update(
            {
                "status": "running",
                "updated_at_ms": self._now_ms(),
                "attempt_count": int(state.get("attempt_count", 0)) + 1,
                "worker": worker_name,
                "delivery_token": delivery_token,
            }
        )

        try:
            claimed = self._client.eval(
                self._MARK_RUNNING_LUA,
                2,
                self.job_key(message.job_id),
                self._stream_key,
                self._consumer_group,
                message.stream_id,
                worker_name,
                self._encode_json(state),
                str(self._job_ttl_seconds),
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to mark job as running: {exc}"
            ) from exc

        if not claimed:
            return None

        return JobLease(
            message=message,
            worker_name=worker_name,
            delivery_token=delivery_token,
        )

    def complete(
        self,
        *,
        lease: JobLease,
        result: Mapping[str, Any],
    ) -> bool:
        state = self._state_for_terminal_update(lease)
        if state is None:
            return False

        state.update(
            {
                "status": "succeeded",
                "updated_at_ms": self._now_ms(),
                "worker": lease.worker_name,
                "result": dict(result),
            }
        )
        state.pop("delivery_token", None)
        state.pop("error_type", None)
        state.pop("error_message", None)

        return self._finalize(lease=lease, state=state)

    def fail(
        self,
        *,
        lease: JobLease,
        error_type: str,
        error_message: str,
    ) -> bool:
        state = self._state_for_terminal_update(lease)
        if state is None:
            return False

        state.update(
            {
                "status": "failed",
                "updated_at_ms": self._now_ms(),
                "worker": lease.worker_name,
                "error_type": error_type,
                "error_message": error_message[:1000],
            }
        )
        state.pop("delivery_token", None)
        state.pop("result", None)

        return self._finalize(lease=lease, state=state)

    def _state_for_terminal_update(
        self,
        lease: JobLease,
    ) -> dict[str, Any] | None:
        state = self.get_job(lease.message.job_id)
        if state is None:
            return None

        if state.get("delivery_token") != lease.delivery_token:
            return None

        return state

    def _finalize(
        self,
        *,
        lease: JobLease,
        state: Mapping[str, Any],
    ) -> bool:
        try:
            result = self._client.eval(
                self._FINALIZE_LUA,
                2,
                self.job_key(lease.message.job_id),
                self._stream_key,
                lease.delivery_token,
                self._encode_json(dict(state)),
                str(self._job_ttl_seconds),
                self._consumer_group,
                lease.message.stream_id,
                lease.worker_name,
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to finalize job: {exc}"
            ) from exc

        return bool(result)

    def _write_state(self, state: Mapping[str, Any]) -> None:
        job_id = state.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise JobQueueProtocolError("job state must include a job_id")

        try:
            self._client.set(
                self.job_key(job_id),
                self._encode_json(dict(state)),
                ex=self._job_ttl_seconds,
            )
        except RedisError as exc:
            raise JobQueueUnavailableError(
                f"failed to update job status: {exc}"
            ) from exc

    def _decode_records(
        self,
        records: Any,
        *,
        reclaimed: bool,
    ) -> list[JobMessage]:
        messages: list[JobMessage] = []

        if not records:
            return messages

        for _stream_name, entries in records:
            for stream_id, fields in entries:
                if not isinstance(fields, Mapping):
                    raise JobQueueProtocolError(
                        f"stream fields must be a mapping: {fields!r}"
                    )

                job_id = fields.get("job_id")
                payload_raw = fields.get("payload")
                created_at_raw = fields.get("created_at_ms")

                if not isinstance(job_id, str) or not job_id:
                    raise JobQueueProtocolError("stream message missing job_id")
                if not isinstance(payload_raw, str):
                    raise JobQueueProtocolError(
                        "stream message missing JSON payload"
                    )

                try:
                    created_at_ms = int(created_at_raw)
                except (TypeError, ValueError) as exc:
                    raise JobQueueProtocolError(
                        "stream message has invalid created_at_ms"
                    ) from exc

                payload = self._decode_json(payload_raw)
                if not isinstance(payload, dict):
                    raise JobQueueProtocolError(
                        "stream payload must be a JSON object"
                    )

                messages.append(
                    JobMessage(
                        stream_id=str(stream_id),
                        job_id=job_id,
                        payload=payload,
                        created_at_ms=created_at_ms,
                        reclaimed=reclaimed,
                    )
                )

        return messages

    @staticmethod
    def _encode_json(value: Any) -> str:
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise JobQueueProtocolError(
                f"value is not JSON serializable: {exc}"
            ) from exc

    @staticmethod
    def _decode_json(raw_value: str) -> Any:
        try:
            return json.loads(raw_value)
        except (TypeError, ValueError) as exc:
            raise JobQueueProtocolError(
                f"invalid JSON payload: {exc}"
            ) from exc

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
