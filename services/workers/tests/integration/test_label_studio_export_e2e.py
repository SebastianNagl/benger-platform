"""The Label Studio export generator runs in the worker image.

Regression for audit finding A3: ``stream_export_label_studio`` imported its
span converter from ``routers.projects.import_export``, a module that exists
only in the API image. The worker's export task dispatches every format
through ``select_export_generator``, so every Label Studio export job failed
with ModuleNotFoundError. This test drives the real generator against the
worker test database, where ``routers`` is not importable either.
"""

import importlib.util
import json

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.database]


def test_routers_package_is_absent_in_worker_env():
    # The point of this module: the worker env has no API routers package. If
    # this ever starts passing because routers became importable, the
    # regression below no longer proves anything.
    assert importlib.util.find_spec("routers") is None


def test_select_export_generator_label_studio_streams_spans(
    db_conn, make_user, make_project, make_task, make_annotation,
):
    from export_stream import select_export_generator

    user = make_user()
    project = make_project(created_by=user.id, title="LS Export Project")
    task = make_task(project.id, {"text": "Der Kläger verlangt Schadensersatz."},
                     created_by=user.id)
    make_annotation(
        project.id,
        task.id,
        user.id,
        [
            {
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 4, "end": 10, "text": "Kläger",
                         "labels": ["Partei"]},
                        {"id": "s2", "start": 20, "end": 34, "text": "Schadensersatz",
                         "labels": ["Anspruch"]},
                    ]
                },
            },
            {"from_name": "answer", "to_name": "text", "type": "choices",
             "value": {"choices": ["Ja"]}},
        ],
    )

    payload = "".join(select_export_generator(db_conn, project, "label_studio"))
    exported = json.loads(payload)

    assert len(exported) == 1
    ls_task = exported[0]
    assert ls_task["data"] == {"text": "Der Kläger verlangt Schadensersatz."}
    assert ls_task["project"] == project.id
    (annotation,) = ls_task["annotations"]
    results = annotation["result"]
    # The span result is flattened into one Label Studio result per span;
    # the choices result passes through unchanged.
    assert [r["id"] for r in results[:2]] == ["s1", "s2"]
    assert results[0]["value"] == {
        "start": 4, "end": 10, "text": "Kläger", "labels": ["Partei"],
    }
    assert results[1]["value"]["labels"] == ["Anspruch"]
    assert results[2]["type"] == "choices"
    assert results[2]["value"] == {"choices": ["Ja"]}
