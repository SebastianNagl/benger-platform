"""
Locust load test for 100-user annotation event with Falllösung LLM judge evaluation.

Simulates the burst pattern: ~100 users submitting annotations within ~1 minute,
each triggering an immediate LLM evaluation, then fetching the next task.

Usage:
    # Against test environment (make test-start first)
    locust -f scripts/load_test_annotation.py --host=http://localhost:8002

    # Against staging
    locust -f scripts/load_test_annotation.py --host=https://api.staging.what-a-benger.net

    # Headless burst simulation (100 users, ramp up over 10s, run 5 min)
    locust -f scripts/load_test_annotation.py --host=http://localhost:8002 \
        --users 100 --spawn-rate 10 --run-time 5m --headless

    # Web UI mode (default): open http://localhost:8089 to control the test
    locust -f scripts/load_test_annotation.py --host=http://localhost:8002

Prerequisites:
    - pip install locust (already in services/api/requirements.txt)
    - A project with tasks assigned to test users and immediate evaluation enabled
    - Set environment variables:
        LOAD_TEST_PROJECT_ID  - project UUID to test against
        LOAD_TEST_USER_PREFIX - username prefix (default: "annotator")
        LOAD_TEST_PASSWORD    - shared password for test users (default: "admin")
        LOAD_TEST_NUM_USERS   - number of pre-created test users (default: 100)
"""

import json
import os
import time

from locust import HttpUser, between, events, task


# Configuration from environment
PROJECT_ID = os.getenv("LOAD_TEST_PROJECT_ID", "")
USER_PREFIX = os.getenv("LOAD_TEST_USER_PREFIX", "annotator")
PASSWORD = os.getenv("LOAD_TEST_PASSWORD", "admin")
NUM_USERS = int(os.getenv("LOAD_TEST_NUM_USERS", "100"))

# Track user index for unique logins
_user_counter = 0


def _next_user_index():
    global _user_counter
    idx = _user_counter % NUM_USERS
    _user_counter += 1
    return idx


# Sample annotation payload (~25KB, simulating 5 pages of legal text)
SAMPLE_ANNOTATION_TEXT = (
    "Der Kläger begehrt die Feststellung der Unwirksamkeit der Kündigung "
    "seines Arbeitsverhältnisses. Er war seit dem 01.01.2020 bei der Beklagten "
    "als Sachbearbeiter beschäftigt. Mit Schreiben vom 15.03.2025 kündigte die "
    "Beklagte das Arbeitsverhältnis zum 30.06.2025. Der Kläger hält die Kündigung "
    "für sozial ungerechtfertigt und macht geltend, dass die Beklagte die "
    "Sozialauswahl fehlerhaft durchgeführt habe. "
) * 50  # ~25KB


