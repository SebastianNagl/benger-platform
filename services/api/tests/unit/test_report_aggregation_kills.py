"""
Aggregation / data-completeness mutation kills for report_service.py.

This is the REPORTING side: the per-model numbers it assembles are the
benchmark's published public output. The historical failure mode here is a
model or metric SILENTLY DROPPED or MIS-ATTRIBUTED in the report (see
"export drops korrektur grades"). The existing test_report_service.py is
coverage-shaped (it touches each function once); this file pins EXACT
aggregated values and COMPLETE sets so a mutation that drops, cross-attributes
or wrongly combines a number flips a concrete assertion.

Hand-reasoned rules pinned (from report_service.py:_resolve_per_model_metrics
lines 29-95 and the callers update_report_evaluation_section / charts /
statistics / can_publish):

  R1 COMPLETENESS — every (model, metric) the data contains appears in the
     output with its own value; no pair dropped, none cross-attributed to the
     wrong model (this is the "drops grades" class).
  R2 ASYMMETRY — a model carrying a metric another model lacks keeps its full
     own set; the other model does NOT inherit the extra metric.
  R3 COMBINE = MEAN — when the same (model, metric) appears in several
     TaskEvaluation rows (multiple generations / runs), the resolved value is
     the arithmetic mean of the per-row values (sum(vs)/len(vs)), NOT the sum,
     last, or first.
  R4 SKIP RULES — `raw_score` and any `*_response` key are dropped as audit
     fields; None / non-numeric metric values are skipped; a row whose model
     resolves to "unknown" or whose metrics are empty contributes nothing and
     does NOT poison other models.
  R5 ANNOTATOR ATTRIBUTION — annotation-backed TaskEvaluation rows
     (generation_id IS NULL, annotation_id IS NOT NULL) are attributed to
     "annotator:<display>" where display follows the pseudonym rule
     (pseudonym if use_pseudonym and pseudonym else name or username).
  R6 SECTION WRITE — update_report_evaluation_section persists every
     model+metric into sections.evaluation.metrics with correct values, stamps
     metadata.last_auto_update + sections_completed, and sets can_publish.
  R7 PUBLISH GATE — can_publish_report returns the documented (bool, reason)
     at each boundary (no tasks / no generations / no completed evals / all ok).
  R8 CHARTS / STATS STRUCTURE — get_evaluation_charts_data mirrors every model
     into by_model AND by_method (transposed) with no model dropped;
     get_report_statistics counts are exact.
  R9 EMPTY / EDGE — a project with no evaluations yields an empty-but-valid
     structure (documented zeros, no crash).

All tests are DB-backed via the shared `test_db` fixture (SAVEPOINT-isolated),
the same lane test_report_service.py already uses for this module.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, Task


# ===========================================================================
# Seed helpers — build the TaskEvaluation -> Generation graph that
# _resolve_per_model_metrics actually reads. The existing test_report_service
# fixtures only seed EvaluationRun.metrics (the FALLBACK path); to kill the
# real per-model resolver we must seed TaskEvaluation rows hung off a
# generation (model attribution) or an annotation (annotator attribution).
# ===========================================================================


def _new_project(test_db: Session, user: User, title: str = "Agg Kill Project") -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title=title,
        description="aggregation completeness kills",
        created_by=user.id,
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


def _new_task(test_db: Session, project: Project, inner_id: int) -> Task:
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=inner_id,
        data={"question": f"q{inner_id}", "answer": f"a{inner_id}"},
    )
    test_db.add(task)
    test_db.commit()
    return task


def _new_generation(
    test_db: Session, project: Project, user: User, task: Task, model_id: str, run_index: int
) -> Generation:
    """Create a ResponseGeneration parent + one child Generation for a model."""
    parent = ResponseGeneration(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id=model_id,
        status="completed",
        created_by=user.id,
    )
    test_db.add(parent)
    test_db.flush()

    gen = Generation(
        id=str(uuid.uuid4()),
        generation_id=parent.id,
        task_id=task.id,
        model_id=model_id,
        case_data="case",
        response_content=f"resp-{model_id}",
        run_index=run_index,
        status="completed",
    )
    test_db.add(gen)
    test_db.commit()
    return gen


def _new_eval_run(
    test_db: Session, project: Project, user: User, *, model_id: str = "mixed",
    eval_type_ids=None, status: str = "completed",
) -> EvaluationRun:
    er = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=eval_type_ids if eval_type_ids is not None else ["exact_match"],
        metrics={},  # NOT NULL; resolver reads TaskEvaluation, not this
        status=status,
        created_by=user.id,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow() if status == "completed" else None,
    )
    test_db.add(er)
    test_db.flush()
    jr = EvaluationJudgeRun(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    test_db.add(jr)
    test_db.commit()
    return er, jr


def _add_task_eval(
    test_db: Session, er: EvaluationRun, jr: EvaluationJudgeRun, task: Task, metrics: dict,
    *, generation: Generation = None, annotation: Annotation = None, field_name: str = "exact_match",
) -> TaskEvaluation:
    te = TaskEvaluation(
        id=str(uuid.uuid4()),
        evaluation_id=er.id,
        judge_run_id=jr.id,
        task_id=task.id,
        generation_id=generation.id if generation is not None else None,
        annotation_id=annotation.id if annotation is not None else None,
        field_name=field_name,
        answer_type="text",
        ground_truth="gt",
        prediction="pred",
        metrics=metrics,
        passed=True,
    )
    test_db.add(te)
    test_db.commit()
    return te


def _new_annotation(test_db: Session, project: Project, task: Task, user: User) -> Annotation:
    ann = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result={"answer": "annotated"},
        was_cancelled=False,
        created_at=datetime.utcnow(),
    )
    test_db.add(ann)
    test_db.commit()
    return ann


# ===========================================================================
# R1 / R2 — _resolve_per_model_metrics COMPLETENESS + ASYMMETRY
# ===========================================================================


class TestResolvePerModelCompleteness:
    """The core 'drops grades' guard: every (model, metric) survives,
    nothing is cross-attributed, asymmetric metric sets stay separate."""

    def test_every_model_metric_pair_present_exact_no_cross_attribution(
        self, test_db: Session, test_user
    ):
        """Two models, each with two metrics across one eval -> EVERY pair
        present with EXACT value; the two models keep DISJOINT metric values
        (no cross-attribution of model-b's numbers onto model-a)."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_a = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen_b = _new_generation(test_db, project, test_user, t2, "model-b", 0)
        er, jr = _new_eval_run(test_db, project, test_user)

        # Distinct values per model so cross-attribution is detectable.
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.5, "f1": 0.8}, generation=gen_a)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.9, "f1": 0.2}, generation=gen_b)

        result = _resolve_per_model_metrics(test_db, [er.id])

        # COMPLETENESS: exactly the two models, no more, no fewer.
        assert set(result.keys()) == {"model-a", "model-b"}
        # Each model carries its own complete, exact metric set.
        assert result["model-a"] == {"accuracy": 0.5, "f1": 0.8}
        assert result["model-b"] == {"accuracy": 0.9, "f1": 0.2}

    def test_asymmetric_metric_sets_stay_separate(self, test_db: Session, test_user):
        """model-a has an extra metric model-b lacks. model-a keeps its full
        set; model-b must NOT inherit the extra metric, and model-a keeps the
        shared one too."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_a = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen_b = _new_generation(test_db, project, test_user, t2, "model-b", 0)
        er, jr = _new_eval_run(test_db, project, test_user)

        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.5, "bleu": 0.7}, generation=gen_a)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.6}, generation=gen_b)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"model-a", "model-b"}
        # model-a keeps BOTH its metrics.
        assert set(result["model-a"].keys()) == {"accuracy", "bleu"}
        assert result["model-a"]["accuracy"] == 0.5
        assert result["model-a"]["bleu"] == 0.7
        # model-b keeps ONLY its own metric — does not inherit bleu.
        assert set(result["model-b"].keys()) == {"accuracy"}
        assert result["model-b"]["accuracy"] == 0.6
        assert "bleu" not in result["model-b"]

    def test_metrics_aggregated_across_multiple_evaluation_ids(
        self, test_db: Session, test_user
    ):
        """The same model evaluated across two separate evaluation runs:
        both runs' rows must be merged into one model entry (no run dropped)."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        gen1 = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen2 = _new_generation(test_db, project, test_user, t1, "model-a", 1)
        er1, jr1 = _new_eval_run(test_db, project, test_user)
        er2, jr2 = _new_eval_run(test_db, project, test_user)

        _add_task_eval(test_db, er1, jr1, t1, {"accuracy": 0.4}, generation=gen1)
        _add_task_eval(test_db, er2, jr2, t1, {"accuracy": 0.8}, generation=gen2)

        # Pass BOTH evaluation ids: rows from both runs feed one model bucket.
        result = _resolve_per_model_metrics(test_db, [er1.id, er2.id])

        assert set(result.keys()) == {"model-a"}
        # MEAN of 0.4 and 0.8 = 0.6 (R3 combine rule across runs).
        assert result["model-a"]["accuracy"] == pytest.approx(0.6)

    def test_evaluation_id_filter_excludes_unlisted_runs(self, test_db: Session, test_user):
        """A row whose evaluation_id is NOT in the passed list must not leak
        into the result (filter completeness in the other direction)."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        gen1 = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen2 = _new_generation(test_db, project, test_user, t1, "model-b", 1)
        er1, jr1 = _new_eval_run(test_db, project, test_user)
        er2, jr2 = _new_eval_run(test_db, project, test_user)

        _add_task_eval(test_db, er1, jr1, t1, {"accuracy": 0.5}, generation=gen1)
        _add_task_eval(test_db, er2, jr2, t1, {"accuracy": 0.9}, generation=gen2)

        # Only er1 requested -> only model-a appears.
        result = _resolve_per_model_metrics(test_db, [er1.id])
        assert set(result.keys()) == {"model-a"}
        assert result["model-a"] == {"accuracy": 0.5}


# ===========================================================================
# R3 — COMBINE = MEAN (the mean<->sum / overwrite<->average mutation)
# ===========================================================================


class TestAggregationIsMean:
    def test_same_model_metric_across_rows_is_mean_not_sum_not_last(
        self, test_db: Session, test_user
    ):
        """Three rows for one (model, metric): result is the MEAN. The chosen
        values make mean/sum/last/first all DISTINCT so any wrong combine
        flips the assertion.
            values = [0.2, 0.5, 0.8]
            mean = 0.5   sum = 1.5   last = 0.8   first = 0.2
        """
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        tasks = [_new_task(test_db, project, i) for i in range(1, 4)]
        er, jr = _new_eval_run(test_db, project, test_user)
        for i, (task, val) in enumerate(zip(tasks, [0.2, 0.5, 0.8])):
            gen = _new_generation(test_db, project, test_user, task, "model-a", i)
            _add_task_eval(test_db, er, jr, task, {"accuracy": val}, generation=gen)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"model-a"}
        assert result["model-a"]["accuracy"] == pytest.approx(0.5)  # mean
        assert result["model-a"]["accuracy"] != pytest.approx(1.5)  # not sum
        assert result["model-a"]["accuracy"] != pytest.approx(0.8)  # not last
        assert result["model-a"]["accuracy"] != pytest.approx(0.2)  # not first

    def test_per_metric_means_are_independent(self, test_db: Session, test_user):
        """Two metrics on the same model average independently — the mean of
        one must not bleed into the other."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        er, jr = _new_eval_run(test_db, project, test_user)
        g1 = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        g2 = _new_generation(test_db, project, test_user, t2, "model-a", 1)
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.2, "f1": 1.0}, generation=g1)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.4, "f1": 0.0}, generation=g2)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert result["model-a"]["accuracy"] == pytest.approx(0.3)  # mean(0.2,0.4)
        assert result["model-a"]["f1"] == pytest.approx(0.5)  # mean(1.0,0.0)


