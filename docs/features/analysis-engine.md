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

Everything described here needs the platform flag `variant_experiments`;
while it is off the routes answer 404 `feature_disabled` and runs are not
computed ([feature flags](feature-flags.md)).

The code lives in `services/shared/analysis/` (pure functions and the spec
schema) and runs in the workers on the `analysis` queue (`tasks.run_analysis`).
The API validates specs and starts and reads runs; it does not load the
numeric stack.

## Where the data comes from

A task belongs to a design through its `meta.benger_variant` block:

```json
{"variant": {"design": "role_swap", "unit": "case_017",
             "factors": {"x_role": "P", "first": "D", "level": 75}}}
```

`design` names the design, `unit` ties the variants of one case together
(it is the usual fixed effect and cluster), and `factors` holds the task's
place in the design. `meta` is never shown to a system under test.

Every completed generation of such a task becomes one row of the frame:
generation, project, task, system, model id, prompt structure, run index,
design, unit, the factors, the quality flags (`parse_ok`, `refusal`,
`truncated`, `retried`, `finish_reason`), the columns of the spec's lookup
tables and the measures of the spec. Rows are sorted canonically (project,
design, unit, task, system, structure, run index, generation, slot), so the
same data always gives the same frame. The system is
the generation's system key `response_metadata.system.key`
(`<model_id>@<12 hex digits of the parameter profile hash>`), so two
parameter profiles of one model are two systems; answers generated before
CORE 2.56 have no key and fall back to the model id. The frame is
stored as Parquet under `analysis/` in object storage, with a content hash
that does not depend on the Parquet writer.

### Slot frames: one row per item of an answer

When a task asks the same questions once per item (per case of a docket,
per person in a judgment), its `meta.benger_variant.slots` lists the items with
their own factors, and the answers sit under indexed control names, as a
Label Studio `<Repeater>` stores them (`risk_0`, `risk_1`, ...; see
[per-item answers](../user-guides/per-item-answers.md)):

```json
{"variant": {"design": "docket", "unit": "docket_017", "factors": {"gender": "f"},
             "slots": [{"index": 0, "factors": {"pos": 1, "group": "a", "fact": "f2"}},
                       {"index": 1, "factors": {"pos": 2, "group": "ref", "fact": "f0"}}]}}
```

With `"frame": {"unit": "slot"}` the frame has one row per generation and
slot: the column `slot` holds the slot index and every slot factor becomes a
column (a slot factor may not share its name with a task factor). A
generation of a task without slots contributes no row (the run warns).

Per-slot measures put `{idx}` where the slot index goes in the control name:

| Measure | Reads | Example |
|---|---|---|
| `field` with `{idx}` | the row's own slot (`"slot": "own"`, the default in a slot frame), the generation's other slot when it has exactly two (`"other"`) or a slot by index (`1`, also in a generation frame) | `{"kind": "field", "field": "months_{idx}", "slot": "other"}` |
| `slot_factor` | a factor of another slot of the same generation | `{"kind": "slot_factor", "factor": "group", "slot": "other"}` |
| `slot_aggregate` | a summary of a per-slot field over all slots of the generation: `mean`, `sum`, `min`, `max`, `sd`, `count`, `is_ranking` (1 when the values are exactly 1..n) | `{"kind": "slot_aggregate", "field": "rank_{idx}", "function": "is_ranking"}` |

Cross-slot measures such as the rank validity are the same on every row of a
generation. A two-person comparison can also stay one row per generation:
`{"kind": "slot_factor", "factor": "group", "slot": 1}` and
`{"kind": "field", "field": "cred_{idx}", "slot": 2}` read the persons by
index.

### Several projects in one frame

