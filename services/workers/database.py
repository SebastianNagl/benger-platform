"""
Database configuration and session management
"""

import os
from typing import Dict, Generator, List

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

# Database URL from environment variable
# Support both DATABASE_URI (production) and DATABASE_URL (legacy) for compatibility
DATABASE_URL = os.getenv("DATABASE_URI") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Build from individual PostgreSQL environment variables
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "changeme")
    pg_host = os.getenv("POSTGRES_HOST", "db")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "postgres")
    DATABASE_URL = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

# Create engine with TCP keepalives to prevent K8s/NAT from dropping idle connections
# during long-running LLM generation (thinking models can take 2-4+ minutes)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # Verify connection is alive before using it
    pool_recycle=1800,         # Recycle connections older than 30 min
    pool_size=5,               # Workers need few connections
    max_overflow=3,            # Allow burst to 8 total
    connect_args={
        "keepalives": 1,              # Enable TCP keepalives
        "keepalives_idle": 30,        # Send keepalive after 30s idle
        "keepalives_interval": 10,    # Retry every 10s
        "keepalives_count": 3,        # Give up after 3 missed
        "connect_timeout": 10,        # 10s connection timeout
    },
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base: DeclarativeMeta = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables"""
    from models import Base

    Base.metadata.create_all(bind=engine)


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
    ]

    # Define evaluation types - only for QA task types
    evaluation_types_data = [
        {
            "id": "f1",
            "name": "F1 Score",
            "description": "F1 score (harmonic mean of precision and recall)",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa", "qa_reasoning"],
        },
        # Q&A metrics
        {
            "id": "exact_match",
            "name": "Exact Match",
            "description": "Percentage of predictions that match the ground truth exactly",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa_reasoning"],
        },
        {
            "id": "token_f1",
            "name": "Token F1",
            "description": "Token-level F1 score between prediction and ground truth",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa_reasoning"],
        },
        {
            "id": "bleu",
            "name": "BLEU Score",
            "description": "BLEU score for evaluating generated text quality",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa_reasoning", "summarization"],
        },
        {
            "id": "rouge_l",
            "name": "ROUGE-L",
            "description": "ROUGE-L score based on longest common subsequence",
            "category": "generation",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa_reasoning", "summarization"],
        },
        {
            "id": "semantic_similarity",
            "name": "Semantic Similarity",
            "description": "Semantic similarity between prediction and ground truth",
            "category": "similarity",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa_reasoning"],
        },
        {
            "id": "answer_relevance",
            "name": "Answer Relevance",
            "description": "Relevance of the answer based on keyword overlap",
            "category": "similarity",
            "higher_is_better": True,
            "value_range": {"min": 0, "max": 1},
            "applicable_task_types": ["qa", "qa_reasoning"],
        },
    ]

    # Get the list of current task type IDs we want to keep
    # [template_type["id"] for template_type in task_types_data]  # COMMENTED: undefined name

    # Remove old task types that are no longer needed
    # TaskType queries removed - old task system cleanup
    # Old task types removed - cleanup not needed

    # Insert/update task types
    for task_type_data in task_types_data:
        # TaskType queries removed - old task system cleanup
        # Note: Old task type creation logic removed
        print(f"Processing task type: {task_type_data['id']}")

    # Insert evaluation types
    for eval_type_data in evaluation_types_data:
        # Check if evaluation type already exists
        existing_eval = (
            db.query(EvaluationType).filter(EvaluationType.id == eval_type_data["id"]).first()
        )
        if not existing_eval:
            eval_type = EvaluationType(**eval_type_data)
            db.add(eval_type)
            print(f"Added evaluation type: {eval_type_data['id']}")
        else:
            # Update existing evaluation type
            for key, value in eval_type_data.items():
                if key != "id":  # Don't update the ID
                    setattr(existing_eval, key, value)
            print(f"Updated evaluation type: {eval_type_data['id']}")

    db.commit()
    print("Task types and evaluation types initialized successfully!")


def _upsert_llm_model(db: Session, model_data: Dict[str, any]):
    """Helper to insert or update a single LLM model definition"""
    from models import LLMModel as DBLLMModel

    existing_model = db.query(DBLLMModel).filter(DBLLMModel.id == model_data["id"]).first()
    if existing_model:
        # Update existing record if necessary
        changed = False
        for field, value in model_data.items():
            if getattr(existing_model, field) != value:
                setattr(existing_model, field, value)
                changed = True
        if changed:
            db.add(existing_model)
    else:
        db.add(DBLLMModel(**model_data))


def initialize_llm_models(db: Session) -> None:
    """Insert default LLM model definitions if they don't exist yet"""
    from anthropic_service import anthropic_service
    from deepinfra_service import deepinfra_service
    from google_service import google_service
    from openai_service import openai_service

    default_models: List[Dict[str, any]] = [
        # OpenAI
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "description": "OpenAI's most advanced multimodal model with vision capabilities",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": openai_service.is_available(),
        },
        {
            "id": "gpt-4",
            "name": "GPT-4",
            "description": "OpenAI's flagship text model (2023-10-04)",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": openai_service.is_available(),
        },
        {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo",
            "description": "Cost-effective OpenAI model for quick iterations",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": ["text-generation", "reasoning"],
            "is_active": openai_service.is_available(),
        },
        # Anthropic
        {
            "id": "claude-sonnet-4",
            "name": "Claude Sonnet 4",
            "description": "Anthropic's latest high-performance model with exceptional reasoning and efficiency",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "multimodal",
            ],
            "is_active": anthropic_service.is_available(),
        },
        {
            "id": "claude-3.7-sonnet",
            "name": "Claude 3.7 Sonnet",
            "description": "Anthropic's first hybrid reasoning model with extended thinking capabilities",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "multimodal",
                "extended-thinking",
            ],
            "is_active": anthropic_service.is_available(),
        },
        # Google
        {
            "id": "gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "description": "Google's advanced multimodal model with enhanced capabilities",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": google_service.is_available(),
        },
        # DeepInfra (Meta/Qwen/DeepSeek)
        {
            "id": "deepinfra-llama-3.3-70b",
            "name": "Llama 3.3 70B (DeepInfra)",
            "description": "Meta's latest Llama model via DeepInfra infrastructure",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": ["text-generation", "data-synthesis", "reasoning"],
            "is_active": deepinfra_service.is_available(),
        },
        {
            "id": "deepinfra-qwen3-235b",
            "name": "Qwen 3 235B A22B (DeepInfra)",
            "description": "Qwen's large language model with enhanced reasoning and multilingual support",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": deepinfra_service.is_available(),
        },
        {
            "id": "deepinfra-llama4-maverick",
            "name": "Llama 4 Maverick (DeepInfra)",
            "description": "Meta's mixture-of-experts multimodal model via DeepInfra",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "multimodal",
            ],
            "is_active": deepinfra_service.is_available(),
        },
        {
            "id": "deepinfra-deepseek-r1",
            "name": "DeepSeek R1 (DeepInfra)",
            "description": "DeepSeek's advanced reasoning model via DeepInfra",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
            ],
            "is_active": deepinfra_service.is_available(),
        },
    ]

    for model in default_models:
        _upsert_llm_model(db, model)
    db.commit()
