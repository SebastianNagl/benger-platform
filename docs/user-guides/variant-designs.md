# Variant designs

A variant experiment runs the same item in several controlled variants and compares the answers: a counterfactual test swaps the parties of a case, a robustness test reorders the case file or removes a piece of evidence. BenGER stores such an experiment in two places, each the single source of one fact:

- The design is a project-level object (`variant_designs`): the unit that ties the variants of one item together, the factors with their levels, optional per-answer slots, and which controls, gold values and text fields the analysis uses. A design can be checked and frozen.
- Each task's place in the design is `task.meta.variant`. Label Studio treats `meta` as opaque task data, so the assignment survives import, export and project cloning unchanged.

The database derives three columns from `meta.variant` (`tasks.variant_design`, `variant_unit`, `variant_cell`) and allows one task per cell and unit. A cell compares regardless of the order of its keys, so `{"role": "claimant", "order": "a"}` and `{"order": "a", "role": "claimant"}` are the same cell.

## The design

The spec follows `services/shared/schemas/variant_design.schema.json`. A party swap with a counterbalanced print order looks like this:

```json
{
  "schema_version": 1,
  "title": "Party swap",
  "unit": {"name": "case"},
  "factors": [
    {"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]},
    {"name": "order", "type": "nominal", "levels": ["a", "b"], "role": "counterbalanced"},
    {"name": "difficulty", "type": "numeric", "varies": "between_units"},
    {"name": "reasoning", "type": "boolean", "source": "system"}
  ],
  "outcomes": [
    {"name": "share", "by_factor": {"factor": "role",
      "controls": {"claimant": "share_claimant", "respondent": "share_respondent"}}}
  ],
  "gold": [{"name": "fair_share", "path": "reference.share"}],
  "invariance": {"fields": ["facts"], "free": ["reference"]}
}
```

- Factors have a type (`nominal`, `ordinal`, `numeric`, `boolean`), a role (`manipulated`, `counterbalanced`, `blocking`, `nuisance`) and a source. Only `task` factors are stored per task; `structure` (the prompt structure, for example an answer format), `system` (the model and its parameter profile) and `run` factors come from the generation.
- A `within_unit` factor (the default) differs between the variants of one unit, and every unit must hold every combination of the levels of these factors, unless the design lists its `cells`. A `between_units` factor is constant inside a unit.
- `slots` describe several records inside one answer (one per person or case), with their own factors and a count that is fixed or follows a list in `task.data`. Per-slot outcomes put `{idx}` where the slot index goes (`risk_{idx}`).
- `gold` names reference values in `task.data`. They are never sent to a system under test.
- `invariance` says what may differ inside a unit: the text of the `fields` only inside the character spans each task declares, the `free` paths freely, and every other value of `task.data` not at all.

## The assignment

`meta.variant` follows `services/shared/schemas/task_variant.schema.json`:

```json
{
  "design": "swap",
  "unit": "case-017",
  "factors": {"role": "claimant", "order": "a", "difficulty": 30},
  "spans": {"facts": [[12, 22], [57, 58]]},
  "provenance": {"generator": "my-builder 1.2", "source_sha256": "..."}
}
```

`spans` are `[start, end)` character ranges of a text field in which this task may differ from its twins; slots can carry their own `spans`. Every write of a task checks its assignment against the design: the JSON and CSV imports, the task meta and data edits, the project import and clone, and the merge import. An unknown design, an unknown level, a missing factor, a span outside its text or a missing required gold value is refused with 422, and a second task in the same cell of the same unit with 409.

In a CSV file (and in rows pasted or uploaded on the project data page) a column named `meta.variant` holds the assignment as JSON text; it moves into `meta` and does not become a data field.

The assignment is never shown to a system under test or to an annotator who works blind: the v1 task reads leave it out for every caller, the blinded task views keep only the tags and the public benchmark descriptors of `meta`, and prompts are built from `task.data` alone. This is an intended deviation from Label Studio, which passes `meta` to its ML backends.

## Checks and freezing

`POST /api/projects/{id}/variant-designs/{key}/check` runs three checks over the tasks of a design and changes nothing:

- assignments: every task fits the current spec;
- balance: every unit holds exactly the expected cells, once each, and the `between_units` factors are constant inside a unit;
- invariance: within each unit, every pair of tasks differs only where the design allows it, and the report quotes the first offending range of both texts.

`POST .../freeze` runs the same checks and, when all pass, records a content hash over the spec and every task's data and assignment. From then on the tasks' `data` and `meta.variant` are read-only (409), the design takes no new tasks, and its tasks cannot be deleted; tags and other meta stay editable. A frozen design is never thawed: a changed experiment is a new design with a new key. A draft's spec can be replaced (`PUT`, the version goes up by one) as long as every task already in it still fits.

## Export and import

The JSON and comprehensive project exports carry a `variant_designs` array when the project has designs, and the NDJSON export carries `variant_design` records before the tasks. Every importer creates the designs before their tasks and freezes a frozen design again before it commits, which re-runs the checks and must reproduce the recorded content hash; an edited export is refused. A task subset export carries its designs as drafts. A single design can also be exported (`GET .../{key}/export`) and imported into another project (`POST .../variant-designs/import`, as a draft); its tasks then follow with a task import.

## Routes

| Method | Path | Needs |
|---|---|---|
| GET | `/api/projects/{id}/variant-designs` | full-data access to the project |
| POST | `/api/projects/{id}/variant-designs` | project edit rights |
| POST | `/api/projects/{id}/variant-designs/import` | project edit rights |
| GET | `/api/projects/{id}/variant-designs/{key}` | full-data access |
| GET | `/api/projects/{id}/variant-designs/{key}/export` | full-data access |
| PUT | `/api/projects/{id}/variant-designs/{key}` | project edit rights |
| DELETE | `/api/projects/{id}/variant-designs/{key}` | project edit rights (a draft no task names) |
| POST | `/api/projects/{id}/variant-designs/{key}/check` | full-data access |
| POST | `/api/projects/{id}/variant-designs/{key}/freeze` | project edit rights |

Refusals answer `{"detail": {"code": ..., "message": ..., "problems": [...]}}`, where each problem names a JSON path (`/spec/factors/0/levels`, `/meta/variant/factors/role`) and what is wrong with it. Access keys need `tasks:read_reference` to read designs and `projects:write` to change them.
