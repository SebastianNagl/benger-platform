"""The platform flags ``variant_experiments`` and ``compliance_records``
(core 2.75): registered by the platform, off by default; while off every
route of their features answers 404 ``feature_disabled`` and every changed
behaviour is the one the platform had before. Tests without a
``flags_on`` marker run with both off, as a fresh deployment does; the
real-row tests switch a flag through the admin API.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from feature_flags import registry, service
from feature_flags.registry import COMPLIANCE_RECORDS, REPORT_PAPER, VARIANT_EXPERIMENTS
from feature_flags.scope import flag_scope
from models import FeatureFlag
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import make_project, v1_auth



@pytest.fixture
async def world(async_test_db):
    db = async_test_db
    w = await seed_world(db, group=False)
    w["project"] = await make_project(db, w["admin"].id, org_id=w["org"].id, title="flags")
    await db.commit()
    return w


def _disabled(response, name=VARIANT_EXPERIMENTS):
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == {"code": "feature_disabled", "flag": name}


# --------------------------------------------------------------------------- #
# registry and real rows
# --------------------------------------------------------------------------- #


def test_platform_registers_its_flags_off():
    for name in (VARIANT_EXPERIMENTS, COMPLIANCE_RECORDS, REPORT_PAPER):
        definition = registry.flag(name)
        assert definition is not None
        assert definition.default_state == registry.STATE_OFF
        assert registry.flag_owner(name) == registry.PLATFORM_OWNER
        # Platform flags are coupled to no overlay's master flag.
        assert registry.coupled_master(name) is None


async def test_me_reports_the_flags_off(async_test_client, async_test_db, world):
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await async_test_client.get("/api/feature-flags/me")
    assert r.status_code == 200
    flags = r.json()["flags"]
    assert flags[VARIANT_EXPERIMENTS] is False
    assert flags[COMPLIANCE_RECORDS] is False
    assert flags[REPORT_PAPER] is False


async def test_switching_the_real_row_opens_and_closes_the_routes(
    async_test_client, async_test_db, world
):
    project_id = world["project"].id
    service.reset_registry_sync_state()
    service.invalidate_cache()
    with v1_auth(async_test_db, session_user=world["member"]):
        _disabled(await async_test_client.get("/api/analysis/engine"))
    await service.sync_registry(async_test_db)

    async def set_state(name, state):
        row = (
            await async_test_db.execute(
                FeatureFlag.__table__.select().where(FeatureFlag.name == name)
            )
        ).first()
        assert row is not None
        await async_test_db.execute(
            FeatureFlag.__table__.update().where(FeatureFlag.name == name).values(state=state)
        )
        await async_test_db.commit()
        service.invalidate_cache()

    await set_state(VARIANT_EXPERIMENTS, "everyone")
    with v1_auth(async_test_db, session_user=world["member"]):
        assert (await async_test_client.get("/api/analysis/engine")).status_code == 200
        assert (
            await async_test_client.get(f"/api/projects/{project_id}/variant-designs")
        ).status_code == 200
        # The other flag stays off.
        _disabled(
            await async_test_client.get("/api/compliance/assessments"), COMPLIANCE_RECORDS
        )
    await set_state(VARIANT_EXPERIMENTS, "off")
    with v1_auth(async_test_db, session_user=world["member"]):
        _disabled(await async_test_client.get("/api/analysis/engine"))
    service.invalidate_cache()


async def test_allowlisted_organization_opens_the_routes_for_its_members(
    async_test_client, async_test_db, world
):
    from models import FeatureFlagTarget

    service.reset_registry_sync_state()
    await service.sync_registry(async_test_db)
    await async_test_db.execute(
        FeatureFlag.__table__.update()
        .where(FeatureFlag.name == VARIANT_EXPERIMENTS)
        .values(state="allowlist")
    )
    flag_id = (
        await async_test_db.execute(
            FeatureFlag.__table__.select().where(FeatureFlag.name == VARIANT_EXPERIMENTS)
        )
    ).first().id
    async_test_db.add(
        FeatureFlagTarget(id=str(uuid.uuid4()), flag_id=flag_id, organization_id=world["org"].id)
    )
    await async_test_db.commit()
    service.invalidate_cache()
    try:
        with v1_auth(async_test_db, session_user=world["member"]):
            assert (await async_test_client.get("/api/analysis/engine")).status_code == 200
        with v1_auth(async_test_db, session_user=world["outsider"]):
            _disabled(await async_test_client.get("/api/analysis/engine"))
    finally:
        service.invalidate_cache()


# --------------------------------------------------------------------------- #
# every new route answers feature_disabled while its flag is off
# --------------------------------------------------------------------------- #


async def test_new_routes_are_closed_while_off(async_test_client, async_test_db, world):
    pid = world["project"].id
    with v1_auth(async_test_db, session_user=world["admin"]):
        for path in (
            "/api/analysis/engine",
            f"/api/projects/{pid}/analysis-runs",
            f"/api/projects/{pid}/analysis-lookups",
            f"/api/analysis-runs/{uuid.uuid4()}",
            f"/api/projects/{pid}/coding-projects",
            f"/api/projects/{pid}/coding",
            f"/api/projects/{pid}/code-validations",
            f"/api/code-validations/{uuid.uuid4()}",
            f"/api/projects/{pid}/variant-designs",
            f"/api/projects/{pid}/variant-designs/swap",
            f"/api/projects/{pid}/variant-designs/swap/units",
            f"/api/projects/{pid}/variant-designs/swap/units/u1",
            f"/api/projects/{pid}/label-config/label-studio",
            f"/api/projects/{pid}/label-config/slots?task_id=x",
            f"/api/evaluations/projects/{pid}/annotator-agreement",
            f"/api/runs/generations/{uuid.uuid4()}/trials/{uuid.uuid4()}/request",
            f"/api/runs/trials/{uuid.uuid4()}/request",
            f"/api/projects/{pid}/report/analysis-runs",
            "/api/runs?type=analysis",
        ):
            _disabled(await async_test_client.get(path))
        for path, body in (
            ("/api/analysis/specs/validate", {"spec": {}}),
            (f"/api/projects/{pid}/analysis-runs", {"spec": {}}),
            (f"/api/projects/{pid}/variant-designs", {"key": "swap", "spec": {}}),
            (f"/api/projects/{pid}/coding-projects", {}),
        ):
            _disabled(await async_test_client.post(path, json=body))
        _disabled(
            await async_test_client.get("/api/compliance/assessments"), COMPLIANCE_RECORDS
        )
        _disabled(
            await async_test_client.post("/api/compliance/assessments", json={}),
            COMPLIANCE_RECORDS,
        )
        _disabled(
            await async_test_client.get(f"/api/compliance/findings/{uuid.uuid4()}"),
            COMPLIANCE_RECORDS,
        )
        # The classic run types are unaffected.
        assert (await async_test_client.get("/api/runs?type=evaluation")).status_code == 200


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
async def test_the_analysis_run_type_lists_with_the_flag(
    async_test_client, async_test_db, world
):
    with v1_auth(async_test_db, session_user=world["admin"]):
        r = await async_test_client.get("/api/runs?type=analysis")
    assert r.status_code == 200 and r.json()["total"] == 0


# --------------------------------------------------------------------------- #
# changed behaviour: the platform's previous behaviour while off
# --------------------------------------------------------------------------- #


async def _put_runs(client, project_id, runs):
    return await client.put(
        f"/api/projects/{project_id}/generation-config", json={"runs_per_task": runs}
    )


async def test_runs_cap_is_25_while_off(async_test_client, async_test_db, world):
    pid = world["project"].id
    with v1_auth(async_test_db, session_user=world["admin"]):
        assert (await _put_runs(async_test_client, pid, 25)).status_code == 200
        r = await _put_runs(async_test_client, pid, 26)
        assert r.status_code == 422
        assert r.json()["detail"] == "runs_per_task must be an integer between 1 and 25"
        start = await async_test_client.post(
            f"/api/generation-tasks/projects/{pid}/generate",
            json={"mode": "missing", "runs_per_task": 30},
        )
    assert start.status_code == 422
    errors = start.json()["detail"]
    assert errors[0]["loc"] == ["body", "runs_per_task"]
    assert errors[0]["type"] == "less_than_equal" and errors[0]["ctx"] == {"le": 25}


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
async def test_runs_cap_is_100_with_the_flag(async_test_client, async_test_db, world):
    pid = world["project"].id
    with v1_auth(async_test_db, session_user=world["admin"]):
        assert (await _put_runs(async_test_client, pid, 100)).status_code == 200
        r = await _put_runs(async_test_client, pid, 101)
    assert r.status_code == 422
    assert r.json()["detail"] == "runs_per_task must be an integer between 1 and 100"


_STRUCTURE = {
    "name": "Fixed",
    "system_prompt": "Sys",
    "instruction_prompt": "Q",
    "append_schema_instruction": False,
    "structured_output": "off",
    "format_retry": {"message": "JSON only."},
}


async def test_answer_format_options_are_neither_shown_nor_written_while_off(
    async_test_client, async_test_db, world
):
    pid = world["project"].id
    url = f"/api/projects/{pid}/generation-config/structures/fixed"
    with v1_auth(async_test_db, session_user=world["admin"]):
        put = await async_test_client.put(url, json=_STRUCTURE)
        got = await async_test_client.get(url)
    assert put.status_code == 200, put.text
    for body in (put.json(), got.json()):
        assert body["append_schema_instruction"] is True
        assert body["structured_output"] == "auto"
        assert body["format_retry"] is None
        assert body["schema_instruction_preview"] is None
    await async_test_db.refresh(world["project"])
    stored = world["project"].generation_config["prompt_structures"]["fixed"]
    assert "format_retry" not in stored and "structured_output" not in stored


async def test_an_edit_while_off_keeps_the_stored_options(async_test_client, async_test_db, world):
    project = world["project"]
    project.generation_config = {
        "prompt_structures": {"fixed": {**_STRUCTURE, "key": "fixed"}},
    }
    await async_test_db.commit()
    url = f"/api/projects/{project.id}/generation-config/structures/fixed"
    with v1_auth(async_test_db, session_user=world["admin"]):
        r = await async_test_client.put(
            url, json={"name": "Fixed", "system_prompt": "New", "instruction_prompt": "Q"}
        )
    assert r.status_code == 200, r.text
    await async_test_db.refresh(project)
    stored = project.generation_config["prompt_structures"]["fixed"]
    assert stored["system_prompt"] == "New"
    assert stored["format_retry"] == {"message": "JSON only."}
    assert stored["structured_output"] == "off"


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
async def test_answer_format_options_with_the_flag(async_test_client, async_test_db, world):
    pid = world["project"].id
    url = f"/api/projects/{pid}/generation-config/structures/fixed"
    with v1_auth(async_test_db, session_user=world["admin"]):
        put = await async_test_client.put(url, json=_STRUCTURE)
    assert put.status_code == 200, put.text
    assert put.json()["format_retry"] == {"message": "JSON only."}
    assert put.json()["structured_output"] == "off"


async def test_text_pattern_is_not_a_supported_metric_while_off(
    async_test_client, async_test_db, world
):
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await async_test_client.get("/api/evaluations/supported-metrics")
    assert r.status_code == 200
    assert "text_pattern" not in r.json()["supported_metrics"]
    assert "bleu" in r.json()["supported_metrics"]


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
async def test_text_pattern_is_a_supported_metric_with_the_flag(
    async_test_client, async_test_db, world
):
    with v1_auth(async_test_db, session_user=world["member"]):
        r = await async_test_client.get("/api/evaluations/supported-metrics")
    assert "text_pattern" in r.json()["supported_metrics"]


_REPEATER = (
    '<View><Repeater on="$items" indexFlag="{{idx}}">'
    '<Text name="t_{{idx}}" value="$items[{{idx}}].text"/>'
    '<TextArea name="a_{{idx}}" toName="t_{{idx}}"/></Repeater></View>'
)


def test_repeater_is_an_unsupported_field_type_while_off():
    from services.label_config.validator import LabelConfigValidator

    with flag_scope({VARIANT_EXPERIMENTS: False}):
        ok, errors = LabelConfigValidator.validate(_REPEATER)
    assert not ok
    assert "Unsupported field type: 'Repeater'" in errors
    with flag_scope({VARIANT_EXPERIMENTS: True}):
        ok, errors = LabelConfigValidator.validate(_REPEATER)
    assert ok, errors


async def test_panel_models_are_hidden_and_refused_while_off(
    async_test_client, async_test_db, world
):
    from models import LLMModel

    panel = LLMModel(
        id=f"panel/{uuid.uuid4().hex[:6]}",
        name="Panel model",
        provider="DeepInfra",
        model_type="chat",
        capabilities=["text-generation"],
        is_active=True,
        is_official=True,
        default_config={"feature_flag": VARIANT_EXPERIMENTS},
    )
    thinking = LLMModel(
        id=f"thinking/{uuid.uuid4().hex[:6]}",
        name="Thinking model",
        provider="DeepInfra",
        model_type="chat",
        capabilities=["text-generation"],
        is_active=True,
        is_official=True,
        default_config={
            "reasoning_config": {
                "parameter": "enable_thinking",
                "values": ["off", "on"],
                "default": "on",
                "feature_flag": VARIANT_EXPERIMENTS,
            }
        },
    )
    async_test_db.add_all([panel, thinking])
    # A project ready to generate, so the refusal is the model's.
    world["project"].generation_config = {
        "prompt_structures": {
            "s": {"name": "S", "system_prompt": "Sys", "instruction_prompt": "Q"}
        },
        "selected_configuration": {"models": [panel.id], "active_structures": ["s"]},
    }
    await async_test_db.commit()
    with v1_auth(async_test_db, session_user=world["admin"]):
        listing = await async_test_client.get("/api/llm_models/public/models")
        start = await async_test_client.post(
            f"/api/generation-tasks/projects/{world['project'].id}/generate",
            json={"mode": "missing", "model_ids": [panel.id], "structure_keys": ["s"]},
        )
    by_id = {m["id"]: m for m in listing.json()}
    assert panel.id not in by_id
    assert "reasoning_config" not in (by_id[thinking.id]["default_config"] or {})
    assert start.status_code == 400, start.text
    assert panel.id in start.json()["detail"]


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
async def test_panel_models_are_listed_with_the_flag(async_test_client, async_test_db, world):
    from models import LLMModel

    panel = LLMModel(
        id=f"panel/{uuid.uuid4().hex[:6]}",
        name="Panel model",
        provider="DeepInfra",
        model_type="chat",
        capabilities=["text-generation"],
        is_active=True,
        is_official=True,
        default_config={"feature_flag": VARIANT_EXPERIMENTS},
    )
    async_test_db.add(panel)
    await async_test_db.commit()
    with v1_auth(async_test_db, session_user=world["admin"]):
        listing = await async_test_client.get("/api/llm_models/public/models")
    assert panel.id in {m["id"] for m in listing.json()}


async def test_counts_are_not_taken_while_off(async_test_client, async_test_db, world):
    from models import AnalysisRun

    spec = {"spec_version": 1, "name": "s", "inputs": {"designs": ["d"]}}
    async_test_db.add(
        AnalysisRun(
            id=str(uuid.uuid4()), project_id=world["project"].id, created_by=world["admin"].id,
            name="done", status="completed", spec=spec, normalized_spec=spec,
            spec_hash="0" * 64, spec_version=1, engine_version="1.0.0",
        )
    )
    await async_test_db.commit()
    with v1_auth(async_test_db, session_user=world["admin"]):
        detail = await async_test_client.get(f"/api/projects/{world['project'].id}")
        listing = await async_test_client.get("/api/projects/")
        with patch("routers.dashboard.cache") as cache:
            cache.get.return_value = None
            dashboard = await async_test_client.get("/api/dashboard/stats")
    assert detail.json()["analysis_count"] == 0
    item = next(p for p in listing.json()["items"] if p["id"] == world["project"].id)
    assert item["analysis_count"] == 0
    assert dashboard.json()["analyses_count"] == 0


async def test_import_provenance_options_are_ignored_while_off(
    async_test_client, async_test_db, world
):
    from models import ImportJob

    pid = world["project"].id
    sent = MagicMock()
    sent.id = "celery-import-1"
    with v1_auth(async_test_db, session_user=world["admin"]), patch(
        "routers.projects.import_export.send_task_safe", return_value=sent
    ) as send:
        r = await async_test_client.post(
            f"/api/projects/{pid}/imports",
            json={
                "object_key": f"imports/2026/06/{pid}/20260601_120000_import.json",
                "reimport": True,
                "source_manifest": {"source": "x"},
            },
        )
    if r.status_code != 202:
        pytest.fail(f"import job not created: {r.status_code} {r.text}")
    job = await async_test_db.get(ImportJob, r.json()["job_id"])
    assert job.source_manifest is None
    kwargs = send.call_args.kwargs.get("kwargs") or {}
    assert "reimport" not in kwargs


# --------------------------------------------------------------------------- #
# report snapshot parts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("experiments", [False, True])
@pytest.mark.parametrize("paper", [False, True])
def test_snapshot_parts_are_built_only_with_their_flag(test_db, test_users, experiments, paper):
    from project_models import Project
    from report_snapshot import (
        EXPERIMENT_SNAPSHOT_KEYS,
        PAPER_SNAPSHOT_KEYS,
        build_report_snapshot,
        snapshot_sha256,
    )

    project = Project(id=str(uuid.uuid4()), title="snap", created_by=test_users[0].id)
    test_db.add(project)
    test_db.flush()
    snap = build_report_snapshot(
        test_db, project.id, variant_experiments=experiments, report_paper=paper
    )
    for key in EXPERIMENT_SNAPSHOT_KEYS:
        assert (key in snap) is experiments
    assert ("analysis_count" in snap["statistics"]) is experiments
    for key in PAPER_SNAPSHOT_KEYS:
        assert (key in snap) is paper
    if paper:
        assert snap["reproducibility"]["snapshot_sha256"] == snapshot_sha256(snap)


def _stored_snapshot():
    from report_snapshot import snapshot_sha256

    snapshot = {
        "statistics": {"task_count": 2, "analysis_count": 3},
        "annotator_agreement": {"controls": []},
        "analyses": {"runs": [{"id": "r1"}]},
        "data": {
            "task_count": 2,
            "variant_designs": [{"key": "d"}],
            "imports": [{"format": "nested", "completed_at": None, "payload_sha256": "b" * 64,
                         "mode": "nested", "byte_size": 9, "task_count": 2, "no_op": False,
                         "declared_manifest": None}],
        },
        "generation": {
            "models": [{"model_id": "m", "refusal_rate": 0.5, "retry_rate": 0.0,
                        "request_record_share": 1.0, "parse_failure_rate": 0.1}],
            "totals": {"generations": 2, "refusal_rate": 0.5, "retry_rate": 0.0,
                       "request_record_share": 1.0, "parse_failure_rate": 0.1},
        },
        "human_evaluations": {"likert": {"dimensions": []}},
        "reproducibility": {
            "variant_designs": [{"key": "d"}],
            "analysis_runs": [{"id": "r1"}],
            "imports": [{"payload_sha256": "b" * 64, "completed_at": None, "no_op": False}],
            "snapshot_sha256": None,
        },
    }
    snapshot["reproducibility"]["snapshot_sha256"] = snapshot_sha256(snapshot)
    return snapshot


def _signed(snapshot):
    from report_snapshot import snapshot_sha256

    snapshot["reproducibility"]["snapshot_sha256"] = None
    snapshot["reproducibility"]["snapshot_sha256"] = snapshot_sha256(snapshot)
    return snapshot


def _served(snapshot, *, annotations=None, can_edit=True, member=True):
    """The content one reader gets through the report routes' response."""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from routers.reports import _report_response

    report = SimpleNamespace(
        id="r", project_id="p", is_published=True, is_public=True, published_at=None,
        published_by=None, created_by="u", created_at=datetime.now(timezone.utc),
        updated_at=None,
        content={
            "sections": {
                "annotations": annotations or {"show_participants": True},
                "analyses": {"runs": []},
            },
            "metadata": {},
            "snapshot": snapshot,
        },
    )
    response = _report_response(report, "t", True, "ok", can_edit=can_edit, member=member)
    return response.content.model_dump()


