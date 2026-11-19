"""Flag answers a job carries into code that has no caller (core 2.69).

A worker job (a generation, an evaluation run) decides a platform flag once
for the user the job belongs to (``worker.flag_enabled_sync``) and opens
:func:`flag_scope` around its work; shared code deep below it that has no
user of its own (a provider client choosing which request fields to send)
reads the answer with :func:`scoped_flag`. One job then sees one answer
everywhere, whichever context the task message carried.

Outside a scope :func:`scoped_flag` falls back to
``extension_activation.flag_active``: the caller of the API request, or the
user and project of the task's context, the rule every package flag
follows in shared code.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, Iterator, Mapping, Optional

_scope: ContextVar[Optional[Dict[str, bool]]] = ContextVar("feature_flag_scope", default=None)


@contextmanager
def flag_scope(answers: Mapping[str, bool]) -> Iterator[None]:
    """Run the block with these flag answers (nested scopes add to and
    override the outer one)."""
    outer = _scope.get() or {}
    token = _scope.set({**outer, **{name: bool(on) for name, on in answers.items()}})
    try:
        yield
    finally:
        _scope.reset(token)


def scoped_answer(name: str) -> Optional[bool]:
    """The answer of the innermost scope naming ``name``, or None."""
    answers = _scope.get()
    if answers is not None and name in answers:
        return answers[name]
    return None


def scoped_flag(name: str) -> bool:
    """The answer of the innermost scope naming ``name``, else the current
    request or task context's (``extension_activation.flag_active``)."""
    answers = _scope.get()
    if answers is not None and name in answers:
        return answers[name]
    try:
        import extension_activation

        return extension_activation.flag_active(name)
    except Exception:
        return False
