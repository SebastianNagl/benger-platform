"""Cost estimate for LLM-judge evaluations sizes the rendered judge prompt.

A Bewertungsbogen judge call carries the template, the case context, the
Musterlösung, the rendered sheet, the graded answer (an annotation for
human-side configs) and the system/schema overhead. The legacy estimate
tokenized only the flattened task data and came out ~20 % under the billed
input on prod. These tests seed a rubric exam with distinct, sizeable parts
and assert every part is counted, plus the structured estimate fields the
UI phrases in the reader's language.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import tiktoken

from models import LLMModel  # noqa: F401  (registers the table)
from project_models import Annotation, Project, Task, TaskRubric
from rubric_structure import rubric_prompt_text
from services.token_estimation import (
    ESTIMATE_ACCURACY_PERCENT,
    JUDGE_FIXED_OVERHEAD_TOKENS,
    JUDGE_OUTPUT_FIXED_TOKENS,
    JUDGE_OUTPUT_TOKENS_PER_STEP,
    JUDGE_SCHEMA_TOKENS_PER_STEP,
)
from tests.integration.test_cost_estimate_branches import (
    _as_user,
    _post,
    _seed_model,
    _seed_user,
)

JUDGE = "gpt-5-mini"
ENC = tiktoken.get_encoding("o200k_base")

TEMPLATE_INSTRUCTIONS = "Bewerte die Bearbeitung Schritt für Schritt anhand des Bogens. " * 40
SACHVERHALT = "Die Polizei spricht gegen H einen Platzverweis aus. " * 60
MUSTERLOESUNG = "Die Klage ist zulässig und begründet, weil die Maßnahme rechtswidrig war. " * 150
ANSWER = "Ich prüfe zunächst die Zulässigkeit der Fortsetzungsfeststellungsklage. " * 90
STALE_SHEET = "alt"


def _tokens(text: str) -> int:
    return len(ENC.encode(text))


def _criteria():
    return {
        f"s{i:02d}_schritt": {
            "name": f"Schritt {i}",
            "description": "Prüfung der Rechtmäßigkeit mit ausführlicher Begründung. " * 10,
            "rubric": "",
            "max_score": 2.0,
        }
        for i in range(1, 6)
    }


async def _seed_exam(db, owner, *, with_answer: bool = True, template: bool = True):
    project = Project(
        id=str(uuid.uuid4()),
        title="judge-prompt-estimate",
        label_config="<View></View>",
        label_config_version="v1",
        created_by=owner.id,
        is_published=True,
        is_private=False,
    )
    params = {"judges": [{"judge_model_id": JUDGE, "runs": 1}]}
    if template:
        params["custom_prompt_template"] = (
            TEMPLATE_INSTRUCTIONS
            + "\n<sachverhalt>{context}</sachverhalt>\n<musterloesung>{{ground_truth}}</musterloesung>"
            + "\n<bewertungsbogen>{bewertungsbogen}</bewertungsbogen>\n<bearbeitung>{prediction}</bearbeitung>"
        )
    project.evaluation_config = {
        "evaluation_configs": [
            {
                "id": "rubric-free",
                "metric": "llm_judge_rubric",
                "enabled": True,
                "prediction_fields": ["human:loesung"],
                "reference_fields": ["task.musterloesung"],
                "metric_parameters": params,
            }
        ]
    }
    db.add(project)
    await db.flush()
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=1,
        data={"sachverhalt": SACHVERHALT, "musterloesung": MUSTERLOESUNG, "bewertungsbogen": STALE_SHEET},
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(task)
    await db.flush()
    rubric = TaskRubric(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        title="Bogen",
        criteria=_criteria(),
        total_points=10,
        source="human",
        status="active",
    )
    db.add(rubric)
    if with_answer:
        db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=project.id,
            completed_by=owner.id,
            result=[{"from_name": "loesung", "to_name": "text", "type": "textarea", "value": {"text": [ANSWER]}}],
            was_cancelled=False,
            created_at=datetime.now(timezone.utc),
        ))
    await db.flush()
    return project, rubric


class TestRubricJudgePromptEstimate:
    @pytest.mark.asyncio
    async def test_counts_template_context_reference_sheet_answer_and_overhead(
        self, async_test_client, async_test_db
    ):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project, rubric = await _seed_exam(async_test_db, actor)
        sheet = rubric_prompt_text(rubric, include_grade_scale=False)
        pid = project.id
        await async_test_db.commit()

        with _as_user(actor):
            resp = await _post(async_test_client, project_id=pid, mode="evaluation", judge_models=[JUDGE])
        assert resp.status_code == 200, resp.text
        body = resp.json()

        parts = (
            _tokens(TEMPLATE_INSTRUCTIONS)
            + _tokens(SACHVERHALT)
            + _tokens(MUSTERLOESUNG)
            + _tokens(sheet)
            + _tokens(ANSWER)
        )
        overhead = JUDGE_FIXED_OVERHEAD_TOKENS + 5 * JUDGE_SCHEMA_TOKENS_PER_STEP
        mean = body["token_estimate"]["input_mean"]
        assert parts + overhead <= mean <= parts + overhead + 150
        # The stale task-data copy of the sheet is replaced by the rubric row.
        assert _tokens(sheet) > 100

        assert body["input_basis"] == "rendered_judge_prompt"
        assert body["accuracy_percent"] == ESTIMATE_ACCURACY_PERCENT
        assert body["encoding"] == "o200k_base" == body["token_estimate"]["encoding"]
        assert body["output_utilization_percent"] == 15
        # A Bewertungsbogen judge writes a score, reason and quote per step;
        # its output grows with the sheet instead of following max_tokens.
        assert body["output_basis"] == "judge_steps"
        assert body["token_estimate"]["output_estimate"] == pytest.approx(
            JUDGE_OUTPUT_FIXED_TOKENS + 5 * JUDGE_OUTPUT_TOKENS_PER_STEP
        )
        assert body["sample_size"] == 1
        assert body["missing_only"] is False
        assert "rendered judge prompt" in body["note"]
        assert "per scored step" in body["note"]

    @pytest.mark.asyncio
    async def test_without_template_the_parts_are_still_counted(
        self, async_test_client, async_test_db
    ):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project, rubric = await _seed_exam(async_test_db, actor, template=False)
        sheet = rubric_prompt_text(rubric, include_grade_scale=False)
        pid = project.id
        await async_test_db.commit()

        with _as_user(actor):
            resp = await _post(async_test_client, project_id=pid, mode="evaluation", judge_models=[JUDGE])
        assert resp.status_code == 200, resp.text
        mean = resp.json()["token_estimate"]["input_mean"]
        parts = _tokens(SACHVERHALT) + _tokens(MUSTERLOESUNG) + _tokens(sheet) + _tokens(ANSWER)
        assert mean >= parts + JUDGE_FIXED_OVERHEAD_TOKENS

    @pytest.mark.asyncio
    async def test_unanswered_task_borrows_an_answer_from_another_task(
        self, async_test_client, async_test_db
    ):
        """A task nobody answered yet is sized with another task's answer, so
        an exam with few submissions is not estimated as if answers were empty."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project, rubric = await _seed_exam(async_test_db, actor)
        second = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=2,
            data={"sachverhalt": SACHVERHALT, "musterloesung": MUSTERLOESUNG},
            created_by=actor.id,
            updated_by=actor.id,
        )
        async_test_db.add(second)
        await async_test_db.flush()
        async_test_db.add(TaskRubric(
            id=str(uuid.uuid4()), task_id=second.id, project_id=project.id, title="Bogen",
            criteria=_criteria(), total_points=10, source="human", status="active",
        ))
        sheet = rubric_prompt_text(rubric, include_grade_scale=False)
        pid = project.id
        await async_test_db.commit()

        with _as_user(actor):
            resp = await _post(async_test_client, project_id=pid, mode="evaluation", judge_models=[JUDGE])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["sample_size"] == 2
        parts = (
            _tokens(TEMPLATE_INSTRUCTIONS) + _tokens(SACHVERHALT) + _tokens(MUSTERLOESUNG)
            + _tokens(sheet) + _tokens(ANSWER)
        )
        # Both samples carry the answer: the p95 (the smaller sample is still
        # near the mean) stays above the parts sum.
        assert body["token_estimate"]["input_p95"] >= parts
        assert body["token_estimate"]["input_mean"] >= parts

    @pytest.mark.asyncio
    async def test_exam_without_any_answer_is_still_sized(
        self, async_test_client, async_test_db
    ):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project, _rubric = await _seed_exam(async_test_db, actor, with_answer=False)
        pid = project.id
        await async_test_db.commit()

        with _as_user(actor):
            resp = await _post(async_test_client, project_id=pid, mode="evaluation", judge_models=[JUDGE])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        legacy = _tokens("\n".join([SACHVERHALT, MUSTERLOESUNG, STALE_SHEET]))
        assert body["token_estimate"]["input_mean"] > legacy
        assert body["input_basis"] == "rendered_judge_prompt"

    @pytest.mark.asyncio
    async def test_generation_estimate_reports_structured_fields(
        self, async_test_client, async_test_db
    ):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project, _rubric = await _seed_exam(async_test_db, actor)
        pid = project.id
        await async_test_db.commit()

        with _as_user(actor):
            resp = await _post(
                async_test_client, project_id=pid, mode="generation", model_ids=[JUDGE], generation_mode="missing"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["input_basis"] == "task_data"
        assert body["output_utilization_percent"] is None
        assert body["missing_only"] is True
        assert body["per_judge_cells"] is False