`inputs.projects` adds further projects, each with its own designs:
`{"designs": ["docket"], "projects": [{"project_id": "...", "designs":
["docket"]}]}`. The run's own project contributes `inputs.designs`. The
column `project_id` keeps the rows apart; combine it with `unit` in fixed
effects and clusters when two projects can use the same unit ids, and scope
by `project_id` to report each project separately. Starting such a run and
downloading its frame need the ORG_ADMIN or CONTRIBUTOR role on every input
project (a project-restricted access key must also include each of them),
because their answers enter the frame. Reading such a run (its detail, fits
and estimates, also through `/api/v1`) needs read access to every input
project as well, as for the run's own project; a viewer without it gets 404
and does not see the run in the run lists. The input projects of a run are
those of `inputs.projects` and the projects that own a stored lookup table
it joins. A soft-deleted input project still counts (only a superadmin
reads past it). Purging an input project deletes the frames of the runs that
read it; the runs and their estimates stay, and since the purged project no
longer counts for reads, the readers of the run's own project see them with
the warning `frame deleted: input project <id> was purged`. A run that has
not stored its results when one of its input projects is deleted or purged fails with `input project <id> was deleted; the run cannot
read it` and stores no frame.

### Lookup tables

A lookup joins a table onto the frame by key columns before the measures are
computed, for example a coding per system, offence and group:

```json
"lookups": [{"id": "coding", "table": {"name": "congruence", "version": 2},
             "keys": {"system": "model", "fact": "fact", "group": "group"},
             "columns": {"cong": "cong", "assoc": "assoc"},
             "fill": {"cong": 0, "assoc": 0}}]
```

`keys` maps frame columns (base columns, factors, slot factors, `slot`) to
the table's columns; values match as canonical text, so `1` and `1.0` match
and a missing key matches nothing. A key that two table rows share is an
error. `columns` names the new frame columns; rows without a match take
`fill`, or missing. A lookup gives its rows inline (`"rows": [{...}]`) or
names a stored table: `POST /api/projects/{project_id}/analysis-lookups`
with `{"name", "columns", "rows", "description"}` stores the next version
of a name (rows as lists in column order or objects), and versions never
change. `table` takes `name`, `version`, optionally `project_id` (a table of
another project, which needs the same access as an input project) and
`content_hash`, which the run checks. The run records every table it read
with its content hash in `resolved_inputs`, together with `models`: the
models whose answers are in the frame (every `model_id` and the model part
of every system key), so a report can tell whether a private model may
appear in the run.

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
| `list` | an answer's list of items against a gold list (hits, recall, F1, Jaccard, ...) | `{"kind": "list", "field": "cited", "gold": {"path": "gold.cited"}, "statistic": "recall"}` |
| `text_pattern` | a code of a versioned regex set on the answer or a field | `{"kind": "text_pattern", "set": "signals", "code": "canary"}` |
| `coder` | an output of a coder plugin an overlay registered | `{"kind": "coder", "coder": "blame", "output": "direction"}` |
| `judge_code` | a judge system's code of the answer in a coding project | `{"kind": "judge_code", "coding_project": "...", "field": "side", "system": "..."}` |

The last four are codes and lists, described in [codes.md](codes.md), with
the spec key `pattern_sets` for the regex sets; a code read by a
confirmatory family needs a recorded validation.

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

A global `filter`, an estimand's `subset` and a paired treatment's `subset`
are expressions too (rows where they are true are used); ambiguous number
texts read by `number()` there are reported in the run warnings as well.

### Estimators

