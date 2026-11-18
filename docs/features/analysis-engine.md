# Analysis engine for variant experiments

A project can be run as a controlled variant experiment: every task is one
cell of a design (for example the same case with the parties' roles swapped,
or with one fact changed), and the systems' answers to those tasks are
compared within each unit of the design. The analysis engine turns such a
project into a frame of observations, computes the estimands a spec declares
(fixed-effects regressions, means, paired differences), their contrasts,
equivalence tests and multiplicity-adjusted p-values, and records everything
it needs to reproduce the numbers: the spec, the frame snapshot and its hash,
the engine version and the numeric library versions.

The code lives in `services/shared/analysis/` (pure functions and the spec
schema) and runs in the workers on the `analysis` queue (`tasks.run_analysis`).
The API validates specs and starts and reads runs; it does not load the
numeric stack.

## Where the data comes from

A task belongs to a design through its `meta.variant` block:

```json
{"variant": {"design": "role_swap", "unit": "case_017",
             "factors": {"x_role": "P", "first": "D", "level": 75}}}
```

`design` names the design, `unit` ties the variants of one case together
(it is the usual fixed effect and cluster), and `factors` holds the task's
place in the design. `meta` is never shown to a system under test.

Every completed generation of such a task becomes one row of the frame:
generation, task, system, model id, prompt structure, run index,
design, unit, the factors, the quality flags (`parse_ok`, `refusal`,
`truncated`, `retried`, `finish_reason`) and the measures of the spec. Rows
are sorted canonically (design, unit, task, system, structure, run index,
generation), so the same data always gives the same frame. The system is
the generation's system key `response_metadata.system.key`
(`<model_id>@<12 hex digits of the parameter profile hash>`), so two
parameter profiles of one model are two systems; answers generated before
CORE 2.56 have no key and fall back to the model id. The frame is
stored as Parquet under `analysis/` in object storage, with a content hash
that does not depend on the Parquet writer.

## The spec

The spec is JSON, validated against
`services/shared/analysis/schemas/analysis_spec.schema.json` (format version
1). `GET /api/analysis/engine` returns the schema, the estimator catalogue and
the default conventions; `POST /api/analysis/specs/validate` checks a spec
and returns its normalized form and hash.

```json
{
  "spec_version": 1,
  "name": "role swap",
  "inputs": {"designs": ["role_swap"]},
  "measures": {
    "share_p": {"kind": "field", "field": "share_p"},
    "x_p": {"kind": "expression", "expr": "1 * (x_role == 'P')"},
    "first_x": {"kind": "expression", "expr": "1 * (x_role == first)"},
    "share_x": {"kind": "expression", "expr": "if(x_p == 1, share_p, 100 - share_p)"},
    "gold_low": {"kind": "gold", "path": "gold.low"}
  },
  "estimands": [
    {
      "id": "role",
      "estimator": "fe_ols",
      "outcome": "share_x",
      "terms": ["x_p", "first_x"],
      "fixed_effects": [["unit", "system"]],
      "vcov": {"type": "cluster", "by": ["unit", "name_id"]},
      "scopes": ["pooled", {"by": ["system"]}],
      "contrasts": [{"id": "role", "weights": {"x_p": 1}, "tost": {"margin": 3}}]
    }
  ],
  "families": [
    {"id": "per_system", "method": "holm",
     "members": [{"estimand": "role", "scope": "by:system"}]}
  ]
}
```

### Inputs

`designs` (required), and optionally `systems` (each a system key or a model
id, which selects every profile of that model) and `structures` to narrow the
frame, and `factor_types` to declare a factor `number` or `text` instead of
inferring it.

### Measures

| Kind | Reads | Example |
|---|---|---|
| `field` | a parsed answer value by control name, or a control chosen by a factor's value (`"by": "x_role", "fields": {"P": "own_share", "D": "other_share"}`) | `{"kind": "field", "field": "share_p"}` |
| `expression` | fields, factors, gold and earlier measures | `{"kind": "expression", "expr": "100 * (share_p == 50)"}` |
| `gold` | a task data path (a numeric segment indexes a list) | `{"kind": "gold", "path": "gold.low"}` |

Field and gold measures take a `type`: `number` (the default), `text` or
`bool`. Expressions use a small whitelisted language: literals, column names,
arithmetic, comparisons, `in`, `and`/`or`/`not` and the functions `if`, `abs`,
`log`, `exp`, `sqrt`, `sign`, `round`, `clip`, `min`, `max`, `isnull`,
`notnull`, `coalesce` and `number`. Missing values propagate (a comparison
with a missing operand is missing, not false); non-finite results become
missing and are reported. Nothing is evaluated as Python.

Number text (a `number` field or gold value, or `number()` in an expression)
never guesses between a thousands and a decimal separator. A dot is the
decimal mark (`"2.5"`, `"1e3"`, and `"1.000"` is 1.0). A single comma without
a dot is the decimal mark unless exactly three digits follow it (`"1,5"` is
1.5, `"12,25"` is 12.25). The grouped forms with groups of exactly three
digits and the other separator as decimal mark are read (`"1.000,50"` and
`"1,000.50"` are 1000.5). Any other text of digits and separators (`"1,000"`,
`"1,2,3"`, `"1.000.000"`) is ambiguous: it becomes missing and the run warns,
for example `measure 'amount': 3 number text(s) with an ambiguous separator
set to missing`.

