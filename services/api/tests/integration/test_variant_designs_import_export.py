"""Variant designs through export and import (CORE 2.59).

Every import path validates ``meta.variant`` (nested JSON, a flat CSV-style
row, the tabular CSV import, the full project import or clone in both
serializations, the merge import), refuses a duplicate cell also with
reordered factor keys, refuses new tasks in a frozen design, and an export
followed by an import keeps the designs (frozen again, same content hash)
and every task's assignment. Synthetic content only.
"""

import copy
import io
import json
import uuid

import pytest
from sqlalchemy import text

from export_stream import stream_export_json
from import_stream import (
    MERGE_TASK_MISMATCH,
    ImportValidationError,
    run_full_project_import,
    run_merge_import,
    run_nested_import,
    run_tabular_import,
)
from project_models import Project, ProjectOrganization, Task, VariantDesign
from routers.projects._export_stream import (
    stream_comprehensive_project_data_json,
    stream_export_ndjson,
)
from variant_design_guard import export_document, freeze_design, new_design_row

pytestmark = pytest.mark.integration

NAMES = {"claimant": "Alma Reyes", "respondent": "Bodo Lind"}
SPEC = {
    "schema_version": 1,
    "unit": {"name": "case"},
    "factors": [
        {"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]},
        {"name": "order", "type": "nominal", "levels": ["a", "b"], "role": "counterbalanced"},
    ],
    "invariance": {"fields": ["facts"]},
}


def _uid() -> str:
    return str(uuid.uuid4())


def item(unit, role, order, *, design="swap", facts=None, factors=None):
    name = NAMES[role]
    facts = facts if facts is not None else f"{name} wants the fence moved ({order})."
    at = facts.find(name)
    return {
        "data": {"facts": facts},
        "meta": {
            "variant": {
                "design": design,
                "unit": unit,
                "factors": factors if factors is not None else {"role": role, "order": order},
                "spans": {"facts": [[at, at + len(name)], [len(facts) - 3, len(facts) - 2]]},
            }
        },
    }


def full_items(units=("u1", "u2")):
    return [
        item(unit, role, order)
        for unit in units
        for role in ("claimant", "respondent")
        for order in ("a", "b")
    ]


def _project(test_db, admin, org, title="VD IO"):
    project = Project(
        id=_uid(),
        title=f"{title} {_uid()[:8]}",
        label_config='<View><Text name="facts_view" value="$facts"/></View>',
        created_by=admin.id,
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=admin.id
        )
    )
    test_db.commit()
    return project


def _nested(test_db, project, admin, items, designs=None):
    payload = {"data": items}
    if designs is not None:
        payload["variant_designs"] = designs
    return run_nested_import(
        test_db, project.id, io.BytesIO(json.dumps(payload).encode("utf-8")), admin.id
    )


def _refused(test_db, fn, *args, **kwargs) -> ImportValidationError:
    with pytest.raises(ImportValidationError) as exc:
        fn(*args, **kwargs)
    test_db.rollback()
    return exc.value


def _assignments(test_db, project_id):
    rows = test_db.query(Task.meta, Task.variant_design, Task.variant_unit).filter(
        Task.project_id == project_id
    )
    return sorted(
        (json.dumps(meta["variant"], sort_keys=True), design, unit) for meta, design, unit in rows
    )


@pytest.fixture
def world(test_db, test_users, test_org):
    admin = test_users[0]
    project = _project(test_db, admin, test_org)
    test_db.add(new_design_row(project.id, "swap", copy.deepcopy(SPEC), created_by=admin.id))
    test_db.commit()
    return {"admin": admin, "org": test_org, "project": project}


