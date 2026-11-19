"""Inter-annotator agreement per control (shared/annotator_agreement.py).

The expected numbers are computed by hand in the comments, independently of
``bg_statistics``, so the test pins the formulas and not just the wiring.
"""

import pytest

from annotator_agreement import MAX_PAIRS_PER_CONTROL, agreement_by_control


def _choice(name, *choices):
    return {"from_name": name, "to_name": "text", "type": "choices", "value": {"choices": list(choices)}}


def _rating(name, value):
    return {"from_name": name, "to_name": "text", "type": "rating", "value": {"rating": value}}


def _number(name, value):
    return {"from_name": name, "to_name": "text", "type": "number", "value": {"number": value}}


def _text(name, value):
    return {"from_name": name, "to_name": "text", "type": "textarea", "value": {"text": [value]}}


def _row(task, user, *results, pseudonym=None):
    return {"task_id": task, "completed_by": user, "result": list(results), "pseudonym": pseudonym}


# Three annotators label four tasks with "x" or "y":
#
#   task  A  B  C   counts (x, y)   P_i = (sum n_ij^2 - n) / (n (n - 1))
#   t1    x  x  x   (3, 0)          (9 - 3) / 6 = 1
#   t2    x  x  y   (2, 1)          (4 + 1 - 3) / 6 = 1/3
#   t3    y  y  y   (0, 3)          1
#   t4    x  y  y   (1, 2)          1/3
#
# P_bar = (1 + 1/3 + 1 + 1/3) / 4 = 2/3; p_x = 6/12 = p_y, so P_e = 1/2.
# Fleiss' kappa = (2/3 - 1/2) / (1 - 1/2) = 1/3.
#
# Cohen's kappa per pair, kappa = (p_o - p_e) / (1 - p_e):
#   A-B: p_o = 3/4; A has x 3/4, B has x 2/4: p_e = 3/4*2/4 + 1/4*2/4 = 1/2;  kappa = 1/2
#   A-C: p_o = 2/4; C has x 1/4: p_e = 3/4*1/4 + 1/4*3/4 = 3/8;              kappa = (1/2 - 3/8) / (5/8) = 1/5
#   B-C: p_o = 3/4; p_e = 2/4*1/4 + 2/4*3/4 = 1/2;                            kappa = 1/2
# Mean pairwise kappa = (1/2 + 1/5 + 1/2) / 3 = 2/5. All three agree on t1 and t3: 2/4.
LABELS = {
    "t1": ("x", "x", "x"),
    "t2": ("x", "x", "y"),
    "t3": ("y", "y", "y"),
    "t4": ("x", "y", "y"),
}


def _three_annotator_rows():
    rows = []
    for task, values in LABELS.items():
        for user, value in zip(("user-a", "user-b", "user-c"), values):
            rows.append(_row(task, user, _choice("label", value), pseudonym=f"Pseudo {user[-1].upper()}"))
    return rows


