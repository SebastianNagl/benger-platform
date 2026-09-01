"""Group-scoped org API keys: project_id threading contracts (worker side).

A project attached to an org via an organization GROUP spends that group's
key (shared/org_groups + shared_org_api_key_service.resolve_api_key). The
group is derived from the PROJECT id at key-resolution time, so every leaf
dispatch site must thread ``project_id`` into the AI-service factories — a
site that forgets silently degrades to the org-wide key row, and for an org
whose keys are all group-scoped (the migrated Uni-Saarland shape) that means
"no key configured" and a failed run.

Layer 1: signature + forwarding contracts on the factories.
Layer 2: source contracts pinning each leaf call site's ``project_id=``.
DB-free and fast, mirroring test_evaluation_fanout.py's style.
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch


WORKERS = Path(__file__).resolve().parents[1]
SHARED = WORKERS.parent / "shared"


def _call_block(src: str, needle: str, span: int = 25) -> list[str]:
    """Every ``needle`` call site with its following ``span`` lines."""
    lines = src.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        if needle in line and "def " + needle.rstrip("(") not in line:
            blocks.append("\n".join(lines[i : i + span]))
    return blocks


# ---------------------------------------------------------------------------
# Layer 1: factory signatures + forwarding
# ---------------------------------------------------------------------------


def test_factories_accept_project_id():
    from ai_services.user_aware_ai_service import UserAwareAIService
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user
    from shared_org_api_key_service import OrgApiKeyService

    assert "project_id" in inspect.signature(
        UserAwareAIService.get_ai_service_for_user
    ).parameters
    assert "project_id" in inspect.signature(
        UserAwareAIService.get_ai_service_for_model_row
    ).parameters
    assert "project_id" in inspect.signature(create_llm_judge_for_user).parameters
    assert "project_id" in inspect.signature(
        OrgApiKeyService.resolve_api_key
    ).parameters


def test_create_llm_judge_forwards_project_id():
    from ml_evaluation import llm_judge_evaluator as mod

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no BYOM row

    with patch(
        "ai_services.user_aware_ai_service.user_aware_ai_service.get_ai_service_for_user"
    ) as factory:
        factory.return_value = MagicMock()
        mod.create_llm_judge_for_user(
            db=db,
            user_id="u1",
            provider="openai",
            judge_model="gpt-5-mini",
            organization_id="org1",
            project_id="proj-42",
        )
        assert factory.call_args.kwargs.get("project_id") == "proj-42"


def test_resolver_prefers_group_key_then_org_wide():
    """Pure forwarding contract on the worker twin: with a group on the
    project's attachment, the group-scoped row is tried before the
    org-wide row (integration coverage lives in the api suite)."""
    from shared_org_api_key_service import OrgApiKeyService

    svc = OrgApiKeyService(encryption_service=MagicMock())
    svc._get_org_setting_require_private_keys = MagicMock(return_value=False)
    svc._user_may_spend_org_key = MagicMock(return_value=True)
    calls = []

    def fake_get(db, org_id, provider, group_id=None):
        calls.append(group_id)
        return None if group_id else "ORG_WIDE_KEY"

    svc._get_org_api_key = fake_get

    with patch("org_groups.resolve_project_group_for_org", return_value="grp-1"):
        got = svc.resolve_api_key(
            MagicMock(), "u1", "org1", "openai", project_id="p1"
        )
    assert calls == ["grp-1", None], "group row must be tried first, then org-wide"
    assert got == "ORG_WIDE_KEY"

    # Without a project id: org-wide row only, no group lookup.
    calls.clear()
    got = svc.resolve_api_key(MagicMock(), "u1", "org1", "openai")
    assert calls == [None]
    assert got == "ORG_WIDE_KEY"


# ---------------------------------------------------------------------------
# Layer 2: leaf call sites thread project_id
# ---------------------------------------------------------------------------


def test_cell_evaluator_threads_project_id():
    src = (WORKERS / "evaluation" / "cell_evaluator.py").read_text()
    blocks = _call_block(src, "_reconstruct_judge_evaluators_for_cell(")
    # Both cell impls (generation + annotation) rebuild judges with the
    # project in scope.
    call_blocks = [b for b in blocks if "configs_for_cell=" in b]
    assert len(call_blocks) >= 2
    for block in call_blocks:
        assert "project_id=project_id" in block, block


def test_tasks_judge_sites_thread_project_id():
    src = (WORKERS / "tasks.py").read_text()
    blocks = _call_block(src, "create_llm_judge_for_user(")
    call_blocks = [b for b in blocks if "db=db" in b]
    assert len(call_blocks) >= 2, "expected orchestrator + sub-task judge init sites"
    for block in call_blocks:
        assert "project_id=" in block, block


def test_single_sample_judge_threads_project_id():
    src = (WORKERS / "evaluation" / "judge_evaluator.py").read_text()
    (block,) = _call_block(src, "llm_judge = create_llm_judge_for_user(")
    assert "project_id=project_id" in block


def test_generation_service_threads_project_id():
    src = (WORKERS / "generation" / "llm_generation_service.py").read_text()
    blocks = _call_block(src, "get_ai_service_for_model_row(", span=6)
    assert blocks, "generation dispatch site missing"
    for block in blocks:
        assert "project_id=" in block, block


def test_generation_metadata_stamps_project():
    """Billing forensics: response_metadata carries the invocation project
    (alongside route/org) so a group-key spend is traceable."""
    src = (WORKERS / "generation" / "llm_generation_service.py").read_text()
    assert src.count("invocation_project_id") >= 2
