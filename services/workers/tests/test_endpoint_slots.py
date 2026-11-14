"""Concurrency limit per custom model endpoint (generation/endpoint_slots.py).

A generation run queues every job at once. Without a limit, each job a worker
picks up sends its request to the custom endpoint and waits in the
provider's queue on the clock of its own Celery time limit; a 581-job run
against a server handling 2 requests at a time lost 9 jobs to
``SoftTimeLimitExceeded``. These tests run against the real test Redis.
"""

import os
import threading
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
import redis
from celery.exceptions import Retry

import tasks
from generation import endpoint_slots
from generation.endpoint_slots import EndpointBusy, acquire, acquire_for_job, slot_key


@pytest.fixture
def client():
    url = os.environ.get("REDIS_URL") or "redis://test-redis:6379"
    c = redis.Redis.from_url(f"{url}/3", decode_responses=True)
    try:
        c.ping()
    except redis.exceptions.ConnectionError as e:  # pragma: no cover
        pytest.fail(f"the workers suite needs the test Redis: {e}")
    yield c


@pytest.fixture
def model_id(client):
    mid = f"custom-{uuid.uuid4()}"
    yield mid
    client.delete(slot_key(mid))


@pytest.fixture(autouse=True)
def _no_limit_cache():
    endpoint_slots._limit_cache.clear()
    yield
    endpoint_slots._limit_cache.clear()


class TestAcquire:
    def test_at_most_limit_slots_are_held(self, client, model_id):
        first = acquire(client, model_id, "job-1", limit=2, lease_seconds=60)
        acquire(client, model_id, "job-2", limit=2, lease_seconds=60)

        with pytest.raises(EndpointBusy) as busy:
            acquire(client, model_id, "job-3", limit=2, lease_seconds=60)
        low, high = endpoint_slots.RETRY_DELAY_RANGE
        assert low <= busy.value.retry_in <= high

        first.release()
        acquire(client, model_id, "job-3", limit=2, lease_seconds=60)
        assert client.zcard(slot_key(model_id)) == 2

    def test_a_redelivered_job_takes_its_own_slot_back(self, client, model_id):
        acquire(client, model_id, "job-1", limit=1, lease_seconds=60)
        # Same task id again (acks_late redelivery after a worker died).
        acquire(client, model_id, "job-1", limit=1, lease_seconds=60)
        assert client.zcard(slot_key(model_id)) == 1

    def test_an_expired_lease_frees_its_slot(self, client, model_id):
        acquire(client, model_id, "killed-job", limit=1, lease_seconds=0.2)
        with pytest.raises(EndpointBusy):
            acquire(client, model_id, "job-2", limit=1, lease_seconds=60)
        time.sleep(0.3)
        acquire(client, model_id, "job-2", limit=1, lease_seconds=60)

    def test_release_is_idempotent(self, client, model_id):
        slot = acquire(client, model_id, "job-1", limit=1, lease_seconds=60)
        slot.release()
        slot.release()
        assert client.zcard(slot_key(model_id)) == 0

    def test_models_have_separate_slots(self, client, model_id):
        other = f"custom-{uuid.uuid4()}"
        try:
            acquire(client, model_id, "job-1", limit=1, lease_seconds=60)
            acquire(client, other, "job-2", limit=1, lease_seconds=60)
        finally:
            client.delete(slot_key(other))


class TestLimits:
    @pytest.mark.parametrize(
        "value,expected",
        [(None, 2), (0, 2), (-3, 2), (True, 2), ("4", 2), (1, 1), (16, 16)],
    )
    def test_clamp(self, value, expected):
        assert endpoint_slots.clamp_limit(value) == expected

    def test_official_models_are_not_limited(self, client):
        factory = MagicMock()
        slot = acquire_for_job(
            "gpt-4o",
            "job-1",
            redis_client_factory=lambda: client,
            session_factory=factory,
            lease_seconds=60,
        )
        assert slot is None
        factory.assert_not_called()

    def test_without_redis_the_job_runs_unlimited(self, model_id):
        with patch.object(endpoint_slots, "model_limit", return_value=1):
            slot = acquire_for_job(
                model_id,
                "job-1",
                redis_client_factory=lambda: None,
                session_factory=MagicMock(),
                lease_seconds=60,
            )
        assert slot is None

    def test_the_row_limit_is_read_from_the_database(self, model_id):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = (5,)
        assert endpoint_slots.model_limit(model_id, lambda: db) == 5
        db.close.assert_called_once()
        # Cached: a second lookup does not read the row again.
        assert endpoint_slots.model_limit(model_id, lambda: db) == 5
        assert db.query.call_count == 1

    def test_a_missing_row_gets_the_default(self, model_id):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        limit = endpoint_slots.model_limit(model_id, lambda: db)
        assert limit == endpoint_slots.DEFAULT_MAX_CONCURRENT_REQUESTS


