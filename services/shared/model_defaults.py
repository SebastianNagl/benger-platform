"""Model defaults shared by the api and the workers.

``DEFAULT_JUDGE_MODEL_ID`` is the judge a config grades with when it names
none. The frontend pickers start on the same model
(``services/frontend/src/lib/modelDefaults.ts``, ``DEFAULT_MODEL_ID``), and a
Jest drift test fails if the two differ. A picker that shows one model while
the worker grades with another is the silent substitution this constant
exists to prevent: until 2026-09-14 the worker fell back to gpt-4o while every
picker showed gpt-5.4-mini.

Whatever id sits here must be an active, official row of the model catalog
(``services/shared/seeds/llm_models.yaml``).

``RUBRIC_JUDGE_MAX_TOKENS`` is the completion budget of the Bewertungsbogen
judge (``llm_judge_rubric``): the worker floors a default-tier
``max_tokens`` to it (``METRIC_MAX_TOKENS_FLOOR``), the metric registry
seeds new configs with it and the extended rubric lanes read it, so one
number governs every place that sets the budget. 32000 is measured, not
guessed: grading a submission against the 46-step Polizeirecht
Korrekturbogen on gpt-5-mini spent the ENTIRE 8000-token budget (6928
prompt + 8000 completion) without closing the JSON. Reasoning models bill
their thinking against the same completion budget, so the usable room for
~46 reasons is a fraction of the cap. The generator that writes these
sheets already runs at 32000; grading one is the same order of work. A cap
is not a spend: only emitted tokens are billed.
"""

DEFAULT_JUDGE_MODEL_ID = "gpt-5.4-mini"

RUBRIC_JUDGE_MAX_TOKENS = 32000

# Per-metric floors on a DEFAULT-tier max_tokens (see the module docstring
# and tasks._apply_metric_max_tokens_floor for the tier rule).
METRIC_MAX_TOKENS_FLOOR = {
    "llm_judge_rubric": RUBRIC_JUDGE_MAX_TOKENS,
}
