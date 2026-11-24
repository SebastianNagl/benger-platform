"""One score per evaluation method, in the results grid, the cell modal and
the per-submission results file.

The case these tests rebuild: an answer graded on submit (bare field name,
one config of a two-config method), then re-evaluated by a teacher (a batch
run with the composite ``config|pred|ref`` key, both configs, and one row per
reference field of a judge that reads its references itself). Before, the
grid and the modal kept every row because their field names differed; now
each cell has one current score, and a method group (the extension hook's
answer) shows the official config per answer. A config that grades once per
reference field keeps one current score per reference field.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.integration.test_eval_results_branches import (
    BASE,
    _add_judge_run,
    _as_user,
    _make_annotation,
    _make_eval_run,
    _make_generation,
    _make_org,
    _make_owner,
    _make_task_evaluation,
    _setup_project,
)

CFG_A = "llm_judge_custom-model-a"
CFG_B = "llm_judge_custom-model-b"
KORREKTUR = "korrektur_custom-k1"


GROUPS = {"notenpunkte": {"config_ids": [CFG_A, CFG_B], "label": "Notenpunkte"}}


def _grouped(**answer):
    """The extension hook groups CFG_A and CFG_B as one method."""
    return patch(
        "extensions.evaluation_method_selection", return_value={"groups": GROUPS, **answer}
    )


def _configs():
    return {
        "evaluation_configs": [
            {
                "id": CFG_A, "metric": "llm_judge_custom", "display_name": "Notenpunkte (A)",
                "prediction_fields": ["__all_model__", "human:loesung"],
                "reference_fields": ["task.musterloesung", "task.bewertungsbogen"],
                # The judge reads both reference fields itself.
                "metric_parameters": {
                    "custom_prompt_template": "{musterloesung} {bewertungsbogen} {prediction}"
                },
                "enabled": True,
            },
            {
                "id": CFG_B, "metric": "llm_judge_custom", "display_name": "Notenpunkte (B)",
                "prediction_fields": ["human:loesung"],
                "reference_fields": ["task.musterloesung"],
                "enabled": True,
            },
            {
                "id": KORREKTUR, "metric": "korrektur_custom", "display_name": "Korrektur",
                "prediction_fields": ["human:loesung"], "reference_fields": [],
                "enabled": True,
            },
        ]
    }


async def _seed(db):
    """A submission graded on submit (CFG_B, under the legacy model-side
    label), then by a forced batch re-run (both configs, two reference
    fields for CFG_A), and a second student graded on submit only."""
    owner = await _make_owner(db)
    org = await _make_org(db)
    project, tasks = await _setup_project(db, owner, org, num_tasks=1)
    project.evaluation_config = _configs()
    task = tasks[0]
    student = await _make_owner(db, name="Student One", is_superadmin=False)
    other = await _make_owner(db, name="Student Two", is_superadmin=False)
    ann = await _make_annotation(db, task, project, student.id)
    ann_other = await _make_annotation(db, task, project, other.id)

    t0 = datetime.now(timezone.utc) - timedelta(hours=3)
    immediate = await _make_eval_run(db, project, model_id="immediate")
    on_submit = await _make_task_evaluation(
        db, immediate, task, annotation=ann, field_name="__all_model__",
        evaluation_config_id=CFG_B, metrics={"llm_judge_custom": 0.75},
        created_at=t0,
    )
    on_submit_other = await _make_task_evaluation(
        db, immediate, task, annotation=ann_other, field_name="human:loesung",
        evaluation_config_id=CFG_B,
        metrics={"llm_judge_custom": 0.5, "llm_judge_custom_grade_points": 9},
        created_at=t0,
    )

    batch = await _make_eval_run(db, project, model_id="annotator:Student One")
    jr = [batch._test_judge_run, await _add_judge_run(db, batch, 1), await _add_judge_run(db, batch, 2)]
    t1 = t0 + timedelta(minutes=20)
    b_row = await _make_task_evaluation(
        db, batch, task, annotation=ann, judge_run=jr[0],
        field_name=f"{CFG_B}|human:loesung|task.musterloesung", evaluation_config_id=CFG_B,
        metrics={"llm_judge_custom": 0.82, "llm_judge_custom_grade_points": 14}, created_at=t1,
    )
    a_ref1 = await _make_task_evaluation(
        db, batch, task, annotation=ann, judge_run=jr[1],
        field_name=f"{CFG_A}|human:loesung|task.musterloesung", evaluation_config_id=CFG_A,
        metrics={"llm_judge_custom": 0.96}, created_at=t1,
    )
    a_ref2 = await _make_task_evaluation(
        db, batch, task, annotation=ann, judge_run=jr[2],
        field_name=f"{CFG_A}|human:loesung|task.bewertungsbogen", evaluation_config_id=CFG_A,
        metrics={"llm_judge_custom": 0.95}, created_at=t1 + timedelta(seconds=1),
    )
    await db.commit()
    return {
        "owner": owner, "project": project, "task": task, "student": student,
        "other": other, "ann": ann, "ann_other": ann_other, "on_submit": on_submit, "b_row": b_row,
        "a_ref1": a_ref1, "a_ref2": a_ref2, "on_submit_other": on_submit_other,
    }


def _grid_url(project_id, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{BASE}/projects/{project_id}/results/by-task-model?{qs}"


@pytest.mark.integration
class TestGridOneScorePerConfig:
    @pytest.mark.asyncio
    async def test_on_submit_and_rerun_collapse(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        with _as_user(s["owner"]):
            resp = await async_test_client.get(
                _grid_url(s["project"].id, metric="llm_judge_custom", evaluation_config_id=CFG_B)
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == s["task"].id)
        # The re-run is the current score; the on-submit row (written under
        # the legacy model-side label) is history of the same cell.
        assert cell["scores"]["annotator:Student One"] == pytest.approx(0.82)
        assert cell["scores"]["annotator:Student Two"] == pytest.approx(0.5)
        # One score per cell feeds the column average.
        assert body["summary"]["annotator:Student One"]["count"] == 1

    @pytest.mark.asyncio
    async def test_reference_fan_out_counts_once(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        with _as_user(s["owner"]):
            resp = await async_test_client.get(
                _grid_url(s["project"].id, metric="llm_judge_custom", evaluation_config_id=CFG_A)
            )
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == s["task"].id)
        # The two reference-field rows are one cell; the newer one is current.
        assert cell["scores"] == {"annotator:Student One": pytest.approx(0.95)}
        assert body["summary"]["annotator:Student One"]["count"] == 1

    @pytest.mark.asyncio
    async def test_method_group_shows_the_official_config_per_answer(
        self, async_test_client, async_test_db
    ):
        s = await _seed(async_test_db)
        with _grouped(), _as_user(s["owner"]):
            default = await async_test_client.get(
                _grid_url(s["project"].id, metric="llm_judge_custom", method_group="notenpunkte")
            )
        assert default.status_code == 200, default.text
        cell = next(t for t in default.json()["tasks"] if t["task_id"] == s["task"].id)
        # Without an official answer the group's first config (CFG_A) is.
        # CFG_A never graded Student Two, so CFG_B's score stands in.
        assert cell["scores"] == {
            "annotator:Student One": pytest.approx(0.95),
            "annotator:Student Two": pytest.approx(0.5),
        }

        # The extension makes CFG_B official.
        with _grouped(official={"notenpunkte": CFG_B}):
            with _as_user(s["owner"]):
                hooked = await async_test_client.get(
                    _grid_url(s["project"].id, metric="llm_judge_custom", method_group="notenpunkte")
                )
        cell = next(t for t in hooked.json()["tasks"] if t["task_id"] == s["task"].id)
        assert cell["scores"] == {
            "annotator:Student One": pytest.approx(0.82),
            "annotator:Student Two": pytest.approx(0.5),
        }

        per_user = {s["student"].id: {"notenpunkte": CFG_A}}
        with _grouped(official_by_user=per_user):
            with _as_user(s["owner"]):
                mixed = await async_test_client.get(
                    _grid_url(s["project"].id, metric="llm_judge_custom", method_group="notenpunkte")
                )
        cell = next(t for t in mixed.json()["tasks"] if t["task_id"] == s["task"].id)
        # Student One: CFG_A by the hook; Student Two: the default (CFG_A),
        # which has not graded them, so CFG_B's score stands in.
        assert cell["scores"] == {
            "annotator:Student One": pytest.approx(0.95),
            "annotator:Student Two": pytest.approx(0.5),
        }

    @pytest.mark.asyncio
    async def test_unknown_method_group_is_404(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        with _as_user(s["owner"]):
            resp = await async_test_client.get(
                _grid_url(s["project"].id, method_group="nope")
            )
        assert resp.status_code == 404


@pytest.mark.integration
class TestMethodsEndpoint:
    @pytest.mark.asyncio
    async def test_lists_groups_and_research_configs(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        with _grouped(), _as_user(s["owner"]):
            resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/methods"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["groups"] == [
            {
                "key": "notenpunkte",
                "method_key": "group:notenpunkte",
                "label": "Notenpunkte",
                "config_ids": [CFG_A, CFG_B],
                "default_official_config_id": CFG_A,
            }
        ]
        assert body["research_config_ids"] == [CFG_B]

    @pytest.mark.asyncio
    async def test_no_groups(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        with _as_user(s["owner"]):
            resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/methods"
            )
        assert resp.json()["groups"] == [] and resp.json()["research_config_ids"] == []

    @pytest.mark.asyncio
    async def test_a_failing_hook_groups_nothing(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        import extensions

        def boom(*_a, **_k):
            raise RuntimeError("hook down")

        with patch.object(extensions, "_single_hook", return_value=boom):
            with _as_user(s["owner"]):
                resp = await async_test_client.get(
                    f"{BASE}/projects/{s['project'].id}/results/methods"
                )
        assert resp.status_code == 200
        assert resp.json()["groups"] == [] and resp.json()["research_config_ids"] == []


@pytest.mark.integration
class TestCellModal:
    @pytest.mark.asyncio
    async def test_history_off_one_current_row_per_config(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        url = f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student One"
        with _as_user(s["owner"]):
            off = await async_test_client.get(url + "&include_history=false")
            on = await async_test_client.get(url + "&include_history=true")
            scoped = await async_test_client.get(
                url + f"&include_history=false&evaluation_config_ids={CFG_B}"
            )
        assert off.status_code == 200, off.text
        assert {r["id"] for r in off.json()["results"]} == {s["b_row"].id, s["a_ref2"].id}
        flags = {r["id"]: r["is_current"] for r in on.json()["results"]}
        assert flags == {
            s["on_submit"].id: False,
            s["b_row"].id: True,
            s["a_ref1"].id: False,
            s["a_ref2"].id: True,
        }
        assert [r["id"] for r in scoped.json()["results"]] == [s["b_row"].id]

    @pytest.mark.asyncio
    async def test_method_group_hides_research_rows(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        url = (
            f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student One"
            "&include_history=false&method_group=notenpunkte"
        )
        with _grouped(), _as_user(s["owner"]):
            hidden = await async_test_client.get(url + "&include_research=false")
            shown = await async_test_client.get(url)
        assert [r["id"] for r in hidden.json()["results"]] == [s["a_ref2"].id]
        rows = {r["id"]: r["is_official"] for r in shown.json()["results"]}
        assert rows == {s["a_ref2"].id: True, s["b_row"].id: False}


@pytest.mark.integration
class TestOfficialConfigWithoutAScore:
    """The official choice is per account, so the official config can lack a
    score for an answer another config of the group graded: that score
    stands in (evaluation_methods.teacher_current_rows)."""

    @pytest.mark.asyncio
    async def test_modal_shows_and_labels_the_stand_in(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        url = (
            f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student Two"
            "&include_history=false"
        )
        with _grouped(), _as_user(s["owner"]):
            default = await async_test_client.get(url + "&include_research=false")
            scoped = await async_test_client.get(
                url + "&method_group=notenpunkte&include_research=false"
            )
            research = await async_test_client.get(url)
        assert default.status_code == 200, default.text
        for resp in (default, scoped, research):
            (row,) = resp.json()["results"]
            assert row["id"] == s["on_submit_other"].id
            assert row["is_official"] is True
            assert row["stands_in_for_config_id"] == CFG_A
            assert row["evaluation_config_label"] == "Notenpunkte (B)"

    @pytest.mark.asyncio
    async def test_modal_rows_of_the_official_config_carry_no_stand_in(
        self, async_test_client, async_test_db
    ):
        s = await _seed(async_test_db)
        url = (
            f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student One"
            "&include_history=false&method_group=notenpunkte&include_research=false"
        )
        with _grouped(), _as_user(s["owner"]):
            resp = await async_test_client.get(url)
        (row,) = resp.json()["results"]
        assert row["id"] == s["a_ref2"].id
        assert row["stands_in_for_config_id"] is None

    @pytest.mark.asyncio
    async def test_modal_scoped_to_one_config_keeps_the_official_choice(
        self, async_test_client, async_test_db
    ):
        """Scoping the modal to the research config does not turn it into a
        stand-in: the official config has a score for this answer."""
        s = await _seed(async_test_db)
        url = (
            f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student One"
            f"&include_history=false&evaluation_config_ids={CFG_B}"
        )
        with _grouped(), _as_user(s["owner"]):
            research = await async_test_client.get(url)
            default = await async_test_client.get(url + "&include_research=false")
        (row,) = research.json()["results"]
        assert row["id"] == s["b_row"].id
        assert row["is_official"] is False
        assert row["stands_in_for_config_id"] is None
        assert default.json()["results"] == []

    @pytest.mark.asyncio
    async def test_no_config_of_the_group_has_a_score(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        # Student Two's only grading failed: the cell stays empty.
        s["on_submit_other"].metrics = {"error": "judge timeout"}
        await async_test_db.commit()
        with _grouped(), _as_user(s["owner"]):
            grid = await async_test_client.get(
                _grid_url(s["project"].id, metric="llm_judge_custom", method_group="notenpunkte")
            )
            csv_resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/by-submission"
            )
        cell = next(t for t in grid.json()["tasks"] if t["task_id"] == s["task"].id)
        assert "annotator:Student Two" not in cell["scores"]
        rows = list(csv.reader(io.StringIO(csv_resp.text)))
        assert "Notenpunkte (graded by)" not in rows[0]
        other = next(r for r in rows[1:] if r[2] == s["other"].id)
        assert other[5] == ""

    @pytest.mark.asyncio
    async def test_grid_generation_falls_back_to_another_config(
        self, async_test_client, async_test_db
    ):
        s = await _seed(async_test_db)
        gen, _ = await _make_generation(async_test_db, s["task"], model_id="gpt-4")
        run = await _make_eval_run(async_test_db, s["project"], model_id="gpt-4")
        await _make_task_evaluation(
            async_test_db, run, s["task"], generation=gen,
            field_name=f"{CFG_B}|model:loesung|task.musterloesung", evaluation_config_id=CFG_B,
            metrics={"llm_judge_custom": 0.6},
        )
        await async_test_db.commit()
        with _grouped(), _as_user(s["owner"]):
            resp = await async_test_client.get(
                _grid_url(s["project"].id, metric="llm_judge_custom", method_group="notenpunkte")
            )
        assert resp.status_code == 200, resp.text
        cell = next(t for t in resp.json()["tasks"] if t["task_id"] == s["task"].id)
        # Generations use the default official config (CFG_A), which did not
        # grade this one.
        assert cell["scores"]["gpt-4"] == pytest.approx(0.6)


@pytest.mark.integration
class TestResultsBySubmission:
    @pytest.mark.asyncio
    async def test_csv_one_row_per_submission_one_column_per_method(
        self, async_test_client, async_test_db
    ):
        s = await _seed(async_test_db)
        with _grouped(), _as_user(s["owner"]):
            resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/by-submission"
            )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(resp.text)))
        header, body = rows[0], rows[1:]
        # The group is one column; the research config has none; the human
        # Korrektur has a column that stays empty until it happened.
        # Student Two was graded only by CFG_B, which stands in for the
        # official CFG_A: the column names the config behind each score.
        assert header == [
            "task_id", "task", "submitter_id", "submitter", "submitted_at",
            "Notenpunkte", "Notenpunkte (grade points)", "Notenpunkte (graded by)",
            "Korrektur",
        ]
        by_submitter = {r[2]: r for r in body}
        assert set(by_submitter) == {s["student"].id, s["other"].id}
        assert by_submitter[s["student"].id][5:] == ["0.95", "", "Notenpunkte (A)", ""]
        assert by_submitter[s["other"].id][5:] == ["0.5", "9", "Notenpunkte (B)", ""]
        # A file never names anyone.
        assert "Student" not in resp.text

    @pytest.mark.asyncio
    async def test_research_columns_and_grade_points(self, async_test_client, async_test_db):
        s = await _seed(async_test_db)
        with _grouped(), _as_user(s["owner"]):
            resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/by-submission?include_research=true"
            )
        rows = list(csv.reader(io.StringIO(resp.text)))
        header = rows[0]
        assert header[5:] == [
            "Notenpunkte (A)", "Notenpunkte (B)", "Notenpunkte (B) (grade points)", "Korrektur",
        ]
        by_submitter = {r[2]: r for r in rows[1:]}
        assert by_submitter[s["student"].id][6:8] == ["0.82", "14"]
        assert by_submitter[s["other"].id][6:8] == ["0.5", "9"]


CFG_PER_REF = "llm_judge_custom-per-ref"


async def _seed_per_reference(db):
    """A judge whose prompt names only ``{ground_truth}`` grades the answer
    once against each of its two reference fields: one batch run writes two
    different gradings (0.9 and 0.4) at the same moment."""
    owner = await _make_owner(db)
    org = await _make_org(db)
    project, tasks = await _setup_project(db, owner, org, num_tasks=1)
    project.evaluation_config = {
        "evaluation_configs": [
            {
                "id": CFG_PER_REF, "metric": "llm_judge_custom", "display_name": "Judge",
                "prediction_fields": ["human:loesung"],
                "reference_fields": ["task.musterloesung", "task.bewertungsbogen"],
                "metric_parameters": {"custom_prompt_template": "{ground_truth} {prediction}"},
                "enabled": True,
            }
        ]
    }
    task = tasks[0]
    student = await _make_owner(db, name="Student One", is_superadmin=False)
    ann = await _make_annotation(db, task, project, student.id)
    batch = await _make_eval_run(db, project, model_id="annotator:Student One")
    graded_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    rows = {}
    for ref, score in (("task.musterloesung", 0.9), ("task.bewertungsbogen", 0.4)):
        rows[ref] = await _make_task_evaluation(
            db, batch, task, annotation=ann,
            field_name=f"{CFG_PER_REF}|human:loesung|{ref}", evaluation_config_id=CFG_PER_REF,
            metrics={"llm_judge_custom": score}, created_at=graded_at,
        )
    await db.commit()
    return {"owner": owner, "project": project, "task": task, "student": student, "rows": rows}


@pytest.mark.integration
class TestConfigGradedPerReference:
    @pytest.mark.asyncio
    async def test_modal_shows_both_gradings_as_current(self, async_test_client, async_test_db):
        s = await _seed_per_reference(async_test_db)
        url = f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student One"
        with _as_user(s["owner"]):
            off = await async_test_client.get(url + "&include_history=false")
            on = await async_test_client.get(url + "&include_history=true")
        assert off.status_code == 200, off.text
        expected = {row.id for row in s["rows"].values()}
        assert {r["id"] for r in off.json()["results"]} == expected
        assert {r["id"]: r["is_current"] for r in on.json()["results"]} == {
            row_id: True for row_id in expected
        }

    @pytest.mark.asyncio
    async def test_results_file_has_a_column_per_reference_field(
        self, async_test_client, async_test_db
    ):
        s = await _seed_per_reference(async_test_db)
        with _as_user(s["owner"]):
            resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/by-submission"
            )
        assert resp.status_code == 200, resp.text
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0][5:] == ["Judge (task.musterloesung)", "Judge (task.bewertungsbogen)"]
        assert rows[1][5:] == ["0.9", "0.4"]


@pytest.mark.integration
class TestStandInWithHistory:
    """The grid and the cell modal with history show the rows of the config
    that supplies the cell: for Student Two that is CFG_B, standing in for
    the official CFG_A, which never graded them."""

    @pytest.mark.asyncio
    async def test_grid_and_modal_agree_on_the_stand_in_cell(
        self, async_test_client, async_test_db
    ):
        s = await _seed(async_test_db)
        earlier = await _make_eval_run(async_test_db, s["project"], model_id="earlier")
        older = await _make_task_evaluation(
            async_test_db, earlier, s["task"], annotation=s["ann_other"],
            field_name=f"{CFG_B}|human:loesung|task.musterloesung", evaluation_config_id=CFG_B,
            metrics={"llm_judge_custom": 0.3},
            created_at=s["on_submit_other"].created_at - timedelta(hours=1),
        )
        await async_test_db.commit()
        modal_url = (
            f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student Two"
            "&include_history=true&method_group=notenpunkte&include_research=false"
        )
        with _grouped(), _as_user(s["owner"]):
            grid = await async_test_client.get(
                _grid_url(
                    s["project"].id, metric="llm_judge_custom", method_group="notenpunkte",
                    include_history="true",
                )
            )
            modal = await async_test_client.get(modal_url)
        assert grid.status_code == 200, grid.text
        assert modal.status_code == 200, modal.text
        cell = next(t for t in grid.json()["tasks"] if t["task_id"] == s["task"].id)
        # Student Two: the mean of CFG_B's two gradings (0.5 and 0.3).
        # Student One: CFG_A's two gradings (0.96 and 0.95), as before.
        assert cell["scores"] == {
            "annotator:Student One": pytest.approx(0.955),
            "annotator:Student Two": pytest.approx(0.4),
        }
        rows = {r["id"]: r for r in modal.json()["results"]}
        assert set(rows) == {s["on_submit_other"].id, older.id}
        assert {r["stands_in_for_config_id"] for r in rows.values()} == {CFG_A}
        assert all(r["is_official"] for r in rows.values())
        scores = [r["metrics"]["llm_judge_custom"] for r in rows.values()]
        assert sum(scores) / len(scores) == pytest.approx(
            cell["scores"]["annotator:Student Two"]
        )


CFG_REF_A = "llm_judge_custom-ref-a"
CFG_REF_B = "llm_judge_custom-ref-b"
REFS = ("task.musterloesung", "task.bewertungsbogen")


async def _seed_grouped_per_reference(db):
    """Two configs of one method that both grade once per reference field.
    The official CFG_REF_A scored the answer against musterloesung (0.9) and
    failed against bewertungsbogen; CFG_REF_B scored both (0.3 and 0.7)."""
    owner = await _make_owner(db)
    org = await _make_org(db)
    project, tasks = await _setup_project(db, owner, org, num_tasks=1)
    project.evaluation_config = {
        "evaluation_configs": [
            {
                "id": cid, "metric": "llm_judge_custom", "display_name": name,
                "prediction_fields": ["human:loesung"], "reference_fields": list(REFS),
                "metric_parameters": {"custom_prompt_template": "{ground_truth} {prediction}"},
                "enabled": True,
            }
            for cid, name in ((CFG_REF_A, "Judge A"), (CFG_REF_B, "Judge B"))
        ]
    }
    task = tasks[0]
    student = await _make_owner(db, name="Student One", is_superadmin=False)
    ann = await _make_annotation(db, task, project, student.id)
    batch = await _make_eval_run(db, project, model_id="annotator:Student One")
    graded_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    rows = {}
    for cid, metrics in (
        (CFG_REF_A, ({"llm_judge_custom": 0.9}, {"error": "judge timeout"})),
        (CFG_REF_B, ({"llm_judge_custom": 0.3}, {"llm_judge_custom": 0.7})),
    ):
        for ref, m in zip(REFS, metrics):
            rows[(cid, ref)] = await _make_task_evaluation(
                db, batch, task, annotation=ann,
                field_name=f"{cid}|human:loesung|{ref}", evaluation_config_id=cid,
                metrics=m, created_at=graded_at,
            )
    await db.commit()
    return {"owner": owner, "project": project, "task": task, "rows": rows}


@pytest.mark.integration
class TestStandInPerReferenceField:
    @pytest.mark.asyncio
    async def test_csv_takes_the_stand_in_only_for_the_failed_reference_field(
        self, async_test_client, async_test_db
    ):
        s = await _seed_grouped_per_reference(async_test_db)
        groups = {"judge": {"config_ids": [CFG_REF_A, CFG_REF_B], "label": "Judge"}}
        with patch(
            "extensions.evaluation_method_selection", return_value={"groups": groups}
        ), _as_user(s["owner"]):
            resp = await async_test_client.get(
                f"{BASE}/projects/{s['project'].id}/results/by-submission"
            )
            modal = await async_test_client.get(
                f"{BASE}/sample-result?task_id={s['task'].id}&model_id=annotator:Student One"
                "&include_history=false&method_group=judge&include_research=false"
            )
        assert resp.status_code == 200, resp.text
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0][5:] == [
            "Judge (task.musterloesung)",
            "Judge (task.bewertungsbogen)",
            "Judge (task.bewertungsbogen) (graded by)",
        ]
        assert rows[1][5:] == ["0.9", "0.7", "Judge B"]
        shown = {r["id"]: r["stands_in_for_config_id"] for r in modal.json()["results"]}
        assert shown == {
            s["rows"][(CFG_REF_A, REFS[0])].id: None,
            s["rows"][(CFG_REF_B, REFS[1])].id: CFG_REF_A,
        }