| Estimator | What it estimates |
|---|---|
| `fe_ols` | OLS of `outcome` on `terms` with optional `fixed_effects` (each a column or a combination of columns), absorbed by group means (`method: within`, the default; several sets by alternating projections) or by dummies (`method: dummies`). Terms are numeric columns, dummy codings `{"dummies": "cond", "reference": "C0"}` (columns `cond[N]`; with `"by": "type"` one column per `cond[N]:type[x]`) and products `{"interact": [a, b]}`. |
| `mean_rate` | the mean of `outcome` (parameter `(mean)`); with the iid variance its SE is `sd / sqrt(n)` |
| `paired_within` | the mean within-pair difference: treated rows minus the mean of the reference rows of the same `pair_by` group (parameter `(difference)`); `min_n` gates small samples |
| `logit` | a logit of `outcome` (0/1, or a share between 0 and 1) on `terms`, fitted by Newton-Raphson to machine precision; `fixed_effects` as dummies; with `informative_only` (default) the fixed-effect groups whose outcome does not vary are left out and counted. Contrasts of kind `ame` give average marginal effects. |
| `bradley_terry` | paired comparisons: `outcome` is 1 when the first of the two `players` columns wins; one strength `strength[<level>]` per player level other than `reference` on the +1/-1 coding (first minus second), with optional `terms` and `fixed_effects` (dummies; an intercept without them); `link` `logit` (default) or `linear` (a linear probability model by OLS, without the informative-cell filter); with declared `levels`, rows with a player outside them are left out and counted as dropped, with a warning |
| `plackett_luce` | a rank-ordered logit: the rows of one `choice_set` (default `generation_id`, the slots of an answer in a slot frame) are alternatives ranked by `outcome` (1 = chosen first); each of `stages` choices (default all) picks from the alternatives left. A choice set whose ranks are not exactly 1..n, or with a missing regressor, is left out and counted; regressors constant within every choice set cancel and are dropped. Newton-Raphson with the analytic Hessian. |
| `clogit_rank1` | the conditional logit of the first choice only: the alternative with `outcome` 1 against all of its choice set (exactly one per set) |
| `mixedlm` | a linear mixed model with a random intercept per `groups` (statsmodels MixedLM, REML by default): the optimizers of `mixedlm_optimizers` are tried in order and the first fit is accepted that converged with a finite log-likelihood and finite, positive variances whose standard errors are at most `mixedlm_max_se_ratio` times the outcome's standard deviation. The variance is model-based (`vcov` iid); the fit summary reports the variance components and the optimizer. |
| `spearman` | Spearman's rank correlation of `outcome` and `x` over the complete pairs (parameter `(rho)`, with scipy's p-value on n-2 degrees of freedom); a constant input is not estimable |

Rows with a missing outcome, regressor, dummy factor, fixed-effect key or
cluster key are left out and counted. A regressor the fixed effects absorb is
dropped and named; a contrast on it is `not_estimable`.

`scopes` repeats an estimand per level of the `by` columns, next to the
pooled fit.

The summary of every fit with `terms` (`fe_ols`, `logit`, `bradley_terry`,
`mixedlm`, `plackett_luce`, `clogit_rank1`) records `references`: the
reference level each dummy coding was measured against (factor -> level),
the declared `reference` or else the first level of the estimation sample.
A Bradley-Terry fit records its `reference` under `strength` and
`players_are_systems`, true when every player level is a value of the
frame's `system` (or `model_id`) column. Both keys are provenance only and
move no estimate; fits of runs made before they existed lack them.

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

The likelihood estimators take conventions of their own (only those
estimands carry them in the normalized spec):

| Convention | Estimators | Default |
|---|---|---|
| `ml_tolerance`, `ml_max_iter` | `logit`, `bradley_terry`, `plackett_luce`, `clogit_rank1`: Newton stops when the largest step is below `ml_tolerance * (1 + max abs(b))` | 1e-10, 100 |
| `informative_only` | `logit`, `bradley_terry`: leave out fixed-effect groups without outcome variation | true |
| `separation_bound` | `logit`, `bradley_terry`: a parameter beyond it in absolute value, or with a standard error below 1e-8 or not finite, counts as separated; contrasts on it keep estimate and interval but get no p-value (status `separation`) | 8 |
| `reml`, `mixedlm_optimizers`, `mixedlm_max_se_ratio` | `mixedlm` | true, `["lbfgs", "powell", "bfgs"]`, 100 |

For the maximum-likelihood estimators the variances are sandwich
variances around the inverse information: `iid` is the inverse information,
`hc1` the sandwich without a small-sample factor (as statsmodels computes it
for these models), `cluster` the clustered sandwich times G/(G-1) *
(N-1)/(N-K) under `ssc: statsmodels` and without a factor under `none`, N
being the answers (logit) or the choice sets (rank-ordered logits). The
`fixest` convention is for OLS only.

