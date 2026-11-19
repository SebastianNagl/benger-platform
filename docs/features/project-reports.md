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
analysis-only project can publish as well as a benchmark. Every run the
Analyses section names must also be one the report can show (see
[Analyses](#analyses)). The refusal reasons are `Project must have tasks`,
`Project must have annotations, generations, evaluations or analyses` and
`Every run in the Analyses section must be a completed analysis run of this
project that reads no other project`.

## The snapshot

Publishing and "Refresh data" compute the snapshot and store it in
`project_reports.content.snapshot`; the editor's preview computes one on the
first view of a draft. Nothing else writes it: saving the editor's content
keeps the stored snapshot and ignores one a client sends. Every number is aggregated in Postgres. Besides the
metric evaluation (`statistics`, `methods`, `configs`, `series`,
`distributions`, `participants`, `models`) it holds five sections. Each is
present for every project and empty when the project has nothing of its
kind, and the viewer hides a section without data, so an annotation-only
project gets a report with Data, Annotations and Reproducibility only.

| Key | Contents |
|---|---|
| `data` | task count; per [variant design](../user-guides/variant-designs.md) its key, title, status, version, unit, factors (type, role, source, levels), task, unit and cell counts, content hash, spec hash and provenance; completed imports with payload hash and size, mode, task count, the declared manifest and whether the import was a no-op repeat (at most 200, with the total) |
| `generation` | per model the generations, completed and failed ones, tasks, runs per task, prompt structures, and the refusal, truncation and retry rates (shares of completed generations), the parse-failure rate (share of parsed generations) and the share with a stored request record; the same totals over all visible models |
| `human_evaluations` | Likert ratings per dimension (n, mean, standard deviation, counts per scale point, per model) and preference comparisons (per model wins, losses, ties and win rate, per pair of models), with the number of evaluators |
| `analyses` | the runs of the [Analyses section](#analyses) with their metadata, the estimates their exhibits select and the exhibits, plus `omitted`, the runs it names but cannot show |
| `reproducibility` | platform versions (app and CORE), label config version and SHA-256, model and provider ids, prompt structure keys with the SHA-256 of their stored definition, each evaluation config with the parameter snapshots its judge runs used (judge model, sample count, SHA-256 and the parameters), variant design and import hashes, the completed analysis runs that read this project only (spec hash and version, engine version, frame hash and SHA-256, rows, estimates, library versions, lockfile SHA-256, seed), and `snapshot_sha256` |

A declared manifest or design provenance larger than 16 KB is stored as its
SHA-256 only. Where an import's payload was stored (object key, file name)
is never part of a report.

### What a reader outside the project gets

The stored snapshot is whole, but what is served follows the reader. Report
authors and members of the project's organizations (the report read rights
of `check_report_access`) get it as stored. A reader outside the project, an
anonymous or signed-in reader of a public report, gets the public view
(`public_snapshot` in `report_snapshot.py`), applied on every read path
(`GET /api/reports/{id}/data`, its `snapshot` and `report.content.snapshot`):
each judge run's parameters, each declared import manifest and each design
provenance keep their SHA-256 but lose their content, so custom judge
prompts, rubric and Bewertungsbogen criteria and author manifests stay
inside the project, and the Analyses section's `omitted` list is left out.

### Hidden models

A custom (BYOM) model that is neither official nor public is left out of a
report unless the builder is called with `include_private_models`, like on
the LLM leaderboard. The rule holds in every section: its metric rows, its
generation counts and rates, the ratings of its answers, and every
preference comparison it took part in (dropped whole, since its opponent's
record would otherwise tell how it did). A hidden judge model is not named
either: its config's `judge_model` and the judge runs in the reproducibility
appendix show no id, and a judge run whose parameters name a hidden model
(its `judge_model` or a `judges[].judge_model_id`) keeps only their SHA-256,
for every reader.

### `snapshot_sha256`

`snapshot_sha256` is the SHA-256 of the canonical JSON of the snapshot
without `generated_at`, `reproducibility.platform` and the hash itself: keys
sorted, no whitespace, floats rounded to 12 significant digits, and every
list sorted to a total order. A rebuild over unchanged data therefore gives
the same hash, whenever and on whichever build it runs, and any change to a
number or record changes it. `canonical_snapshot_json` and `snapshot_sha256`
in `report_snapshot.py` compute it; a reader with the project's read rights
can recompute it from the JSON the report's data link serves (the public view
leaves content out, so it carries the hash but cannot reproduce it).

## Content sections

`content.sections` holds the author's prose and switches. Besides the
existing keys, `data.show_provenance`, `generation.show_details` and
`evaluation.show_human_evaluation` (all default true) switch the new record
parts on and off, and `sections.reproducibility` (`visible`, default true,
and `custom_text` for the author's notes on reproduction) controls the
appendix, and `sections.analyses` holds the [Analyses section](#analyses).
Older reports without these keys show everything.

## Analyses

The Analyses section shows analysis runs of the project the way a paper
shows its results: per run the author's title and text, the run's metadata,
its multiplicity families and warnings, and the exhibits the author defined,
numbered across the report as figures (forest plots) and tables. With an
Analyses section, the conclusions follow it.

The editor's Analyses card offers the runs of `GET
/api/projects/{project_id}/report/analysis-runs` (report authors): the
project's completed runs that read no further project, neither through
`inputs.projects` nor through a stored lookup table of another project
(`report_analysis_runs` in `report_snapshot.py`), because a report must not
publish another project's numbers. The reproducibility appendix lists the
same runs. Per exhibit the author picks the type (forest plot or table) and
the filters, and the card previews the run's live estimates with the
components the report draws (`ContrastForest` and the compact
`EstimatesTable` of `components/analysis`).

`content.sections.analyses` has this shape, normalized and checked on save
(`parse_analyses_section`; a problem answers 422 `invalid_report_analyses`
listing every problem):

```json
{
  "visible": true,
  "custom_text": "What the analyses examine",
  "runs": [
    {
      "run_id": "<analysis run id>",
      "title": "Framing effect",
      "text": "What this run shows",
      "exhibits": [
        {
          "id": "exhibit-1",
          "type": "forest",
          "title": "Effect per system",
          "caption": "Points are estimates, lines 95 % intervals.",
          "filters": {"estimands": ["framing_effect"], "systems": ["sys_a"]},
          "band": 0
        }
      ]
    }
  ]
}
```

A section takes at most 10 runs and a run at most 12 exhibits. An exhibit
`id` is 1 to 64 letters, digits, `-` or `_`, unique within its run; `type`
is `forest` or `table`; `band` is the equivalence bound set a forest draws
(the index into an estimate's `tost`, default the first, `null` for none).
Each filter is a list of values, and an absent or empty one does not
restrict. An estimate is shown when every given filter holds
(`exhibit_selects`, mirrored for the preview by `exhibitSelects` in
`services/frontend/src/lib/reports/analyses.ts`):

- `estimands`: its `estimand_id` is listed;
- `contrasts`: its `contrast_id` is listed;
- `families`: a family it belongs to (`family` or an `adjustments` entry) is
  listed;
- `systems`: it involves at least one system and every system it involves
  is listed, so a fully pooled estimate that involves no system shows only
  in an exhibit without a systems filter, and a pooled contrast of system B
  against the reference does not show in an exhibit filtered to system A.

The systems an estimate involves (`estimate_systems`, mirrored by
`estimateSystems`) are the one it is scoped to (its `system` or `model_id`
scope value) plus every system level its definition in the run's normalized
spec names as a parameter `system[<level>]` or `model_id[<level>]`: the
weight keys of a listed contrast (numerator and denominator of a ratio; the
level and reference of an average marginal effect over a system column),
the contrast id itself when the spec lists no such contrast (as for
`terms`), the rows, parameters (matched against the fit's parameters) or
contrasts of a joint test, and the level and reference of a paired
treatment over a system column. A `system` or `model_id` parameter (also
inside an interaction) is measured against the reference level of its
dummy coding, so that level is involved too: the one the fit recorded in
its summary (`references`), or, for a run made before fits recorded it, the
`reference` the spec declares (a level is never guessed from the order of
the levels). Bradley-Terry strengths `strength[<level>]` and their
reference count as systems when the fit recorded `players_are_systems`.
The editor reads the run's normalized spec and fits for its preview, so it
selects the rows the snapshot copies.

Publishing and "Refresh data" copy into `snapshot.analyses.runs`, per run:
id, name, spec hash and version, engine version, frame hash and SHA-256,
frame rows, estimate count, completion time, warnings, the families of the
shown estimates (method and size), `truncated`, `estimates` (the union of
its exhibits' estimates in engine order, every engine field without the
database row id, non-finite numbers as null) and `exhibits` (id, type,
filters, band, `row_count` and the `positions` of its estimates). A run
keeps at most 1000 estimates; beyond that the first ones in engine order
stay and the run is `truncated`, which the editor warns about. The viewer
draws numbers only from this copy, so a published report keeps them
whatever happens to the run's project afterwards; titles, texts and
captions are the author's prose and are read live from `content.sections`,
matched by run and exhibit id. A run the section names but the report
cannot show (not a run of this project, not completed, or reading another
project) is listed in `omitted` with the reason and blocks publishing.

The hidden-model rule applies per run here. A run is member-only when a
hidden model (`model_is_public`) may appear anywhere in it: among the
models of its frame (`resolved_inputs.models`, recorded by the worker: every
`model_id` and the model part of every system key), among the levels its
fits name (parameters, recorded `references`, Bradley-Terry `players`) or
among the scope values of its estimates. A run that does not record its
frame's models (made before the worker did) counts as member-only. The
snapshot copies a member-only run whole and marks it `member_only`;
members of the project see it, while the public view (`public_snapshot`,
served to every reader outside the project) leaves it out. The run list
of the editor says per run whether it is member-only: the editor marks
such a run and does not offer it while the report is public. Publishing
as public, or switching a published report to public, is refused while
the snapshot holds a member-only run ("A public report cannot show an
analysis run in which a private model may appear"). A report that was
already public when such a run was added keeps it out of its public view,
and the editor says so. The frame is never linked, and only a report
author gets a link to the run page.

## Reading and citing a report

The viewer ends with a citation block for a published report: a citation
with title, publication date, URL and snapshot hash, a BibTeX entry, a
"Data (JSON)" link to `GET /api/reports/{id}/data` (the report row and its
snapshot, readable by whoever may read the report) and a print button. The
page prints as a document: the app header, sidebar and footer are hidden,
tables are not clipped, and a report viewed in dark mode prints dark text on
white (the print rules in `services/frontend/src/styles/tailwind.css`).
