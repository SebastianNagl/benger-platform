# BenGER — Platform and Benchmark for German Legal Reasoning

[![License: Apache 2.0 (code)](https://img.shields.io/badge/Code-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![License: CC BY 4.0 (data)](https://img.shields.io/badge/Data-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20409635-blue.svg)](https://doi.org/10.5281/zenodo.20409635)

This repository hosts **two distinct projects** under the BenGER name:

1. **The platform** (Apache 2.0, `services/`) — an open-source web application that runs the full benchmarking pipeline for Large Language Models in the German legal domain: task creation, collaborative annotation, configurable LLM execution, and 40+ automatic and judge-based metrics in one browser-based workflow. *Companion paper: ICAIL 2026 system demonstration (Nagl & Grabmair); source under `publications/Plattform_ICAIL/`.*
2. **The BenGER benchmark** (CC BY 4.0, `publications/Dataset_ARR/`) — a dataset with three subsets (*Benchathon*, *ZJS*, *Grundprinzipien*) covering legal-reasoning tasks across civil, criminal, and public German law, plus human-validated leaderboards across 12 LLM systems. *Companion paper: full-length research paper with nine co-authors; source under `publications/Dataset_ARR/` (citation below).*

The platform generates the benchmark; the benchmark validates the platform. Different scopes, different author lists, different licenses, one repo — pick the project that matches what you came for.

## The BenGER Benchmark

A dataset with three thematic subsets, produced and reviewed by nine co-authors across TUM, LMU, Konstanz, and Saarbrücken:

| Subset | Source | Focus | Tasks |
|---|---|---|---|
| `benchathon` | Curated by the BenGER team — a one-day competitive grading event with seven blind expert reviews per solution | All three legal branches, three difficulty tiers | 45 picks, 180 human grades |
| `zjs` | *Zeitschrift für das Juristische Studium* — published exam-style cases from 2008–2026 | Long-form *Gutachten*-style case analysis | 581 cases |
| `grundprinzipien` | Foundational legal-principle multiple-choice items | Knowledge probe across the three branches | (see paper) |

**Zenodo (archival, citable)**: [10.5281/zenodo.20409635](https://doi.org/10.5281/zenodo.20409635) — the full anonymised dataset (`benger-v1.0.zip`) with `benchathon/`, `zjs/`, `grundprinzipien/`, and the small derived `processed/` files used by the manuscript.
**Paper (preprint)**: t.b.d.
**In-repo copies of the derived artefacts** the paper loads (small JSON/CSV files, ~5 MB total): `publications/Dataset_ARR/data/processed/` and `publications/Dataset_ARR/data/interim/`.

The data is licensed CC BY 4.0; the platform code is Apache 2.0. Human-grader identities have been replaced with stable codes (`grader_01..grader_07`).

## The Platform

Key capabilities:

- **Task creation** — legal experts define tasks and reference solutions directly in the platform
- **Collaborative annotation** — free-text QA, multiple choice, span annotation, with inter-annotator agreement
- **LLM execution** — batch execution across OpenAI, Anthropic, Google, Mistral, Cohere, DeepInfra, Zhipu AI
- **Evaluation** — 40+ metrics: classification, lexical, semantic, factual, LLM-as-a-judge
- **Multi-organization** — tenant isolation, role-based access (Admin, Contributor, Annotator), invitation onboarding

### Quick Start

```bash
git clone https://github.com/SebastianNagl/benger-platform.git
cd benger-platform

# Local env files from templates (dev-safe defaults)
cp services/api/.env.example       services/api/.env
cp services/workers/.env.example   services/workers/.env
cp services/frontend/.env.example  services/frontend/.env.local

cd infra/
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Seed initial data (admin/admin, contributor/admin, annotator/admin)
docker compose exec api python init_complete.py

# Frontend: http://benger.localhost
# API Docs: http://api.localhost/docs
```

On modern macOS, Linux, and Windows, `*.localhost` resolves to 127.0.0.1 automatically — no `/etc/hosts` edit needed. To exercise LLM execution, configure provider keys in the app's organization settings after first login.

## Project Structure

```
BenGER/
├── services/
│   ├── frontend/           # Next.js 15 web application
│   ├── api/                # FastAPI backend service
│   ├── workers/            # Celery background workers (40+ evaluation metrics)
│   └── shared/             # Shared models, seeds, and AI services
├── infra/                  # Docker Compose, Helm charts, Traefik
├── scripts/                # Automation, deployment, maintenance
├── docs/                   # User and developer documentation
└── publications/
    └── Dataset_ARR/        # The BenGER benchmark paper + dataset preparation
        ├── manuscript.qmd  # Quarto source for the paper
        ├── data/           # Processed + interim data (raw lives on HF + Zenodo)
        └── scripts/        # Data preparation, IP clearance, anonymization
```

## Technology Stack

- **Frontend**: Next.js 15 (App Router, Turbopack), TypeScript, Tailwind, Headless UI, Zustand, TanStack Query, Recharts/Plotly
- **Backend**: FastAPI (Python 3.11+), PostgreSQL 15 with SQLAlchemy, Redis + Celery, JWT auth, Alembic migrations
- **ML/Evaluation**: PyTorch, Transformers, Sentence-Transformers, BERTScore, SacreBLEU, ROUGE, METEOR, MoverScore, LLM-as-a-judge (Claude, GPT-4)
- **Infra**: Docker Compose, Kubernetes (k3s) + Helm, Traefik v3

## Development & Testing

```bash
# Full test suite (containerized; takes ~10 min)
make test

# Targeted suites (run `make test-start` first)
make test-unit       # API + Workers + Frontend Jest
make test-e2e        # Playwright E2E
make test-api        # API only
make test-workers    # Workers only
make test-frontend   # Frontend Jest only
```

Test ports (isolated from dev): PostgreSQL 5433, Redis 6380, API 8002, Frontend 8090.

## Documentation

- [User Guide](docs/user-guides/README.md)
- [Admin Guide](docs/user-guides/admin-guide.md)
- [Developer Authentication](docs/setup/developer-auth.md)
- [Environment Variables](docs/setup/environment-variables.md)
- [Deployment Guide](docs/setup/deployment/DEPLOYMENT.md)
- [Testing Guide](docs/development/TESTING.md)
- [Feature Flags](docs/setup/feature-flags.md)
- [Documentation Index](docs/README.md)

## License

- **Code** — Apache License 2.0 (`LICENSE`)
- **Dataset** — CC BY 4.0 (`publications/Dataset_ARR/DATA_LICENSE`)

## Citing BenGER

The platform and the benchmark are separate publications with different author lists. Cite the work you actually use.

**Platform** — the ICAIL system-demonstration paper (two authors):

```bibtex
@inproceedings{nagl2026benger,
  title     = {{BenGER}: A Collaborative Web Platform for End-to-End Benchmarking of German Legal Tasks},
  author    = {Nagl, Sebastian and Grabmair, Matthias},
  booktitle = {Proceedings of the International Conference on Artificial Intelligence and Law (ICAIL)},
  year      = {2026},
  address   = {Singapore},
  note      = {System demonstration}
}
```

**Benchmark** — the dataset paper (nine authors across four institutions):

```bibtex
@article{nagl2026bengerbench,
  title   = {{BenGER}: Benchmarking {LLM} Systems on Subsumption-Based Legal Reasoning in German Law},
  author  = {Nagl, Sebastian and Mayrhofer, Ann-Kristin and Heidebach, Martin
             and Ko{\c{c}}ak, Aleyna and Zettelmeier, Anne and Breu, Elly
             and Greiner, Angelina and Milijas, Sofija and Grabmair, Matthias},
  year    = {2026}
  % venue + DOI populated with the preprint
}
```

## Acknowledgments

- Technical University of Munich, Ludwig Maximilian University of Munich, University of Konstanz, and University of Saarbrücken for supporting this research
- Label Studio for annotation system UI/UX inspiration

## Contact

- **Issues**: [GitHub Issues](https://github.com/SebastianNagl/benger-platform/issues)
- **Email**: [sebastian.nagl@tum.de](mailto:sebastian.nagl@tum.de)