### Contrasts, equivalence and MDE

A linear contrast has `weights` over the fitted parameters and a `null`
(default 0). A ratio contrast is `scale * (a'b + a0) / (c'b + c0)` with a
delta-method SE and an optional `min_abs_denominator`. `tost` takes one or
several bound sets (`{"margin": 3}` or `{"bounds": [-2, 3]}`): the contrast
is equivalent when the `tost_level` interval lies strictly inside the bounds,
and `p_tost` is the larger one-sided p-value. `mde` reports the minimum
detectable effect `(z(1 - alpha/(2m)) + z(power)) * se`.

`"contrasts": "terms"` (the default) reports every fitted parameter.

An average marginal effect (`"kind": "ame"`, logit only) is the mean over
the estimation sample of the predicted probability with `column` set to
`level` minus the same with it set to `reference`, times `scale` (100 for
percentage points), with a delta-method standard error. Interactions that
involve the column follow it, so with `group x gender` terms the effect
averages over the sample's genders. The column must be read by a term and
may not be a fixed-effect column. A column read only by dummy codings must
have rows at `level` and at `reference` in the estimation sample (of the
scope); otherwise the effect is `not_estimable`.

### Joint tests

`joint_tests` on an estimand asks whether several restrictions hold at once:
`{"id": "groups", "contrasts": ["a", "b"]}` (contrasts of the estimand,
each against its null; a ratio contrast without a `null` makes the test
not estimable), `{"id": "groups", "parameters": ["group[*]"]}`
(parameters by name, `*` matching any text) or `{"id": "x", "rows":
[{"group[a]": 1, "group[b]": -1}]}`. The Wald statistic is
`r' pinv(G V G') r` with `r` the restrictions' values minus their nulls and
`G` their gradients; it has as many degrees of freedom as the rank of
`G V G'` (singular values below 1e-10 of the largest count as zero), so a
redundant restriction adds none and the row says so. The estimate row has
kind `wald`, the chi2 statistic, `df` and the p-value, and can be a member
of a family like any contrast.

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
| `GET /api/projects/{project_id}/analysis-runs` | project members | the runs, newest first (without those reading an input project the viewer may not read) |
| `GET /api/analysis-runs/{analysis_run_id}` | project members (and of every input project) | the run: normalized spec and hash, frame hash and counts, engine and library versions, lockfile hash, the identity and validation of every code measure (`codes`), per-fit summaries, warnings, timings |
| `GET /api/analysis-runs/{analysis_run_id}/estimates` | project members (and of every input project) | the estimates in engine order, each with its row `id` (what a compliance finding's `analysis_estimate_id` cites; the v1 route leaves it out) |
| `GET /api/analysis-runs/{analysis_run_id}/frame` | ORG_ADMIN, CONTRIBUTOR (on every input project) | the Parquet snapshot (short-lived URL) |
| `POST /api/projects/{project_id}/analysis-lookups` | edit rights | store the next version of a lookup table (201) |
| `GET /api/projects/{project_id}/analysis-lookups` | project members | the tables without rows, by name and newest version first (`?name=`) |
| `GET /api/projects/{project_id}/analysis-lookups/{name}/versions/{version}` | project members | one version with its rows |

`/api/v1` serves the read routes with the `results:read` scope
([public-api.md](../public-api.md)).

A run is `pending`, `running`, `completed` or `failed`. A spec or data
problem the engine can name (an unknown column, a text outcome) fails the run
with that message. Runs and their estimates are deleted with the project,
and the purge removes their stored frames.

### Counts and the run inventory

Completed runs count wherever a project's numbers are shown. The project
response carries `analysis_count` (detail and list), the project page's
statistics card shows an Analyses line and the project list a badge once
there is one, the dashboard overview answers `analyses_count` with an
Analyses tile, and report statistics, the report snapshot and the published
report list carry `analysis_count`. A run that reads further projects
counts for its own project, also for viewers who may not open it: the
number says only that a run exists. Pending, running and failed runs are
not counted.

`GET /api/runs?type=analysis` lists runs across projects for the `/runs`
inventory (its Analyses tab), newest first, with the run's name, project,
status, frame rows, estimates, spec hash and engine version, filtered by
`project_id` and `status` and paged with `page` and `page_size`. It leaves
out the runs the viewer could not open (inaccessible projects, and runs
reading an input project the viewer may not read), and `total` counts the
same runs, so the pages add up. A row opens the run page.

The dashboard's older keys `projects_with_generations` and
`projects_with_evaluations` stay as aliases of `generations_count` and
`evaluations_count`.

## Configuring and starting analyses

Analyses are configured and started where evaluations are: the project
page's **Evaluation Configuration** card has an **Analyses** part for the
CONTRIBUTOR and ORG_ADMIN roles (the roles that may start runs, save plans
and freeze designs). It holds:

- **Variant designs**: every design of the project with its status (draft or
  frozen), version, units, cells and tasks (the distinct units, distinct
  design cells and tasks that name the design, as `unit_count`, `cell_count`
  and `task_count` of `GET .../variant-designs`) and frozen content hash.
  **Check** runs the assignment, balance and invariance checks
  (`POST .../variant-designs/{key}/check`) and shows the report as the route
  answered it: units, cells per unit, checked pairs, the problems of each
  check and the content hash a freeze would record. **Freeze** (after a
  confirmation) runs the checks again and records the hash
  (`POST .../variant-designs/{key}/freeze`); a design whose checks fail
  stays a draft and its report is shown. **Import design** creates a draft
  from an exported design document (`POST .../variant-designs/import`).
- **Analysis plans**: named analysis specs saved with the project's
  evaluation configuration, under the key `analysis_plans`. A plan can be
  added, edited, deleted and started.
- **Start analysis**: the start dialog the evaluations page shares. A started
  run opens in the Analyses view of `/evaluations`, which follows it until it
  completes.

A plan is stored as `{id, name, spec, spec_hash, saved_at, saved_by}`.
Both writers of the evaluation configuration
(`PUT /api/evaluations/projects/{project_id}/evaluation-config` and
`PATCH /api/projects/{project_id}`) validate every plan's spec with the
engine before anything is written and answer 422 `invalid_analysis_plan`
with the engine's messages, each under the plan's path
(`/analysis_plans/1/spec/measures/x/expr: ...`). The list replaces the stored
one as a whole and `null` deletes it; the other keys of the configuration
stay as they are. `spec` is kept as written; `spec_hash` is the hash of its
normalized form, the same hash a run started from that spec records, so a
run names the plan it used by hash without a further column. `spec_hash`,
`saved_at` and `saved_by` are set by the API: `saved_at` and `saved_by`
change when the plan is new or its spec hash changes, so a renamed plan
keeps the time its spec was saved, and a plan edited after a run gets a new
hash while the run keeps the old one. A plan needs a name (at most 200
characters); a project holds at most 50 plans, and ids are unique.

The start dialog fills its spec form from one of three sources: a saved plan
(its spec, its name and its hash, with the time it was saved), the spec of an
earlier run of the project (`newRunFrom`), or a blank spec to paste.
Validating a spec loaded from a plan says whether it still matches the plan's
hash.

## Results on the evaluations page

Every result of a project is viewed on `/evaluations`. Its filter bar has a
result type next to the project picker: **Metrics** (automated, LLM judge and
human evaluations) or **Analyses**, shown once the project has analysis runs
or variant designs. The project page has one **Evaluations** action; it opens
the Analyses view directly when the project has runs or designs but no metric
evaluation configs, so runs stay reachable after their designs are deleted.

`/evaluations?projectId={project_id}&type=analysis` shows the analysis runs:

- Filters: the run (newest first with its status; by default the newest
  completed run), the systems (from the estimates' `scope_values.system`;
  estimates without a system, such as the pooled fit, always stay), the
  estimands and the family. The URL keeps them as `run`, `systems`,
  `estimands` (comma separated) and `family`, so a reload or a shared link
  shows the same view.
- A strip of the run's facts (status, frame rows, estimates, spec hash,
  engine version) and **Run details**, the run page.