A global `filter` and an estimand's `subset` are expressions too (rows where
they are true are used).

### Estimators

| Estimator | What it estimates |
|---|---|
| `fe_ols` | OLS of `outcome` on `terms` with optional `fixed_effects` (each a column or a combination of columns), absorbed by group means (`method: within`, the default; several sets by alternating projections) or by dummies (`method: dummies`). Terms are numeric columns, dummy codings `{"dummies": "cond", "reference": "C0"}` (columns `cond[N]`; with `"by": "type"` one column per `cond[N]:type[x]`) and products `{"interact": [a, b]}`. |
| `mean_rate` | the mean of `outcome` (parameter `(mean)`); with the iid variance its SE is `sd / sqrt(n)` |
| `paired_within` | the mean within-pair difference: treated rows minus the mean of the reference rows of the same `pair_by` group (parameter `(difference)`); `min_n` gates small samples |

Rows with a missing outcome, regressor, dummy factor, fixed-effect key or
cluster key are left out and counted. A regressor the fixed effects absorb is
dropped and named; a contrast on it is `not_estimable`.

`scopes` repeats an estimand per level of the `by` columns, next to the
pooled fit.

### Variances and inference conventions

`vcov` is `iid`, `hc1` or `cluster` with one or two clustering dimensions
(two-way as V1 + V2 - V12). Every convention is explicit and part of the
normalized spec, so its hash changes with any of them:

| Convention | Values | Default |
|---|---|---|
| `ssc` | `statsmodels`: cluster G/(G-1) * (N-1)/(N-K) per dimension with K the regressors left after absorption, HC1 N/(N-K), iid RSS/(N-K). `fixest`: K also counts absorbed fixed-effect levels (a set nested in a cluster counts once), two-way components use the smallest G. `none`: no factor | `statsmodels` |
| `inference` | `normal`, or `t` with G-1 degrees of freedom for cluster variances and N-K otherwise | `normal` |
| `ci_level` | confidence level | 0.95 |
| `ci_critical` | `exact` (the quantile), or a fixed number such as 1.96 | `exact` |
| `tost_level` | level of the equivalence interval | 0.90 |
| `drop_zero_columns` | drop absorbed regressors | true |
| `degenerate_p` | p-value of a zero-variance contrast: `nan`, or `null_match` (1 when the estimate equals the null) | `nan` |
| `fe_tolerance`, `fe_max_iter` | convergence of alternating projections | 1e-12, 10000 |

### Contrasts, equivalence and MDE

A linear contrast has `weights` over the fitted parameters and a `null`
(default 0). A ratio contrast is `scale * (a'b + a0) / (c'b + c0)` with a
delta-method SE and an optional `min_abs_denominator`. `tost` takes one or
several bound sets (`{"margin": 3}` or `{"bounds": [-2, 3]}`): the contrast
is equivalent when the `tost_level` interval lies strictly inside the bounds,
and `p_tost` is the larger one-sided p-value. `mde` reports the minimum
detectable effect `(z(1 - alpha/(2m)) + z(power)) * se`.

`"contrasts": "terms"` (the default) reports every fitted parameter.

### Families

A family adjusts the p-values of its members with `holm`, `bonferroni` or
`bh` (Benjamini-Hochberg, only in families marked `exploratory`). Members
select an estimand, optionally a contrast and a scope (`pooled`,
`by:<columns>`, `<column>=<value>` or `*`); `split_by` adjusts separately per
estimand, contrast, scope kind or scope. Missing p-values are skipped
(`missing_p: skip`) or counted as tests that cannot reject (`count`, Holm and
Bonferroni only). Each estimate keeps every membership with its adjusted
p-value; `family` and `p_adjusted` are its first family.

## Runs

| Route | Who | What |
|---|---|---|
| `POST /api/projects/{project_id}/analysis-runs` | edit rights | start a run: `{"spec": {...}, "name": "optional"}` (202) |
| `GET /api/projects/{project_id}/analysis-runs` | project members | the runs, newest first |
| `GET /api/analysis-runs/{analysis_run_id}` | project members | the run: normalized spec and hash, frame hash and counts, engine and library versions, lockfile hash, per-fit summaries, warnings, timings |
| `GET /api/analysis-runs/{analysis_run_id}/estimates` | project members | the estimates in engine order |
| `GET /api/analysis-runs/{analysis_run_id}/frame` | ORG_ADMIN, CONTRIBUTOR | the Parquet snapshot (short-lived URL) |

`/api/v1` serves the read routes with the `results:read` scope
([public-api.md](../public-api.md)).

A run is `pending`, `running`, `completed` or `failed`. A spec or data
problem the engine can name (an unknown column, a text outcome) fails the run
with that message. Runs and their estimates are deleted with the project,
and the purge removes their stored frames.

## Reproducibility

The same frame, the same normalized spec and the same engine version give
bit-identical estimates on one machine; the golden-file tests in
`services/workers/tests/analysis/` fail on any numeric change, and a change
that moves a number bumps `ENGINE_VERSION`. The default `statsmodels`
convention reproduces `statsmodels` OLS with cluster-robust covariances on the
same data to machine precision, and the `fixest` convention reproduces
pyfixest's defaults; both are checked in the tests.
