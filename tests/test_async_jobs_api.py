from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.redis_stream_jobs import JobQueueUnavailableError


class FakeJobQueue:
    def __init__(self):
        self.enqueued_payloads = []
        self.jobs = {}
        self.enqueue_error = None
        self.get_error = None

    def enqueue(self, payload):
        if self.enqueue_error is not None:
            raise self.enqueue_error

        self.enqueued_payloads.append(dict(payload))
        job = {
            "job_id": "job-123",
            "status": "queued",
            "created_at_ms": 100,
            "updated_at_ms": 100,
            "attempt_count": 0,
        }
        self.jobs[job["job_id"]] = job
        return job

    def get_job(self, job_id):
        if self.get_error is not None:
            raise self.get_error
        return self.jobs.get(job_id)


@pytest.fixture
def client_and_queue(monkeypatch):
    queue = FakeJobQueue()
    monkeypatch.setattr(main_module, "job_queue", queue)

    with TestClient(main_module.app) as client:
        yield client, queue


def test_post_jobs_accepts_valid_request(client_and_queue):
    client, queue = client_and_queue

    response = client.post(
        "/jobs",
        json={
            "prompt": "async admission validation",
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": "job-123",
        "status": "queued",
        "created_at_ms": 100,
    }
    assert queue.enqueued_payloads == [
        {
            "prompt": "async admission validation",
            "max_new_tokens": 8,
            "temperature": 0.0,
            "thinking_budget": None,
        }
    ]


def test_post_jobs_rejects_blank_prompt(client_and_queue):
    client, queue = client_and_queue

    response = client.post("/jobs", json={"prompt": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "prompt must not be empty"
    assert queue.enqueued_payloads == []


def test_post_jobs_returns_503_when_redis_is_unavailable(client_and_queue):
    client, queue = client_and_queue
    queue.enqueue_error = JobQueueUnavailableError("Redis unavailable")

    response = client.post("/jobs", json={"prompt": "queue unavailable"})

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "job_queue_unavailable"


def test_get_jobs_hides_internal_delivery_token(client_and_queue):
    client, queue = client_and_queue
    queue.jobs["job-running"] = {
        "job_id": "job-running",
        "status": "running",
        "created_at_ms": 100,
        "updated_at_ms": 200,
        "attempt_count": 1,
        "worker": "worker-a",
        "delivery_token": "must-not-be-exposed",
    }

    response = client.get("/jobs/job-running")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert "delivery_token" not in response.json()


def test_get_jobs_returns_404_for_missing_job(client_and_queue):
    client, _queue = client_and_queue

    response = client.get("/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "job_not_found"