- The view (`chartType`): the forest plot (default) of one contrast across
  its scopes, pooled first, with a dashed line at the null value. When the
  spec declares equivalence bounds for the contrast, the first bound set is
  shaded as a band and every row also draws the TOST interval (the
  `tost_level`, 90 % by default) that the equivalence decision uses; the band
  can be switched to another bound set or off. A Bradley-Terry estimand is
  drawn as a strength forest instead: each player level against the
  reference level (fixed at 0), one plot per scope chosen with a row of
  chips. `profile` draws the estimates of one contrast along an ordered or
  numeric scope column (a position of a per-slot frame, a numeric factor, a
  level), one line per series column (the system by default) and one panel
  per facet column, with their intervals. A fitted slope is drawn only
  where the run estimated the slope of exactly what is plotted, with its
  estimate and interval in the legend: for a profile of means
  (`mean_rate`), the pooled linear contrast `{x: 1}` of a linear-model
  estimand (`fe_ols` or `mixedlm`, never a link-scale coefficient such as
  a `logit` one) of the same outcome with x as a term is the slope of
  every line; with an
  interaction of x and the series factor, each level gets its own slope
  (`{x: 1}` for the declared reference level, `{x: 1, "x:factor[level]":
  1}` for the others). A difference or coefficient profile, or any other
  model shape, gets no slope, and the view says that none was estimated.
  `bar` draws the
  estimates of each contrast as bars from 0, with the null value as a dashed
  line, `table` lists the contrasts against their scopes, `data` shows only
  the estimates table.