def test_fleiss_and_cohen_equal_hand_computed_values():
    result = agreement_by_control(_three_annotator_rows())

    assert result["overlap_task_count"] == 4
    assert result["annotator_count"] == 3
    (label,) = result["controls"]
    assert label["control"] == "label"
    assert label["type"] == "choices"
    assert label["score_type"] == "categorical"
    assert label["multi_select"] is False
    assert label["n_items"] == 4
    assert label["n_annotators"] == 3
    assert label["n_annotations"] == 12
    assert label["categories"] == ["x", "y"]
    assert label["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)
    assert label["percent_agreement"] == pytest.approx(0.5)
    assert label["cohens_kappa_mean"] == pytest.approx(2 / 5, abs=1e-4)

    pairs = {(p["annotator_a"], p["annotator_b"]): p for p in label["pairs"]}
    assert pairs[("Pseudo A", "Pseudo B")]["cohens_kappa"] == pytest.approx(0.5, abs=1e-4)
    assert pairs[("Pseudo A", "Pseudo C")]["cohens_kappa"] == pytest.approx(0.2, abs=1e-4)
    assert pairs[("Pseudo B", "Pseudo C")]["cohens_kappa"] == pytest.approx(0.5, abs=1e-4)
    assert all(p["n_items"] == 4 for p in label["pairs"])
    assert label["pairs_total"] == 3


def test_two_annotators_cohen_and_fleiss():
    # A: x x y y x, B: x y y y x. p_o = 4/5; A has x 3/5, B has x 2/5:
    # p_e = 3/5*2/5 + 2/5*3/5 = 12/25; Cohen = (4/5 - 12/25) / (13/25) = 8/13.
    # Fleiss: p_x = 5/10 = p_y, P_e = 1/2; P_i is 1 for agreeing tasks and 0
    # otherwise, P_bar = 4/5; Fleiss = (4/5 - 1/2) / (1/2) = 3/5.
    a = "x x y y x".split()
    b = "x y y y x".split()
    rows = [_row(f"t{i}", "a", _choice("label", v)) for i, v in enumerate(a)]
    rows += [_row(f"t{i}", "b", _choice("label", v)) for i, v in enumerate(b)]

    (label,) = agreement_by_control(rows)["controls"]
    assert label["cohens_kappa_mean"] == pytest.approx(8 / 13, abs=1e-4)
    assert label["pairs"][0]["cohens_kappa"] == pytest.approx(8 / 13, abs=1e-4)
    assert label["fleiss_kappa"] == pytest.approx(3 / 5, abs=1e-4)
    assert label["percent_agreement"] == pytest.approx(4 / 5)


def test_number_controls_report_pearson_and_mean_absolute_deviation():
    # B = A + 1 on every task: r = 1; each task deviates 0.5 from its mean.
    rows = []
    for i, value in enumerate([1, 2, 3, 4]):
        rows.append(_row(f"t{i}", "a", _number("score", value)))
        rows.append(_row(f"t{i}", "b", _number("score", value + 1)))

    (score,) = agreement_by_control(rows)["controls"]
    assert score["score_type"] == "numeric"
    assert score["pearson_r_mean"] == pytest.approx(1.0)
    assert score["pairs"][0]["pearson_r"] == pytest.approx(1.0)
    assert score["mean_absolute_deviation"] == pytest.approx(0.5)
    assert score["fleiss_kappa"] is None and score["cohens_kappa_mean"] is None


def test_ratings_are_ordinal_and_scored_with_kappa():
    rows = []
    for i, (a, b) in enumerate([(1, 1), (2, 2), (3, 3), (4, 5)]):
        rows.append(_row(f"t{i}", "a", _rating("stars", a)))
        rows.append(_row(f"t{i}", "b", _rating("stars", b)))

    (stars,) = agreement_by_control(rows)["controls"]
    assert stars["score_type"] == "ordinal"
    assert stars["categories"] == ["1", "2", "3", "4", "5"]
    assert stars["percent_agreement"] == pytest.approx(0.75)
    # Unweighted kappa by hand. Cohen: p_o = 3/4, p_e = 3 * (1/4 * 1/4) = 3/16,
    # kappa = (3/4 - 3/16) / (1 - 3/16) = 9/13. Fleiss: P_bar = 3/4,
    # p_j = (1/4, 1/4, 1/4, 1/8, 1/8), P_e = 7/32, kappa = 0.68.
    assert stars["cohens_kappa_mean"] == pytest.approx(9 / 13, abs=1e-4)
    assert stars["fleiss_kappa"] == pytest.approx(0.68, abs=1e-4)


def test_multi_select_counts_a_set_of_choices_as_one_category():
    rows = [
        _row("t1", "a", _choice("tags", "p", "q")),
        _row("t1", "b", _choice("tags", "q", "p")),  # same set, other order: agree
        _row("t2", "a", _choice("tags", "p")),
        _row("t2", "b", _choice("tags", "p", "q")),  # different sets: disagree
    ]
    (tags,) = agreement_by_control(rows)["controls"]
    assert tags["multi_select"] is True
    assert tags["categories"] == ["p", "p + q"]
    assert tags["percent_agreement"] == pytest.approx(0.5)


def test_single_annotator_tasks_and_unanswered_controls_are_ignored():
    rows = _three_annotator_rows()
    # A fifth task with one annotator changes nothing.
    rows.append(_row("t5", "user-a", _choice("label", "y")))
    # A control only one annotator answered on a shared task has no overlap.
    rows.append(_row("t1", "user-d", _choice("other", "z")))
    result = agreement_by_control(rows)
    assert [c["control"] for c in result["controls"]] == ["label"]
    assert result["controls"][0]["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)
    assert result["overlap_task_count"] == 4
    assert result["annotator_count"] == 4


def test_text_controls_are_listed_as_unsupported():
    rows = [
        _row("t1", "a", _choice("label", "x"), _text("comment", "fine")),
        _row("t1", "b", _choice("label", "x"), _text("comment", "ok")),
        _row("t2", "a", _choice("label", "y")),
        _row("t2", "b", _choice("label", "y")),
    ]
    result = agreement_by_control(rows)
    assert [c["control"] for c in result["controls"]] == ["label"]
    assert result["unsupported_controls"] == [{"control": "comment", "type": "textarea"}]


def test_no_overlap_returns_none():
    rows = [_row("t1", "a", _choice("label", "x")), _row("t2", "b", _choice("label", "x"))]
    assert agreement_by_control(rows) is None
    assert agreement_by_control([]) is None


def test_annotators_are_labelled_by_pseudonym_or_neutral_id():
    rows = [
        _row("t1", "0123456789abcdef", _choice("label", "x"), pseudonym=None),
        _row("t1", "fedcba9876543210", _choice("label", "y"), pseudonym="Owl"),
        _row("t2", "0123456789abcdef", _choice("label", "x"), pseudonym=None),
        _row("t2", "fedcba9876543210", _choice("label", "x"), pseudonym="Owl"),
    ]
    (pair,) = agreement_by_control(rows)["controls"][0]["pairs"]
    # Pairs read in label order, whatever the account ids.
    assert (pair["annotator_a"], pair["annotator_b"]) == ("Owl", "User 01234567")


def test_pair_list_is_capped_but_counted():
    n_users = 12  # 66 pairs
    rows = [
        _row(f"t{t}", f"user-{u:02d}", _choice("label", "x" if (t + u) % 2 else "y"))
        for t in range(3)
        for u in range(n_users)
    ]
    (label,) = agreement_by_control(rows)["controls"]
    assert label["pairs_total"] == n_users * (n_users - 1) // 2
    assert len(label["pairs"]) == MAX_PAIRS_PER_CONTROL
