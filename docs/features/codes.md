# Codes: text patterns, coder plugins, judge codes and coding validation

A code is an outcome read off an answer by a procedure rather than taken from
a parsed field: whether an answer mentions a phrase, which party it blames,
how many norms it cites. BenGER supports four kinds, all usable as measures
of an [analysis spec](analysis-engine.md), and validates them the Label
Studio way, against human codes in a coding project.

| Kind | What it is | Where it runs |
|---|---|---|
| `text_pattern` | a named, versioned set of regular expressions | analysis frames, the `text_pattern` evaluation metric, validations |
| `coder` | a versioned plugin function registered by an overlay, identified by a code hash | analysis frames, validations |
| `judge_code` | another system's coding of the answer, as its generations on a coding project | analysis frames, validations |
| `list` | an answer's list of items against a gold list | analysis frames |

The code lives in `services/shared/analysis/` (`text_patterns.py`,
`coders.py`, `codes.py`, `list_measures.py`, `coding.py`); validations run in
the workers on the `analysis` queue (`tasks.run_code_validation`).

## Text pattern sets

A pattern set is data, validated against
`services/shared/analysis/schemas/text_pattern_set.schema.json`, normalized
and hashed:

```json
{
  "name": "signals",
  "version": "2",
  "flags": ["IGNORECASE"],
  "codes": {
    "cites_norm": {"mode": "any", "patterns": ["§\\s?\\d+"]},
    "n_norms": {"mode": "count", "patterns": ["§\\s?\\d+"]},
    "own_ref": {"mode": "any", "patterns": ["{{task.case_ref|spaces}}"]},
    "side": {"mode": "first", "default": "none",
             "rules": [{"value": "P", "patterns": ["claimant"]},
                       {"value": "D", "patterns": ["respondent"]}]}
  }
}
```

| Mode | Value |
|---|---|
| `any` | 1 when one of the patterns matches anywhere in the text, else 0 |
| `all` | 1 when every pattern matches, else 0 |
| `count` | the number of non-overlapping matches, summed over the patterns |
| `first` | the `value` of the first rule (in rule order) with a matching pattern, else `default` (`null` is missing) |

Patterns use Python's `re` syntax. `flags` (`IGNORECASE`, `MULTILINE`,
`DOTALL`, `ASCII`, `VERBOSE`) apply to every code unless a code lists its
own, and `normalize` (`NFC` or `NFKC`) normalizes the text's Unicode form
before matching.

Task-parameterised literals: `{{task.<path>}}` inserts the value at that task
data path, regex-escaped, so a pattern can look for something only the task
knows, such as a case reference. `{{task.<path>|spaces}}` allows any number
of spaces between the value's characters and `|whitespace` any whitespace; a
list value matches any of its elements. A code whose literal does not
resolve for a task (a missing path, an empty value) is missing for that
task, never silently 0. A missing answer gives missing codes, an empty answer
is coded (no match).

The set hash covers the name, version, flags, normalization and every code
and pattern (not the descriptions) and the format version, so any change to
what the set matches changes the hash.

### As an analysis measure

```json
"pattern_sets": {"signals": {"name": "signals", "version": "2", "codes": {}}},
"measures": {
  "own_ref": {"kind": "text_pattern", "set": "signals", "code": "own_ref"},
  "begr_lang": {"kind": "text_pattern", "set": "signals", "code": "cites_norm",
                "input": {"field": "begruendung"}},
  "own_ref_pct": {"kind": "expression", "expr": "100 * own_ref"}
}
```

`set` names a set of the spec's `pattern_sets` or gives one inline; `input` is
`"answer"` (the full response, the default) or `{"field": "<control>"}`.

### As the `text_pattern` evaluation metric

An evaluation config with `metric: "text_pattern"` and
`metric_parameters: {"pattern_set": {...}, "code": "<code>"}` writes the code
of each prediction as a TaskEvaluation row: 1/0 for `any` and `all`, the
count for `count`, and for a `first` code 1 when a rule matched (the value is
in `details.label`). `details.codes` holds every code of the set and
`details.pattern_set` its name, version and hash. The metric needs no
reference value, the prediction is coded as stored (not lower-cased), and
task literals read the task's data. The set and the code are checked when
the configuration is saved.

## Coder plugins

For codes a regex set cannot express, an overlay registers a coder:

```python
from analysis.coders import Coder

class BlameDirection(Coder):
    name = "blame_direction"
    version = "3"
    outputs = {"direction": "text", "confidence": "number"}

    def code(self, text, context):
        # context.fields, context.task_data, context.factors, context.parameters
        return {"direction": "P", "confidence": 0.8}

def register_coders(registry):          # in the overlay's workers module
    registry.register(BlameDirection())
```

A coder is a pure, deterministic function of one answer. Outputs are typed
`number`, `text` or `bool` and coerced like parsed fields. On registration
the registry computes the code hash over the name, version, outputs and the
source text of the module that defines the coder (and any `source_modules`
it names); a coder whose source cannot be read cannot be registered. The
measure

```json
{"kind": "coder", "coder": "blame_direction", "version": "3", "output": "direction",
 "input": "answer", "parameters": {}}
```

runs it (`version` pins it: another registered version fails the run). Every
run records the coder's name, version, hash and the package that registered
it. A coder of a package switched off for the run's project or user does not
run.

## List measures

