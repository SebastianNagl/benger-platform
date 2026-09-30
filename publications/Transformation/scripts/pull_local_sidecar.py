#!/usr/bin/env python3
"""Pull rubric-study data from the LOCAL dev stack into data/raw/local/.

Local-dev tool (``make pull``): talks to the dockerized Postgres via
``docker exec … psql`` with JSON aggregation, so the publication venv needs
no DB driver. Pulls:

  - task_rubrics (all candidates + active, with criteria + provenance)
  - llm_judge_rubric task_evaluations (per-step scores, rubric_id, judge run)
  - the rubric-generation prompt structure snapshot (Appendix B source)

``make derive`` must keep working without the stack — this script is the
only one that requires Docker.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "data" / "raw" / "local"
INTERIM = HERE / "data" / "interim"
PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"
DB_CONTAINER = "benger-db-1"


def psql_json(query: str):
    """Run a query wrapped in json_agg and parse the result."""
    wrapped = f"SELECT coalesce(json_agg(q), '[]'::json) FROM ({query}) q;"
    out = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", "postgres", "-d", "benger",
         "-t", "-A", "-c", wrapped],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return json.loads(out)


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    INTERIM.mkdir(parents=True, exist_ok=True)

    rubrics = psql_json(
        f"""
        SELECT r.id, r.task_id, t.inner_id AS task_inner_id, r.title,
               r.criteria::jsonb AS criteria, r.total_points, r.source,
               r.generator_model_id, r.prompt_key, r.prompt_version,
               r.generation_metadata::jsonb AS generation_metadata,
               r.status, r.created_at
        FROM task_rubrics r JOIN tasks t ON r.task_id = t.id
        WHERE r.project_id = '{PROJECT_ID}'
        ORDER BY t.inner_id, r.created_at
        """
    )
    (RAW / "task_rubrics.json").write_text(
        json.dumps(rubrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    judge_rows = psql_json(
        f"""
        SELECT te.id, te.task_id, t.inner_id AS task_inner_id, te.generation_id,
               te.annotation_id, te.evaluation_config_id, te.created_at,
               jr.judge_model_id, jr.run_index,
               g.model_id AS evaluated_model,
               te.metrics -> 'llm_judge_rubric' AS result
        FROM task_evaluations te
        JOIN tasks t ON te.task_id = t.id
        LEFT JOIN evaluation_judge_runs jr ON te.judge_run_id = jr.id
        LEFT JOIN generations g ON te.generation_id = g.id
        WHERE t.project_id = '{PROJECT_ID}' AND te.metrics ? 'llm_judge_rubric'
        ORDER BY t.inner_id, te.created_at
        """
    )
    (RAW / "rubric_judge_rows.json").write_text(
        json.dumps(judge_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    prompt = psql_json(
        f"""
        SELECT generation_config::jsonb -> 'prompt_structures' -> 'bewertungsbogen'
               AS structure
        FROM projects WHERE id = '{PROJECT_ID}'
        """
    )
    (INTERIM / "rubric_prompt_snapshot.json").write_text(
        json.dumps(prompt[0]["structure"] if prompt else None,
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"task_rubrics: {len(rubrics)} rows -> data/raw/local/task_rubrics.json")
    print(f"judge rows:   {len(judge_rows)} rows -> data/raw/local/rubric_judge_rows.json")
    print("prompt snapshot -> data/interim/rubric_prompt_snapshot.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