# ===========================================================================
# R4 — SKIP RULES (audit fields, None/non-numeric, unknown/empty don't poison)
# ===========================================================================


class TestSkipRules:
    def test_audit_fields_dropped_real_metrics_kept(self, test_db: Session, test_user):
        """raw_score and *_response keys are audit fields and must NOT appear;
        real numeric metrics in the same dict survive with exact values."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        gen = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        er, jr = _new_eval_run(test_db, project, test_user)
        _add_task_eval(
            test_db, er, jr, t1,
            {
                "accuracy": 0.7,
                "raw_score": 42.0,          # audit -> dropped
                "judge_response": 3.0,      # *_response -> dropped
                "model_response": 9.0,      # *_response -> dropped
            },
            generation=gen,
        )

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"model-a"}
        assert set(result["model-a"].keys()) == {"accuracy"}
        assert result["model-a"]["accuracy"] == 0.7
        assert "raw_score" not in result["model-a"]
        assert "judge_response" not in result["model-a"]
        assert "model_response" not in result["model-a"]

    def test_none_and_non_numeric_metric_values_skipped(self, test_db: Session, test_user):
        """None and string metric values are skipped; the numeric sibling on
        the same model survives. A skipped value must not produce a key with a
        bogus number, nor drop the whole model."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        gen = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        er, jr = _new_eval_run(test_db, project, test_user)
        _add_task_eval(
            test_db, er, jr, t1,
            {"accuracy": 0.6, "broken": None, "label": "good"},
            generation=gen,
        )

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"model-a"}
        assert set(result["model-a"].keys()) == {"accuracy"}
        assert result["model-a"]["accuracy"] == 0.6

    def test_null_metric_does_not_poison_mean_of_other_rows(
        self, test_db: Session, test_user
    ):
        """A row whose metric value is None contributes NOTHING to that
        metric's list; the mean is taken only over the real rows. Two real
        rows 0.4 and 0.6 plus one None -> mean 0.5 (not 0.333 from counting
        the None as a third sample, not None-poisoned)."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        tasks = [_new_task(test_db, project, i) for i in range(1, 4)]
        er, jr = _new_eval_run(test_db, project, test_user)
        vals = [0.4, 0.6, None]
        for i, (task, val) in enumerate(zip(tasks, vals)):
            gen = _new_generation(test_db, project, test_user, task, "model-a", i)
            _add_task_eval(test_db, er, jr, task, {"accuracy": val}, generation=gen)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert result["model-a"]["accuracy"] == pytest.approx(0.5)

    def test_unknown_model_row_excluded_and_does_not_poison_others(
        self, test_db: Session, test_user
    ):
        """A generation whose model_id == 'unknown' is excluded entirely, and
        a real model in the same eval is unaffected (no crash, no leak)."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_unknown = _new_generation(test_db, project, test_user, t1, "unknown", 0)
        gen_real = _new_generation(test_db, project, test_user, t2, "model-a", 1)
        er, jr = _new_eval_run(test_db, project, test_user)
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.99}, generation=gen_unknown)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.5}, generation=gen_real)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"model-a"}
        assert result["model-a"]["accuracy"] == 0.5

    def test_empty_metrics_row_drops_model_with_no_real_values(
        self, test_db: Session, test_user
    ):
        """A row whose metrics dict is empty contributes nothing; if that is
        the model's only row, the model does not appear (no empty {} entry)."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_empty = _new_generation(test_db, project, test_user, t1, "model-empty", 0)
        gen_real = _new_generation(test_db, project, test_user, t2, "model-a", 1)
        er, jr = _new_eval_run(test_db, project, test_user)
        _add_task_eval(test_db, er, jr, t1, {}, generation=gen_empty)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.5}, generation=gen_real)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"model-a"}
        assert "model-empty" not in result

    def test_empty_evaluation_ids_returns_empty_dict(self, test_db: Session):
        """The documented early-return: no ids -> {} (R9 edge)."""
        from report_service import _resolve_per_model_metrics

        assert _resolve_per_model_metrics(test_db, []) == {}


# ===========================================================================
# R5 — ANNOTATOR ATTRIBUTION (the human-leaderboard merge path)
# ===========================================================================


class TestAnnotatorAttribution:
    def test_annotation_rows_attributed_to_annotator_display_name(
        self, test_db: Session, test_user
    ):
        """An annotation-backed TaskEvaluation (no generation) is attributed
        to 'annotator:<name>'. test_user has no pseudonym, so display = name.
        Also confirms the generation path and annotation path MERGE into one
        result dict, each keeping its own model key + metric."""
        from report_service import _resolve_per_model_metrics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        ann = _new_annotation(test_db, project, t2, test_user)
        er, jr = _new_eval_run(test_db, project, test_user)

        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.5}, generation=gen)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.9}, annotation=ann)

        result = _resolve_per_model_metrics(test_db, [er.id])

        # test_user.name == "Generation Test User" (no pseudonym set).
        expected_annotator_key = f"annotator:{test_user.name}"
        assert set(result.keys()) == {"model-a", expected_annotator_key}
        assert result["model-a"]["accuracy"] == 0.5
        assert result[expected_annotator_key]["accuracy"] == 0.9

    def test_annotator_uses_pseudonym_when_enabled(self, test_db: Session):
        """display = pseudonym when use_pseudonym AND pseudonym set; the real
        name must NOT be used as the key."""
        from report_service import _resolve_per_model_metrics

        pseudo_user = User(
            id=str(uuid.uuid4()),
            username="realuser",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            name="Real Name",
            hashed_password="x",
            pseudonym="Anonymous-Grader-7",
            use_pseudonym=True,
            is_active=True,
        )
        test_db.add(pseudo_user)
        test_db.commit()

        project = _new_project(test_db, pseudo_user)
        t1 = _new_task(test_db, project, 1)
        ann = _new_annotation(test_db, project, t1, pseudo_user)
        er, jr = _new_eval_run(test_db, project, pseudo_user)
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.77}, annotation=ann)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"annotator:Anonymous-Grader-7"}
        assert "annotator:Real Name" not in result
        assert result["annotator:Anonymous-Grader-7"]["accuracy"] == 0.77

    def test_annotator_falls_back_to_name_when_pseudonym_off(self, test_db: Session):
        """use_pseudonym=False -> display = name even if a pseudonym exists."""
        from report_service import _resolve_per_model_metrics

        u = User(
            id=str(uuid.uuid4()),
            username="uname",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            name="Visible Name",
            hashed_password="x",
            pseudonym="Hidden-Pseudo",
            use_pseudonym=False,
            is_active=True,
        )
        test_db.add(u)
        test_db.commit()

        project = _new_project(test_db, u)
        t1 = _new_task(test_db, project, 1)
        ann = _new_annotation(test_db, project, t1, u)
        er, jr = _new_eval_run(test_db, project, u)
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.33}, annotation=ann)

        result = _resolve_per_model_metrics(test_db, [er.id])

        assert set(result.keys()) == {"annotator:Visible Name"}
        assert result["annotator:Visible Name"]["accuracy"] == 0.33


# ===========================================================================
# R6 — update_report_evaluation_section persists the full matrix + metadata
# ===========================================================================


class TestEvaluationSectionWrite:
    def test_section_carries_every_model_metric_and_stamps_metadata(
        self, test_db: Session, test_user
    ):
        """The written evaluation section must contain the complete per-model
        metric matrix (resolved from TaskEvaluation, not the empty
        EvaluationRun.metrics fallback) AND stamp metadata."""
        from report_service import (
            create_initial_report_draft,
            update_report_evaluation_section,
        )

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_a = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen_b = _new_generation(test_db, project, test_user, t2, "model-b", 0)
        er, jr = _new_eval_run(
            test_db, project, test_user, eval_type_ids=["exact_match", "f1"]
        )
        _add_task_eval(test_db, er, jr, t1, {"exact_match": 0.5, "f1": 0.8}, generation=gen_a)
        _add_task_eval(test_db, er, jr, t2, {"exact_match": 0.9, "f1": 0.2}, generation=gen_b)

        create_initial_report_draft(test_db, project.id, test_user.id)
        report = update_report_evaluation_section(test_db, project.id)

        section = report.content["sections"]["evaluation"]
        assert section["status"] == "completed"

        metrics = section["metrics"]
        # COMPLETENESS: both models, full exact matrices, no cross-attribution.
        assert set(metrics.keys()) == {"model-a", "model-b"}
        assert metrics["model-a"] == {"exact_match": 0.5, "f1": 0.8}
        assert metrics["model-b"] == {"exact_match": 0.9, "f1": 0.2}

        # methods are the dedup'd evaluation_type_ids.
        assert set(section["methods"]) == {"exact_match", "f1"}

        # metadata stamped: section recorded + a timestamp written.
        assert "evaluation" in report.content["metadata"]["sections_completed"]
        assert report.content["metadata"]["last_auto_update"] is not None

    def test_section_excludes_non_completed_evaluation_runs(
        self, test_db: Session, test_user
    ):
        """Only status=='completed' EvaluationRuns feed the section. A pending
        run's model must not appear."""
        from report_service import (
            create_initial_report_draft,
            update_report_evaluation_section,
        )

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_done = _new_generation(test_db, project, test_user, t1, "model-done", 0)
        gen_pending = _new_generation(test_db, project, test_user, t2, "model-pending", 1)
        er_done, jr_done = _new_eval_run(test_db, project, test_user, status="completed")
        er_pending, jr_pending = _new_eval_run(test_db, project, test_user, status="pending")
        _add_task_eval(test_db, er_done, jr_done, t1, {"accuracy": 0.5}, generation=gen_done)
        _add_task_eval(test_db, er_pending, jr_pending, t2, {"accuracy": 0.9}, generation=gen_pending)

        create_initial_report_draft(test_db, project.id, test_user.id)
        report = update_report_evaluation_section(test_db, project.id)

        metrics = report.content["sections"]["evaluation"]["metrics"]
        assert set(metrics.keys()) == {"model-done"}
        assert "model-pending" not in metrics

    def test_section_falls_back_to_evaluation_run_metrics_when_no_task_evals(
        self, test_db: Session, test_user
    ):
        """When no TaskEvaluation rows exist, the resolver returns {} and the
        section falls back to EvaluationRun.model_id -> EvaluationRun.metrics
        (the direct-evaluation path). Pins that the fallback still produces the
        right per-model matrix."""
        from report_service import (
            create_initial_report_draft,
            update_report_evaluation_section,
        )

        project = _new_project(test_db, test_user)
        # Direct EvaluationRuns carrying their own metrics, no TaskEvaluations.
        er1 = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            model_id="gpt-4",
            evaluation_type_ids=["exact_match"],
            metrics={"exact_match": 0.85},
            status="completed",
            created_by=test_user.id,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        er2 = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            model_id="claude-3-opus",
            evaluation_type_ids=["exact_match"],
            metrics={"exact_match": 0.82},
            status="completed",
            created_by=test_user.id,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        test_db.add_all([er1, er2])
        test_db.commit()

        create_initial_report_draft(test_db, project.id, test_user.id)
        report = update_report_evaluation_section(test_db, project.id)

        metrics = report.content["sections"]["evaluation"]["metrics"]
        assert set(metrics.keys()) == {"gpt-4", "claude-3-opus"}
        assert metrics["gpt-4"]["exact_match"] == 0.85
        assert metrics["claude-3-opus"]["exact_match"] == 0.82