- The estimates table: every estimate in engine order with its standard
  error, confidence interval, p-value, first family with its method and
  adjusted p-value, the first equivalence test and the sample and cluster
  counts. A row opens to every equivalence test, every family membership
  (with the family MDE), the test statistic, the engine's message and the
  conventions.
- The statistics panel: **Inference** (each family with its adjustment method
  and the adjusted p-values of its members, the equivalence tests with their
  bounds and decisions, the minimum detectable effects and the joint Wald
  tests) and **Fit** (the run's warnings and the per-fit summaries).

- **Examples**, for a run that reads variant designs: the units of the
  design, paged, and one unit opened in the unit viewer with the answers of
  the chosen system. Along the factor the chosen contrast compares (read
  from the spec: an `ame` contrast's column, a dummy term `factor[level]`,
  or an expression measure that reads one factor, such as
  `1 * (role == 'A')`), twin tasks stand side by side, the reference level
  on the left, with the spans the design lets differ highlighted; the
  reader can pick another factor and levels. Each answer shows its parsed
  values and flags and opens the request it sent, with the hash check. The
  units need full read access to the task content (ORG_ADMIN, CONTRIBUTOR).

Superadmins and members whose project grants edit rights (`can_edit`) get
**Start analysis**: a dialog that takes a spec as JSON, a saved plan or an
earlier run's spec (see above), validates it against the engine (every
problem it names is listed) and starts the run, which the view then selects
and polls. A pending or running run is polled until it finishes.

`/evaluations/analysis/{analysis_run_id}` is the run page, next to the
evaluation run page `/evaluations/{id}`. It shows the same status, warnings,
forest plot and estimates, plus the run's provenance (spec hash, frame hash,
the SHA-256 of the stored frame file and its size, the lockfile hash, engine,
spec format and library versions, the seed, the frame counts and the
timings), the variant designs the run read (factor tree, status, content
and spec hashes, and the assignment, balance and invariance checks on
request), the spec (normalized, or as submitted) and the per-fit summaries.
It also shows the profile of a contrast that varies over an ordered scope
and the examples.
"New run from this spec" opens the start dialog prefilled with that run's
spec (`&newRunFrom={analysis_run_id}`). The frame download button (ORG_ADMIN
and CONTRIBUTOR) fetches the short-lived URL of the Parquet snapshot.