class AnnotatorUser(HttpUser):
    """Simulates a single annotator during the event."""

    # Steady state: 1-3 minutes between annotations (realistic pacing)
    # For burst testing, override via Locust UI or use BurstAnnotator below
    wait_time = between(60, 180)

    def on_start(self):
        """Login and discover assigned tasks."""
        self.user_index = _next_user_index()
        self.username = f"{USER_PREFIX}{self.user_index + 1}"
        self.access_token = None
        self.project_id = PROJECT_ID
        self.current_task = None
        self.tasks_completed = 0

        self._login()
        if self.access_token and self.project_id:
            self._get_next_task()

    def _login(self):
        """Authenticate and store access token."""
        with self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": PASSWORD},
            name="/api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get("access_token")
                resp.success()
            else:
                resp.failure(f"Login failed for {self.username}: {resp.status_code}")

    def _headers(self):
        """Auth headers for API requests."""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    def _get_next_task(self):
        """Fetch the next assigned task."""
        if not self.project_id:
            return

        with self.client.get(
            f"/api/projects/{self.project_id}/next",
            headers=self._headers(),
            name="/api/projects/[id]/next",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.current_task = data.get("task")
                if self.current_task is None:
                    resp.failure("No more tasks available")
                else:
                    resp.success()
            else:
                resp.failure(f"Get next task failed: {resp.status_code}")
                self.current_task = None

    @task(10)
    def annotate_and_evaluate(self):
        """Submit annotation -> trigger immediate eval -> poll status -> get next task."""
        if not self.access_token or not self.current_task:
            self._login()
            self._get_next_task()
            if not self.current_task:
                return

        task_id = self.current_task["id"]

        # 1. Submit annotation
        annotation_id = self._submit_annotation(task_id)
        if not annotation_id:
            return

        # 2. Trigger immediate evaluation
        evaluation_id = self._trigger_immediate_eval(task_id, annotation_id)

        # 3. Poll evaluation status (if async)
        if evaluation_id:
            self._poll_eval_status(task_id, evaluation_id)

        # 4. Get next task
        self.tasks_completed += 1
        self._get_next_task()

    def _submit_annotation(self, task_id):
        """POST annotation with ~25KB legal text payload."""
        payload = {
            "result": [
                {
                    "from_name": "response",
                    "to_name": "text",
                    "type": "textarea",
                    "value": {"text": [SAMPLE_ANNOTATION_TEXT]},
                }
            ],
            "was_cancelled": False,
            "lead_time": 120.0,
            "active_duration_ms": 110000,
            "focused_duration_ms": 100000,
            "tab_switches": 0,
        }

        with self.client.post(
            f"/api/projects/tasks/{task_id}/annotations",
            json=payload,
            headers=self._headers(),
            name="/api/projects/tasks/[id]/annotations",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                resp.success()
                return data.get("id")
            else:
                resp.failure(f"Annotation submit failed: {resp.status_code}")
                return None

    def _trigger_immediate_eval(self, task_id, annotation_id):
        """POST immediate evaluation dispatch."""
        with self.client.post(
            f"/api/evaluations/projects/{self.project_id}/tasks/{task_id}/immediate",
            json={"annotation_id": annotation_id},
            headers=self._headers(),
            name="/api/evaluations/projects/[id]/tasks/[id]/immediate",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                resp.success()
                return data.get("evaluation_id")
            else:
                resp.failure(f"Immediate eval trigger failed: {resp.status_code}")
                return None

    def _poll_eval_status(self, task_id, evaluation_id, max_polls=30, interval=2.0):
        """Poll evaluation status until completed or timeout."""
        for i in range(max_polls):
            time.sleep(interval)
            with self.client.get(
                f"/api/evaluations/projects/{self.project_id}/tasks/{task_id}/immediate/{evaluation_id}/status",
                headers=self._headers(),
                name="/api/evaluations/.../immediate/[id]/status",
                catch_response=True,
            ) as resp:
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "")
                    if status == "completed":
                        resp.success()
                        return
                    elif status == "failed":
                        resp.failure(f"Evaluation failed: {data.get('error', 'unknown')}")
                        return
                    else:
                        resp.success()  # Still pending, keep polling
                else:
                    resp.failure(f"Eval status poll failed: {resp.status_code}")
                    return

    @task(1)
    def browse_project(self):
        """Background activity: browse project details."""
        if not self.access_token or not self.project_id:
            return

        self.client.get(
            f"/api/projects/{self.project_id}/my-tasks?page=1&page_size=10",
            headers=self._headers(),
            name="/api/projects/[id]/my-tasks",
        )


class BurstAnnotator(AnnotatorUser):
    """
    Burst mode: minimal wait between annotations to simulate the event burst pattern.
    Use this class to test peak load (100 submissions in ~1 minute).

    Usage:
        locust -f scripts/load_test_annotation.py --host=http://localhost:8002 \
            --users 100 --spawn-rate 50 BurstAnnotator
    """

    wait_time = between(0.5, 2)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    if not PROJECT_ID:
        print("\n" + "=" * 70)
        print("WARNING: LOAD_TEST_PROJECT_ID not set!")
        print("Set it to a project UUID with tasks and immediate evaluation enabled.")
        print("Example: export LOAD_TEST_PROJECT_ID='your-project-uuid'")
        print("=" * 70 + "\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Log slow requests for debugging."""
    if response_time > 5000 and "status" not in name:
        print(f"SLOW: {request_type} {name} took {response_time:.0f}ms")
