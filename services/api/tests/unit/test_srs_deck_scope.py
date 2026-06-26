"""Unit tests for the SRS deck-scope clause (issue #35, Anki Stapel alignment).

``_deck_scope_clause`` restricts a collection's cards to one deck *and its
subdecks* by matching ``task.data['deck']`` exactly OR by the ``deck + "::"``
prefix. These tests pin the SQL it renders (no DB needed) so the two failure
modes that would silently corrupt a study session can't regress:

* a sibling deck bleeding in via a partial-segment prefix
  (scoping "Strafrecht" must NOT pull in "Strassenrecht"), and
* the JSONB-only ``.astext`` accessor sneaking back in — ``Task.data`` is typed
  as the generic ``JSON`` here, so the clause must use ``.as_string()``.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from routers.projects.srs import _deck_scope_clause


def _sql(deck: str | None) -> str:
    clause = _deck_scope_clause(deck)
    if clause is None:
        return ""
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_no_deck_returns_none():
    assert _deck_scope_clause(None) is None
    assert _deck_scope_clause("") is None


def test_exact_match_and_subdeck_prefix():
    sql = _sql("Jura::BGB")
    # Exact-match arm.
    assert "= 'Jura::BGB'" in sql
    # Subdeck arm: a LIKE on the "Jura::BGB::" prefix (so subdecks are included).
    assert "LIKE 'Jura::BGB::'" in sql
    assert "OR" in sql.upper()


def test_uses_generic_json_accessor_not_jsonb_astext():
    # ``.as_string()`` renders as ``->>`` + CAST; the JSONB-only ``.astext``
    # would not compile against the generic JSON-typed column.
    sql = _sql("Jura")
    assert "->>" in sql
    assert "CAST" in sql.upper()


def test_prefix_boundary_is_a_full_segment():
    # The prefix arm matches "Strafrecht::…" only — the trailing "::" stops a
    # sibling like "Strafrechtler" from being swept in.
    sql = _sql("Strafrecht")
    assert "LIKE 'Strafrecht::'" in sql
    assert "LIKE 'Strafrecht'" not in sql  # no bare-prefix match


def test_like_wildcards_in_deck_name_are_escaped():
    # A deck literally containing "%" must be escaped so it can't act as a
    # wildcard (startswith(autoescape=True) adds an ESCAPE clause).
    sql = _sql("50%Klausur")
    assert "ESCAPE" in sql.upper()
