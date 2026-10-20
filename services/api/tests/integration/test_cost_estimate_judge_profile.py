"""Cost estimate for judges an extension package sizes itself.

``llm_judge_feedback`` (extended) sends a long French prompt per exam type
that only the package can render, and writes several pages of Markdown back.
The estimate used to count only case + answer and 15 % of the project's
generation ``max_tokens`` as output, about 5x under the billed cost of a real
run (5.3k input, 3.2k output tokens per copy). A package now registers a
judge cost profile (``judge_cost_profiles``); without one, a judge's output
follows its own ``metric_parameters.max_tokens``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import tiktoken

import judge_cost_profiles
from models import LLMModel  # noqa: F401  (registers the table)
from project_models import Annotation, Project, Task
from services import token_estimation
from services.token_estimation import (
    JUDGE_FIXED_OVERHEAD_TOKENS,
    JUDGE_OUTPUT_UTILIZATION,
)
from tests.integration.test_cost_estimate_branches import (
    _as_user,
    _per_model,
    _post,
    _seed_model,
    _seed_user,
)

JUDGE = "gpt-5.4-mini"
METRIC = "llm_judge_feedback"
ENC = tiktoken.get_encoding("o200k_base")

PROMPT_FILE = "Tu corriges la copie rubrique par rubrique et relèves chaque erreur. " * 250
SUJET = "La Cour de cassation, dans un arrêt du 3 mai 2000, a jugé que le vendeur. " * 20
COPIE = "En l'espèce, la question posée à la Cour était de savoir si le silence. " * 80
EXPECTED_OUTPUT = 3500
SYSTEM_OVERHEAD = 120


def _tokens(text: str) -> int:
    return len(ENC.encode(text))


@pytest.fixture(autouse=True)
def _clean_profiles():
    token_estimation._CACHE.clear()
    yield
    judge_cost_profiles.unregister_judge_cost_profile(METRIC)
    token_estimation._CACHE.clear()


async def _seed_feedback_exam(db, owner, *, max_tokens=16000):
    project = Project(
        id=str(uuid.uuid4()),
        title="feedback-estimate",
        label_config="<View></View>",
        label_config_version="v1",
        created_by=owner.id,
        is_published=True,
        is_private=False,
    )
    params = {
        "judges": [{"judge_model_id": JUDGE, "runs": 1}],
        "exam_type": "fr-commentaire-arret",
        "judge_model": JUDGE,
    }
    if max_tokens:
        params["max_tokens"] = max_tokens
    project.evaluation_config = {
        "evaluation_configs": [
            {
                "id": "feedback",
                "metric": METRIC,
                "enabled": True,
                "prediction_fields": ["human:copie"],
                "reference_fields": [],
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
        data={"sachverhalt": SUJET},
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(task)
    await db.flush()
    db.add(Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        completed_by=owner.id,
        result=[{"from_name": "copie", "to_name": "text", "type": "textarea", "value": {"text": [COPIE]}}],
        was_cancelled=False,
        created_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    return project


def _feedback_profile(calls):
    """Stand-in for extended's profiler: the package's prompt file with the
    case and the copy filled in, its system prompt and the expected answer."""

    def profile(task_data, prediction, metric_parameters):
        calls.append((task_data, prediction, metric_parameters))
        return {
            "prompt": PROMPT_FILE + task_data["sachverhalt"] + prediction,
            "overhead_tokens": SYSTEM_OVERHEAD,
            "output_tokens": EXPECTED_OUTPUT,
        }

    return profile


async def _estimate(client, db, actor, project):
    pid = project.id
    await db.commit()
    with _as_user(actor):
        resp = await _post(client, project_id=pid, mode="evaluation", judge_models=[JUDGE])
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRegisteredJudgeProfile:
    @pytest.mark.asyncio
    async def test_profile_sizes_prompt_overhead_and_output(self, async_test_client, async_test_db):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE, input_cost=1.0, output_cost=5.0)
        project = await _seed_feedback_exam(async_test_db, actor)
        calls = []
        judge_cost_profiles.register_judge_cost_profile(METRIC, _feedback_profile(calls))

        body = await _estimate(async_test_client, async_test_db, actor, project)

        # The profiler saw the task data, the sampled copy and the config.
        assert len(calls) == 1
        task_data, prediction, params = calls[0]
        assert task_data["sachverhalt"] == SUJET
        assert prediction == COPIE
        assert params["exam_type"] == "fr-commentaire-arret"

        expected_input = _tokens(PROMPT_FILE + SUJET + COPIE) + SYSTEM_OVERHEAD
        assert body["token_estimate"]["input_mean"] == pytest.approx(expected_input, abs=1)
        assert body["token_estimate"]["output_estimate"] == pytest.approx(EXPECTED_OUTPUT)
        assert body["input_basis"] == "rendered_judge_prompt"
        assert body["output_basis"] == "judge_profile"
        assert "extension package" in body["note"]

        row = _per_model(body, JUDGE)
        per_call = expected_input / 1000 * 0.001 + EXPECTED_OUTPUT / 1000 * 0.005
        assert row["per_call_usd"] == pytest.approx(per_call, rel=0.01)

    @pytest.mark.asyncio
    async def test_profile_defaults_overhead_and_output(self, async_test_client, async_test_db):
        """A profile that gives only the prompt keeps the platform defaults:
        the fixed judge overhead and 15 % of the config's max_tokens."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project = await _seed_feedback_exam(async_test_db, actor, max_tokens=16000)
        judge_cost_profiles.register_judge_cost_profile(
            METRIC, lambda data, pred, params: {"prompt": PROMPT_FILE + pred}
        )

        body = await _estimate(async_test_client, async_test_db, actor, project)

        assert body["token_estimate"]["input_mean"] == pytest.approx(
            _tokens(PROMPT_FILE + COPIE) + JUDGE_FIXED_OVERHEAD_TOKENS, abs=1
        )
        assert body["token_estimate"]["output_estimate"] == pytest.approx(16000 * JUDGE_OUTPUT_UTILIZATION)
        assert body["output_basis"] == "judge_profile"

    @pytest.mark.asyncio
    async def test_failing_profile_falls_back_to_generic_sizing(self, async_test_client, async_test_db):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project = await _seed_feedback_exam(async_test_db, actor)

        def broken(data, pred, params):
            raise KeyError("exam_type")

        judge_cost_profiles.register_judge_cost_profile(METRIC, broken)

        body = await _estimate(async_test_client, async_test_db, actor, project)

        assert body["output_basis"] == "utilization"
        assert body["token_estimate"]["input_mean"] == pytest.approx(
            _tokens(SUJET + "\n\n" + COPIE) + JUDGE_FIXED_OVERHEAD_TOKENS, abs=2
        )


class TestUnprofiledJudgeOutputFollowsConfigMaxTokens:
    @pytest.mark.asyncio
    async def test_output_is_share_of_config_max_tokens(self, async_test_client, async_test_db):
        """Without a profile the judge's own max_tokens (what the worker sends)
        sizes the output, not the project's generation default (4000)."""
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project = await _seed_feedback_exam(async_test_db, actor, max_tokens=16000)

        body = await _estimate(async_test_client, async_test_db, actor, project)

        assert body["output_basis"] == "utilization"
        assert body["token_estimate"]["output_estimate"] == pytest.approx(2400)

    @pytest.mark.asyncio
    async def test_without_config_max_tokens_the_project_budget_applies(
        self, async_test_client, async_test_db
    ):
        actor = await _seed_user(async_test_db)
        await _seed_model(async_test_db, JUDGE)
        project = await _seed_feedback_exam(async_test_db, actor, max_tokens=None)

        body = await _estimate(async_test_client, async_test_db, actor, project)

        assert body["token_estimate"]["output_estimate"] == pytest.approx(4000 * JUDGE_OUTPUT_UTILIZATION)