class TestGenerationTask:
    """``tasks.generate_response`` takes a slot before it calls the model."""

    def _run(self, client, model_id, limit, impl):
        with patch.object(tasks, "_get_progress_redis", return_value=client), patch.object(
            endpoint_slots, "model_limit", return_value=limit
        ), patch.object(tasks, "generate_response_impl", side_effect=impl):
            return tasks.generate_response.run(
                "gen-1", "proj-1", "task-1", model_id, None, False, None, 0
            )

    def test_a_job_with_a_free_slot_runs_and_frees_it(self, client, model_id):
        seen = {}

        def impl(*args):
            seen["held"] = client.zcard(slot_key(model_id))
            return {"status": "success"}

        assert self._run(client, model_id, 2, impl) == {"status": "success"}
        assert seen["held"] == 1
        assert client.zcard(slot_key(model_id)) == 0

    def test_the_slot_is_freed_when_the_job_fails(self, client, model_id):
        def impl(*args):
            raise RuntimeError("provider down")

        with pytest.raises(RuntimeError):
            self._run(client, model_id, 2, impl)
        assert client.zcard(slot_key(model_id)) == 0

    def test_a_busy_endpoint_requeues_the_job_without_calling_the_model(
        self, client, model_id
    ):
        acquire(client, model_id, "running-1", limit=2, lease_seconds=60)
        acquire(client, model_id, "running-2", limit=2, lease_seconds=60)
        impl = MagicMock()

        with patch.object(
            tasks.generate_response, "retry", side_effect=Retry("busy")
        ) as retry:
            with pytest.raises(Retry):
                self._run(client, model_id, 2, impl)

        impl.assert_not_called()
        kwargs = retry.call_args.kwargs
        low, high = endpoint_slots.RETRY_DELAY_RANGE
        assert low <= kwargs["countdown"] <= high
        assert client.zcard(slot_key(model_id)) == 2

    def test_a_long_wait_never_exhausts_the_retry_budget(self, client, model_id):
        """Through Celery's own retry, a job that already waited for many
        turns is requeued again rather than given up (Celery's default budget
        is 3 retries, after which retry() raises MaxRetriesExceededError)."""
        acquire(client, model_id, "running-1", limit=1, lease_seconds=60)
        impl = MagicMock()

        tasks.generate_response.push_request(
            id="waiting-job", retries=50, called_directly=False, is_eager=True
        )
        try:
            with pytest.raises(Retry):
                self._run(client, model_id, 1, impl)
        finally:
            tasks.generate_response.pop_request()

        impl.assert_not_called()

    def test_concurrent_jobs_never_exceed_the_limit(self, client, model_id):
        """Eight jobs against an endpoint limited to 2: at most 2 requests are
        in flight at any time, and every job runs once its turn comes."""
        lock = threading.Lock()
        state = {"in_flight": 0, "peak": 0, "done": 0}

        def impl(*args):
            with lock:
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
            time.sleep(0.05)
            with lock:
                state["in_flight"] -= 1
                state["done"] += 1
            return {"status": "success"}

        def job(i):
            # What Celery does with a Retry: run the job again later.
            while True:
                try:
                    tasks.generate_response.run(
                        f"gen-{i}", "p", "t", model_id, None, False, None, 0
                    )
                    return
                except Retry:
                    time.sleep(0.01)

        with patch.object(tasks, "_get_progress_redis", return_value=client), patch.object(
            endpoint_slots, "model_limit", return_value=2
        ), patch.object(tasks, "generate_response_impl", side_effect=impl), patch.object(
            tasks.generate_response, "retry", side_effect=Retry("busy")
        ):
            threads = [threading.Thread(target=job, args=(i,)) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert state["done"] == 8
        assert state["peak"] <= 2