class TestImportValidation:
    def test_nested_import_accepts_a_valid_design(self, test_db, world):
        result = _nested(test_db, world["project"], world["admin"], full_items())
        assert result["created_tasks"] == 8
        assert {d for _, d, _ in _assignments(test_db, world["project"].id)} == {"swap"}

    @pytest.mark.parametrize(
        "mutate, status",
        [
            (lambda v: v["factors"].update(role="judge"), 422),
            (lambda v: v.update(design="unknown"), 422),
            (lambda v: v.pop("unit"), 422),
            (lambda v: v["spans"].update(facts=[[0, 9999]]), 422),
        ],
    )
    def test_nested_import_rejects_invalid_assignments(self, test_db, world, mutate, status):
        items = full_items()
        mutate(items[3]["meta"]["variant"])
        error = _refused(test_db, _nested, test_db, world["project"], world["admin"], items)
        assert error.status_code == status
        assert "variant" in error.detail
        assert test_db.query(Task).filter(Task.project_id == world["project"].id).count() == 0

    def test_global_meta_counts_too(self, test_db, world):
        payload = {"meta": {"variant": "not an object"}, "data": [{"data": {"facts": "x"}}]}
        error = _refused(
            test_db,
            run_nested_import,
            test_db,
            world["project"].id,
            io.BytesIO(json.dumps(payload).encode()),
            world["admin"].id,
        )
        assert error.status_code == 422

    def test_flat_rows_carry_the_assignment_as_json(self, test_db, world):
        rows = []
        for it in full_items(("u1",)):
            rows.append({**it["data"], "meta.variant": json.dumps(it["meta"]["variant"])})
        _nested(test_db, world["project"], world["admin"], rows)
        tasks = test_db.query(Task).filter(Task.project_id == world["project"].id).all()
        assert len(tasks) == 4
        assert all("meta.variant" not in t.data and t.variant_design == "swap" for t in tasks)
        bad = [{"facts": "x", "meta.variant": json.dumps({"design": "swap"})}]
        error = _refused(test_db, _nested, test_db, world["project"], world["admin"], bad)
        assert error.status_code == 422

    def test_csv_import_with_a_variant_column(self, test_db, world):
        import csv

        def body(items):
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["facts", "meta.variant"])
            for it in items:
                writer.writerow([it["data"]["facts"], json.dumps(it["meta"]["variant"])])
            return io.BytesIO(out.getvalue().encode("utf-8"))

        result = run_tabular_import(
            test_db, world["project"].id, body(full_items(("u1",))), world["admin"].id, "csv"
        )
        assert result["created_tasks"] == 4
        assert len(_assignments(test_db, world["project"].id)) == 4
        broken = full_items(("u2",))
        broken[0]["meta"]["variant"]["factors"]["order"] = "c"
        error = _refused(
            test_db,
            run_tabular_import,
            test_db,
            world["project"].id,
            body(broken),
            world["admin"].id,
            "csv",
        )
        assert error.status_code == 422

    def test_duplicate_cell_is_refused_also_with_reordered_keys(self, test_db, world):
        items = full_items(("u1",))
        twin = item("u1", "claimant", "a", factors={"order": "a", "role": "claimant"})
        error = _refused(
            test_db, _nested, test_db, world["project"], world["admin"], items + [twin]
        )
        assert error.status_code == 409
        assert error.code == "variant_cell_duplicate"

    def test_frozen_design_takes_no_new_tasks(self, test_db, world):
        _nested(test_db, world["project"], world["admin"], full_items(("u1",)))
        freeze_design(test_db, world["project"].id, "swap", world["admin"].id)
        test_db.commit()
        error = _refused(
            test_db, _nested, test_db, world["project"], world["admin"], full_items(("u2",))
        )
        assert error.status_code == 409
        assert error.code == "variant_design_frozen"

    def test_frozen_rows_refuse_raw_sql_edits(self, test_db, world):
        _nested(test_db, world["project"], world["admin"], full_items(("u1",)))
        freeze_design(test_db, world["project"].id, "swap", world["admin"].id)
        test_db.commit()
        task_id = test_db.query(Task.id).filter(Task.project_id == world["project"].id).first()[0]
        from sqlalchemy.exc import DBAPIError

        for statement in (
            "UPDATE tasks SET data = CAST('{\"facts\": \"x\"}' AS json) WHERE id = :id",
            "UPDATE tasks SET meta = CAST('{}' AS json) WHERE id = :id",
        ):
            with pytest.raises(DBAPIError) as exc:
                test_db.execute(text(statement), {"id": task_id})
            assert "variant_design_frozen" in str(exc.value)
            test_db.rollback()
        # Meta beside the assignment stays editable.
        test_db.execute(
            text(
                "UPDATE tasks SET meta = CAST((meta::jsonb || '{\"tags\": [\"x\"]}') AS json) "
                "WHERE id = :id"
            ),
            {"id": task_id},
        )


