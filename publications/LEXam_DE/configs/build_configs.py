#!/usr/bin/env python3
"""Build the exact LEXam-DE configuration payloads from the prompt sources.

Emits, per project, into ./generated/:
  <slug>.structure.<key>.json  — PUT body for
      /api/projects/{id}/generation-config/structures/{key}
  <slug>.evalconfig.json       — the evaluation_configs ENTRIES to append
      (the eval-config PUT deep-merges but replaces lists wholesale: GET the
      current config, append these entries, PUT the full list back)

Template-engine note (two different engines, deliberate):
  * generation instruction templates use {{var}} (GenerationStructureParser)
  * judge custom_prompt_template uses single-brace {var} (str.format in the
    single-criterion judge path; literal JSON braces escaped as {{ }})

Projects (prod ids; local mirror ids in LOCAL_IDS):
  Benchathon       e529779b-300f-48c0-89cb-90f3f4b72a51
  ZJS Fälle        0fefa5c8-29c7-4eb5-b107-c2271f2288f9
  Grundprinzipien  7995bf7a-24e8-405c-9769-bb1024cf2afb
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
PROMPTS = HERE.parent / "prompts"
OUT = HERE / "generated"
OUT.mkdir(exist_ok=True)

open_tpl = (PROMPTS / "generation-lexam-open.txt").read_text()
binary_tpl = (PROMPTS / "generation-lexam-binary-grundprinzipien.txt").read_text()
judge_tpl = (PROMPTS / "judge-lexam.txt").read_text()
judge_gp_tpl = (PROMPTS / "judge-lexam-grundprinzipien.txt").read_text()

# Grundprinzipien has no single question field: the open template's Question
# block interpolates fall + task instead.
open_tpl_gp = open_tpl.replace("{{question}}", "{{fall}}\n\n{{task}}")

# Single mini judge per Sebastian's cost call (2026-08-12); LEXam's paper uses
# a 3-judge min-ensemble, its released repo a single GPT-4o — we sit in between
# with a single house mini. Documented in the deviations register.
JUDGES = [
    {"judge_model_id": "gpt-5.4-mini", "runs": 1},
]

STRUCTURE_DESCRIPTION = (
    "LEXam open-question protocol (arXiv:2505.12864), Swiss law shifted to "
    "German law. Single user message, no system prompt, zero-shot. "
    "Do not activate; runs select this structure explicitly."
)


def structure(name, template, fields):
    return {
        "name": name,
        "description": STRUCTURE_DESCRIPTION,
        # {"template": ""} is the ONLY shape that yields an empty system
        # prompt: "" / null are rejected by the API and an absent key
        # reinstates the worker's hardcoded German fallback.
        "system_prompt": {"template": ""},
        "instruction_prompt": {"template": template, "fields": fields},
        "evaluation_prompt": None,
    }


def judge_config(config_id, display_name, prediction_fields, reference_fields,
                 template, field_mappings):
    return {
        "id": config_id,
        "metric": "llm_judge_lexam",
        "display_name": display_name,
        "prediction_fields": prediction_fields,
        "reference_fields": reference_fields,
        "enabled": True,
        "metric_parameters": {
            "judges": JUDGES,
            "score_scale": "0-1",
            "max_tokens": 8000,
            "seed": 42,
            "field_mappings": field_mappings,
            "custom_prompt_template": template,
        },
    }


PROJECTS = {
    "benchathon": {
        "prod_id": "e529779b-300f-48c0-89cb-90f3f4b72a51",
        "local_id": "3dd112dc-e20e-4dc7-9ab5-a183f00b7486",
        "structures": {
            "lexam-open": structure(
                "LEXam Open (DE)", open_tpl,
                {"course_name": "$bereich", "question": "$sachverhalt"},
            ),
        },
        "eval_configs": [
            judge_config(
                "llm-judge-lexam-open",
                "LEXam Judge (DE)",
                # Models + the 234 human Benchathon submissions under the
                # identical protocol (human-vs-model anchor).
                ["__all_model__", "human:loesung"],
                ["musterlösung"],
                judge_tpl,
                {"question": "$sachverhalt"},
            ),
        ],
    },
    "zjs-faelle": {
        "prod_id": "0fefa5c8-29c7-4eb5-b107-c2271f2288f9",
        "local_id": "c49e9db5-d7f1-4ccc-8a38-57c294757e1d",
        "structures": {
            "lexam-open": structure(
                "LEXam Open (DE)", open_tpl,
                {"course_name": "$lexam_course", "question": "$Aufgabe"},
            ),
        },
        "eval_configs": [
            judge_config(
                "llm-judge-lexam-open",
                "LEXam Judge (DE)",
                ["__all_model__"],
                ["Musterlösung"],
                judge_tpl,
                {"question": "$Aufgabe"},
            ),
        ],
    },
    "grundprinzipien": {
        "prod_id": "7995bf7a-24e8-405c-9769-bb1024cf2afb",
        "local_id": None,  # prod only
        "structures": {
            "lexam-open": structure(
                "LEXam Open (DE)", open_tpl_gp,
                {"course_name": "$lexam_course", "fall": "$fall", "task": "$task"},
            ),
            "lexam-binary": structure(
                "LEXam Binary (DE)", binary_tpl,
                {"course_name": "$lexam_course", "fall": "$fall", "task": "$task"},
            ),
        },
        "eval_configs": [
            judge_config(
                "llm-judge-lexam-open",
                "LEXam Judge (DE)",
                ["__all_model__"],
                ["reasoning"],
                judge_gp_tpl,
                {"fall": "$fall", "task": "$task", "entscheidung": "$binary_solution"},
            ),
            # Binary accuracy on the lexam-binary structure reuses the
            # project's EXISTING exact_match/accuracy configs — nothing new
            # to save; scoping happens at run time via structure_keys.
        ],
    },
}


def main():
    for slug, spec in PROJECTS.items():
        for key, body in spec["structures"].items():
            path = OUT / f"{slug}.structure.{key}.json"
            path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
            print(f"wrote {path.name} ({len(body['instruction_prompt']['template'])} tpl chars)")
        path = OUT / f"{slug}.evalconfig.json"
        path.write_text(json.dumps(spec["eval_configs"], ensure_ascii=False, indent=2) + "\n")
        print(f"wrote {path.name}")
    ids = {s: {"prod_id": p["prod_id"], "local_id": p["local_id"]} for s, p in PROJECTS.items()}
    (OUT / "project-ids.json").write_text(json.dumps(ids, indent=2) + "\n")
    print("wrote project-ids.json")


if __name__ == "__main__":
    main()
