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
"""

DEFAULT_JUDGE_MODEL_ID = "gpt-5.4-mini"