# ===========================================================================
# R7 — can_publish_report gate (boolean + exact reason at each boundary)
# ===========================================================================


class TestCanPublishGate:
    def test_no_report_blocks_with_report_not_found(self, test_db: Session, test_user):
        from report_service import can_publish_report

        project = _new_project(test_db, test_user)
        ok, reason = can_publish_report(test_db, project.id)
        assert ok is False
        assert reason == "Report not found"

    def test_no_tasks_blocks_with_tasks_reason(self, test_db: Session, test_user):
        from report_service import can_publish_report, create_initial_report_draft

        project = _new_project(test_db, test_user)
        create_initial_report_draft(test_db, project.id, test_user.id)
        ok, reason = can_publish_report(test_db, project.id)
        assert ok is False
        assert reason == "Project must have tasks"

    def test_no_generations_blocks_with_generation_reason(self, test_db: Session, test_user):
        from report_service import can_publish_report, create_initial_report_draft

        project = _new_project(test_db, test_user)
        _new_task(test_db, project, 1)
        create_initial_report_draft(test_db, project.id, test_user.id)
        ok, reason = can_publish_report(test_db, project.id)
        assert ok is False
        assert reason == "Project must have LLM generations"

    def test_no_completed_eval_blocks_with_evaluation_reason(
        self, test_db: Session, test_user
    ):
        from report_service import can_publish_report, create_initial_report_draft

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        _new_generation(test_db, project, test_user, t1, "model-a", 0)
        create_initial_report_draft(test_db, project.id, test_user.id)
        ok, reason = can_publish_report(test_db, project.id)
        assert ok is False
        assert reason == "Project must have completed evaluations"

    def test_pending_eval_does_not_satisfy_gate(self, test_db: Session, test_user):
        """A non-completed evaluation run must NOT count toward the gate."""
        from report_service import can_publish_report, create_initial_report_draft

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        _new_generation(test_db, project, test_user, t1, "model-a", 0)
        _new_eval_run(test_db, project, test_user, status="pending")
        create_initial_report_draft(test_db, project.id, test_user.id)
        ok, reason = can_publish_report(test_db, project.id)
        assert ok is False
        assert reason == "Project must have completed evaluations"

    def test_all_requirements_met_allows_publish(self, test_db: Session, test_user):
        from report_service import can_publish_report, create_initial_report_draft

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        _new_generation(test_db, project, test_user, t1, "model-a", 0)
        _new_eval_run(test_db, project, test_user, status="completed")
        create_initial_report_draft(test_db, project.id, test_user.id)
        ok, reason = can_publish_report(test_db, project.id)
        assert ok is True
        assert reason == "All requirements met"


