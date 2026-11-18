"""The measure expression language: grammar whitelist and missing-value logic."""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.expression import ExpressionError, parse_expression

NAN = float("nan")


def _eval(text, **columns):
    n = len(next(iter(columns.values()))) if columns else 1
    cols = {
        k: (np.array(v, dtype=object) if any(isinstance(x, str) for x in v if x is not None) else np.array(v, dtype=float))
        for k, v in columns.items()
    }
    kind, out = parse_expression(text).evaluate(cols, n)
    return kind, list(out)


def _same(a, b):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        if isinstance(y, float) and math.isnan(y):
            assert isinstance(x, float) and math.isnan(x), (a, b)
        else:
            assert x == y, (a, b)


def test_arithmetic_and_role_dependent_choice():
    kind, out = _eval("if(x_role == 'P', share, 100 - share)", x_role=["P", "D", None], share=[30.0, 30.0, 30.0])
    assert kind == "num"
    _same(out, [30.0, 70.0, NAN])


def test_comparison_with_a_missing_operand_is_missing():
    _, out = _eval("100 * (share == 50)", share=[50.0, 40.0, NAN])
    _same(out, [100.0, 0.0, NAN])


def test_kleene_and_or_not():
    a = [1.0, 1.0, 0.0, NAN, NAN, 0.0]
    b = [1.0, NAN, NAN, 0.0, 1.0, 0.0]
    _same(_eval("a and b", a=a, b=b)[1], [1.0, NAN, 0.0, 0.0, NAN, 0.0])
    _same(_eval("a or b", a=a, b=b)[1], [1.0, 1.0, NAN, NAN, 1.0, 0.0])
    _same(_eval("not a", a=a, b=b)[1], [0.0, 0.0, 1.0, NAN, NAN, 1.0])


def test_membership_and_chained_comparison():
    _same(_eval("level in (0, 100)", level=[0.0, 50.0, 100.0, NAN])[1], [1.0, 0.0, 1.0, NAN])
    _same(_eval("level not in [0, 100]", level=[0.0, 50.0])[1], [0.0, 1.0])
    _same(_eval("cred in ('P', 'D')", cred=["P", "E", None])[1], [1.0, 0.0, NAN])
    _same(_eval("0 < x <= 2", x=[0.0, 1.0, 2.0, 3.0])[1], [0.0, 1.0, 1.0, 0.0])


def test_functions():
    x = [-2.0, 0.0, 4.0, NAN]
    _same(_eval("abs(x)", x=x)[1], [2.0, 0.0, 4.0, NAN])
    _same(_eval("sign(x)", x=x)[1], [-1.0, 0.0, 1.0, NAN])
    _same(_eval("clip(x, -1, 1)", x=x)[1], [-1.0, 0.0, 1.0, NAN])
    _same(_eval("min(x, 1)", x=x)[1], [-2.0, 0.0, 1.0, NAN])
    _same(_eval("max(x, 1, 3)", x=x)[1], [3.0, 3.0, 4.0, NAN])
    _same(_eval("isnull(x)", x=x)[1], [0.0, 0.0, 0.0, 1.0])
    _same(_eval("notnull(x)", x=x)[1], [1.0, 1.0, 1.0, 0.0])
    _same(_eval("coalesce(x, 7)", x=x)[1], [-2.0, 0.0, 4.0, 7.0])
    _same(_eval("round(x / 3, 1)", x=[1.0, 2.0])[1], [0.3, 0.7])
    _same(_eval("sqrt(x)", x=[4.0, 9.0])[1], [2.0, 3.0])
    _same(_eval("exp(log(x))", x=[2.0])[1], [pytest.approx(2.0)])
    _same(_eval("100 * s * log(a)", s=[1.0, -1.0], a=[math.e, math.e])[1], [pytest.approx(100.0), pytest.approx(-100.0)])
    _same(_eval("x ** 2 % 5", x=[3.0])[1], [4.0])