def _verifies(served):
    from report_snapshot import snapshot_sha256

    return served["reproducibility"]["snapshot_sha256"] == snapshot_sha256(served)


def test_served_report_drops_every_flagged_part_while_both_are_off_for_everybody():
    content = _served(_stored_snapshot())
    assert content["snapshot"] == {"statistics": {"task_count": 2}}
    assert "analyses" not in content["sections"]


def test_served_paper_without_variant_experiments_has_no_values_of_its_features():
    stored = _stored_snapshot()
    with flag_scope({REPORT_PAPER: True}):
        content = _served(stored)
    served = content["snapshot"]
    assert served["statistics"] == {"task_count": 2}
    assert "analyses" not in served and "annotator_agreement" not in served
    assert served["data"] == {
        "task_count": 2, "variant_designs": [],
        "imports": [{"format": "nested", "completed_at": None}],
    }
    assert served["generation"] == {
        "models": [{"model_id": "m", "parse_failure_rate": 0.1}],
        "totals": {"generations": 2, "parse_failure_rate": 0.1},
    }
    assert served["reproducibility"]["variant_designs"] == []
    assert served["reproducibility"]["analysis_runs"] == []
    assert served["reproducibility"]["imports"] == [{"completed_at": None}]
    # The served hash is the one of the served body, not the stored one.
    assert _verifies(served)
    assert served["reproducibility"]["snapshot_sha256"] != stored["reproducibility"]["snapshot_sha256"]
    assert "analyses" not in content["sections"]


