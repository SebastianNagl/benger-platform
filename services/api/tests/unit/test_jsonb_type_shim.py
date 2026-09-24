"""The shared models map JSONB columns to the type the database really has (issue #299).

The models used to pick postgresql.JSONB only when DATABASE_URL was set, but
every deployment sets DATABASE_URI alone, so in dev, staging and prod every
Column(JSONB) silently became generic JSON. The test suite never saw it
because conftest sets DATABASE_URL. The mapping now follows the URL that
database.py resolves, so each case imports the models in a fresh interpreter
with a controlled environment.
"""

import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import select

API_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED_DIR = os.path.normpath(os.path.join(API_DIR, "..", "shared"))

_PROBE = """
import json
import models, project_models, report_models
from sqlalchemy.dialects import postgresql

def kind(col):
    return "JSONB" if isinstance(col.type, postgresql.JSONB) else type(col.type).__name__

print(json.dumps({
    "task_evaluation_metrics": kind(models.TaskEvaluation.metrics),
    "annotation_result": kind(project_models.Annotation.result),
    "report_content": kind(report_models.ProjectReport.content),
    "task_data": kind(project_models.Task.data),
}))
"""


def _mapped_types(**env_overrides):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DATABASE_URL", "DATABASE_URI", "ASYNC_DATABASE_URL")
        and not k.startswith("POSTGRES_")
    }
    env.update(env_overrides)
    env["PYTHONPATH"] = os.pathsep.join([SHARED_DIR, API_DIR])
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


PG_URL = "postgresql://user:pw@db.invalid:5432/benger"


def test_database_uri_alone_maps_real_jsonb():
    """The deployed configuration: only DATABASE_URI is set."""
    types = _mapped_types(DATABASE_URI=PG_URL)
    assert types["task_evaluation_metrics"] == "JSONB"
    assert types["annotation_result"] == "JSONB"
    assert types["report_content"] == "JSONB"


def test_no_url_at_all_maps_real_jsonb():
    """database.py then builds a postgres URL from its defaults; the models follow it."""
    types = _mapped_types()
    assert types["task_evaluation_metrics"] == "JSONB"


def test_sqlite_url_maps_generic_json(tmp_path):
    types = _mapped_types(DATABASE_URL=f"sqlite:///{tmp_path / 'shim.db'}")
    assert types["task_evaluation_metrics"] == "JSON"
    assert types["annotation_result"] == "JSON"
    assert types["report_content"] == "JSON"


def test_task_data_stays_plain_json():
    """tasks.data is json, not jsonb, in the migrated databases (jsonb would
    reorder imported task keys), so the model must not claim JSONB for it."""
    types = _mapped_types(DATABASE_URI=PG_URL)
    assert types["task_data"] == "JSON"


@pytest.mark.integration
def test_has_key_needs_no_cast_on_jsonb_column(test_db):
    """With the real JSONB comparator, has_key runs as-is against Postgres."""
    from models import TaskEvaluation

    stmt = select(TaskEvaluation.id).where(TaskEvaluation.metrics.has_key("__no_such_metric__"))
    assert test_db.execute(stmt).scalars().all() == []
