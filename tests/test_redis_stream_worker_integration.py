import os
import time
import uuid

import pytest
import redis
from redis.exceptions import RedisError

from app.job_worker import JobWorker
from app.redis_stream_jobs import RedisStreamJobQueue


TEST_REDIS_URL = os.getenv(
    "TEST_REDIS_URL",
    "redis://127.0.0.1:6379/0",
)


@pytest.fixture
def redis_client():
    client = redis.Redis.from_url(
        TEST_REDIS_URL,
        decode_responses=True,
    )

    try:
        client.ping()
    except RedisError:
        pytest.skip(f"Redis is unavailable at {TEST_REDIS_URL}")

    return client


@pytest.fixture
def queue(redis_client):
    prefix = f"ai-inference:week4:test-worker:{uuid.uuid4().hex}"

    instance = RedisStreamJobQueue(
        redis_url=TEST_REDIS_URL,
        key_prefix=prefix,
        consumer_group="test-workers",
        socket_timeout_seconds=0.5,
        job_ttl_seconds=60,
        client=redis_client,
    )
    instance.ensure_consumer_group()

    try:
        yield instance
    finally:
        keys = list(redis_client.scan_iter(match=f"{{{prefix}}}:*"))
        if keys:
            redis_client.delete(*keys)


def test_replacement_worker_reclaims_and_completes_running_job(queue):
    accepted = queue.enqueue(
        {
            "prompt": "worker crash recovery validation",
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        }
    )

    abandoned = queue.read_new(
        consumer_name="crashed-worker",
        count=1,
        block_ms=0,
    )[0]

    abandoned_lease = queue.mark_running(
        message=abandoned,
        worker_name="crashed-worker",
    )
    assert abandoned_lease is not None

    time.sleep(0.02)

    calls = []

    def generate_text(**kwargs):
        calls.append(kwargs)
        return {
            "response": "recovered by replacement worker",
            "backend": "mock",
        }

    replacement = JobWorker(
        queue=queue,
        consumer_name="replacement-worker",
        generate_text=generate_text,
        batch_size=1,
        block_ms=0,
        reclaim_idle_ms=1,
    )

    outcome = replacement.process_once()

    assert outcome.reclaimed == 1
    assert outcome.received_new == 0
    assert outcome.succeeded == 1
    assert outcome.failed == 0
    assert outcome.skipped == 0

    assert calls == [
        {
            "prompt": "worker crash recovery validation",
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        }
    ]

    final_state = queue.get_job(accepted["job_id"])
    assert final_state is not None
    assert final_state["status"] == "succeeded"
    assert final_state["worker"] == "replacement-worker"
    assert final_state["attempt_count"] == 2
    assert final_state["result"]["response"] == (
        "recovered by replacement worker"
    )

    assert queue._client.xpending_range(
        queue.stream_key,
        queue.consumer_group,
        "-",
        "+",
        10,
    ) == []
    assert queue._client.xlen(queue.stream_key) == 0