```json
{"kind": "list", "field": "relied_on", "gold": {"path": "gold.unusable"},
 "statistic": "recall",
 "items": {"pattern": "\\bB\\s*([1-5])\\b", "template": "B{1}", "flags": ["IGNORECASE"]},
 "normalize": ["strip", "casefold"]}
```

The answer's value (a list from a multi-select or a Repeater, or a text,
split by `split` when given) and the gold value (a task data path or fixed
`values`) become sets of canonical items: `items` extracts items by a
pattern and a template, `normalize` applies `strip`, `collapse_whitespace`,
`casefold`, `nfc` or `nfkc`. Statistics: `n_answer`, `n_gold`, `hits`,
`misses`, `extras`, `precision`, `recall`, `f1`, `jaccard`, `exact`, `any`
(the sets share an item) and `all` (every gold item is in the answer).
Precision with no answer items, recall with no gold items and Jaccard of two
empty sets are missing; a missing answer or gold value gives a missing
statistic.

## Coding projects

A coding project is an ordinary project made from a seeded sample of another
project's answers:

```
POST /api/projects/{project_id}/coding-projects
{"title": "Coding: blame direction",
 "label_config": "<View><Text name=\"answer\" value=\"$answer\"/><Choices name=\"side\" toName=\"answer\">...</Choices></View>",
 "answer": "answer",
 "context_fields": ["sachverhalt"],
 "sample": {"seed": 20261119, "size": 90, "designs": ["role_swap"], "systems": ["model-a"]}}
```

Each task shows one answer as `data.answer` (the full response, or a parsed
field with `"answer": {"field": "<control>"}`) and the copied context
fields; the label config is the coding scheme and must show `$answer`. The
sample takes the completed answers that match the filters, orders them by
SHA-256 of `"<seed>:<generation id>"` and keeps the first `size` with a
non-empty text (all of them without `size`), so the same seed always draws
the same answers. Each task records its source in `tasks.meta.coding`
(source project, task and generation, the answer source, the seed and rank);
`meta` is never shown to annotators. The coding project lives where the
source does (its organizations and groups, or private).

Human coders annotate the coding project like any project. A judge codes it
by generating on it: the judge model, its parameters (the system key) and
the prompt structure are the pinned judge, and its generations are the
automatic codes, the way Label Studio treats model predictions.

`GET /api/projects/{project_id}/coding-projects` lists the coding projects
drawn from a project; `GET /api/projects/{project_id}/coding` says how a
coding project was drawn.

### Judge codes in an analysis

```json
{"kind": "judge_code", "coding_project": "<coding project id>", "field": "side",
 "system": "judge-model@0123456789ab", "structure": "judge", "run_index": 0}
```

reads, for every answer of the analysed project, the judge's value of `field`
on the coding task that shows it. `system` is a system key or a model id. An
answer with no coding task, no judge answer, an unparsed judge answer, or
more than one matching judge answer gets a missing code; the run records
the counts. The coding project must have been drawn from the analysed
project.

## Code validations

```
POST /api/projects/{coding_project_id}/code-validations
{"code": {"kind": "text_pattern", "set": {...}, "code": "side"},
 "control": "side",
 "value_map": {"plaintiff": "P"},
 "missing": "category"}
```

`code` is shaped like the measure it validates, without `input` (the coding
project's answer source) and `validation`: a text pattern set and code, a
coder (`coder`, `version`, `output`, `parameters`) or a judge (`system`,
`structure`, `run_index`; its `field` defaults to the control). The worker
codes every coding task with it, compares the result with the human codes
of `control` (non-cancelled annotations) and stores:

- the agreement with the reference code: Cohen's kappa (unweighted), observed
  and chance agreement, the confusion matrix and precision, recall and F1 per
  category. The reference is an item's human code, or the majority of its
  human codes; items whose human codes tie are counted and left out;
- the agreement with each human coder and, with two or more coders, between
  the coders (pairwise Cohen's kappa, Fleiss' kappa, percent agreement);
- the per-task automatic and human codes (`items`, shown only to callers
  with full read access to the task content).

A missing automatic code counts as its own category `(missing)` (it
disagrees), or leaves the item out with `"missing": "exclude"`. `value_map`
maps automatic values to scheme values before comparing.

The validation records the code's identity hash: for a text pattern code the
set hash, the code and the input; for a coder its code hash, the output, the
input and the parameters; for a judge the coding project, field, system,
structure and run index.

`GET /api/projects/{coding_project_id}/code-validations` lists them and
`GET /api/code-validations/{code_validation_id}` returns one.

## Confirmatory analyses need validated codes

A code measure (`text_pattern`, `coder`, `judge_code`) that an estimand of a
non-exploratory family reads (as its outcome, a term, a fixed effect, a
cluster, a scope or pairing column, or a name in its subset or the global
filter, directly or through expressions) must name a validation:

```json
"side": {"kind": "text_pattern", "set": "signals", "code": "side", "validation": "<validation id>"}
```

The run fails unless that validation is completed, was drawn from the
analysed project and has the measure's identity hash. Exploratory families
and estimands outside families need no validation. Whether the agreement is
good enough is not the engine's call; the run records the validation's kappa
next to the code.

Every run records each code measure in `codes`: kind, ref, version, hash,
the coder's hash and owner or the pattern set's hash, the coding counts of a
judge, the missing count, the confirmatory estimands and the accepted
validation.