The old paths redirect permanently: `/projects/{project_id}/analysis` to
`/evaluations?projectId={project_id}&type=analysis`, its `?from={run}` to
`&newRunFrom={run}`, and `/projects/{project_id}/analysis/{run}` to
`/evaluations/analysis/{run}`.

The pages compute no statistics; every number is the stored estimate. The
Metrics view gains the same forest view: the mean and 95 % confidence
interval of each model per metric, from the statistics of the Model analysis
level.

### Building on the views

Metric statistics and analysis estimates both map into interval rows
(`@/lib/results/intervalRows`: `intervalRowsFromStatistics`,
`intervalRowsFromEstimates`), and the forest, bar and table views draw
interval rows whatever produced them. The forest plot
(`@/components/analysis/ForestPlot`) takes plain rows, a null value, an
optional band and a `mode` (`point` or `bar`), so overlay views can reuse it
with their own bounds. `ContrastForest` draws one contrast with a given band
and no pickers, and `EstimatesTable` takes `compact` to drop its filters and
its count; the project report's Analyses section draws its exhibits with
both (see [Project reports](project-reports.md#analyses)). Links to result pages use the path helpers in
`@/lib/results/paths` (`analysisRunPath(runId)`,
`evaluationsPath({ projectId, type, run, newRunFrom })`).

The generic views take plain props and have a loader beside them, so the
evaluations page, the run page, the report and overlays render the same
components (CORE 2.73):

| Component | Draws |
|---|---|
| `EstimateProfileChart` (data from `@/lib/analysis/profile`) | estimates over an ordered or numeric x, series, facets, a fitted and a reference slope, a band |
| `ValueDistributionChart` | a distribution of values (exact values or bins) with a reference line, the mean and a summary |
| `StrengthForestPlot`, `EstimatesForest` | Bradley-Terry strengths (`strength[<level>]`) against the reference per scope; term coefficients and user contrasts of the estimand stay in the contrast forest |
| `VariantUnitViewer`, `VariantUnitLoader` | the tasks of a unit, twins side by side with their spans highlighted, answers and requests |
| `RequestRecordView`, `RequestRecordLoader` | a request record with its hash check (also the generation page's request view) |
| `VariantDesignPanel`, `VariantDesignsLoader` | a design's factor tree, status, hashes and checks |
| `ExamplesPanel` | the units behind a contrast |

`@/lib/api/variantViews` reads the units, designs and request records.

## Compliance overlay slots

The platform owns the routes the compliance overlay fills; the overlay
registers the components. They render only while the overlay's master flag
`extension.compliance` is on for the viewer, and otherwise show a
not-available notice (route shells) or nothing (inline slot):

| Slot | Where | Props |
|---|---|---|
| `ComplianceDashboard` | `/compliance` (and a navigation entry) | none |
| `AssessmentDetail` | `/compliance/assessments/{assessment_id}` | `{ assessmentId }` |
| `AnalysisRunFindings` | the analysis run page, below the estimates, and the Analyses view of `/evaluations` for the selected run, below the statistics panel | `{ projectId, run, estimates }` |

## Reproducibility

The same frame, the same normalized spec and the same engine version give
bit-identical estimates on one machine (MixedLM's variance component as far
as statsmodels' optimizer is deterministic, which the workers' lock pins); the golden-file tests in
`services/workers/tests/analysis/` fail on any numeric change, and a change
that moves a number bumps `ENGINE_VERSION`. The default `statsmodels`
convention reproduces `statsmodels` OLS with cluster-robust covariances on the
same data to machine precision, and the `fixest` convention reproduces
pyfixest's defaults; both are checked in the tests. The logit, its
variances and marginal effects, MixedLM, Bradley-Terry, the rank-ordered
logits, the joint tests and Spearman's rho are checked at 1e-9 relative
against independent reference implementations on simulated answers
(statsmodels formula fits, a scipy-optimised rank-ordered logit,
`scipy.stats.spearmanr`), see `test_analysis_estimator_references.py`.
