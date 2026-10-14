# BenGER — Platform and Benchmark for German Legal Reasoning

[![License: Apache 2.0 (code)](https://img.shields.io/badge/Code-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![License: CC BY 4.0 (data)](https://img.shields.io/badge/Data-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.23366269-blue.svg)](https://doi.org/10.5281/zenodo.23366269)
[![arXiv](https://img.shields.io/badge/arXiv-2605.28183-b31b1b.svg)](https://arxiv.org/abs/2605.28183)

This repository hosts **two distinct projects** under the BenGER name, and the **publications** written with them:

1. **The platform** (Apache 2.0, `services/`) — an open-source web application that runs the full benchmarking pipeline for Large Language Models in the German legal domain: task creation, collaborative annotation, configurable LLM execution, and 40+ automatic and judge-based metrics in one browser-based workflow. *Companion paper: ICAIL 2026 system demonstration (Nagl & Grabmair); source under `publications/Plattform_ICAIL/`.*
2. **The BenGER benchmark** (CC BY 4.0, `publications/Benchmark_EMNLP/`) — a dataset with three subsets (*Benchathon*, *ZJS*, *Grundprinzipien*) covering legal-reasoning tasks across civil, criminal, and public German law, plus human-validated leaderboards across 12 LLM systems. *Companion paper: Findings of EMNLP 2026, nine co-authors; source under `publications/Benchmark_EMNLP/` (citation below).*
3. **Publications** (`publications/`) — the source of every paper in this line of work, one folder per paper with the manuscript, the derived data it loads and the scripts that produced that data. Beyond the two companion papers this covers research that builds on the platform and the benchmark, such as the SoK on grading open-text legal answers. See [Publications](#publications).

The platform generates the benchmark; the benchmark validates the platform; the papers document both and the research built on them. Different scopes, different author lists, different licenses, one repo — pick the part that matches what you came for.

## The BenGER Benchmark

A dataset with three thematic subsets, produced and reviewed by nine co-authors across TUM, LMU, Konstanz, and Saarbrücken:

| Subset | Source | Focus | Tasks |
|---|---|---|---|
| `benchathon` | Curated by the BenGER team — a one-day competitive grading event with seven blind expert reviews per solution | All three legal branches, three difficulty tiers | 45 picks, 180 human grades |
| `zjs` | *Zeitschrift für das Juristische Studium* — published exam-style cases from 2008–2026 | Long-form *Gutachten*-style case analysis | 581 cases |
| `grundprinzipien` | Foundational legal-principle multiple-choice items | Knowledge probe across the three branches | (see paper) |

**Zenodo (archival, citable)**: [10.5281/zenodo.23366269](https://doi.org/10.5281/zenodo.23366269) — v3.0: the full anonymised dataset with `benchathon/`, `zjs/`, `grundprinzipien/`, the small derived `processed/` files used by the manuscript, and the task metadata (legal areas and other attributes per task). Earlier snapshots: [v2.0](https://doi.org/10.5281/zenodo.20489788) (judge re-anchored on GPT-5.4-mini) and [v1.0](https://doi.org/10.5281/zenodo.20409635).
**Paper**: Findings of EMNLP 2026; preprint [arXiv:2605.28183](https://arxiv.org/abs/2605.28183)
**In-repo copies of the derived artefacts** the paper loads (small JSON/CSV files, ~5 MB total): `publications/Benchmark_EMNLP/data/processed/` and `publications/Benchmark_EMNLP/data/interim/`.

The data is licensed CC BY 4.0; the platform code is Apache 2.0. Human-grader identities have been replaced with stable codes (`grader_01..grader_07`).

## The Platform

Key capabilities:

- **Task creation** — legal experts define tasks and reference solutions directly in the platform
- **Collaborative annotation** — free-text QA, multiple choice, span annotation, with inter-annotator agreement
- **LLM execution** — batch execution across OpenAI, Anthropic, Google, Mistral, Cohere, DeepInfra and xAI, plus your own OpenAI-compatible endpoints; the model catalog lives in `services/shared/seeds/llm_models.yaml`
- **Evaluation** — 40+ metrics: classification, lexical, semantic, factual, LLM-as-a-judge
- **Multi-organization** — tenant isolation, role-based access (Admin, Contributor, Annotator), groups, invitation onboarding
- **Import, export and reports** — project import/export through S3-compatible object storage (MinIO), per-project reports, in-app how-to guides
- **LMS integration (LTI 1.3)** — launch from a Moodle or ILIAS course, grades returned to the gradebook via AGS. The data model and admin API are in this repository; the protocol implementation ships in the commercial edition. See the [LMS integration guide](docs/lms-integration.md).

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

## Publications

Every paper in this line of work keeps its source under `publications/`, one folder per paper: the manuscript (Quarto or LaTeX), the derived data it loads and the scripts that produced that data, so each paper rebuilds from the folder. Raw material that cannot be shared, such as student scripts and raw platform exports, stays out of git.

| Folder | Paper | Status |
|---|---|---|
| `Plattform_ICAIL/` | *BenGER Platform: A Collaborative Web Platform for End-to-End Benchmarking of German Legal Tasks* (Nagl, Grabmair) | ICAIL 2026 system demonstration; preprint [arXiv:2604.13583](https://arxiv.org/abs/2604.13583) |
| `Benchmark_EMNLP/` | *BenGER: Benchmarking LLM Systems on Subsumption-Based Legal Reasoning in German Law* (Nagl et al., nine authors) | Findings of EMNLP 2026; preprint [arXiv:2605.28183](https://arxiv.org/abs/2605.28183); dataset v3.0 on [Zenodo](https://doi.org/10.5281/zenodo.23366269) |
| `SoK_CSLAW/` | *SoK: Grading Open-Text Legal Answers, from Law School Exams to Trustworthy Rubric Judges* (Nagl) | Submitted to the 6th ACM Symposium on Computer Science and Law (CSLAW '27) on 2026-10-14; arXiv preprint submitted, identifier follows |
| `LEXam_DE/` | *Replicating LEXam on German First State Exam-Style Essay Cases to Probe the "Statistical" Face of Legal Reasoning* | Work in progress: the full paper behind an accepted conference abstract, with the reproduction protocol, prompts and configs |

## Project Structure

```
BenGER/
├── services/
│   ├── frontend/           # Next.js 16 web application
│   ├── api/                # FastAPI backend service
│   ├── workers/            # Celery background workers (40+ evaluation metrics)
│   └── shared/             # Shared models, seeds, and AI services
├── infra/                  # Docker Compose, Helm charts, Traefik
├── scripts/                # Automation, deployment, maintenance
├── docs/                   # User and developer documentation
└── publications/
    ├── Benchmark_EMNLP/    # The BenGER benchmark paper + dataset preparation
    │   ├── manuscript.qmd  # Quarto source for the paper
    │   ├── data/           # Processed + interim data (raw lives on HF + Zenodo)
    │   └── scripts/        # Data preparation, IP clearance, anonymization
    ├── Plattform_ICAIL/    # The ICAIL system-demonstration paper
    └── SoK_CSLAW/          # SoK on grading open-text legal answers (CSLAW '27 submission)
```

## Technology Stack

- **Frontend**: Next.js 16 (App Router, Turbopack) on React 19 and Node 24, TypeScript 6, Tailwind 4, Headless UI, Zustand, TanStack Query, Recharts/Plotly
- **Backend**: FastAPI (Python 3.13+), PostgreSQL 15+ (18 in production) with SQLAlchemy, Redis + Celery, MinIO object storage, JWT auth, Alembic migrations
- **ML/Evaluation**: PyTorch, Transformers, Sentence-Transformers, BERTScore, SacreBLEU, ROUGE, METEOR, MoverScore, LLM-as-a-judge with any catalog model (GPT-5 and Claude families by default)
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
- [LMS setup guides (German, step by step)](docs/lms-setup/README.md)
- [LMS Integration (LTI 1.3 — Moodle, ILIAS)](docs/lms-integration.md)
- [Developer Authentication](docs/setup/developer-auth.md)
- [Environment Variables](docs/setup/environment-variables.md)
- [Deployment Guide](docs/setup/deployment/DEPLOYMENT.md)
- [Testing Guide](docs/development/TESTING.md)
- [Documentation Index](docs/README.md)

## License

- **Code** — Apache License 2.0 (`LICENSE`)
- **Dataset** — CC BY 4.0 (`publications/Benchmark_EMNLP/DATA_LICENSE`)

## Citing BenGER

The platform, the benchmark and the SoK are separate publications with different author lists. Cite the work you actually use.

**Platform** — the ICAIL system-demonstration paper (two authors):

```bibtex
@inproceedings{nagl2026benger,
  title     = {{BenGER Platform}: A Collaborative Web Platform for End-to-End Benchmarking of {German} Legal Tasks},
  author    = {Nagl, Sebastian and Grabmair, Matthias},
  booktitle = {Proceedings of the Twenty-First International Conference on Artificial Intelligence and Law (ICAIL 2026)},
  publisher = {ACM},
  year      = {2026},
  address   = {Singapore},
  note      = {System demonstration; preprint arXiv:2604.13583}
}
```

**Benchmark** — the dataset paper (nine authors across four institutions):

```bibtex
@inproceedings{nagl2026bengerbench,
  title         = {{BenGER}: Benchmarking {LLM} Systems on Subsumption-Based Legal Reasoning in German Law},
  author        = {Nagl, Sebastian and Mayrhofer, Ann-Kristin and Heidebach, Martin
                   and Ko{\c{c}}ak, Aleyna and Zettelmeier, Anne and Breu, Elly
                   and Greiner, Angelina and Milijas, Sofija and Grabmair, Matthias},
  booktitle     = {Findings of the Association for Computational Linguistics: EMNLP 2026},
  publisher     = {Association for Computational Linguistics},
  year          = {2026},
  eprint        = {2605.28183},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  doi           = {10.5281/zenodo.23366269}
}
```

**SoK** — the systematization paper on grading open-text legal answers (single author):

```bibtex
@misc{nagl2026sok,
  title  = {{SoK}: Grading Open-Text Legal Answers, from Law School Exams to Trustworthy Rubric Judges},
  author = {Nagl, Sebastian},
  year   = {2026},
  note   = {Submitted to the 6th ACM Symposium on Computer Science and Law (CSLAW '27); arXiv preprint}
}
```

## Acknowledgments

- Technical University of Munich, Ludwig Maximilian University of Munich, University of Konstanz, and University of Saarbrücken for supporting this research
- Label Studio for annotation system UI/UX inspiration

## Contact

- **Issues**: [GitHub Issues](https://github.com/SebastianNagl/benger-platform/issues)
- **Email**: [sebastian.nagl@tum.de](mailto:sebastian.nagl@tum.de)