def test_text_results_and_number_conversion():
    kind, out = _eval("if(x > 0, 'pos', null)", x=[1.0, -1.0, NAN])
    assert kind == "str"
    assert out == ["pos", None, None]
    _same(_eval("number(t)", t=["1,5", "2.25", "n/a", None])[1], [1.5, 2.25, NAN, NAN])
    ambiguous = []
    texts = ["1,000", "1.000,50", "1,000.50", "1,2,3", "12,25", "1.000", None]
    _, out = parse_expression("number(t)").evaluate({"t": np.array(texts, dtype=object)}, len(texts), ambiguous)
    _same(list(out), [NAN, 1000.5, 1000.5, NAN, 12.25, 1.0, NAN])
    assert ambiguous == ["1,000", "1,2,3"]
    assert _eval("coalesce(t, 'none')", t=["a", None])[1] == ["a", "none"]


def test_if_is_only_renamed_outside_strings():
    kind, out = _eval("if(t == 'if(', 1, 0)", t=["if(", "x"])
    _same(out, [1.0, 0.0])


def test_bare_null_is_an_all_missing_number():
    kind, out = parse_expression("null").evaluate({}, 2)
    assert kind == "num" and all(math.isnan(v) for v in out)


def test_names_are_collected():
    assert parse_expression("if(a > b, c, d + 1)").names == frozenset({"a", "b", "c", "d"})


@pytest.mark.parametrize(
    "text, message",
    [
        ("__import__('os')", "unknown function"),
        ("__class__ + 1", "unsupported name"),
        ("x.real", "unsupported syntax"),
        ("x[0]", "unsupported syntax"),
        ("lambda: 1", "unsupported syntax"),
        ("[i for i in x]", "unsupported syntax"),
        ("open('f')", "unknown function"),
        ("abs(x, y)", "takes 1 arguments"),
        ("abs(x=1)", "keyword"),
        ("x in y", "list of literals"),
        ("x in ('a')", "for one value"),
        ("x in ('a', 1)", "mixes text and numbers"),
        ("x in ()", "non-empty"),
        ("x if y else z", "unsupported syntax"),
        ("", "non-empty"),
        ("1 +", "does not parse"),
        ("x // 2", "unsupported operator"),
        ("f'{x}'", "unsupported"),
    ],
)
def test_rejected_syntax(text, message):
    with pytest.raises(ExpressionError, match=message):
        parse_expression(text)


def test_too_long_and_too_complex():
    with pytest.raises(ExpressionError, match="longer than"):
        parse_expression("1 + " * 1200 + "1")
    with pytest.raises(ExpressionError, match="nested too deeply"):
        parse_expression("x+" * 1001 + "x")
    with pytest.raises(ExpressionError, match="nested too deeply|does not parse"):
        parse_expression("(" * 300 + "x" + ")" * 300)
    with pytest.raises(ExpressionError, match="nested too deeply"):
        parse_expression("abs(" * 150 + "x" + ")" * 150)
    with pytest.raises(ExpressionError, match="too complex"):
        parse_expression("max(" + ", ".join(["x"] * 1100) + ")")
    # a chain within the limits still parses
    assert parse_expression("x+" * 90 + "x").names == frozenset({"x"})


@pytest.mark.parametrize(
    "text, message",
    [
        ("t + 1", "needs a number"),
        ("t < 'a'", "not defined for text"),
        ("t == 1", "compares text with a number"),
        ("t in (1, 2)", "compares text with numbers"),
        ("x in ('a', 'b')", "compares a number with text"),
        ("if(x > 0, t, 1)", "mixes text and numbers"),
        ("unknown + 1", "unknown column"),
        ("round(x, x)", "constant whole number"),
    ],
)
def test_type_errors_at_evaluation(text, message):
    with pytest.raises(ExpressionError, match=message):
        parse_expression(text).evaluate(
            {"t": np.array(["a", "b"], dtype=object), "x": np.array([1.0, 2.0])}, 2
        )


def test_multiline_text_is_accepted():
    kind, out = _eval("if(x > 0,\n 1,\n 0)", x=[1.0])
    _same(out, [1.0])