def test_the_served_hash_verifies_after_the_flag_strip_and_hidden_participants():
    stored = _stored_snapshot()
    stored["participants"] = [{"id": "a", "label": "Heron"}]
    stored = _signed(stored)
    with flag_scope({REPORT_PAPER: True}):
        served = _served(stored, annotations={"show_participants": False})["snapshot"]
    assert served["participants"] == []
    assert _verifies(served)


def test_the_served_hash_verifies_for_hidden_participants_with_both_flags():
    stored = _stored_snapshot()
    stored["participants"] = [{"id": "a", "label": "Heron"}]
    stored["annotator_agreement"] = {"controls": [{"name": "c", "pairs": [{"a": "x", "b": "y"}]}]}
    stored = _signed(stored)
    with flag_scope({REPORT_PAPER: True, VARIANT_EXPERIMENTS: True}):
        served = _served(stored, annotations={"show_participants": False})["snapshot"]
    assert served["participants"] == []
    assert served["annotator_agreement"]["controls"][0]["pairs"] == []
    assert _verifies(served)
    assert served["reproducibility"]["snapshot_sha256"] != stored["reproducibility"]["snapshot_sha256"]


def test_the_served_hash_verifies_for_a_reader_outside_the_project():
    stored = _stored_snapshot()
    stored["data"]["imports"][0]["declared_manifest"] = {"sha256": "d" * 64, "content": {"files": []}}
    stored = _signed(stored)
    with flag_scope({REPORT_PAPER: True, VARIANT_EXPERIMENTS: True}):
        served = _served(stored, can_edit=False, member=False)["snapshot"]
    assert served["data"]["imports"][0]["declared_manifest"] == {"sha256": "d" * 64}
    assert _verifies(served)
    assert served["reproducibility"]["snapshot_sha256"] != stored["reproducibility"]["snapshot_sha256"]


