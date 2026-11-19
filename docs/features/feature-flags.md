# Platform feature flags

The platform's own features that are not released to everybody sit behind
platform feature flags. They use the same engine as the overlay packages
(`services/shared/feature_flags`, `/api/feature-flags`, the admin console at
`/admin/feature-flags`) with the states `off`, `everyone` and `allowlist`
(listed users, members of listed organizations). Every platform flag is owned
by the platform and coupled to no overlay's master flag.

| Flag | Default | Covers |
|---|---|---|
| `public_api` | off (`PUBLIC_API_ENABLED` sets it) | access keys and `/api/v1` ([public-api.md](../public-api.md)) |
| `variant_experiments` | off | controlled variant experiments and their analyses, see below |
| `compliance_records` | off | the compliance records API and the `/compliance` pages |

## `variant_experiments`

Covers variant designs, per-item answers (Label Studio `<Repeater>`),
generation fidelity (the request record, answer-format options, format
retry, lossless generation export and import, up to 100 runs per task), the
open-weight panel models and the system key, analysis runs (engine,
estimators, frames, lookup tables), codes, text patterns and coding
validation, analysis plans and the Analyses part of the project's
Evaluation card, the analysis results views and counts (profiles,
strengths, examples, the unit and request views), import provenance,
annotator agreement (computed from annotations alone, on the evaluations
page and in the report's Annotation section), the Agreement and validity
block (judge agreement on the evaluations page, code validations of the
analysis runs' codes in runs and reports) and, inside reports, the Analyses
section and every place a report lists or counts analysis runs or variant
designs.

The report as the project's paper is not behind the flag: project owners and
organization admins author and publish it, a project publishes with tasks
and at least one annotation, generation or evaluation, and a snapshot has
its data, generation, human evaluation and reproducibility parts for every
project type.

With the flag off:

- the feature's routes answer `404 {"code": "feature_disabled", "flag":
  "variant_experiments"}`: analysis, coding, variant designs and their
  units, the label-config `label-studio` and `slots` routes, the trial
  request record (by generation and trial, and by trial alone),
  annotator agreement, the report's `analysis-runs` list,
  `/api/runs?type=analysis` and the v1 analysis routes;
- analysis runs and code validations of an owner with the flag off are not
  computed and end failed with the feature-disabled message;
- the pages are not found, and the entry points, panels, counts, chart
  types and changelog entries are not shown;
- every behaviour these features changed is the one the platform had
  before: a generation records no request and no system key and runs every
  prompt structure at the default answer format; a multi-choice control
  asks for one value and answers are parsed as before; at most 25 runs per
  task; `text_pattern` is not offered and does not run; a `<Repeater>` label
  config is refused; every import imports (no provenance, no no-op
  repeats); generation exports and task-level imports have their previous
  fields; the panel models are not listed or generated with and the
  `enable_thinking` switch of Qwen 3.8 27B, Nemotron 3.5 Lightning and
  Gemma 4 26B is neither shown nor sent; a completed analysis run does not
  count as a result for publishing a report, new snapshots have no
  annotator agreement, Analyses section or analysis count and list no
  variant designs or analysis runs in their data and reproducibility parts,
  saving a report neither adds nor changes its Analyses settings nor adds
  the agreement and code validation switches, and an evaluation config
  write ignores `analysis_plans`;
- stored data stays as it is: designs, runs, codes, records, options and
  report snapshots are neither deleted nor rewritten, and a project built
  while the flag was on still opens without errors.

## `compliance_records`

Covers the generic compliance records API (`/api/compliance`: assessments,
suite runs and findings) and the `/compliance` route shells with their
navigation item. The compliance overlay's own UI inside those shells also
needs the overlay's master flag `extension.compliance`.

## Who a flag is decided for

- API routes and pages: the caller, as for every flag. On the v1 analysis
  routes an organization access key also counts for its organization, as
  with `public_api`.
- Jobs: the user the job belongs to (the generation's or run's creator, the
  import or export requester), decided once per job; the job carries the
  answer into shared code through `feature_flags.scope`.
- Report content read by others (published reports, anonymous readers): a
  snapshot holds the flag's parts only when it was built with the flag on,
  and they are served while the flag is on for anybody, so switching the
  flag off for everybody hides them everywhere without rewriting a report.

## Left on with the flag off

Genuine fixes that shipped together with these features stay on, among them
the report's participant visibility, the hidden-model filters of reports
(including the refusal to make a report public while its stored snapshot
holds an analysis run in which a private model may appear), the labelled
close button of dialogs, the significance heatmap's dark mode and phone
width, the e2e seed's evaluation config ids,
the `/api/runs` paging and access count, the provider quota fail-fast, the
JSON fallback prompt of OpenAI, Cohere and Mistral, the code-fence parse fix,
the Label Studio `to_name` fill on export and the evaluations page's project
search. Data-layer pieces stay too: the migrations, the purge of analysis
rows, the `analysis` queue, and the import and export of variant designs
(only projects that have designs carry them).

## Rollout on production

Both flags start `off` in code, and the registry sync creates a missing row
at that default without ever overwriting a row's state. On production they
start off for everyone except an allowlist, for the pilot the TUM
organization. After the deploy that brings the flags, a superadmin sets this
once per flag (`variant_experiments`, `compliance_records`), either in the
admin console at `/admin/feature-flags` (state `allowlist`, then add the
organization as a target) or through the API:

```
PUT  /api/feature-flags/variant_experiments           {"state": "allowlist"}
POST /api/feature-flags/variant_experiments/targets   {"organization_id": "<TUM organization id>"}
PUT  /api/feature-flags/compliance_records            {"state": "allowlist"}
POST /api/feature-flags/compliance_records/targets    {"organization_id": "<TUM organization id>"}
```

The steps are idempotent: setting the same state again changes nothing, and
adding a target that is already listed answers `409 target_exists`. Members
of the TUM organization then get the features, everybody else keeps the
flag-off behaviour above; the compliance overlay's own UI also needs
`extension.compliance` for them.

## Variant assignments: `meta.benger_variant`

A task's place in a variant design is stored under the reserved key
`meta.benger_variant` (`variant_designs.META_KEY`). The database derives the
design columns from it, refuses a key naming no design, allows one task per
design cell and keeps frozen designs read-only, whatever the flag. A
`meta.variant` a user stores is plain data.
