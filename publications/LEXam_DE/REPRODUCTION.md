# LEXam-DE: the LEXam benchmark reproduced on German legal data

Reproduction of the LEXam benchmark methodology (arXiv:2505.12864, ICLR 2026;
Apache-2.0 code, CC-BY-4.0 data — prompts adapted with attribution) on three
BenGER prod projects, with every Swiss legal reference shifted to German law
and everything else kept as close to the original as the platform allows.
Executed 2026-08-12 to 2026-08-14 on prod (runs from a temporary admin
account in the TUM org context, since removed).

## Datasets (prod projects)

| Project | Tasks | Track(s) | Gold |
|---|---|---|---|
| ZJS Fälle (`0fefa5c8`) | 581 | open | `Musterlösung` (avg 32k chars) |
| Grundprinzipien (`7995bf7a`) | 531 | open + binary | `binary_solution` + `reasoning` |
| Benchathon (`e529779b`) | 15 | open (+ 234 human submissions) | `musterlösung` |

## Protocol

- **Generation**: the LEXam zero-shot open-question prompt (single user
  message, empty system prompt), Germanized (`prompts/generation-lexam-open.txt`);
  Grundprinzipien's binary track uses the LEXam MCQ prompt adapted to Ja/Nein
  (`prompts/generation-lexam-binary-grundprinzipien.txt`). Temperature 0
  (clamped to fixed-1 on gpt-5.x minis), max_tokens 16000, seed 42, one run
  per task. Prompts byte-verified against the sent payloads.
- **Judging**: the LEXam production judge prompt (20250324 variant),
  Germanized (`prompts/judge-lexam.txt`), 0.0–1.0 correctness in 0.1 steps
  vs the reference answer; run as the `llm_judge_lexam` metric through the
  platform's generic judge path, scoped to the `lexam-*` prompt structures
  so no historical generation was touched. Headline = mean × 100.
- **Binary track**: exact_match/accuracy of the parsed `kurzantwort`
  against the cleaned Ja/Nein gold (random baseline 50).
- **Roster** (cheap tier only, 14): gpt-5.4-mini, gpt-4o-mini, gpt-4.1-mini,
  gemma-3-12b-it, gemma-4-26B-A4B-it, gemini-3.1-flash-lite-preview /
  gemini-3-flash-preview (Benchathon), DeepSeek-V4-Flash, GLM-4.7-Flash,
  GLM-5.2, Qwen3.5-122B-A10B, Qwen3.6-27B, Qwen3.6-35B-A3B,
  Llama-4-Maverick, gpt-oss-120b (BYOM via DeepInfra).

## Headline results (`analysis/report.md` for full tables)

- **Difficulty ordering**: ZJS Fälle (long Klausuren) ≫ Benchathon ≫
  Grundprinzipien. Best model per project: GLM-5.2 (ZJS 43.3, GP 74.3) and
  gemini-3-flash-preview (Benchathon 57.3).
- **Humans matter — split by working mode** (pooling is misleading; see
  `analysis/human_split_lexam_judge.py`): the 220 Benchathon participant
  solutions average 57.1 under the identical judge, but the pool is 156
  co-creation (mean **61.6**, beats every model in the field) vs 63 unaided
  (mean **46.7**, above the model average of 42.1 but below the top five
  models). The co-creation uplift (+14.9) matches the rubric-side uplift in
  the BenGER paper (+15.7) — it replicates across both grading instruments.
- **German vs Swiss anchors** (models with published LEXam open-question
  scores): ZJS is *harder* than LEXam's Swiss exams for all three anchors
  (deltas −15 to −22), Benchathon harder (−14 to −16), Grundprinzipien
  easier (+6 to +11). The long-form German Klausur format is the
  differentiator, not the language shift.
- **Binary track**: all models beat the 50% baseline except gemma-3-12b
  (46.0); GLM-5.2 tops at 82.1.
- **Quality diagnostics**: truncation ≤0.6% per model (the 16k cap was
  never binding in practice), zero `<think>` contamination, judge-cell
  error rate 0.0000, 4.5% zero scores (genuine zeros + the judge's
  unparseable-→-0 semantics pooled).

## Deviations register (vs the LEXam paper/repo)

1. **Judge**: single gpt-5.4-mini at fixed temperature 1 (cost decision),
   not the published 3-judge min-ensemble (GPT-4o + Qwen3-32B +
   DeepSeek-V3; ensemble judge temperature not documented — temp 0 is only
   stated for the earlier single-judge setup). Absolute scores read more
   lenient than the ensemble.
2. **Judge output**: JSON (`{explanation, feedback, score}`) instead of
   free text + `[[score]]` regex; the platform's judge system prompt is
   fixed ("expert evaluator… valid JSON"), so LEXam's judge system line is
   folded into the user template.
