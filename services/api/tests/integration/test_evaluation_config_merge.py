"""
Merge semantics of PUT /api/evaluations/projects/{id}/evaluation-config.

Issue #289: the frontend sends minimal bodies (e.g. only ``evaluation_configs``)
and relies on the server merging them into the stored document, so sibling keys
written by the eval-defaults PATCH (``default_temperature``, ``defaults_mode``,
``selected_methods``, …) survive. The PUT deep-merges with the same contract as
PATCH /projects/{id} (utils/json_merge.deep_merge_dicts): nested dicts merge
recursively, lists are replaced wholesale, explicit nulls delete keys.

The PUT handler is sync (Session lane) — these tests use the legacy
``client``/``test_db`` fixtures, which share one session, so post-PUT state is
read back directly after ``expire_all()``.
"""

import uuid

import pytest

from project_models import Project, ProjectOrganization

BASE = "/api/evaluations"


def _uid():
    return str(uuid.uuid4())


def _seed_project(test_db, test_users, test_org, evaluation_config=None):
    project = Project(
        id=_uid(),
        title="Merge Semantics Project",
        created_by=test_users[0].id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=test_users[0].id,
        )
    )
    test_db.commit()
    return project


def _stored_config(test_db, project_id):
    test_db.expire_all()
    return test_db.query(Project).filter(Project.id == project_id).first().evaluation_config


STORED = {
    "default_temperature": 0.2,
    "default_max_tokens": 900,
    "defaults_mode": "custom",
    "selected_methods": {"answer": {"automated": ["bleu"]}},
    "available_methods": {"answer": {"available_metrics": ["bleu"], "available_human": []}},
    "evaluation_configs": [{"id": "a", "metric": "bleu", "enabled": True}],
}


@pytest.mark.integration
class TestEvaluationConfigMerge:
    def _headers(self, auth_headers, test_org):
        return {**auth_headers["admin"], "X-Organization-Context": test_org.id}

    def test_put_merges_body_into_stored_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, dict(STORED))
        new_configs = [{"id": "b", "metric": "rouge", "enabled": True}]
        resp = client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={"evaluation_configs": new_configs},
            headers=self._headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text

        stored = _stored_config(test_db, project.id)
        # Sibling keys written by other savers survive a minimal-body PUT.
        assert stored["default_temperature"] == 0.2
        assert stored["default_max_tokens"] == 900
        assert stored["defaults_mode"] == "custom"
        assert stored["selected_methods"] == STORED["selected_methods"]
        assert stored["available_methods"] == STORED["available_methods"]
        assert stored["evaluation_configs"] == new_configs
        assert "label_config_version" in stored

        # Response echoes the merged document, not just the body.
        body = resp.json()["config"]
        assert body["default_temperature"] == 0.2
        assert body["evaluation_configs"] == new_configs

    def test_put_replaces_evaluation_configs_list_wholesale(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        stored = dict(STORED)
        stored["evaluation_configs"] = [
            {"id": "a", "metric": "bleu", "enabled": True},
            {"id": "b", "metric": "rouge", "enabled": True},
        ]
        project = _seed_project(test_db, test_users, test_org, stored)
        resp = client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={"evaluation_configs": [{"id": "a", "metric": "bleu", "enabled": True}]},
            headers=self._headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        # Lists replace wholesale — removing an entry actually removes it.
        assert _stored_config(test_db, project.id)["evaluation_configs"] == [
            {"id": "a", "metric": "bleu", "enabled": True}
        ]

    def test_put_none_value_deletes_key(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _seed_project(test_db, test_users, test_org, dict(STORED))
        resp = client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={"defaults_mode": None},
            headers=self._headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        stored = _stored_config(test_db, project.id)
        assert "defaults_mode" not in stored
        assert stored["default_temperature"] == 0.2

    def test_put_full_doc_on_empty_stored_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Full-document writes (ProjectCreationWizard, e2e specs) still work
        when nothing is stored yet."""
        project = _seed_project(test_db, test_users, test_org, None)
        doc = {
            "evaluation_configs": [{"id": "a", "metric": "bleu", "enabled": True}],
            "defaults_mode": "recommended",
        }
        resp = client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json=doc,
            headers=self._headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        stored = _stored_config(test_db, project.id)
        assert stored["evaluation_configs"] == doc["evaluation_configs"]
        assert stored["defaults_mode"] == "recommended"
        assert "label_config_version" in stored

    def test_after_save_hook_receives_merged_doc(
        self, client, test_db, test_users, auth_headers, test_org, monkeypatch
    ):
        """Extended derives Korrektur state from the hook's config — it must
        see the merged document, not the partial body."""
        import extensions

        seen = []
        monkeypatch.setattr(
            extensions,
            "run_after_eval_config_save",
            lambda db, project, config: seen.append(dict(config)),
        )

        project = _seed_project(test_db, test_users, test_org, dict(STORED))
        new_configs = [{"id": "k", "metric": "korrektur_falloesung", "enabled": True}]
        resp = client.put(
            f"{BASE}/projects/{project.id}/evaluation-config",
            json={"evaluation_configs": new_configs},
            headers=self._headers(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert len(seen) == 1
        assert seen[0]["evaluation_configs"] == new_configs
        assert seen[0]["default_temperature"] == 0.2
        assert seen[0]["selected_methods"] == STORED["selected_methods"]