# ===========================================================================
# R8 — get_evaluation_charts_data / get_report_statistics structure + counts
# ===========================================================================


class TestChartsAndStatistics:
    def test_charts_mirror_every_model_into_by_model_and_by_method(
        self, test_db: Session, test_user
    ):
        """by_model and by_method are TRANSPOSES of the same matrix; every
        (model, metric) must appear in BOTH with the exact value. A drop on
        either side, or a transpose bug, flips an assertion."""
        from report_service import get_evaluation_charts_data

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        gen_a = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen_b = _new_generation(test_db, project, test_user, t2, "model-b", 0)
        er, jr = _new_eval_run(test_db, project, test_user)
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.5, "f1": 0.8}, generation=gen_a)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.9, "f1": 0.2}, generation=gen_b)

        data = get_evaluation_charts_data(test_db, project.id)

        # by_model: full per-model matrix.
        assert set(data["by_model"].keys()) == {"model-a", "model-b"}
        assert data["by_model"]["model-a"] == {"accuracy": 0.5, "f1": 0.8}
        assert data["by_model"]["model-b"] == {"accuracy": 0.9, "f1": 0.2}

        # by_method: transposed — metric -> {model: value}. Same numbers.
        assert set(data["by_method"].keys()) == {"accuracy", "f1"}
        assert data["by_method"]["accuracy"] == {"model-a": 0.5, "model-b": 0.9}
        assert data["by_method"]["f1"] == {"model-a": 0.8, "model-b": 0.2}

    def test_charts_empty_for_project_with_no_evaluations(self, test_db: Session, test_user):
        """R9 edge: no evaluations -> empty-but-valid structure, no crash."""
        from report_service import get_evaluation_charts_data

        project = _new_project(test_db, test_user)
        data = get_evaluation_charts_data(test_db, project.id)
        assert data == {"by_model": {}, "by_method": {}, "metric_metadata": {}}

    def test_statistics_counts_are_exact(self, test_db: Session, test_user):
        """task/annotation/participant/model counts are each exact and
        independent. Seed asymmetric counts so a swapped count is detectable."""
        from report_service import get_report_statistics

        project = _new_project(test_db, test_user)
        tasks = [_new_task(test_db, project, i) for i in range(1, 5)]  # 4 tasks
        # 2 annotations by the same single participant.
        _new_annotation(test_db, project, tasks[0], test_user)
        _new_annotation(test_db, project, tasks[1], test_user)
        # 3 distinct models across generations.
        _new_generation(test_db, project, test_user, tasks[0], "model-a", 0)
        _new_generation(test_db, project, test_user, tasks[1], "model-b", 0)
        _new_generation(test_db, project, test_user, tasks[2], "model-c", 0)

        stats = get_report_statistics(test_db, project.id)

        assert stats["task_count"] == 4
        assert stats["annotation_count"] == 2
        assert stats["participant_count"] == 1
        assert stats["model_count"] == 3

    def test_statistics_excludes_cancelled_annotations(self, test_db: Session, test_user):
        """A was_cancelled annotation must not be counted (annotation_count
        and participant_count both filter it out)."""
        from report_service import get_report_statistics

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        _new_annotation(test_db, project, t1, test_user)
        cancelled = Annotation(
            id=str(uuid.uuid4()),
            task_id=t2.id,
            project_id=project.id,
            completed_by=test_user.id,
            result={"answer": "x"},
            was_cancelled=True,
            created_at=datetime.utcnow(),
        )
        test_db.add(cancelled)
        test_db.commit()

        stats = get_report_statistics(test_db, project.id)
        assert stats["task_count"] == 2
        assert stats["annotation_count"] == 1  # cancelled excluded

    def test_statistics_batch_matches_single_and_zeros_for_empty(
        self, test_db: Session, test_user
    ):
        """The batched aggregation must produce the same per-project numbers
        as the single-project path, and emit documented zeros for a project
        with no data (no missing key, no crash)."""
        from report_service import get_report_statistics, get_report_statistics_batch

        p1 = _new_project(test_db, test_user, title="P1")
        tasks = [_new_task(test_db, p1, i) for i in range(1, 4)]  # 3 tasks
        _new_annotation(test_db, p1, tasks[0], test_user)
        _new_generation(test_db, p1, test_user, tasks[0], "model-a", 0)
        _new_generation(test_db, p1, test_user, tasks[1], "model-b", 0)

        p_empty = _new_project(test_db, test_user, title="Empty")

        single = get_report_statistics(test_db, p1.id)
        batch = get_report_statistics_batch(test_db, [p1.id, p_empty.id])

        assert batch[p1.id] == single
        assert batch[p1.id]["task_count"] == 3
        assert batch[p1.id]["model_count"] == 2
        # Empty project -> all-zero envelope, present (not missing).
        assert batch[p_empty.id] == {
            "task_count": 0,
            "annotation_count": 0,
            "participant_count": 0,
            "model_count": 0,
        }

    def test_statistics_batch_empty_input_returns_empty(self, test_db: Session):
        from report_service import get_report_statistics_batch

        assert get_report_statistics_batch(test_db, []) == {}


