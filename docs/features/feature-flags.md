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
| `report_paper` | off | the project report as the project's paper, see below |
| `bug_reports` | off | "Report a problem": in-app problem reports delivered as issues ([bug-reports.md](bug-reports.md)) |

## `variant_experiments`

Covers variant designs, per-item answers (Label Studio `<Repeater>`),
generation fidelity (the request record, answer-format options, format
retry, lossless generation export and import, up to 100 runs per task), the
open-weight panel models and the system key, analysis runs (engine,
estimators, frames, lookup tables), codes, text patterns and coding
validation, analysis plans and the Analyses part of the project's
Evaluation card, the analysis results views and counts (profiles,
strengths, examples, the unit and request views), import provenance,
annotator agreement, the Agreement and validity block (judge agreement on
the evaluations page, code validations of the analysis runs' codes in runs
and reports) and, inside reports, the Analyses section, the analysis count
and the values the paper's parts take from these features.

Annotator agreement stays behind this flag although it is computed from
annotations alone: the agreement on the evaluations page, the snapshot's
`annotator_agreement`, the report's agreement block in its Annotation
section and the editor's `show_agreement` switch are all off without it.

Inside the parts of the report as paper (`report_paper`), this flag covers
the variant designs of the data part, the provenance of imports (mode,
size, task count, payload hash, no-op repeats, declared manifest), the
refusal, retry and request record shares of the generation part, and the
variant design, import hash and analysis run lists of the reproducibility
appendix. With `report_paper` on and this flag off a report shows the paper
without those values: their columns and lines are not shown, and the
editor's data switch reads "Show imports".

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
  annotator agreement, Analyses section or analysis count nor the values
  listed above in the paper's parts, none of these is served while the
  flag is off for everybody, saving a report neither adds nor changes its
  Analyses settings nor adds the agreement and code validation switches,
  and an evaluation config write ignores `analysis_plans`;
- stored data stays as it is: designs, runs, codes, records, options and
  report snapshots are neither deleted nor rewritten, and a project built
  while the flag was on still opens without errors.

## `report_paper`

Covers the project report as the project's paper: authorship of the
project owner and the admins of the project's organizations besides
superadmins (the project page's report card for them too), the publish rule
for every project type (tasks plus at least one annotation, generation,
evaluation or, with `variant_experiments`, analysis run), the snapshot's
data, generation, human evaluation and reproducibility parts with
`snapshot_sha256`, the editor's switches and cards for them, the viewer's
hiding of empty tiles and sections and its citation block, and the
changelog entry of the report as paper.

With the flag off, reports behave as before this work: only superadmins
author them (each route answers its previous 403 message, for example "Only
superadmins can publish reports"), a report is published once the project
has tasks, LLM generations and completed evaluations, new snapshots have
none of the paper's parts, and stored ones are served without them while
the flag is off for everybody.

## `compliance_records`

Covers the generic compliance records API (`/api/compliance`: assessments,
suite runs and findings) and the `/compliance` route shells with their
navigation item. The compliance overlay's own UI inside those shells also
needs the overlay's master flag `extension.compliance`.

## `bug_reports`

Covers "Report a problem" (account menu, footer, error pages), the report
endpoint `POST /api/bug-reports`, the superadmin list at
`/admin/bug-reports` with its routes, the recorder of recent errors, failed
requests and page changes, and the changelog entry. Off: the entries are
gone, the recorder stops and drops what it held since page load, and every
route answers 404 `feature_disabled`; stored reports stay. A report sent
without a session counts as anonymous, so the flag reaches visitors only in
state `everyone`. Details in [bug-reports.md](bug-reports.md).

## Who a flag is decided for

- API routes and pages: the caller, as for every flag. On the v1 analysis
  routes an organization access key also counts for its organization, as
  with `public_api`.
- Jobs: the user the job belongs to (the generation's or run's creator, the
  import or export requester), decided once per job; the job carries the
  answer into shared code through `feature_flags.scope`.
- Report content read by others (published reports, anonymous readers): a
  snapshot holds a flag's parts only when it was built with the flag on for
  its author, and they are served while the flag is on for anybody, so
  switching a flag off for everybody hides them everywhere without
  rewriting a report. The hash a reader gets verifies against the data that
  reader gets: when serving leaves anything out (these flag parts, the
  report's visibility switches or the public view),
  `reproducibility.snapshot_sha256` is computed over what is served, and
  when nothing is left out it is the stored snapshot's hash
  (`report_snapshot.with_served_hash`).

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

All three flags (`variant_experiments`, `compliance_records`,
`report_paper`) are registered `off` in code. The rollout happens by itself
on deploy: migration `152_platform_flags_tum_rollout`, which the deploy's
migration job runs before the new API starts, creates each flag's row in
state `allowlist` with the TUM organization as its only target, when that
organization exists (the production organization by its id, else an
organization named `TUM`, as development and test seeds create) and the
flag has no row yet, that is, nobody has set it. A row that exists is left
exactly as it is, without a TUM organization nothing is written, and a
second run changes nothing. The registry sync after the migrations only
creates missing rows at `off` and fills in descriptions; it never changes a
row's state or targets.

Members of the TUM organization then get the features, everybody else keeps
the flag-off behaviour above; the compliance overlay's own UI also needs
`extension.compliance` for them. Afterwards an admin changes a flag in the
admin console at `/admin/feature-flags`, for example `report_paper` to
`everyone` on its own.

## Variant assignments: `meta.benger_variant`

A task's place in a variant design is stored under the reserved key
`meta.benger_variant` (`variant_designs.META_KEY`). The database derives the
design columns from it, refuses a key naming no design, allows one task per
design cell and keeps frozen designs read-only, whatever the flag. A
`meta.variant` a user stores is plain data.