3. **Token cap**: 16000 for all models (LEXam: 4096/8192). Empirically
   non-binding (see truncation rates).
4. **Grundprinzipien binary**: Ja/Nein with the platform's JSON answer
   block instead of `###letter###` MCQ letters; the judge's open-track
   prediction is the raw JSON answer blob.
5. **`course_name`** comes from the coarse Bereich field (Zivilrecht /
   Strafrecht / Öffentliches Recht…), not UZH-style course names.
6. **English prompt wrapper** kept (LEXam's own choice for its German items).
7. **Coverage**: cells that failed generation twice are absent rather than
   scored 0 — GLM-4.7-Flash is the one material case (482/581 on ZJS; its
   empty-response pathology on long prompts), GLM-5.2 minor (540/581 ZJS,
   ~510/531 GP). One Gemini content-policy refusal (criminal-law facts).
8. Per-model temperature deviations where providers fix temp=1 are recorded
   in each run's `_param_provenance`.

## Reproduction artifacts

- `prompts/` — the four Germanized templates (generation open/binary, judge
  open/Grundprinzipien variant); the diff vs the LEXam originals is exactly
  the Swiss→German shift described above.
- `configs/build_configs.py` — emits the exact structure + evaluation-config
  payloads (template-engine note: generation uses `{{var}}`, judge uses
  single-brace `{var}`).
- `analysis/dump_results.sh` + `analysis/lexam_report.py` → `analysis/report.md`.
- `analysis/human_split_lexam_judge.py` — the traditional/co-creation split of
  the human baseline (needs the private Benchathon export from Dataset_ARR).
- `analysis/pipeline_rank_comparison.py` — the 11-model rank agreement between
  the two pipelines (the paper's mutual-validation claim).
- Known data quirk: a handful of superseded duplicate generations survive in
  the dumps (Benchathon Qwen3.6-27B n=16 on 15 tasks; GP-binary gpt-5.4-mini
  n=532 on 531) — same platform pattern as the Dataset_ARR double-count fix.
  Verified immaterial: similarity correlations shift ≤0.02, quadrant shares
  ≤0.7 pp, and canonical dedup would only *improve* the rank agreement (the
  one adjacent swap involves Qwen3.5-122B, whose rubric mean is dragged down
  by superseded truncated generations).
- Canonical dedup executed 2026-08-27 directly against the prod DB (latest
  generation per task and model, `DISTINCT ON (task_id, model_id) ... ORDER BY
  created_at DESC`): every model lands at n=581, Qwen3.5-122B rubric mean
  44.2, and the two pipelines' rankings agree exactly (0 discordant pairs).
  Manuscript and slides state the deduped result.
- `snapshots/` — pre-LEXam prod config snapshots (restored after the runs).

## LEXam pipeline vs the BenGER Falllösung pipeline (ZJS, same models, same judge model)

Comparing the two full pipelines (generation prompt + judging protocol differ;
judge model gpt-5.4-mini on both sides): the **rank ordering of models is
identical** across the 11 overlapping models (0 discordant pairs after the
canonical dedup above; with the superseded duplicates left in, one adjacent
swap appears), but the LEXam pipeline scores 1–10 points lower, with the gap
growing for stronger models. Answer lengths are essentially equal under both prompts (~6.5k output
tokens on ZJS), so the level gap comes from the judging protocol: the
Falllösung rubric awards ~30/100 craft points (Gliederung, Sprache, Formalia,
Methodik) that well-formed answers collect regardless of substance, while the
LEXam judge scores substance-vs-reference only and penalizes deviations.
Benchathon deltas are direction-mixed at n=15. The isolating experiment
(LEXam judge over the fallloesung-prompt generations, one structure-scoped
dispatch ≈ €23–42) was considered and deliberately not run (2026-08-14).

## Run economics

~23.0k generations (20.9M in / 54.4M out tokens; the earlier "~16.5k" figure
was wrong — the dump counts 23,020) + ~23.2k evaluation cells
(~15.8k judge calls); total ≈ **€65–85** all-in on the cheap-tier roster
(provider billing in USD, ≈ $70–90).

## Platform changes shipped for this reproduction

- `structure_keys` scoping for evaluation runs (API + worker + run dialog).
- Structure-scoped generation matrix view.
- `llm_judge_lexam` metric registration (extended).
- Generic judge editor for registered `llm_judge_*` metrics; FieldMappingEditor
  controlled-parent fix.

Known follow-up (not fixed here): the eval run dialog's scope loader hits an
`InFailedSQLTransactionError` in the async available-fields path on ZJS-scale
projects; the two big judge runs were dispatched via the API fallback with
identical scoping (verified in the dispatch snapshots).
