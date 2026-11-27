"""Migration 162: retired model references at any key, in every saved config.

Migration 161 rewrote a fixed key list; saved evaluation configs still named
gpt-5-mini under ``metric_parameters.judge_model`` (with its
``display_name``), ``metric_parameters.rubric_generator_model_id`` and
``metric_parameters.rubric_generator_selection.model_id``. 162 walks every
JSON value with 161's mapping. The fixture below is shaped like saved
production data: a sheet-judge exam project, a generation project, a project
already on current models, an organization, a wizard draft and strings that
equal a retired id under keys that are not model keys. Every test runs
inside the ``test_db`` transaction, which rolls back.
"""

from __future__ import annotations

import copy
import importlib.util
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"mig_{name}", os.path.join(VERSIONS, name)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load("162_retired_model_references_everywhere.py")


def _uid() -> str:
    return str(uuid.uuid4())


def _user(db):
    from models import User

    user = User(
        id=_uid(),
        username=f"mig162-{_uid()[:8]}",
        email=f"mig162-{_uid()[:8]}@example.com",
        name="Mig 162",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _sheet_judge_config():
    """An exam's evaluation config after 161 ran: the three shapes it left."""
    return {
        "evaluation_configs": [
            {
                "id": "notenpunkte",
                "metric": "llm_judge_classic",
                "display_name": "Notenpunkte (gpt-5-mini)",
                "metric_parameters": {
                    "judge_model": "gpt-5-mini",
                    "score_scale": "0-18",
                },
            },
            {
                "id": "bewertungsbogen",
                "metric": "llm_judge_rubric",
                "display_name": "Bewertungsbogen",
                "metric_parameters": {
                    "judge_model": "gpt-5.6-luna",
                    "rubric_generator_model_id": "gpt-5-mini",
                    "rubric_generator_selection": {
                        "role": "generator",
                        "model_id": "gpt-5-mini",
                        "source": "chosen",
                        "reason": None,
                        "recommended": "gpt-5.6-luna",
                        "skipped": [
                            {"provider": "openai", "model_id": "o3", "key": "missing"}
                        ],
                    },
                    "rubric_prompt_key": "rubric",
                    "custom_prompt_template": "Grade like o3 would: {answer}",
                    # Picks the sheets gpt-5 produced: a lookup, not a model to run.
                    "rubric_selector": {"generator_model_id": "gpt-5"},
                },
            },
        ],
        "grade_scale": {"unit": "percent", "rounding": "down"},
    }


@pytest.mark.integration
class TestMigration162:
    def test_revision_chains_after_161_and_shares_its_mapping(self, migration):
        assert migration.revision == "162_retired_model_references_everywhere"
        assert migration.down_revision == "161_retired_model_references"
        assert (
            migration.REPLACEMENTS
            == _load("161_retired_model_references.py").REPLACEMENTS
        )

    def test_saved_references_at_any_key_move_to_the_replacements(
        self, test_db, migration, capsys
    ):
        from models import Organization
        from project_models import Project, ProjectWizardDraft

        user = _user(test_db)
        org = Organization(
            id=_uid(),
            name="Org",
            display_name="Org",
            slug=f"org-{_uid()[:8]}",
            settings={
                "handwriting_ocr_model": "gpt-6.1-terra",
                "default_judge_model": "o3",
            },
        )
        test_db.add(org)
        exam = Project(
            id=_uid(),
            title="Exam",
            created_by=user.id,
            kind="exam",
            evaluation_config=_sheet_judge_config(),
            korrektur_config=[{"value": "o3", "background": "#fff"}],
            label_config_history=[{"version": "v1", "model": "gpt-5"}],
        )
        generation = Project(
            id=_uid(),
            title="Generation",
            created_by=user.id,
            llm_model_ids=["gpt-6.1-terra", "gpt-5-mini"],
            generation_config={
                "prompt_structures": {
                    "s": {"name": "gpt-5", "user_prompt": "Act as o3."}
                },
                "selected_configuration": {
                    "models": ["gpt-6.1-terra"],
                    "model_configs": {"gpt-5-nano": {"max_tokens": 4000}},
                },
            },
        )
        current = Project(
            id=_uid(),
            title="Current",
            created_by=user.id,
            llm_model_ids=["gpt-5.4-mini"],
            evaluation_config={
                "evaluation_configs": [
                    {
                        "id": "a",
                        "metric": "llm_judge_classic",
                        "display_name": "o3",
                        "metric_parameters": {"judge_model": "gpt-5.4-mini"},
                    },
                ]
            },
        )
        test_db.add_all([exam, generation, current])
        test_db.flush()
        draft = ProjectWizardDraft(
            project_id=generation.id,
            created_by=user.id,
            client_key=_uid()[:16],
            state={
                "title": "o3",
                "selectedModelIds": ["gpt-5", "gpt-6.1-sol"],
                "modelConfigs": {"gpt-5": {"temperature": 0.1}},
                "evaluationConfigs": [
                    {
                        "id": "x",
                        "displayName": "Judge (gpt-5)",
                        "metric_parameters": {"judge_model": "gpt-5"},
                    },
                ],
            },
        )
        test_db.add(draft)
        test_db.commit()
        current_before = copy.deepcopy(current.evaluation_config)

        with patch.object(migration.op, "get_bind", return_value=test_db.connection()):
            migration.upgrade()
        test_db.commit()
        out = capsys.readouterr().out
        summary = out.split("162: rewrote retired model references: ")[1].splitlines()[
            0
        ]
        counts = dict(item.split("=") for item in summary.split(", "))
        assert {k: v for k, v in counts.items() if v != "0"} == {
            "organizations.settings": "1",
            "project_wizard_drafts.state": "1",
            "projects.evaluation_config": "1",
            "projects.generation_config": "1",
            "projects.llm_model_ids": "1",
        }
        # Every JSON column of projects is walked, history excepted.
        assert {"projects.korrektur_config", "projects.exam_tools"} <= set(counts)
        assert "projects.label_config_history" not in counts
        assert "per retired id: gpt-5=1, gpt-5-mini=2, gpt-5-nano=1, o3=1" in out
        entry_path = "projects.evaluation_config.evaluation_configs[]"
        for path in (
            f"{entry_path}.metric_parameters.judge_model=1",
            f"{entry_path}.display_name=1",
            f"{entry_path}.metric_parameters.rubric_generator_model_id=1",
            f"{entry_path}.metric_parameters.rubric_generator_selection.model_id=1",
            "projects.llm_model_ids[]=1",
            "projects.generation_config.selected_configuration.model_configs{}=1",
            "organizations.settings.default_judge_model=1",
            "project_wizard_drafts.state.selectedModelIds[]=1",
            "project_wizard_drafts.state.modelConfigs{}=1",
            "project_wizard_drafts.state.evaluationConfigs[].displayName=1",
        ):
            assert path in out, path

        test_db.expire_all()
        entries = test_db.get(Project, exam.id).evaluation_config["evaluation_configs"]
        assert entries[0]["metric_parameters"]["judge_model"] == "gpt-6.1-terra"
        assert entries[0]["display_name"] == "Notenpunkte (gpt-6.1-terra)"
        params = entries[1]["metric_parameters"]
        assert params["rubric_generator_model_id"] == "gpt-6.1-terra"
        selection = params["rubric_generator_selection"]
        assert selection["model_id"] == "gpt-6.1-terra"
        # Records of the past stay: the sheets gpt-5 produced, the rung a
        # selection skipped, the recommendation it was made against.
        assert selection["skipped"] == [
            {"provider": "openai", "model_id": "o3", "key": "missing"}
        ]
        assert selection["recommended"] == "gpt-5.6-luna"
        assert params["rubric_selector"] == {"generator_model_id": "gpt-5"}
        # A string equal to a retired id under a non-model key stays.
        assert params["custom_prompt_template"] == "Grade like o3 would: {answer}"
        assert entries[1]["display_name"] == "Bewertungsbogen"
        exam_row = test_db.get(Project, exam.id)
        assert exam_row.korrektur_config == [{"value": "o3", "background": "#fff"}]
        assert exam_row.label_config_history == [{"version": "v1", "model": "gpt-5"}]

        gen = test_db.get(Project, generation.id)
        assert gen.llm_model_ids == ["gpt-6.1-terra"]
        assert gen.generation_config["selected_configuration"]["model_configs"] == {
            "gpt-6-luna": {"max_tokens": 4000}
        }
        assert gen.generation_config["prompt_structures"] == {
            "s": {"name": "gpt-5", "user_prompt": "Act as o3."}
        }
        assert test_db.get(Project, current.id).evaluation_config == current_before
        assert test_db.get(Organization, org.id).settings == {
            "handwriting_ocr_model": "gpt-6.1-terra",
            "default_judge_model": "gpt-6.1-sol",
        }
        state = test_db.get(ProjectWizardDraft, generation.id).state
        assert state["title"] == "o3"
        assert state["selectedModelIds"] == ["gpt-6.1-sol"]
        assert state["modelConfigs"] == {"gpt-6.1-sol": {"temperature": 0.1}}
        assert state["evaluationConfigs"][0]["displayName"] == "Judge (gpt-6.1-sol)"
        assert (
            state["evaluationConfigs"][0]["metric_parameters"]["judge_model"]
            == "gpt-6.1-sol"
        )

        # Idempotent: a second run finds nothing left to rewrite.
        with patch.object(migration.op, "get_bind", return_value=test_db.connection()):
            migration.upgrade()
        test_db.commit()
        second = capsys.readouterr().out
        assert "per retired id: none" in second
        assert "per key path: none" in second

    def test_the_walker_rewrites_only_model_keys(self, migration):
        rewrite = migration.rewrite_model_references
        unchanged = (None, set(), {})
        # Key shapes: a model key, a list under one, nested at any depth.
        out, retired, paths = rewrite(
            {
                "a": [
                    {"b": {"judge_model_id": "o3", "judge_models": ["o3-pro", "gpt-5"]}}
                ]
            },
            "evaluation_config",
        )
        assert out == {
            "a": [
                {
                    "b": {
                        "judge_model_id": "gpt-6.1-sol",
                        "judge_models": ["gpt-6.1-sol"],
                    }
                }
            ]
        }
        assert retired == {"o3", "o3-pro", "gpt-5"}
        assert paths["evaluation_config.a[].b.judge_models[]"] == 2
        # A judges list that now names a model twice keeps its first entry.
        out, _, _ = rewrite(
            {
                "judges": [
                    {"judge_model_id": "o3", "runs": 2},
                    {"judge_model_id": "gpt-6.1-sol"},
                ]
            },
            "metric_parameters",
        )
        assert out == {"judges": [{"judge_model_id": "gpt-6.1-sol", "runs": 2}]}
        # Strings equal to a retired id elsewhere, and longer ids, stay.
        assert (
            rewrite({"name": "o3", "label": ["gpt-5"], "note": "gpt-5"}, "settings")
            == unchanged
        )
        assert rewrite({"model": "gpt-5.4-mini"}, "settings") == unchanged
        assert rewrite(["gpt-5", "o3"], "korrektur_config") == unchanged
        assert rewrite(None, "evaluation_config") == unchanged
        assert rewrite({"model_id": "gpt-5", "skipped": [{"model_id": "gpt-5"}]}, "x")[
            0
        ] == {
            "model_id": "gpt-6.1-sol",
            "skipped": [{"model_id": "gpt-5"}],
        }

    def test_a_future_retirement_only_needs_its_mapping(self, migration):
        out, retired, _ = migration.rewrite_model_references(
            {
                "evaluation_configs": [
                    {
                        "display_name": "Votum (gpt-6.1-terra)",
                        "metric_parameters": {
                            "rubric_generator_model_id": "gpt-6.1-terra"
                        },
                    }
                ]
            },
            "evaluation_config",
            {"gpt-6.1-terra": "gpt-7-terra"},
        )
        assert retired == {"gpt-6.1-terra"}
        entry = out["evaluation_configs"][0]
        assert entry["metric_parameters"]["rubric_generator_model_id"] == "gpt-7-terra"
        assert entry["display_name"] == "Votum (gpt-7-terra)"

    def test_model_key_names(self, migration):
        for key in (
            "model",
            "models",
            "model_id",
            "model_ids",
            "judge_model",
            "judge_model_id",
            "generator_model_id",
            "rubric_generator_model_id",
            "llm_model_ids",
            "handwriting_ocr_model",
            "selectedModelIds",
            "judgeModel",
        ):
            assert migration.is_model_key(key), key
        for key in (
            "name",
            "display_name",
            "model_configs",
            "modelling",
            "remodel_note",
            3,
        ):
            assert not migration.is_model_key(key), key
