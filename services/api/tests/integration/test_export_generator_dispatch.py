"""Dispatch + fidelity tests for the shared export-generator selector (issue #158).

The async worker export task (`tasks.export_project`) is now the only export
path; it streams `select_export_generator` / `build_json_export_header_fields`
from `export_stream` straight to object storage. These tests lock that
contract: the selector's JSON output is well-formed and complete, every format
dispatches to the right generator, and an unknown format fails loudly rather
than silently producing an empty/wrong artifact.
"""

import json
import uuid

import pytest

from project_models import Annotation, Project, ProjectOrganization, Task
from routers.projects._export_stream import (
    EXPORT_FORMAT_MEDIA_TYPES,
    build_json_export_header_fields,
    select_export_generator,
)


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def populated_project(test_db, test_users, test_org):
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title="Dispatch Export Project",
        description="generator dispatch fixture",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=admin.id,
        )
    )
    test_db.flush()

    tasks = []
    for i in range(3):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Sample #{i}", "category": f"cat_{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()

    for t in tasks:
        test_db.add(
            Annotation(
                id=_uid(),
                task_id=t.id,
                project_id=project.id,
                completed_by=admin.id,
                result=[{
                    "from_name": "answer",
                    "to_name": "text",
                    "type": "choices",
                    "value": {"choices": ["Ja"]},
                }],
                was_cancelled=False,
            )
        )
    test_db.flush()
    test_db.commit()
    return project


@pytest.mark.integration
class TestSelectExportGenerator:
    def test_json_generator_is_complete(self, test_db, populated_project):
        project = populated_project
        # The worker joins these selector chunks and uploads them verbatim, so
        # the generator's JSON must be well-formed and carry the completeness
        # sentinel — there is no synchronous endpoint to compare against anymore.
        joined = "".join(select_export_generator(test_db, project, "json"))
        parsed = json.loads(joined)
        assert parsed["export_complete"] is True
        assert parsed["project"]["id"] == project.id
        assert len(parsed["tasks"]) == 3

    def test_json_generator_reports_progress(self, test_db, populated_project):
        """`progress_cb` is threaded into the json stream and fires per streamed
        task batch with (tasks_streamed, total_tasks). This is what lets the
        async worker persist real incremental progress instead of jumping
        0 -> 100 (the download-progress-bar bug)."""
        project = populated_project
        calls: list = []
        gen = select_export_generator(
            test_db,
            project,
            "json",
            progress_cb=lambda done, total: calls.append((done, total)),
        )
        # Progress fires during iteration, not at construction — drain the stream.
        "".join(gen)

        assert calls, "progress_cb was never called"
        # Total is the project's task count; counts are monotonic non-decreasing
        # and the final call reports every task streamed.
        assert all(total == 3 and 0 <= done <= 3 for done, total in calls)
        assert calls[-1] == (3, 3)
        dones = [done for done, _ in calls]
        assert dones == sorted(dones)

    def test_json_generator_without_progress_cb_skips_count(self, test_db, populated_project):
        """The default (no progress_cb) path must still produce a complete export
        — the count query is only paid for when a caller wants progress."""
        joined = "".join(select_export_generator(test_db, populated_project, "json"))
        parsed = json.loads(joined)
        assert parsed["export_complete"] is True
        assert len(parsed["tasks"]) == 3

    def test_dispatch_csv_and_tsv(self, test_db, populated_project):
        csv_out = "".join(select_export_generator(test_db, populated_project, "csv"))
        tsv_out = "".join(select_export_generator(test_db, populated_project, "tsv"))
        assert csv_out.splitlines()[0].startswith("task_id,")
        assert "\t" in tsv_out.splitlines()[0]
        assert tsv_out.splitlines()[0].startswith("task_id\t")

    def test_dispatch_label_studio_is_json_array(self, test_db, populated_project):
        out = "".join(
            select_export_generator(test_db, populated_project, "label_studio")
        )
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_dispatch_txt(self, test_db, populated_project):
        out = "".join(select_export_generator(test_db, populated_project, "txt"))
        assert out.startswith("Project: Dispatch Export Project")
        assert "Total Tasks: 3" in out

    def test_dispatch_comprehensive_is_json(self, test_db, populated_project):
        out = "".join(
            select_export_generator(test_db, populated_project, "comprehensive")
        )
        parsed = json.loads(out)
        assert isinstance(parsed, dict)

    def test_unknown_format_raises(self, test_db, populated_project):
        with pytest.raises(ValueError):
            # select_export_generator dispatches eagerly, so the ValueError is
            # raised on the call itself, not on first iteration.
            select_export_generator(test_db, populated_project, "bogus")

    def test_header_fields_counts(self, test_db, populated_project):
        header = build_json_export_header_fields(test_db, populated_project)
        proj = header["project"]
        assert proj["id"] == populated_project.id
        assert proj["task_count"] == 3
        assert proj["annotation_count"] == 3
        assert proj["generation_count"] == 0
        assert proj["task_evaluation_count"] == 0
        assert proj["label_config"] == populated_project.label_config

    def test_format_media_type_map_covers_all_dispatch_formats(self):
        for fmt in ("json", "csv", "tsv", "label_studio", "txt", "comprehensive"):
            media_type, ext = EXPORT_FORMAT_MEDIA_TYPES[fmt]
            assert media_type
            assert ext
