"""
Database configuration and session management
"""

import logging
import os
from typing import AsyncGenerator, Dict, Generator


from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


logger = logging.getLogger(__name__)
load_dotenv()

# Database URL from environment variable
# Support both DATABASE_URL and DATABASE_URI for compatibility
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URI")
if not DATABASE_URL:
    # Build from individual PostgreSQL environment variables
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "changeme")
    pg_host = os.getenv("POSTGRES_HOST", "db")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "postgres")
    DATABASE_URL = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

# Create engine with connection pool configuration
# Configure pool based on environment for E2E test performance
is_e2e_test = os.getenv("ENVIRONMENT") == "test"
# Under pytest, a request driven by the sync Starlette TestClient runs in a
# fresh event loop per request (anyio portal). A pooled asyncpg connection
# bound to a previous loop then raises "attached to a different loop" /
# "Event loop is closed" when an async-lane endpoint is hit through that sync
# client. NullPool opens a fresh connection per checkout (on the current loop),
# eliminating that whole flake class. Test-only — production keeps its pool.
is_testing = os.getenv("TESTING", "").lower() in ("1", "true", "yes")
pool_config = {
    "pool_size": 20 if is_e2e_test else 10,
    "max_overflow": 30 if is_e2e_test else 20,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "pool_timeout": 5,
}

# Postgres-side timeouts so a single hot path can't pin a backend forever.
# statement_timeout: kill any query that runs longer than 15s.
# idle_in_transaction_session_timeout: Postgres force-closes a backend that
#   sits with an open transaction for 30s (the failure mode that wedged the
#   pool in the 2026-05-18 incident — a streaming endpoint held a Session
#   across `await asyncio.sleep(2)` and SQLAlchemy's auto-begin left the
#   connection IDLE IN TRANSACTION between polls).
# application_name: makes pg_stat_activity immediately diagnostic.
connect_args = {
    "options": "-c statement_timeout=15000 -c idle_in_transaction_session_timeout=30000",
    "application_name": "benger-api",
}

engine = create_engine(DATABASE_URL, connect_args=connect_args, **pool_config)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base: DeclarativeMeta = declarative_base()


