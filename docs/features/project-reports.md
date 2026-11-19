# Project reports

A project report is the written account of a project: what data it holds,
who annotated it, which models generated answers, how they were evaluated by
metrics and by people, and what a reader needs to reproduce the numbers. The
author writes the prose and chooses what to show; the numbers come from a
snapshot computed on the server, so a published report stays stable and an
anonymous reader of a public report never touches live data.

The code lives in `services/shared/report_snapshot.py` (the snapshot),
`services/shared/report_service.py` (the publish rule) and
`services/api/routers/reports.py` (the routes and the author rule). The
viewer is `/reports/[id]`, the editor `/projects/[id]/report/edit`, and the
shared view components are in `services/frontend/src/components/reports/view/`.
The snapshot's TypeScript shape is `ReportSnapshot` in
`services/frontend/src/types/report.ts`.

## Who writes and publishes a report

`can_edit_report` in `routers/reports.py` decides who authors a project's
report: who may view the draft, edit it, publish and unpublish it, switch it
between organizations-only and public, and refresh its snapshot.

- A superadmin.
- The project's creator (its owner).
- An active `ORG_ADMIN` of an organization the project is attached to,
  through an attachment that counts for them (a grouped attachment counts
  only for the group's members and the organization's admins, and a
  protected LMS link never does).

This is the project edit rule of `check_user_can_edit_project_async`
narrowed to the `ORG_ADMIN` role. Contributors, annotators and other members
read a published report of their organization but do not author it, and a
soft-deleted project's report is authored by superadmins only. Every report
response carries `can_edit`, which the project page's report card, the
publish toggle, the editor and the viewer's edit link read. A report that
does not exist yet is created on an author's first view.

## When a report can be published

`can_publish_report` allows publishing when the report exists, the project
has tasks, and it has at least one result of any kind: annotations that were
not cancelled, generations, completed evaluation runs or completed analysis
runs. So an annotation study, a human evaluation without generations and an
analysis-only project can publish as well as a benchmark. The refusal reasons
are `Project must have tasks` and `Project must have annotations,
generations, evaluations or analyses`.

## The snapshot

Publishing and "Refresh data" compute the snapshot and store it in
`project_reports.content.snapshot`; the editor's preview computes one on the
first view of a draft. Every number is aggregated in Postgres. Besides the
metric evaluation (`statistics`, `methods`, `configs`, `series`,
`distributions`, `participants`, `models`) it holds four sections. Each is
present for every project and empty when the project has nothing of its
kind, and the viewer hides a section without data, so an annotation-only
project gets a report with Data, Annotations and Reproducibility only.

| Key | Contents |
|---|---|
| `data` | task count; per [variant design](../user-guides/variant-designs.md) its key, title, status, version, unit, factors (type, role, source, levels), task, unit and cell counts, content hash, spec hash and provenance; completed imports with payload hash and size, mode, task count, the declared manifest and whether the import was a no-op repeat (at most 200, with the total) |
| `generation` | per model the generations, completed and failed ones, tasks, runs per task, prompt structures, and the refusal, truncation and retry rates (shares of completed generations), the parse-failure rate (share of parsed generations) and the share with a stored request record; the same totals over all visible models |
| `human_evaluations` | Likert ratings per dimension (n, mean, standard deviation, counts per scale point, per model) and preference comparisons (per model wins, losses, ties and win rate, per pair of models), with the number of evaluators |
| `reproducibility` | platform versions (app and CORE), label config version and SHA-256, model and provider ids, prompt structure keys with the SHA-256 of their stored definition, each evaluation config with the parameter snapshots its judge runs used (judge model, sample count, SHA-256 and the parameters), variant design and import hashes, the completed analysis runs that read this project only (spec hash and version, engine version, frame hash and SHA-256, rows, estimates, library versions, lockfile SHA-256, seed), and `snapshot_sha256` |

A declared manifest or design provenance larger than 16 KB is stored as its
SHA-256 only. Where an import's payload was stored (object key, file name)
is never part of a report.

### Hidden models

A custom (BYOM) model that is neither official nor public is left out of a
report unless the builder is called with `include_private_models`, like on
the LLM leaderboard. The rule holds in every section: its metric rows, its
generation counts and rates, the ratings of its answers, and every
preference comparison it took part in (dropped whole, since its opponent's
record would otherwise tell how it did).

### `snapshot_sha256`

`snapshot_sha256` is the SHA-256 of the canonical JSON of the snapshot
without `generated_at`, `reproducibility.platform` and the hash itself: keys
sorted, no whitespace, floats rounded to 12 significant digits, and every
list sorted to a total order. A rebuild over unchanged data therefore gives
the same hash, whenever and on whichever build it runs, and any change to a
number or record changes it. `canonical_snapshot_json` and `snapshot_sha256`
in `report_snapshot.py` compute it; a reader can recompute it from the JSON
the report's data link serves.

## Content sections

`content.sections` holds the author's prose and switches. Besides the
existing keys, `data.show_provenance`, `generation.show_details` and
`evaluation.show_human_evaluation` (all default true) switch the new record
parts on and off, and `sections.reproducibility` (`visible`, default true,
and `custom_text` for the author's notes on reproduction) controls the
appendix. Older reports without these keys show everything.

## Reading and citing a report

The viewer ends with a citation block for a published report: a citation
with title, publication date, URL and snapshot hash, a BibTeX entry, a
"Data (JSON)" link to `GET /api/reports/{id}/data` (the report row and its
snapshot, readable by whoever may read the report) and a print button. The
page prints as a document: the app header, sidebar and footer are hidden,
tables are not clipped, and a report viewed in dark mode prints dark text on
white (the print rules in `services/frontend/src/styles/tailwind.css`).
