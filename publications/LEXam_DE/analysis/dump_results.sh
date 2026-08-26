#!/usr/bin/env bash
# Dump the LEXam-DE evaluation results from prod into TSVs for lexam_report.py.
# Read-only (SELECT only). Usage: BENGER_PROD_SSH=user@host ./dump_results.sh [outdir]
# Requires SSH access to the deployment host and kubectl access to the benger namespace.
set -euo pipefail
: "${BENGER_PROD_SSH:?set BENGER_PROD_SSH to the deployment host, e.g. user@host}"
OUT="${1:-$(dirname "$0")/data}"
mkdir -p "$OUT"

PSQL='kubectl -n benger exec -i benger-postgresql-0 -- bash -c '"'"'PGPASSWORD=$POSTGRES_PASSWORD psql -U postgres -d benger -A -F "\t" -f -'"'"''

# Per-cell judge scores for llm_judge_lexam, one row per (task, generation, judge run),
# joined to the generation's structure key and the task's Bereich.
ssh "$BENGER_PROD_SSH" "$PSQL" <<'SQL' > "$OUT/judge_cells.tsv"
SELECT p.title AS project, te.task_id, te.generation_id, te.annotation_id,
       g.model_id, rg.structure_key, jr.judge_model_id, jr.run_index,
       (te.metrics::jsonb->>'llm_judge_lexam') AS score,
       (te.metrics::jsonb->'llm_judge_lexam'->>'error') AS metric_error,
       g.truncated, g.finish_reason, g.output_tokens,
       coalesce(tk.data::jsonb->>'lexam_course', tk.data::jsonb->>'bereich') AS bereich,
       te.error_type, te.latency_ms
FROM task_evaluations te
JOIN evaluation_judge_runs jr ON te.judge_run_id = jr.id
JOIN evaluation_runs er ON te.evaluation_id = er.id
JOIN projects p ON er.project_id = p.id
LEFT JOIN generations g ON te.generation_id = g.id
LEFT JOIN response_generations rg ON g.generation_id = rg.id
LEFT JOIN tasks tk ON te.task_id = tk.id
WHERE te.field_name LIKE '%llm_judge_lexam%' OR te.evaluation_config_id LIKE 'llm_judge_lexam%'
SQL

# Binary-track accuracy cells (exact_match on Grundprinzipien lexam-binary generations).
ssh "$BENGER_PROD_SSH" "$PSQL" <<'SQL' > "$OUT/binary_cells.tsv"
SELECT p.title AS project, te.task_id, te.generation_id, g.model_id, rg.structure_key,
       (te.metrics::jsonb->'exact_match'->>'value') AS exact_match,
       (te.metrics::jsonb->'accuracy'->>'value') AS accuracy,
       te.prediction::text AS prediction, te.ground_truth::text AS ground_truth,
       coalesce(tk.data::jsonb->>'lexam_course', '') AS bereich
FROM task_evaluations te
JOIN evaluation_runs er ON te.evaluation_id = er.id
JOIN projects p ON er.project_id = p.id
JOIN generations g ON te.generation_id = g.id
JOIN response_generations rg ON g.generation_id = rg.id
LEFT JOIN tasks tk ON te.task_id = tk.id
WHERE rg.structure_key = 'lexam-binary'
  AND (te.metrics::jsonb ? 'exact_match' OR te.metrics::jsonb ? 'accuracy')
SQL

# Generation-level stats for the lexam structures (truncation, tokens, think-tags).
ssh "$BENGER_PROD_SSH" "$PSQL" <<'SQL' > "$OUT/generations.tsv"
SELECT p.title AS project, g.model_id, rg.structure_key, g.status, g.truncated,
       g.finish_reason, g.output_tokens, g.parse_status,
       (g.response_content LIKE '%<think>%') AS has_think_tag,
       length(g.response_content) AS resp_chars, g.task_id
FROM generations g
JOIN response_generations rg ON g.generation_id = rg.id
JOIN projects p ON rg.project_id = p.id
WHERE rg.structure_key IN ('lexam-open', 'lexam-binary')
SQL

wc -l "$OUT"/*.tsv
