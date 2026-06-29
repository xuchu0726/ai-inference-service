from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import socket
import time
from typing import Any, Callable, Mapping

from prometheus_client import start_http_server

from app.config import (
    JOB_WORKER_BATCH_SIZE,
    JOB_WORKER_BLOCK_MS,
    JOB_WORKER_ERROR_BACKOFF_SECONDS,
    JOB_WORKER_METRICS_HOST,
    JOB_WORKER_METRICS_PORT,
    JOB_WORKER_RECLAIM_IDLE_MS,
    JOB_WORKER_SOCKET_TIMEOUT_SECONDS,
)
from app.metrics.prometheus_metrics import (
    record_async_job_reclaims,
    record_async_job_status_transition,
    record_async_job_worker_result,
)
from app.redis_stream_jobs import (
    JobLease,
    JobMessage,
    JobQueueUnavailableError,
    RedisStreamJobQueue,
)
from app.schemas import GenerateRequest


@dataclass(frozen=True)
class WorkerBatchResult:
    reclaimed: int
    received_new: int
    succeeded: int
    failed: int
    skipped: int


class JobWorker:
    """消费 Redis Stream 推理任务的单 worker 执行器。"""

    def __init__(
        self,
        *,
        queue: RedisStreamJobQueue,
        consumer_name: str,
        generate_text: Callable[..., Mapping[str, Any]],
        batch_size: int,
        block_ms: int,
        reclaim_idle_ms: int,
    ) -> None:
        consumer_name = consumer_name.strip()

        if not consumer_name:
            raise ValueError("consumer_name must not be empty")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if block_ms < 0:
            raise ValueError("block_ms must not be negative")
        if reclaim_idle_ms <= 0:
            raise ValueError("reclaim_idle_ms must be positive")

        self._queue = queue
        self._consumer_name = consumer_name
        self._generate_text = generate_text
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._reclaim_idle_ms = reclaim_idle_ms

        self._consumer_group_ready = False
        self._reclaim_start_id = "0-0"

    def process_once(self) -> WorkerBatchResult:
        self._ensure_consumer_group()

        next_start_id, reclaimed_messages = self._queue.reclaim_idle(
            consumer_name=self._consumer_name,
            min_idle_time_ms=self._reclaim_idle_ms,
            start_id=self._reclaim_start_id,
            count=self._batch_size,
        )
        self._reclaim_start_id = str(next_start_id)
        record_async_job_reclaims(len(reclaimed_messages))

        remaining_capacity = max(
            self._batch_size - len(reclaimed_messages),
            0,
        )

        new_messages: list[JobMessage] = []
        if remaining_capacity:
            new_messages = self._queue.read_new(
                consumer_name=self._consumer_name,
                count=remaining_capacity,
                block_ms=(
                    self._block_ms
                    if not reclaimed_messages
                    else 0
                ),
            )

        succeeded = 0
        failed = 0
        skipped = 0

        for message in [*reclaimed_messages, *new_messages]:
            outcome = self._process_message(message)
            record_async_job_worker_result(outcome)

            if outcome == "succeeded":
                succeeded += 1
                record_async_job_status_transition("succeeded")
            elif outcome == "failed":
                failed += 1
                record_async_job_status_transition("failed")
            else:
                skipped += 1

        return WorkerBatchResult(
            reclaimed=len(reclaimed_messages),
            received_new=len(new_messages),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
        )

    def _ensure_consumer_group(self) -> None:
        if self._consumer_group_ready:
            return

        self._queue.ensure_consumer_group()
        self._consumer_group_ready = True

    def _process_message(self, message: JobMessage) -> str:
        lease = self._queue.mark_running(
            message=message,
            worker_name=self._consumer_name,
        )

        if lease is None:
            return "skipped"

        record_async_job_status_transition("running")

        try:
            request = GenerateRequest(**message.payload)

            if not request.prompt.strip():
                raise ValueError("prompt must not be empty")

            result = self._generate_text(
                **self._request_payload(request)
            )

            if not isinstance(result, Mapping):
                raise TypeError("generate_text must return a mapping")
        except Exception as exc:
            finalized = self._queue.fail(
                lease=lease,
                error_type=type(exc).__name__,
                error_message=str(exc) or type(exc).__name__,
            )
            return "failed" if finalized else "skipped"

        finalized = self._queue.complete(
            lease=lease,
            result=result,
        )
        return "succeeded" if finalized else "skipped"

    @staticmethod
    def _request_payload(
        request: GenerateRequest,
    ) -> dict[str, Any]:
        model_dump = getattr(request, "model_dump", None)

        if callable(model_dump):
            return dict(model_dump())

        return dict(request.dict())


def _default_consumer_name() -> str:
    configured = os.getenv("JOB_WORKER_NAME", "").strip()
    if configured:
        return configured

    return f"{socket.gethostname()}-{os.getpid()}"



def start_worker_metrics_server(
    *,
    host: str = JOB_WORKER_METRICS_HOST,
    port: int = JOB_WORKER_METRICS_PORT,
) -> None:
    start_http_server(port, addr=host)


def main() -> None:
    from app.inference import generate_text
    from app.job_runtime import build_job_queue

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger("ai_inference.job_worker")

    start_worker_metrics_server()
    logger.info(
        "job worker metrics listening on %s:%s",
        JOB_WORKER_METRICS_HOST,
        JOB_WORKER_METRICS_PORT,
    )

    worker = JobWorker(
        queue=build_job_queue(
            socket_timeout_seconds=JOB_WORKER_SOCKET_TIMEOUT_SECONDS,
        ),
        consumer_name=_default_consumer_name(),
        generate_text=generate_text,
        batch_size=JOB_WORKER_BATCH_SIZE,
        block_ms=JOB_WORKER_BLOCK_MS,
        reclaim_idle_ms=JOB_WORKER_RECLAIM_IDLE_MS,
    )

    logger.info("job worker started")

    while True:
        try:
            result = worker.process_once()
        except JobQueueUnavailableError as exc:
            logger.warning("job queue unavailable: %s", exc)
            time.sleep(JOB_WORKER_ERROR_BACKOFF_SECONDS)
            continue

        if result.reclaimed or result.received_new:
            logger.info(
                "batch reclaimed=%s new=%s succeeded=%s failed=%s skipped=%s",
                result.reclaimed,
                result.received_new,
                result.succeeded,
                result.failed,
                result.skipped,
            )


if __name__ == "__main__":
    main()