class TestRoundTrip:
    @pytest.fixture
    def frozen(self, test_db, world):
        _nested(test_db, world["project"], world["admin"], full_items())
        design, report = freeze_design(test_db, world["project"].id, "swap", world["admin"].id)
        test_db.commit()
        assert report["ok"], report
        return design.content_hash

    @pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
    def test_full_export_import_keeps_designs_and_assignments(
        self, test_db, world, frozen, fmt
    ):
        pid = world["project"].id
        if fmt == "ndjson":
            body = "".join(stream_export_ndjson(test_db, pid))
            types = [json.loads(line)["_type"] for line in body.splitlines()]
            assert types.index("variant_design") < types.index("task")
        else:
            body = "".join(stream_comprehensive_project_data_json(test_db, pid))
            assert json.loads(body)["variant_designs"][0]["content_hash"] == frozen
        result = run_full_project_import(
            test_db, io.BytesIO(body.encode("utf-8")), world["admin"].id,
            organization_id=world["org"].id,
        )
        new_pid = result["project_id"]
        assert result["created_variant_designs"] == 1
        assert result["frozen_variant_designs"] == 1
        copy_design = (
            test_db.query(VariantDesign).filter(VariantDesign.project_id == new_pid).one()
        )
        assert copy_design.status == "frozen"
        assert copy_design.content_hash == frozen
        assert copy_design.spec == SPEC
        assert _assignments(test_db, new_pid) == _assignments(test_db, pid)

    def test_tampered_export_is_refused(self, test_db, world, frozen):
        pid = world["project"].id
        doc = json.loads("".join(stream_comprehensive_project_data_json(test_db, pid)))
        # Inside a declared span, so every check still passes; only the hash
        # tells.
        task = next(t for t in doc["tasks"] if t["data"]["facts"].startswith(NAMES["claimant"]))
        task["data"]["facts"] = task["data"]["facts"].replace("Alma Reyes", "Alma Reyez")
        error = _refused(
            test_db,
            run_full_project_import,
            test_db,
            io.BytesIO(json.dumps(doc).encode("utf-8")),
            world["admin"].id,
            organization_id=world["org"].id,
        )
        assert error.status_code == 422
        assert error.code == "variant_design_hash_mismatch"

    def test_broken_invariance_in_an_export_is_reported(self, test_db, world, frozen):
        pid = world["project"].id
        doc = json.loads("".join(stream_comprehensive_project_data_json(test_db, pid)))
        doc["tasks"][0]["data"]["facts"] = doc["tasks"][0]["data"]["facts"].replace("fence", "hedge")
        error = _refused(
            test_db,
            run_full_project_import,
            test_db,
            io.BytesIO(json.dumps(doc).encode("utf-8")),
            world["admin"].id,
            organization_id=world["org"].id,
        )
        assert error.status_code == 409
        assert "invariance" in error.detail and "differs_outside_spans" in error.detail

    def test_full_import_rejects_an_invalid_assignment(self, test_db, world, frozen):
        doc = json.loads("".join(stream_comprehensive_project_data_json(test_db, world["project"].id)))
        doc["tasks"][0]["meta"]["variant"]["factors"]["role"] = "judge"
        error = _refused(
            test_db,
            run_full_project_import,
            test_db,
            io.BytesIO(json.dumps(doc).encode("utf-8")),
            world["admin"].id,
            organization_id=world["org"].id,
        )
        assert error.status_code == 422

    def test_nested_export_import_into_another_project(self, test_db, world, frozen):
        pid = world["project"].id
        doc = json.loads("".join(stream_export_json(test_db, pid, None, {"project_id": pid})))
        assert doc["variant_designs"][0]["status"] == "frozen"
        target = _project(test_db, world["admin"], world["org"], "VD target")
        payload = {k: v for k, v in doc.items() if k != "tasks"}
        payload["data"] = doc["tasks"]
        run_nested_import(
            test_db, target.id, io.BytesIO(json.dumps(payload).encode("utf-8")), world["admin"].id
        )
        copy_design = (
            test_db.query(VariantDesign).filter(VariantDesign.project_id == target.id).one()
        )
        assert (copy_design.status, copy_design.content_hash) == ("frozen", frozen)
        assert _assignments(test_db, target.id) == _assignments(test_db, pid)

    def test_subset_export_carries_drafts(self, test_db, world, frozen):
        pid = world["project"].id
        one = test_db.query(Task.id).filter(Task.project_id == pid).first()[0]
        doc = json.loads("".join(stream_export_json(test_db, pid, [one], {"project_id": pid})))
        assert doc["variant_designs"][0]["status"] == "draft"
        assert doc["variant_designs"][0]["content_hash"] is None

    def test_projects_without_designs_export_as_before(self, test_db, test_users, test_org):
        project = _project(test_db, test_users[0], test_org, "VD none")
        doc = json.loads("".join(stream_comprehensive_project_data_json(test_db, project.id)))
        assert "variant_designs" not in doc

    def test_export_document_round_trip(self, test_db, world, frozen):
        design = test_db.query(VariantDesign).filter(VariantDesign.project_id == world["project"].id).one()
        doc = export_document(design)
        assert doc["format"] == "benger.variant_design.v1"
        assert (doc["status"], doc["content_hash"]) == ("frozen", frozen)


