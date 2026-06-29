from app.config import (
    JOB_QUEUE_CONSUMER_GROUP,
    JOB_QUEUE_JOB_TTL_SECONDS,
    JOB_QUEUE_KEY_PREFIX,
    JOB_QUEUE_REDIS_URL,
    JOB_QUEUE_SOCKET_TIMEOUT_SECONDS,
)
from app.redis_stream_jobs import RedisStreamJobQueue


def build_job_queue(
    *,
    socket_timeout_seconds: float | None = None,
) -> RedisStreamJobQueue:
    timeout_seconds = (
        JOB_QUEUE_SOCKET_TIMEOUT_SECONDS
        if socket_timeout_seconds is None
        else socket_timeout_seconds
    )

    return RedisStreamJobQueue(
        redis_url=JOB_QUEUE_REDIS_URL,
        key_prefix=JOB_QUEUE_KEY_PREFIX,
        consumer_group=JOB_QUEUE_CONSUMER_GROUP,
        socket_timeout_seconds=timeout_seconds,
        job_ttl_seconds=JOB_QUEUE_JOB_TTL_SECONDS,
    )


job_queue = build_job_queue()