# ===========================================================================
# R8 (cont.) — get_report_models / get_report_participants completeness
# ===========================================================================


class TestModelsAndParticipants:
    def test_report_models_unique_and_complete_filtered_by_project(
        self, test_db: Session, test_user
    ):
        """All distinct models of THIS project are returned (deduped), and a
        different project's model does not leak in."""
        from report_service import get_report_models

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        _new_generation(test_db, project, test_user, t1, "model-a", 0)
        _new_generation(test_db, project, test_user, t2, "model-a", 1)  # dup model
        _new_generation(test_db, project, test_user, t2, "model-b", 2)

        other = _new_project(test_db, test_user, title="Other")
        ot = _new_task(test_db, other, 1)
        _new_generation(test_db, other, test_user, ot, "leak-model", 0)

        models = get_report_models(test_db, project.id)
        assert set(models) == {"model-a", "model-b"}
        assert "leak-model" not in models

    def test_report_participants_counts_exact_and_complete(self, test_db: Session, test_user):
        """Each annotator appears once with their exact contribution count;
        cancelled annotations are excluded from the count."""
        from report_service import get_report_participants

        # A second annotator.
        u2 = User(
            id=str(uuid.uuid4()),
            username="annot2",
            email=f"{uuid.uuid4().hex[:8]}@test.com",
            name="Annotator Two",
            hashed_password="x",
            is_active=True,
        )
        test_db.add(u2)
        test_db.commit()

        project = _new_project(test_db, test_user)
        tasks = [_new_task(test_db, project, i) for i in range(1, 5)]
        # test_user: 2 valid annotations; u2: 1 valid annotation.
        _new_annotation(test_db, project, tasks[0], test_user)
        _new_annotation(test_db, project, tasks[1], test_user)
        _new_annotation(test_db, project, tasks[2], u2)

        participants = get_report_participants(test_db, project.id)
        by_id = {p["id"]: p["annotation_count"] for p in participants}

        assert set(by_id.keys()) == {test_user.id, u2.id}
        assert by_id[test_user.id] == 2
        assert by_id[u2.id] == 1


