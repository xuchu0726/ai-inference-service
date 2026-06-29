import os
import uuid

import pytest
import redis
from redis.exceptions import RedisError

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
    prefix = f"ai-inference:week4:test-jobs:{uuid.uuid4().hex}"

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


def _enqueue(queue: RedisStreamJobQueue) -> dict:
    return queue.enqueue(
        {
            "prompt": "Redis Stream integration validation",
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        }
    )


def _read_one(
    queue: RedisStreamJobQueue,
    consumer_name: str,
):
    messages = queue.read_new(
        consumer_name=consumer_name,
        count=1,
        block_ms=0,
    )
    assert len(messages) == 1
    return messages[0]


def _pending(queue: RedisStreamJobQueue):
    return queue._client.xpending_range(
        queue.stream_key,
        queue.consumer_group,
        "-",
        "+",
        10,
    )


def test_enqueue_consume_complete_and_cleanup(queue):
    accepted = _enqueue(queue)

    queued = queue.get_job(accepted["job_id"])
    assert queued is not None
    assert queued["status"] == "queued"
    assert queued["attempt_count"] == 0

    message = _read_one(queue, "worker-a")
    lease = queue.mark_running(
        message=message,
        worker_name="worker-a",
    )

    assert lease is not None

    running = queue.get_job(accepted["job_id"])
    assert running is not None
    assert running["status"] == "running"
    assert running["worker"] == "worker-a"
    assert running["attempt_count"] == 1
    assert "delivery_token" in running

    completed = queue.complete(
        lease=lease,
        result={
            "response": "completed",
            "backend": "mock",
        },
    )

    assert completed is True

    final_state = queue.get_job(accepted["job_id"])
    assert final_state is not None
    assert final_state["status"] == "succeeded"
    assert final_state["worker"] == "worker-a"
    assert final_state["result"]["response"] == "completed"
    assert "delivery_token" not in final_state
    assert _pending(queue) == []
    assert queue._client.xlen(queue.stream_key) == 0


def test_worker_failure_is_persisted_and_acknowledged(queue):
    accepted = _enqueue(queue)
    message = _read_one(queue, "worker-a")

    lease = queue.mark_running(
        message=message,
        worker_name="worker-a",
    )
    assert lease is not None

    failed = queue.fail(
        lease=lease,
        error_type="backend_timeout",
        error_message="upstream timed out",
    )

    assert failed is True

    final_state = queue.get_job(accepted["job_id"])
    assert final_state is not None
    assert final_state["status"] == "failed"
    assert final_state["worker"] == "worker-a"
    assert final_state["error_type"] == "backend_timeout"
    assert final_state["error_message"] == "upstream timed out"
    assert "result" not in final_state
    assert "delivery_token" not in final_state
    assert _pending(queue) == []
    assert queue._client.xlen(queue.stream_key) == 0


def test_reclaimed_job_rejects_stale_worker_and_accepts_new_owner(queue):
    accepted = _enqueue(queue)

    message_a = _read_one(queue, "worker-a")
    lease_a = queue.mark_running(
        message=message_a,
        worker_name="worker-a",
    )
    assert lease_a is not None

    next_start_id, reclaimed = queue.reclaim_idle(
        consumer_name="worker-b",
        min_idle_time_ms=0,
        start_id="0-0",
        count=1,
    )

    assert next_start_id == "0-0"
    assert len(reclaimed) == 1
    assert reclaimed[0].stream_id == message_a.stream_id
    assert reclaimed[0].reclaimed is True

    stale_mark_running = queue.mark_running(
        message=message_a,
        worker_name="worker-a",
    )
    assert stale_mark_running is None

    stale_complete = queue.complete(
        lease=lease_a,
        result={"response": "stale-worker-result"},
    )
    assert stale_complete is False

    lease_b = queue.mark_running(
        message=reclaimed[0],
        worker_name="worker-b",
    )
    assert lease_b is not None

    current_complete = queue.complete(
        lease=lease_b,
        result={"response": "accepted-worker-b-result"},
    )
    assert current_complete is True

    final_state = queue.get_job(accepted["job_id"])
    assert final_state is not None
    assert final_state["status"] == "succeeded"
    assert final_state["worker"] == "worker-b"
    assert final_state["attempt_count"] == 2
    assert final_state["result"]["response"] == "accepted-worker-b-result"
    assert "delivery_token" not in final_state
    assert _pending(queue) == []
    assert queue._client.xlen(queue.stream_key) == 0
