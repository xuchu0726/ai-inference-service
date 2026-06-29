from app.job_worker import JobWorker
from app.redis_stream_jobs import JobLease, JobMessage


def _message(
    stream_id: str,
    *,
    prompt: str = "worker validation",
    reclaimed: bool = False,
) -> JobMessage:
    return JobMessage(
        stream_id=stream_id,
        job_id=f"job-{stream_id}",
        payload={
            "prompt": prompt,
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        },
        created_at_ms=1,
        reclaimed=reclaimed,
    )


class FakeQueue:
    def __init__(
        self,
        *,
        reclaimed_messages=None,
        new_messages=None,
        stale_stream_ids=None,
    ) -> None:
        self.reclaimed_messages = list(reclaimed_messages or [])
        self.new_messages = list(new_messages or [])
        self.stale_stream_ids = set(stale_stream_ids or [])

        self.ensure_calls = 0
        self.reclaim_calls = []
        self.read_calls = []
        self.complete_calls = []
        self.fail_calls = []

    def ensure_consumer_group(self):
        self.ensure_calls += 1

    def reclaim_idle(self, **kwargs):
        self.reclaim_calls.append(kwargs)
        return "0-0", list(self.reclaimed_messages)

    def read_new(self, **kwargs):
        self.read_calls.append(kwargs)
        count = kwargs["count"]
        return list(self.new_messages[:count])

    def mark_running(self, *, message, worker_name):
        if message.stream_id in self.stale_stream_ids:
            return None

        return JobLease(
            message=message,
            worker_name=worker_name,
            delivery_token=f"token-{message.stream_id}",
        )

    def complete(self, *, lease, result):
        self.complete_calls.append((lease, dict(result)))
        return True

    def fail(self, *, lease, error_type, error_message):
        self.fail_calls.append(
            (lease, error_type, error_message)
        )
        return True


def _worker(queue, generate_text, *, batch_size=2):
    return JobWorker(
        queue=queue,
        consumer_name="worker-test",
        generate_text=generate_text,
        batch_size=batch_size,
        block_ms=1000,
        reclaim_idle_ms=60_000,
    )


def test_worker_processes_new_job_successfully():
    message = _message("1-0")
    queue = FakeQueue(new_messages=[message])
    calls = []

    def generate_text(**kwargs):
        calls.append(kwargs)
        return {"response": "ok", "backend": "mock"}

    result = _worker(queue, generate_text).process_once()

    assert result.reclaimed == 0
    assert result.received_new == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.skipped == 0

    assert queue.ensure_calls == 1
    assert calls == [
        {
            "prompt": "worker validation",
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        }
    ]
    assert queue.complete_calls[0][1]["response"] == "ok"
    assert queue.fail_calls == []


def test_worker_records_generation_failure():
    message = _message("2-0")
    queue = FakeQueue(new_messages=[message])

    def generate_text(**kwargs):
        raise RuntimeError("mock upstream failed")

    result = _worker(queue, generate_text).process_once()

    assert result.succeeded == 0
    assert result.failed == 1
    assert result.skipped == 0
    assert queue.complete_calls == []

    _, error_type, error_message = queue.fail_calls[0]
    assert error_type == "RuntimeError"
    assert error_message == "mock upstream failed"


def test_worker_processes_reclaimed_before_new_jobs():
    reclaimed = _message("3-0", reclaimed=True)
    new = _message("4-0")

    queue = FakeQueue(
        reclaimed_messages=[reclaimed],
        new_messages=[new],
    )

    def generate_text(**kwargs):
        return {"response": kwargs["prompt"]}

    result = _worker(
        queue,
        generate_text,
        batch_size=2,
    ).process_once()

    assert result.reclaimed == 1
    assert result.received_new == 1
    assert result.succeeded == 2
    assert queue.read_calls[0]["block_ms"] == 0

    completed_stream_ids = [
        lease.message.stream_id
        for lease, _result in queue.complete_calls
    ]
    assert completed_stream_ids == ["3-0", "4-0"]


def test_worker_skips_message_after_ownership_is_lost():
    message = _message("5-0")
    queue = FakeQueue(
        new_messages=[message],
        stale_stream_ids={"5-0"},
    )

    calls = []

    def generate_text(**kwargs):
        calls.append(kwargs)
        return {"response": "unexpected"}

    result = _worker(queue, generate_text).process_once()

    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert calls == []
    assert queue.complete_calls == []
    assert queue.fail_calls == []