class TestMerge:
    def test_merge_of_the_own_export_matches_assignments(self, test_db, world):
        _nested(test_db, world["project"], world["admin"], full_items(("u1",)))
        pid = world["project"].id
        body = "".join(stream_comprehensive_project_data_json(test_db, pid))
        result = run_merge_import(
            test_db, pid, io.BytesIO(body.encode("utf-8")), world["admin"].id
        )
        assert result["statistics"]["matched_tasks"] == 4

    def test_merge_refuses_a_task_in_another_cell(self, test_db, world):
        _nested(test_db, world["project"], world["admin"], full_items(("u1",)))
        pid = world["project"].id
        doc = json.loads("".join(stream_comprehensive_project_data_json(test_db, pid)))
        doc["tasks"][0]["meta"]["variant"]["unit"] = "u9"
        error = _refused(
            test_db,
            run_merge_import,
            test_db,
            pid,
            io.BytesIO(json.dumps(doc).encode("utf-8")),
            world["admin"].id,
        )
        assert error.status_code == 409
        assert error.code == MERGE_TASK_MISMATCH
        assert "different cell" in error.detail

    def test_merge_refuses_a_different_design(self, test_db, world):
        _nested(test_db, world["project"], world["admin"], full_items(("u1",)))
        pid = world["project"].id
        doc = json.loads("".join(stream_comprehensive_project_data_json(test_db, pid)))
        doc["variant_designs"][0]["spec"]["title"] = "changed"
        error = _refused(
            test_db,
            run_merge_import,
            test_db,
            pid,
            io.BytesIO(json.dumps(doc).encode("utf-8")),
            world["admin"].id,
        )
        assert error.status_code == 409