# ===========================================================================
# R6 + R9 — create_or_update_report_from_existing_data full assembly + empty
# ===========================================================================


class TestCreateOrUpdateFullAssembly:
    def test_full_assembly_carries_complete_metric_matrix(
        self, test_db: Session, test_user
    ):
        """The retroactive assembler resolves the SAME per-model matrix into
        the evaluation section and marks every populated section completed."""
        from report_service import create_or_update_report_from_existing_data

        project = _new_project(test_db, test_user)
        t1 = _new_task(test_db, project, 1)
        t2 = _new_task(test_db, project, 2)
        _new_annotation(test_db, project, t1, test_user)
        gen_a = _new_generation(test_db, project, test_user, t1, "model-a", 0)
        gen_b = _new_generation(test_db, project, test_user, t2, "model-b", 0)
        er, jr = _new_eval_run(test_db, project, test_user)
        _add_task_eval(test_db, er, jr, t1, {"accuracy": 0.5}, generation=gen_a)
        _add_task_eval(test_db, er, jr, t2, {"accuracy": 0.9}, generation=gen_b)

        report = create_or_update_report_from_existing_data(
            test_db, project.id, test_user.id
        )

        sections = report.content["sections"]
        assert sections["data"]["status"] == "completed"
        assert sections["annotations"]["status"] == "completed"
        assert sections["generation"]["status"] == "completed"
        assert sections["evaluation"]["status"] == "completed"

        metrics = sections["evaluation"]["metrics"]
        assert set(metrics.keys()) == {"model-a", "model-b"}
        assert metrics["model-a"]["accuracy"] == 0.5
        assert metrics["model-b"]["accuracy"] == 0.9

        # can_publish requires data + generation + evaluation, all present.
        assert report.content["metadata"]["can_publish"] is True

    def test_empty_project_yields_pending_sections_and_no_publish(
        self, test_db: Session, test_user
    ):
        """R9: a project with NO tasks/annotations/generations/evaluations ->
        sections stay pending, can_publish False, no crash."""
        from report_service import create_or_update_report_from_existing_data

        project = _new_project(test_db, test_user)
        report = create_or_update_report_from_existing_data(
            test_db, project.id, test_user.id
        )

        sections = report.content["sections"]
        assert sections["project_info"]["status"] == "completed"
        assert sections["data"]["status"] == "pending"
        assert sections["annotations"]["status"] == "pending"
        assert sections["generation"]["status"] == "pending"
        assert sections["evaluation"]["status"] == "pending"
        assert report.content["metadata"]["can_publish"] is False
