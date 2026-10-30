"""Register a model, import tasks, generate, evaluate and print the scores.

Usage:

    export BENGER_API_KEY=bgr_live_...
    export BENGER_BASE_URL=https://api.what-a-benger.net   # optional, the default
    export ENDPOINT_BASE_URL=https://inference.example.org/v1
    export ENDPOINT_MODEL=our-legal-llm-7b
    export ENDPOINT_API_KEY=sk-...                          # if the endpoint needs one
    python examples/research_pipeline.py [--project-id <existing project>]

The key needs the scopes models:manage, projects:write, tasks:write,
runs:write, evaluations:run and results:read (plus the matching :read
scopes for polling).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from benger_client import BengerAPIError, BengerClient, BengerJobError

LABEL_CONFIG = (
    "<View>"
    '<Text name="question" value="$question"/>'
    '<TextArea name="answer" toName="question"/>'
    "</View>"
)

TASKS = [
    {
        "data": {
            "question": "Kommt ein Kaufvertrag durch Schweigen auf ein Angebot zustande?",
            "reference_answer": "Grundsätzlich nein; Schweigen ist keine Willenserklärung.",
        }
    },
    {
        "data": {
            "question": "Ab welchem Alter ist man nach dem BGB voll geschäftsfähig?",
            "reference_answer": "Mit Vollendung des 18. Lebensjahres (§ 2 BGB).",
        }
    },
]

EVALUATION_CONFIGS = [
    {
        "id": "bleu-answer",
        "metric": "bleu",
        "display_name": "BLEU vs. reference",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["reference_answer"],
        "enabled": True,
    },
    {
        "id": "rouge-answer",
        "metric": "rouge",
        "display_name": "ROUGE vs. reference",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["reference_answer"],
        "enabled": True,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", help="use an existing project instead of creating one")
    args = parser.parse_args()

    with BengerClient() as benger:
        principal = benger.me()["principal"]
        print(f"Key {principal.get('key_prefix')} with scopes {principal['scopes']}")

        # 1. Register the model and check that BenGER can reach it.
        model = benger.models.register_custom(
            name=os.environ.get("ENDPOINT_MODEL", "my-model"),
            base_url=os.environ["ENDPOINT_BASE_URL"],
            endpoint_model_name=os.environ.get("ENDPOINT_MODEL", "my-model"),
            api_key=os.environ.get("ENDPOINT_API_KEY"),
            requires_api_key=bool(os.environ.get("ENDPOINT_API_KEY")),
        )
        print(f"Registered {model['id']} ({model['name']})")
        probe = benger.models.test(model["id"], chat_ping=True)
        print(f"Endpoint test: {probe['status']} {probe.get('message') or ''}")
        if probe["status"] != "success":
            return 1

        # 2. Project and tasks.
        if args.project_id:
            project_id = args.project_id
        else:
            project_id = benger.projects.create(
                "Research pipeline example", label_config=LABEL_CONFIG
            )["id"]
            print(f"Created project {project_id}")
        job = benger.imports.upload(project_id, TASKS)
        print(f"Imported: {job.get('result')}")

        # 3. Generation.
        benger.generation.configure(project_id, models=[model["id"]])
        started = benger.generation.start(
            project_id, mode="missing", model_ids=[model["id"]], temperature=0.0, seed=42
        )
        print(started["message"])
        generation = benger.generation.wait(project_id, started)
        print(f"Generation finished: {generation['counts']}")

        # 4. Evaluation.
        saved = benger.evaluations.configure(project_id, EVALUATION_CONFIGS)
        for warning in saved.get("warnings") or []:
            print(f"Warning: {warning.get('message', warning)}")
        run = benger.evaluations.run(project_id)
        print(f"Evaluation {run['evaluation_id']}: {run['message']}")
        try:
            benger.evaluations.wait(run)
        except BengerJobError as exc:
            print(exc, file=sys.stderr)
            return 1

        results = benger.evaluations.results(run["evaluation_id"])
        print(json.dumps(results.get("aggregated_metrics"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BengerAPIError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        sys.exit(2)
