"""Deploy-critical regression guard: ``import tasks`` must stay light.

The beat scheduler and the API import the Celery app (``from tasks import app``)
but never compute neural metrics. The beat's startup probe is literally
``python -c 'from tasks import app'`` with a 15s timeout, and the beat pod is
sized as a tiny scheduler (300m CPU / 384Mi).

If importing ``tasks`` eagerly drags in the neural ML stack (torch, spacy,
transformers, sentence-transformers, bert_score — ~7s + ~500Mi), the beat probe
times out, the pod never goes Ready, ``helm --wait`` never completes, and EVERY
deploy times out and rolls back.

This regressed once during the Tier-2 worker decomposition (``from tasks import
app`` went 1.7s/no-ML -> 7.2s/torch via an eager ``ml_evaluation`` import). The
heavy libs are now imported lazily (see ``ml_evaluation/sample_evaluator.py``
``__getattr__`` and the in-function import in ``ml_evaluation/metrics/
factuality.py``); they load only when a neural metric is actually computed.

This test runs ``import tasks`` in a FRESH interpreter (so neural imports from
other tests in this process can't mask the regression) and asserts none of the
heavy libs were pulled in.
"""

import os
import subprocess
import sys

HEAVY = ("torch", "spacy", "transformers", "sentence_transformers", "bert_score")


def test_import_tasks_does_not_eagerly_load_neural_ml():
    code = (
        "import tasks, sys; "
        f"heavy=[m for m in {HEAVY!r} if m in sys.modules]; "
        "print('HEAVY=' + ','.join(heavy)); "
        "sys.exit(1 if heavy else 0)"
    )
    # Mirror this process's import path so `import tasks` resolves identically.
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, (
        "`import tasks` eagerly loaded the neural ML stack — this breaks the beat "
        "startup probe and every deploy. Keep ml_evaluation's heavy imports lazy.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr[-2000:]}"
    )