def test_served_report_is_the_stored_one_with_both_flags():
    stored = _stored_snapshot()
    with flag_scope({REPORT_PAPER: True, VARIANT_EXPERIMENTS: True}):
        for kwargs in ({}, {"can_edit": False, "member": True}):
            served = _served(stored, **kwargs)["snapshot"]
            assert served == stored
            assert served["reproducibility"]["snapshot_sha256"] == stored["reproducibility"]["snapshot_sha256"]


async def test_only_superadmins_author_reports_while_off(async_test_client, async_test_db, world):
    pid = world["project"].id
    with v1_auth(async_test_db, session_user=world["admin"]):
        publish = await async_test_client.put(f"/api/projects/{pid}/report/publish")
        refresh = await async_test_client.post(f"/api/projects/{pid}/report/refresh")
    assert publish.status_code == 403
    assert publish.json()["detail"] == "Only superadmins can publish reports"
    assert refresh.status_code == 403
    assert refresh.json()["detail"] == "Only superadmins can refresh reports"


@pytest.mark.flags_on(REPORT_PAPER)
async def test_the_project_owner_authors_the_report_with_the_flag(
    async_test_client, async_test_db, world
):
    pid = world["project"].id
    with v1_auth(async_test_db, session_user=world["admin"]):
        publish = await async_test_client.put(f"/api/projects/{pid}/report/publish")
    # Past the author check (the project has no report yet).
    assert publish.status_code != 403, publish.text


@pytest.mark.flags_on(VARIANT_EXPERIMENTS)
async def test_variant_experiments_alone_leaves_reports_to_superadmins(
    async_test_client, async_test_db, world
):
    pid = world["project"].id
    with v1_auth(async_test_db, session_user=world["admin"]):
        publish = await async_test_client.put(f"/api/projects/{pid}/report/publish")
    assert publish.status_code == 403
    assert publish.json()["detail"] == "Only superadmins can publish reports"
