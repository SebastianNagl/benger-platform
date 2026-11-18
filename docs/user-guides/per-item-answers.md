# Per-item answers: `<Repeater>` and indexed fields

Some tasks ask the same questions once per item of a list: a risk score per
case of a docket, a sentence and a credibility rating per defendant, a
verdict per claim. BenGER stores such answers the way Label Studio does, as
one result per control under an indexed name (`risk_0`, `risk_1`, ... or
hand-written names such as `months_1`, `months_2`), so analyses, exports and
Label Studio all read the same results.

## Writing the config

Label Studio's `<Repeater>` writes the per-item block once:

```xml
<View>
  <Header value="Docket"/>
  <Repeater on="$cases" indexFlag="{{idx}}" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <Choices name="priority_{{idx}}" toName="case_{{idx}}">
      <Choice value="high"/><Choice value="low"/>
    </Choices>
  </Repeater>
</View>
```

with task data such as `{"cases": [{"text": "..."}, {"text": "..."}]}`.

For each task the block is repeated once per element of the array `on`
names, and `{{idx}}` is replaced by the element's position counted from 0 in
every attribute, exactly as Label Studio expands the tag. A task with three
cases therefore gets `risk_0`, `risk_1` and `risk_2`; tasks may hold different
numbers of items.

Rules (the config editor rejects a config that breaks them):

- `on` is a `$` binding to an array in the task data (`$cases`, `$doc.cases`).
  The path is looked up exactly as written, as in Label Studio: keys are
  case-sensitive, so `$cases` does not find a `Cases` array.
- Every named control inside the block contains the index flag in its name,
  once per attribute.
- No expanded name may equal the name of a control outside the block
  (`risk_0` next to `risk_{{idx}}`) or the expansion of another template
  (`a_{{idx}}` in one block and `a_{{i}}` in another).
- Repeaters do not nest.
- `indexFlag` is optional (`{{idx}}` by default); `mode="pagination"` is
  accepted, and BenGER shows all items one below the other.

Hand-written indexed names need no `<Repeater>`: a config with `months_1`,
`months_2` and so on is an ordinary config.

Wherever BenGER lists a project's fields (evaluation setup, the project
creation wizard, the public project view of the v1 API), a Repeater appears
under its indexed names, expanded to the longest list any task of the project
holds, and never under its template names. Before any task is imported the
wizard lists no fields for it; the array `on` names is offered as a prompt
variable, the bindings into its items are not.

## Model answers

For generation, a `<Repeater>` block asks for a JSON list with one object per
item. The keys of each object are the control names without the index flag
(`risk_{{idx}}` becomes `risk`). Structured output pins the list to the
task's number of items, and the answer is stored under the indexed names:

```json
{"cases": [{"case": 1, "risk": 45, "priority": "low"},
           {"case": 2, "risk": 60, "priority": "high"}]}
```

- The list sits under the last part of the `on` binding (`cases`). When the
  config has only one block, a bare JSON list is read as that block's list.
- `answerKey` (a BenGER attribute that Label Studio ignores) names the key
  that says which item an object answers, numbered from `answerKeyStart`
  (default 1, as prompts usually number items from 1). Without it, objects
  are matched to items by their order.
- A list with the wrong number of objects, an item number out of range or an
  item answered twice is a failed parse (`validation_error`); nothing is
  stored under the indexed names then.
- The flat form works too: an object keyed by the indexed names
  (`{"risk_0": 45, "risk_1": 60}`) is stored exactly like the list above.
- A block without answer controls (one that only displays the items) asks
  for no list, so a bare JSON list still goes to the config's labels field.

## Label Studio

Label Studio has marked `<Repeater>` for deprecation and removed it from its
documentation, so BenGER treats it only as a shorthand:

- `GET /api/projects/{id}/label-config/label-studio` returns the config with
  every Repeater expanded to plain indexed controls, to the longest list any
  task of the project holds. Paste this form into Label Studio; it does not
  depend on the Repeater tag.
- The Label Studio task export fills a result's missing `to_name` from the
  config, which Label Studio needs to show a stored result.

## Slot maps

`GET /api/projects/{id}/label-config/slots?task_id=...` lists, for one task,
which control names hold which item's answers: one group per `<Repeater>`
(slot index = the position counted from 0) and, with
`pattern=months_{idx}&pattern=credibility_{idx}`, one group for hand-written
indexed names (slot index = the number in the name). Analyses use it to turn
one answer into one row per item.