# ---- Async engine (Phase 0 of the asyncpg migration) -----------------------
#
# Lives alongside the sync engine; every existing handler continues to use
# get_db() + SessionLocal unchanged. Future handlers opt into async DB by
# taking `db: AsyncSession = Depends(get_async_db)` and calling `await
# db.execute(select(...))`. See benger-platform/CLAUDE.md for the rule.
#
# Critical config differences from the sync engine:
#   * URL scheme switches to `postgresql+asyncpg://` — asyncpg, not psycopg2.
#   * `connect_args` uses `server_settings={...}` instead of the psycopg2
#     `-c options` string (asyncpg's API for the same Postgres-side config).
#   * `application_name` is "benger-api-async" so pg_stat_activity can
#     distinguish sync vs async traffic at a glance — essential for the
#     migration's canary gating.
#   * Pool is intentionally smaller during migration (5/10 per process)
#     because Postgres `max_connections=200` in prod and the sync engine
#     already consumes most of that budget at peak. Once Phase 4 shifts
#     traffic to async, rebalance.
ASYNC_DATABASE_URL: str | None = None
async_engine = None
AsyncSessionLocal = None

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    # psycopg2 → asyncpg URL rewrite. `postgresql+asyncpg://` vs
    # `postgresql://`.
    ASYNC_DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )

    async_connect_args = {
        "server_settings": {
            "statement_timeout": "15000",
            "idle_in_transaction_session_timeout": "30000",
            "application_name": "benger-api-async",
        },
    }

    if is_testing:
        # NullPool: no cross-loop connection reuse under the sync TestClient.
        from sqlalchemy.pool import NullPool

        async_pool_config = {"poolclass": NullPool}
    else:
        async_pool_config = {
            "pool_size": 10 if is_e2e_test else 5,
            "max_overflow": 20 if is_e2e_test else 10,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "pool_timeout": 5,
        }

    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        connect_args=async_connect_args,
        **async_pool_config,
    )

    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Async equivalent of get_db. Opt in via:

        from sqlalchemy.ext.asyncio import AsyncSession
        from database import get_async_db

        @router.get(...)
        async def my_handler(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(Model).where(...))
            obj = result.scalar_one_or_none()
    """
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Async DB engine not initialized — DATABASE_URL is missing or "
            "not a postgresql URL. Sync get_db() still works in that case."
        )
    async with AsyncSessionLocal() as session:
        yield session


def init_db() -> None:
    """
    DEPRECATED: Use Alembic migrations instead
    This function should not be used - database schema is managed by Alembic
    """
    raise DeprecationWarning(
        "init_db() is deprecated. Use Alembic migrations to manage database schema. "
        "Run: alembic upgrade head"
    )


def initialize_task_types_and_evaluation_types(db: Session) -> None:
    """Initialize predefined task types and evaluation types in the database"""
    from models import EvaluationType

    # Define task types - only the ones derived from actual data formats
    task_types_data = [
        {
            "id": "qa_reasoning",
            "name": "Question Answering & Reasoning",
            "description": "Legal case analysis, complex reasoning tasks, and legal problem solving",
            "default_template": """
                <View>
                    <Header value="Legal Case Analysis"/>
                    <Text name="case_name" value="$case_name"/>
                    <Text name="area" value="$area" style="color: #666; font-style: italic;"/>
                    <Text name="fall" value="$fall"/>

                    <Header value="Analysis"/>
                    <Choices name="binary_solution" toName="fall" choice="single-radio">
                        <Choice value="Ja"/>
                        <Choice value="Nein"/>
                    </Choices>

                    <Header value="Legal Reasoning"/>
                    <TextArea name="reasoning" toName="fall" placeholder="Provide detailed legal reasoning..." rows="8" required="true"/>
                </View>
            """,
            "supported_metrics": [
                "exact_match",
                "f1",
                "token_f1",
                "bleu",
                "rouge_l",
                "semantic_similarity",
                "answer_relevance",
            ],
            "model_config_schema": {
                "type": "object",
                "properties": {
                    "model_type": {
                        "type": "string",
                        "enum": ["qa", "generative_qa", "reasoning"],
                    },
                    "answer_type": {
                        "type": "string",
                        "enum": [
                            "extractive",
                            "generative",
                            "multiple_choice",
                        ],
                    },
                    "language": {
                        "type": "string",
                        "enum": ["de", "en"],
                        "default": "de",
                    },
                },
                "required": ["model_type", "answer_type"],
            },
        },
        {
            "id": "qa",
            "name": "QA (Question & Answer)",
            "description": "Simple question and answer pairs for annotation",
            "default_template": """
                <View>
                    <Text name="question" value="$Frage"/>
                    <Header value="Answer"/>
                    <TextArea name="answer" toName="question" placeholder="Enter answer..." rows="3" required="true"/>
                </View>
            """,
            "supported_metrics": [
                "exact_match",
                "f1",
                "token_f1",
                "bleu",
                "rouge_l",
                "semantic_similarity",
            ],
            "model_config_schema": {
                "type": "object",
                "properties": {
                    "model_type": {
                        "type": "string",
                        "enum": ["qa", "generative_qa"],
                    },
                    "answer_type": {
                        "type": "string",
                        "enum": ["extractive", "generative"],
                    },
                    "language": {
                        "type": "string",
                        "enum": ["de", "en"],
                        "default": "de",
                    },
                },
                "required": ["model_type", "answer_type"],
            },
        },
        {
            "id": "multiple_choice",
            "name": "Multiple Choice Question",
            "description": "Four-option multiple choice questions for standardized legal assessments",
            "default_template": """
                <View>
                    <Header value="Question"/>
                    <Text name="question" value="$question" style="white-space: pre-wrap; font-size: 16px; margin-bottom: 15px;"/>

                    <Text name="context" value="$context" style="color: #666; font-style: italic; margin-bottom: 10px;"/>

                    <Header value="Choose the correct answer:"/>
                    <Choices name="selected_answer" toName="question" choice="single-radio" required="true">
                        <Choice value="A" style="margin-bottom: 8px;"/>
                        <Choice value="B" style="margin-bottom: 8px;"/>
                        <Choice value="C" style="margin-bottom: 8px;"/>
                        <Choice value="D" style="margin-bottom: 8px;"/>
                    </Choices>

                    <Header value="Answer Options"/>
                    <Text name="choice_a" value="A) $choice_a" style="margin-bottom: 5px;"/>
                    <Text name="choice_b" value="B) $choice_b" style="margin-bottom: 5px;"/>
                    <Text name="choice_c" value="C) $choice_c" style="margin-bottom: 5px;"/>
                    <Text name="choice_d" value="D) $choice_d" style="margin-bottom: 5px;"/>

                    <Header value="Confidence Level"/>
                    <Rating name="confidence" toName="question" maxRating="5" defaultValue="3"/>
                </View>
            """,
            "supported_metrics": [
                "accuracy",
                "exact_match",
                "choice_distribution",
                "confidence_correlation",
            ],
            "model_config_schema": {
                "type": "object",
                "properties": {
                    "model_type": {
                        "type": "string",
                        "enum": ["multiple_choice", "qa"],
                    },
                    "answer_type": {
                        "type": "string",
                        "enum": ["single_choice"],
                        "default": "single_choice",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["de", "en"],
                        "default": "de",
                    },
                },
                "required": ["model_type"],
            },
        },
        {
            "id": "generation",
            "name": "Generation",
            "description": "Long-form text generation tasks for comprehensive legal analysis and document creation",
            "default_template": """
                <View>
                    <Header value="Context Document"/>
                    <Text name="initial_text" value="$initial_text" style="white-space: pre-wrap; max-height: 400px; overflow-y: auto;"/>

                    <Header value="System Prompt"/>
                    <Text name="system_prompt" value="$system_prompt" style="background: #f0f8ff; padding: 10px;"/>

                    <Header value="Instructions"/>
                    <Text name="instruction_prompts" value="$instruction_prompts" style="white-space: pre-wrap;"/>

                    <Header value="Generated Response"/>
                    <TextArea name="generated_answer" toName="initial_text" placeholder="Enter generated response..." rows="12" required="true"/>

                    <Header value="Quality Assessment"/>
                    <Rating name="quality" toName="initial_text" maxRating="5" defaultValue="3"/>
                    <Rating name="relevance" toName="initial_text" maxRating="5" defaultValue="3"/>
                </View>
            """,
            "supported_metrics": [
                "bleu",
                "rouge_l",
                "semantic_similarity",
                "coherence",
                "length_appropriateness",
            ],
            "model_config_schema": {
                "type": "object",
                "properties": {
                    "model_type": {
                        "type": "string",
                        "enum": ["generation", "text_generation"],
                    },
                    "generation_type": {
                        "type": "string",
                        "enum": ["free_form", "structured", "document"],
                        "default": "free_form",
                    },
                    "max_length": {
                        "type": "integer",
                        "minimum": 100,
                        "maximum": 10000,
                        "default": 2000,
                    },
                    "language": {
                        "type": "string",
                        "enum": ["de", "en"],
                        "default": "de",
                    },
                },
                "required": ["model_type"],
            },
        },
    ]

    # Define evaluation types - only for QA task types
    evaluation_types_data = [
        {
            "id": "accuracy",
            "name": "Accuracy",
            "description": "Percentage of correct predictions",
            "category": "classification",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["multiple_choice"],
        },
        {
            "id": "f1",
            "name": "F1 Score",
            "description": "F1 score (harmonic mean of precision and recall)",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa", "qa_reasoning"],
        },
        # Q&A metrics
        {
            "id": "exact_match",
            "name": "Exact Match",
            "description": "Percentage of predictions that match the ground truth exactly",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa_reasoning", "multiple_choice"],
        },
        {
            "id": "token_f1",
            "name": "Token F1",
            "description": "Token-level F1 score between prediction and ground truth",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa_reasoning"],
        },
        {
            "id": "bleu",
            "name": "BLEU Score",
            "description": "BLEU score for evaluating generated text quality",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa_reasoning", "summarization", "generation"],
        },
        {
            "id": "rouge_l",
            "name": "ROUGE-L",
            "description": "ROUGE-L score based on longest common subsequence",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa_reasoning", "summarization", "generation"],
        },
        {
            "id": "semantic_similarity",
            "name": "Semantic Similarity",
            "description": "Semantic similarity between prediction and ground truth",
            "category": "similarity",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa_reasoning", "generation"],
        },
        {
            "id": "answer_relevance",
            "name": "Answer Relevance",
            "description": "Relevance of the answer based on keyword overlap",
            "category": "similarity",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_project_types": ["qa", "qa_reasoning"],
        },
        {
            "id": "human_eval",
            "name": "Human Evaluation",
            "description": "Human evaluation of LLM responses using Likert scales for correctness, completeness, style, and usability",
            "category": "human_assessment",
            "higher_is_better": True,
            "value_range": {"min": 1, "max": 5},
            "applicable_project_types": ["qa", "qa_reasoning"],
        },
    ]

    # Get the list of current task type IDs we want to keep
    [task_type["id"] for task_type in task_types_data]

    # Remove old task types that are no longer needed
    # ProjectType queries removed - old task system cleanup
    old_project_types = []  # No longer querying ProjectType - removed from system  # noqa: F841

    # Insert/update task types
    for task_type_data in task_types_data:
        # ProjectType system removed - skip task type initialization
        # This functionality has been migrated to project-based architecture
        pass

    # Insert evaluation types
    for eval_type_data in evaluation_types_data:
        existing = (
            db.query(EvaluationType).filter(EvaluationType.id == eval_type_data["id"]).first()
        )
        if not existing:
            eval_type = EvaluationType(**eval_type_data)
            db.add(eval_type)
            print(f"Added evaluation type: {eval_type_data['id']}")
        else:
            # Update existing evaluation type
            # type: ignore[assignment]
            for key, value in eval_type_data.items():
                if key != "id":  # Don't update the ID
                    setattr(existing, key, value)
            print(f"Updated evaluation type: {eval_type_data['id']}")

    db.commit()
    print("Project types and evaluation types initialized successfully!")


def _upsert_llm_model(db: Session, model_data: Dict[str, any]) -> str:
    """Insert or update a single LLM model definition.

    Returns one of: 'inserted', 'updated', 'unchanged'.
    """
    from models import LLMModel as DBLLMModel

    existing = db.query(DBLLMModel).filter(DBLLMModel.id == model_data["id"]).first()
    if existing:
        changed = False
        for field, value in model_data.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            db.add(existing)
            return "updated"
        return "unchanged"
    db.add(DBLLMModel(**model_data))
    return "inserted"


def initialize_llm_models(db: Session) -> int:
    """Upsert the LLM model catalog from seeds/llm_models.yaml.

    Returns the number of inserted + updated rows so callers can log a
    one-line summary. Models present in the DB but absent from the YAML
    are flipped to is_active=False (kept for historical evaluation rows).
    """
    from models import LLMModel as DBLLMModel
    from seeds.llm_models_loader import load_catalog

    catalog = load_catalog()

    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for model in catalog.models:
        # Map YAML "constraints" key onto the DB column "parameter_constraints"
        row = dict(model)
        if "constraints" in row:
            row["parameter_constraints"] = row.pop("constraints")
        result = _upsert_llm_model(db, row)
        counts[result] += 1

    catalog_ids = {m["id"] for m in catalog.models}
    deactivated = 0
    stale = db.query(DBLLMModel).filter(
        ~DBLLMModel.id.in_(catalog_ids), DBLLMModel.is_active.is_(True)
    ).all()
    for model in stale:
        model.is_active = False
        deactivated += 1

    db.commit()

    logger.info(
        "LLM seed v%s: %d models (%d inserted, %d updated, %d unchanged, %d deactivated) from %s",
        catalog.content_hash[:8],
        len(catalog.models),
        counts["inserted"],
        counts["updated"],
        counts["unchanged"],
        deactivated,
        ", ".join(catalog.sources),
    )
    return counts["inserted"] + counts["updated"]
