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
pool_config = {
    "pool_size": 20 if is_e2e_test else 3,
    "max_overflow": 30 if is_e2e_test else 7,
    "pool_pre_ping": True,  # Verify connections before use
    "pool_recycle": 3600,  # Recycle connections after 1 hour
}

engine = create_engine(DATABASE_URL, **pool_config)

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
    old_project_types = []  # No longer querying ProjectType - removed from system

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


def _upsert_llm_model(db: Session, model_data: Dict[str, any]):
    """Helper to insert or update a single LLM model definition"""
    from models import LLMModel as DBLLMModel

    existing = db.query(DBLLMModel).filter(DBLLMModel.id == model_data["id"]).first()
    if existing:
        # Update existing record if necessary
        changed = False
        for field, value in model_data.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            db.add(existing)
    else:
        db.add(DBLLMModel(**model_data))


def initialize_llm_models(db: Session) -> None:
    """Insert default LLM model definitions if they don't exist yet"""

    default_models: List[Dict[str, any]] = [
        # OpenAI Models - GPT-5 Series
        {
            "id": "gpt-5",
            "name": "GPT-5",
            "description": "Flagship model with PhD-level intelligence and reasoning",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 1.25,
            "output_cost_per_million": 10.00,
        },
        {
            "id": "gpt-5.4",
            "name": "GPT-5.4",
            "description": "Latest flagship with 1M context window",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 2.50,
            "output_cost_per_million": 15.00,
        },
        {
            "id": "gpt-5.2",
            "name": "GPT-5.2",
            "description": "High-performance model with 400K context",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 1.75,
            "output_cost_per_million": 14.00,
        },
        {
            "id": "gpt-5.1",
            "name": "GPT-5.1",
            "description": "Efficient flagship with 400K context",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": True,
            "input_cost_per_million": 1.25,
            "output_cost_per_million": 10.00,
        },
        {
            "id": "gpt-5-mini",
            "name": "GPT-5 Mini",
            "description": "Cost-efficient GPT-5 variant with 400K context",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 2.00,
        },
        {
            "id": "gpt-5-nano",
            "name": "GPT-5 Nano",
            "description": "Lightweight GPT-5 for fast responses",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.05,
            "output_cost_per_million": 0.40,
        },
        # OpenAI Models - GPT-4.1 Series
        {
            "id": "gpt-4.1",
            "name": "GPT-4.1",
            "description": "Best instruction-following with 1M context",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 2.00,
            "output_cost_per_million": 8.00,
        },
        {
            "id": "gpt-4.1-mini",
            "name": "GPT-4.1 Mini",
            "description": "Fast GPT-4.1 variant with 1M context",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 1.60,
        },
        {
            "id": "gpt-4.1-nano",
            "name": "GPT-4.1 Nano",
            "description": "Ultra-cheap GPT-4.1 with 1M context",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.10,
            "output_cost_per_million": 0.40,
        },
        # OpenAI Models - o-Series (Reasoning)
        {
            "id": "o4-mini",
            "name": "o4-mini",
            "description": "Cost-efficient reasoning model",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 1.10,
            "output_cost_per_million": 4.40,
            "default_config": {
                "reasoning_config": {
                    "parameter": "reasoning_effort",
                    "type": "select",
                    "values": ["low", "medium", "high"],
                    "default": "medium",
                    "label": "Thinking/Reasoning Level",
                }
            },
        },
        {
            "id": "o3",
            "name": "o3",
            "description": "Advanced reasoning model with deep thinking",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 2.00,
            "output_cost_per_million": 8.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "reasoning_effort",
                    "type": "select",
                    "values": ["low", "medium", "high"],
                    "default": "medium",
                    "label": "Thinking/Reasoning Level",
                }
            },
        },
        {
            "id": "o3-mini",
            "name": "o3-mini",
            "description": "Efficient reasoning model with configurable thinking",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 1.10,
            "output_cost_per_million": 4.40,
            "default_config": {
                "reasoning_config": {
                    "parameter": "reasoning_effort",
                    "type": "select",
                    "values": ["low", "medium", "high"],
                    "default": "medium",
                    "label": "Thinking/Reasoning Level",
                }
            },
        },
        {
            "id": "o1",
            "name": "o1",
            "description": "Original reasoning model with chain-of-thought",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "advanced-reasoning",
            ],
            "is_active": False,
            "input_cost_per_million": 15.00,
            "output_cost_per_million": 60.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "reasoning_effort",
                    "type": "select",
                    "values": ["low", "medium", "high"],
                    "default": "medium",
                    "label": "Thinking/Reasoning Level",
                }
            },
        },
        # OpenAI Models - GPT-4o Series
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "description": "Multimodal model for complex tasks",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": True,
            "input_cost_per_million": 2.50,
            "output_cost_per_million": 10.00,
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "description": "Smaller, faster variant of GPT-4o",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.15,
            "output_cost_per_million": 0.60,
        },
        {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo",
            "description": "Fast and cost-effective for simple tasks",
            "provider": "OpenAI",
            "model_type": "chat",
            "capabilities": ["text-generation", "reasoning"],
            "is_active": True,
            "input_cost_per_million": 0.50,
            "output_cost_per_million": 1.50,
        },
        # Anthropic Models - Claude 4.6 Series (Latest)
        {
            "id": "claude-opus-4-6",
            "name": "Claude Opus 4.6",
            "description": "Latest flagship model with 200K context (1M beta)",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "advanced-reasoning",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 5.00,
            "output_cost_per_million": 25.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "claude-sonnet-4-6",
            "name": "Claude Sonnet 4.6",
            "description": "Latest balanced model with excellent reasoning",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        # Anthropic Models - Claude 4 Series
        {
            "id": "claude-opus-4-1-20250805",
            "name": "Claude Opus 4.1",
            "description": "Most capable and intelligent Claude model",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "advanced-reasoning",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 15.00,
            "output_cost_per_million": 75.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "claude-opus-4-5-20251101",
            "name": "Claude Opus 4.5",
            "description": "Most capable model with enhanced creativity and writing",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "advanced-reasoning",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 5.00,
            "output_cost_per_million": 25.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "claude-sonnet-4-5-20250929",
            "name": "Claude Sonnet 4.5",
            "description": "Best balance of intelligence, speed, and cost",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "claude-haiku-4-5-20251001",
            "name": "Claude Haiku 4.5",
            "description": "Fastest model for high-volume tasks",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 1.00,
            "output_cost_per_million": 5.00,
        },
        {
            "id": "claude-opus-4-20250514",
            "name": "Claude Opus 4",
            "description": "Best for coding and complex agent workflows",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 15.00,
            "output_cost_per_million": 75.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4",
            "description": "High-performance with exceptional reasoning",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "extended-thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 1024,
                    "max": 128000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "claude-3-5-haiku-20241022",
            "name": "Claude 3.5 Haiku",
            "description": "Fast and efficient for high-volume tasks",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": False,
            "input_cost_per_million": 0.80,
            "output_cost_per_million": 4.00,
        },
        # Anthropic Models - Claude 3 Series (Legacy)
        {
            "id": "claude-3-opus-20240229",
            "name": "Claude 3 Opus",
            "description": "Previous generation flagship model",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
            ],
            "is_active": False,
            "input_cost_per_million": 15.00,
            "output_cost_per_million": 75.00,
        },
        {
            "id": "claude-3-sonnet-20240229",
            "name": "Claude 3 Sonnet",
            "description": "Balanced performance and speed",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": False,
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
        },
        {
            "id": "claude-3-haiku-20240307",
            "name": "Claude 3 Haiku",
            "description": "Fast and efficient for simple tasks",
            "provider": "Anthropic",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
            ],
            "is_active": False,
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 1.25,
        },
        # Google Models - Gemini 3 Series (Preview)
        {
            "id": "gemini-3.1-pro-preview",
            "name": "Gemini 3.1 Pro Preview",
            "description": "Most advanced Gemini model for complex tasks (preview)",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 2.00,
            "output_cost_per_million": 12.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 0,
                    "max": 24576,
                    "default": 1024,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "gemini-3-flash-preview",
            "name": "Gemini 3 Flash Preview",
            "description": "Frontier-class performance rivaling larger models (preview)",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 0.50,
            "output_cost_per_million": 3.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 0,
                    "max": 24576,
                    "default": 1024,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "gemini-3.1-flash-lite-preview",
            "name": "Gemini 3.1 Flash-Lite Preview",
            "description": "Most cost-effective Gemini 3 model (preview)",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 1.50,
        },
        # Google Models - Gemini 2.5 Series
        {
            "id": "gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "description": "State-of-the-art thinking model for complex problems",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 1.25,
            "output_cost_per_million": 10.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 0,
                    "max": 24576,
                    "default": 1024,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "description": "Best price/performance with thinking capabilities",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 0.30,
            "output_cost_per_million": 2.50,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 0,
                    "max": 24576,
                    "default": 1024,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "gemini-2.5-flash-lite",
            "name": "Gemini 2.5 Flash-Lite",
            "description": "Cost-efficient variant for high throughput",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.10,
            "output_cost_per_million": 0.40,
        },
        # Google Models - Gemini 2.0 Series (deprecated June 1, 2026)
        {
            "id": "gemini-2.0-flash",
            "name": "Gemini 2.0 Flash",
            "description": "Fast with native tool use (1M context) - deprecated June 2026",
            "provider": "Google",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "tool-use",
            ],
            "is_active": False,
            "input_cost_per_million": 0.10,
            "output_cost_per_million": 0.40,
        },
        # DeepInfra Models - DeepSeek Series
        {
            "id": "deepseek-ai/DeepSeek-V3.1",
            "name": "DeepSeek-V3.1",
            "description": "671B params MoE model with 37B activated",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.21,
            "output_cost_per_million": 0.79,
        },
        {
            "id": "deepseek-ai/DeepSeek-R1-0528",
            "name": "DeepSeek-R1",
            "description": "State-of-the-art reasoning model",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.50,
            "output_cost_per_million": 2.15,
        },
        {
            "id": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            "name": "DeepSeek-R1-Distill-Llama-70B",
            "description": "Efficient distilled model with strong reasoning",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
            ],
            "is_active": True,
            "input_cost_per_million": 0.70,
            "output_cost_per_million": 0.80,
        },
        # DeepInfra Models - DeepSeek V3.2
        {
            "id": "deepseek-ai/DeepSeek-V3.2",
            "name": "DeepSeek-V3.2",
            "description": "Latest DeepSeek 671B MoE model with improved performance",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.26,
            "output_cost_per_million": 0.38,
        },
        # DeepInfra Models - Qwen Series
        {
            "id": "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "name": "Qwen3-235B Instruct",
            "description": "Instruction-following variant (non-thinking, very cheap)",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.071,
            "output_cost_per_million": 0.10,
        },
        {
            "id": "Qwen/Qwen3-235B-A22B-Thinking-2507",
            "name": "Qwen3-235B Thinking",
            "description": "Advanced model with thinking capabilities",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 0.23,
            "output_cost_per_million": 2.30,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 0,
                    "max": 32000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "Qwen/QwQ-32B",
            "name": "QwQ-32B",
            "description": "Reasoning model competitive with o1-mini",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "analysis",
                "advanced-reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.20,
            "output_cost_per_million": 0.60,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_budget",
                    "type": "number",
                    "min": 0,
                    "max": 32000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "name": "Qwen 2.5 Coder 32B",
            "description": "Specialized for coding tasks",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "coding",
                "analysis",
            ],
            "is_active": True,
            "input_cost_per_million": 0.20,
            "output_cost_per_million": 0.60,
        },
        # DeepInfra Models - Llama Series
        {
            "id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "name": "Llama 3.3 70B Turbo",
            "description": "FP8 optimized for faster inference",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.10,
            "output_cost_per_million": 0.32,
        },
        {
            "id": "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "name": "Llama 3.1 70B",
            "description": "Open-source large language model",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 0.40,
        },
        {
            "id": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "name": "Llama 3.1 8B",
            "description": "Smaller, faster Llama variant",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.02,
            "output_cost_per_million": 0.05,
        },
        {
            "id": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "name": "Llama 4 Scout",
            "description": "10M context multimodal MoE model",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": True,
            "input_cost_per_million": 0.08,
            "output_cost_per_million": 0.30,
        },
        {
            "id": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "name": "Llama 4 Maverick",
            "description": "1M context 128-expert MoE model",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": True,
            "input_cost_per_million": 0.15,
            "output_cost_per_million": 0.60,
        },
        {
            "id": "moonshotai/Kimi-K2-Instruct-0905",
            "name": "Kimi K2 Instruct",
            "description": "262K context model with strong reasoning",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 2.00,
        },
        {
            "id": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "name": "Qwen3 Coder 480B",
            "description": "Coding specialist MoE model",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "coding",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 1.60,
        },
        {
            "id": "MiniMaxAI/MiniMax-M2.5",
            "name": "MiniMax-M2.5",
            "description": "230B MoE model (10B active), 205K context, MIT licensed",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "analysis",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 0.27,
            "output_cost_per_million": 0.95,
        },
        # Kimi K2.5 (via DeepInfra)
        {
            "id": "moonshotai/Kimi-K2.5",
            "name": "Kimi K2.5",
            "description": "262K context model with advanced reasoning",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.45,
            "output_cost_per_million": 2.25,
        },
        # GLM Models (via DeepInfra)
        {
            "id": "zai-org/GLM-4.7",
            "name": "GLM-4.7",
            "description": "Zhipu AI's 358B MoE model with interleaved thinking",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 1.75,
        },
        {
            "id": "zai-org/GLM-5",
            "name": "GLM-5",
            "description": "Zhipu AI's flagship model with 200K context, hosted on DeepInfra",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.80,
            "output_cost_per_million": 2.56,
        },
        {
            "id": "zai-org/GLM-4.7-Flash",
            "name": "GLM-4.7 Flash",
            "description": "Zhipu AI's efficient 30B MoE model with 200K context, hosted on DeepInfra",
            "provider": "DeepInfra",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
            ],
            "is_active": True,
            "input_cost_per_million": 0.06,
            "output_cost_per_million": 0.40,
        },
        # Grok (xAI) Models
        {
            "id": "grok-4",
            "name": "Grok 4",
            "description": "xAI's most advanced model with reasoning (256K context)",
            "provider": "Grok",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
        },
        {
            "id": "grok-4-1-fast",
            "name": "Grok 4.1 Fast",
            "description": "xAI's tool-calling model for agentic tasks (2M context)",
            "provider": "Grok",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.20,
            "output_cost_per_million": 0.50,
        },
        {
            "id": "grok-3",
            "name": "Grok 3",
            "description": "xAI's Grok 3 stable release (131K context)",
            "provider": "Grok",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
        },
        {
            "id": "grok-3-mini",
            "name": "Grok 3 Mini",
            "description": "xAI's compact Grok 3 stable release",
            "provider": "Grok",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.30,
            "output_cost_per_million": 0.50,
            "default_config": {
                "reasoning_config": {
                    "parameter": "reasoning_effort",
                    "type": "select",
                    "values": ["low", "high"],
                    "default": "low",
                    "label": "Thinking/Reasoning Level",
                }
            },
        },
        {
            "id": "grok-3-beta",
            "name": "Grok 3 Beta",
            "description": "xAI's Grok 3 with improved reasoning (131K context)",
            "provider": "Grok",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 5.00,
            "output_cost_per_million": 15.00,
        },
        {
            "id": "grok-3-mini-beta",
            "name": "Grok 3 Mini Beta",
            "description": "xAI's compact Grok 3 model (131K context)",
            "provider": "Grok",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.30,
            "output_cost_per_million": 0.50,
            "default_config": {
                "reasoning_config": {
                    "parameter": "reasoning_effort",
                    "type": "select",
                    "values": ["low", "high"],
                    "default": "low",
                    "label": "Thinking/Reasoning Level",
                }
            },
        },
        # Mistral AI Models
        {
            "id": "mistral-large-latest",
            "name": "Mistral Large",
            "description": "Mistral AI's top-tier model (41B active, 675B total)",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "coding",
            ],
            "is_active": True,
            "input_cost_per_million": 0.50,
            "output_cost_per_million": 1.50,
        },
        {
            "id": "mistral-medium-latest",
            "name": "Mistral Medium",
            "description": "Mistral AI's frontier-class multimodal model (Medium 3.1)",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "multimodal",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 2.00,
        },
        {
            "id": "mistral-small-latest",
            "name": "Mistral Small",
            "description": "Mistral AI's efficient model with vision (128K context)",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
                "multimodal",
            ],
            "is_active": True,
            "input_cost_per_million": 0.06,
            "output_cost_per_million": 0.18,
        },
        {
            "id": "codestral-latest",
            "name": "Codestral",
            "description": "Mistral AI's code model for completion (128K context)",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "coding",
                "text-generation",
            ],
            "is_active": True,
            "input_cost_per_million": 0.30,
            "output_cost_per_million": 0.90,
        },
        {
            "id": "devstral-latest",
            "name": "Devstral",
            "description": "Agentic coding model for software engineering (Devstral 2)",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "coding",
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.40,
            "output_cost_per_million": 0.90,
        },
        {
            "id": "magistral-medium-latest",
            "name": "Magistral Medium",
            "description": "Mistral AI's frontier reasoning model",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "reasoning",
                "text-generation",
                "analysis",
            ],
            "is_active": True,
            "input_cost_per_million": 2.00,
            "output_cost_per_million": 5.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "prompt_mode",
                    "type": "toggle",
                    "values": ["reasoning", None],
                    "default": "reasoning",
                    "label": "Thinking/Reasoning Mode",
                }
            },
        },
        {
            "id": "magistral-small-latest",
            "name": "Magistral Small",
            "description": "Mistral AI's efficient reasoning model",
            "provider": "Mistral",
            "model_type": "chat",
            "capabilities": [
                "reasoning",
                "text-generation",
            ],
            "is_active": True,
            "input_cost_per_million": 0.50,
            "output_cost_per_million": 1.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "prompt_mode",
                    "type": "toggle",
                    "values": ["reasoning", None],
                    "default": "reasoning",
                    "label": "Thinking/Reasoning Mode",
                }
            },
        },
        # Cohere Models
        {
            "id": "command-a-03-2025",
            "name": "Command A",
            "description": "Cohere's most performant model (111B params, 256K context)",
            "provider": "Cohere",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
                "analysis",
                "thinking",
            ],
            "is_active": True,
            "input_cost_per_million": 2.50,
            "output_cost_per_million": 10.00,
            "default_config": {
                "reasoning_config": {
                    "parameter": "thinking_token_budget",
                    "type": "number",
                    "min": 0,
                    "max": 16000,
                    "default": None,
                    "label": "Thinking/Reasoning Budget (tokens)",
                }
            },
        },
        {
            "id": "command-r-plus-08-2024",
            "name": "Command R+",
            "description": "Cohere's flagship model for RAG and tool use",
            "provider": "Cohere",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "data-synthesis",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 2.50,
            "output_cost_per_million": 10.00,
        },
        {
            "id": "command-r-08-2024",
            "name": "Command R",
            "description": "Cohere's balanced model with high throughput",
            "provider": "Cohere",
            "model_type": "chat",
            "capabilities": [
                "text-generation",
                "reasoning",
            ],
            "is_active": True,
            "input_cost_per_million": 0.15,
            "output_cost_per_million": 0.60,
        },
    ]

    # Parameter constraints for models with non-standard temperature/token behavior.
    # Three modes: fixed (supported=False), clamped range (min/max), unconstrained (no entry).
    _GPT5_CONSTRAINTS = {
        "temperature": {
            "supported": False,
            "required_value": 1.0,
            "reason": "OpenAI GPT-5 series enforces temperature=1.0 via API",
        },
        "max_tokens": {"default": 8000},
        "unsupported_params": [
            "top_p", "presence_penalty", "frequency_penalty",
            "logprobs", "top_logprobs", "logit_bias",
        ],
        "reproducibility_impact": "CRITICAL",
        "benchmark_notes": "Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.",
    }
    _O_SERIES_CONSTRAINTS = {
        "temperature": {
            "supported": False,
            "required_value": 1.0,
            "reason": "OpenAI o-series enforces temperature=1.0 via API",
        },
        "unsupported_params": [
            "top_p", "presence_penalty", "frequency_penalty",
            "logprobs", "top_logprobs", "logit_bias",
        ],
        "reproducibility_impact": "CRITICAL",
        "benchmark_notes": "Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.",
    }

    MODEL_CONSTRAINTS = {
        # GPT-5 series - fixed temperature=1.0
        "gpt-5": _GPT5_CONSTRAINTS,
        "gpt-5.4": _GPT5_CONSTRAINTS,
        "gpt-5.2": _GPT5_CONSTRAINTS,
        "gpt-5.1": _GPT5_CONSTRAINTS,
        "gpt-5-mini": _GPT5_CONSTRAINTS,
        "gpt-5-nano": _GPT5_CONSTRAINTS,
        # o-series - fixed temperature=1.0
        "o1": {**_O_SERIES_CONSTRAINTS, "max_tokens": {"default": 16000}},
        "o3": {**_O_SERIES_CONSTRAINTS, "max_tokens": {"default": 16000}},
        "o3-mini": {**_O_SERIES_CONSTRAINTS, "max_tokens": {"default": 8000}},
        "o4-mini": {**_O_SERIES_CONSTRAINTS, "max_tokens": {"default": 8000}},
        # Claude - standard temp support, max=1.0 (Anthropic limit)
        "claude-opus-4-6": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
            "max_tokens": {"default": 16000},
        },
        "claude-sonnet-4-6": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
            "max_tokens": {"default": 8000},
        },
        "claude-opus-4-1-20250805": {
            "temperature": {
                "supported": True, "default": 0.0, "min": 0.0, "max": 1.0,
                "reason": "Standard support, but conflicts with top_p",
            },
            "top_p": {"supported": True, "conflicts_with": ["temperature"]},
            "max_tokens": {"default": 16000},
            "reproducibility_impact": "LOW",
            "benchmark_notes": "Use temperature=0.0 only, omit top_p parameter.",
        },
        "claude-opus-4-5-20251101": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
            "max_tokens": {"default": 16000},
        },
        "claude-sonnet-4-5-20250929": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
            "max_tokens": {"default": 8000},
        },
        "claude-opus-4-20250514": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
            "max_tokens": {"default": 16000},
        },
        "claude-sonnet-4-20250514": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
            "max_tokens": {"default": 8000},
        },
        # Qwen thinking models - min temperature 0.6 (greedy decoding causes repetitions)
        "Qwen/QwQ-32B": {
            "temperature": {
                "supported": True, "default": 0.6, "min": 0.6, "max": 2.0,
                "reason": "Greedy decoding (temp<0.6) causes endless repetitions",
            },
            "max_tokens": {"default": 8000},
            "reproducibility_impact": "MEDIUM",
            "benchmark_notes": "Lowest stable temperature is 0.6. Run 3 iterations, report variance.",
        },
        "Qwen/Qwen3-235B-A22B-Thinking-2507": {
            "temperature": {
                "supported": True, "default": 0.6, "min": 0.6, "max": 2.0,
                "reason": "Thinking mode requires temp>=0.6 to avoid repetitions",
            },
            "max_tokens": {"default": 8000},
            "reproducibility_impact": "MEDIUM",
            "benchmark_notes": "Lowest stable temperature is 0.6. Run 3 iterations, document thinking tokens.",
        },
        # DeepSeek R1 - works at 0.0 but optimal at 0.5-0.7
        "deepseek-ai/DeepSeek-R1-0528": {
            "temperature": {
                "supported": True, "default": 0.6, "min": 0.0, "max": 2.0,
                "reason": "Works at 0.0 but optimal performance at 0.5-0.7",
            },
            "max_tokens": {"default": 8000},
            "reproducibility_impact": "LOW",
            "benchmark_notes": "For reproducibility: use 0.0. For quality benchmarks: use 0.6.",
        },
        "deepseek-ai/DeepSeek-R1-Distill-Llama-70B": {
            "temperature": {
                "supported": True, "default": 0.6, "min": 0.0, "max": 2.0,
                "reason": "Distilled model optimized for temp=0.5-0.7",
            },
            "max_tokens": {"default": 8000},
            "reproducibility_impact": "LOW",
            "benchmark_notes": "For reproducibility: use 0.0. For quality benchmarks: use 0.6.",
        },
        "deepseek-ai/DeepSeek-V3.1": {
            "temperature": {
                "supported": True, "default": 0.6, "min": 0.0, "max": 2.0,
                "reason": "Optimal performance at 0.5-0.7",
            },
            "max_tokens": {"default": 8000},
            "reproducibility_impact": "LOW",
        },
        # Gemini thinking models - standard temp support
        "gemini-2.5-pro": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 2.0},
            "max_tokens": {"default": 8000},
        },
        "gemini-2.5-flash": {
            "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 2.0},
            "max_tokens": {"default": 8000},
        },
    }

    # Apply constraints to model dicts
    for model in default_models:
        if model["id"] in MODEL_CONSTRAINTS:
            model["parameter_constraints"] = MODEL_CONSTRAINTS[model["id"]]

    for model in default_models:
        _upsert_llm_model(db, model)

    # Deactivate models not in the script to prevent stale entries on prod/staging
    from models import LLMModel as DBLLMModel

    script_ids = {m["id"] for m in default_models}
    stale = db.query(DBLLMModel).filter(
        ~DBLLMModel.id.in_(script_ids), DBLLMModel.is_active == True
    ).all()
    for model in stale:
        model.is_active = False
        print(f"Deactivated stale model not in seed script: {model.id}")

    db.commit()
