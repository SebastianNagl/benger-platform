# Inter-annotator agreement

When two or more people annotate the same task, BenGER reports how closely
they agree, separately for every control of the labeling interface. The
numbers appear in two places:

- on the evaluations page (`/evaluations`), in the "Annotator agreement"
  block below the evaluation results of the selected project, computed from
  the live annotations;
- in the project report, at the end of the Annotation section, frozen into
  the report snapshot when the report is published or refreshed. The report
  editor's Annotation card has a switch to hide the block; with it off,
  every API response that carries the report or its snapshot leaves out the
  agreement data entirely, and switching it back on shows the frozen block
  again without a refresh. When the card's participant switch is off, the
  report keeps the summary numbers and the participant count, but every API
  response that carries the report or its snapshot leaves out the annotator
  pairs and both participant lists (the snapshot's and the Annotation
  section's). The stored report stays complete, so switching participants
  back on shows the frozen pair table and participant list again without a
  refresh.

Both places hide the block when no task has two annotators, or when none of
the overlapping controls can be scored.

## What is compared

A task counts for a control when at least two people answered that control
on it. Only active annotations count (withdrawn ones do not); BenGER keeps
one active annotation per person and task.

| Control | Compared as | Reported |
|---|---|---|
| `Choices` (single selection) | category | Fleiss' kappa, Cohen's kappa per pair, mean of the pairwise kappas, share of tasks where everyone agrees |
| `Choices` (multiple selection) | one category per set of choices | as above; two annotations agree only when they picked exactly the same set |
| `Rating` | category (unweighted kappa) | as above |
| `Number` | number | Pearson's r per pair and its mean, mean absolute deviation from each task's mean |

Free text, spans and other controls have no comparable value and are listed
as not scored.

The block reads kappa on the Landis and Koch scale: below 0 poor, 0 to
0.20 slight, up to 0.40 fair, up to 0.60 moderate, up to 0.80 substantial
and above 0.80 almost perfect, each upper limit included in its band. A pair
of annotators needs at least two shared tasks for a Cohen's kappa. With many
annotators the pair table shows the 50 pairs with the most shared tasks and
says how many there are in total; the summary numbers always cover all
pairs.

Annotators are shown by pseudonym, or by a neutral label built from the
account id when they have none, never by real name or login name.

## API

```http
GET /api/evaluations/projects/{project_id}/annotator-agreement
```

Needs read access to the project (access keys: `annotations:read`). Returns
`available: false` without overlap, otherwise:

```json
{
  "available": true,
  "overlap_task_count": 4,
  "annotator_count": 3,
  "controls": [
    {
      "control": "label",
      "type": "choices",
      "score_type": "categorical",
      "multi_select": false,
      "n_items": 4,
      "n_annotators": 3,
      "n_annotations": 12,
      "categories": ["x", "y"],
      "fleiss_kappa": 0.3333,
      "cohens_kappa_mean": 0.4,
      "percent_agreement": 0.5,
      "pearson_r_mean": null,
      "mean_absolute_deviation": null,
      "pairs": [
        {"annotator_a": "Ash", "annotator_b": "Birch", "n_items": 4, "cohens_kappa": 0.5}
      ],
      "pairs_total": 3
    }
  ],
  "unsupported_controls": [{"control": "comment", "type": "textarea"}]
}
```

The report snapshot stores the same object (without `available`) under
`annotator_agreement`, or `null` without overlap.

## Implementation

`services/shared/annotator_agreement.py` loads the active annotations of
tasks with two or more annotators and passes (annotator, task, value)
triples per control to `bg_statistics.compute_agreement`, the helper the
statistics endpoint also uses for agreement between LLM judges.
