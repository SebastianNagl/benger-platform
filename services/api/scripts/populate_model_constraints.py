"""
DEPRECATED: Parameter constraints are now managed in database.py initialize_llm_models()
and applied via Alembic migration 028_populate_parameter_constraints.

This standalone script is kept for reference only. Do not run it directly.
The single source of truth is database.py MODEL_CONSTRAINTS dict.
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Model parameter constraints
MODELS_WITH_CONSTRAINTS = {
    # OpenAI GPT-5 Series - HARD requirement (API enforces temperature=1.0)
    'gpt-5': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI GPT-5 series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'gpt-5.4': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI GPT-5 series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'gpt-5.2': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI GPT-5 series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'gpt-5.1': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI GPT-5 series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'gpt-5-mini': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI GPT-5 series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'gpt-5-nano': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI GPT-5 series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    # OpenAI o-Series - HARD requirement (API enforces temperature=1.0)
    'o1': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI o-series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'o3': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI o-series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'o3-mini': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI o-series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    'o4-mini': {
        'temperature': {
            'supported': False,
            'required_value': 1.0,
            'reason': 'OpenAI o-series enforces temperature=1.0 via API',
            'reproducibility_impact': 'CRITICAL - Model inherently non-deterministic',
        },
        'unsupported_params': [
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'logprobs',
            'top_logprobs',
            'logit_bias',
        ],
        'benchmark_notes': 'Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.',
    },
    # Anthropic Claude Opus 4.1 - Parameter conflict
    'claude-opus-4-1-20250805': {
        'temperature': {
            'supported': True,
            'default': 0.0,
            'reason': 'Standard support, but conflicts with top_p',
        },
        'top_p': {
            'supported': True,
            'conflicts_with': ['temperature'],
            'reason': 'Cannot specify both temperature and top_p simultaneously',
        },
        'reproducibility_impact': 'LOW - Can use temperature=0.0 alone',
        'benchmark_notes': 'Use temperature=0.0 only, omit top_p parameter. Fully deterministic.',
    },
    # Qwen Thinking Models - Performance issues with greedy decoding
    'Qwen/QwQ-32B': {
        'temperature': {
            'supported': True,
            'default': 0.6,
            'recommended_range': [0.6, 0.7],
            'avoid_values': [0.0],
            'reason': 'Greedy decoding (temp=0.0) causes endless repetitions',
        },
        'top_p': {'supported': True, 'recommended': 0.95},
        'reproducibility_impact': 'MEDIUM - Use temp=0.6 for best reproducibility',
        'benchmark_notes': 'Lowest stable temperature is 0.6. Run 3 iterations, report variance ~5-10%.',
    },
    'Qwen/Qwen3-235B-A22B-Thinking-2507': {
        'temperature': {
            'supported': True,
            'default': 0.6,
            'recommended_range': [0.6, 0.7],
            'avoid_values': [0.0],
            'reason': 'Thinking mode requires temp>=0.6 to avoid repetitions',
        },
        'top_p': {'supported': True, 'recommended': 0.95},
        'enable_thinking': {
            'supported': True,
            'default': True,
            'reason': 'Thinking-specific model',
        },
        'reproducibility_impact': 'MEDIUM - Use temp=0.6 for best reproducibility',
        'benchmark_notes': 'Lowest stable temperature is 0.6. Run 3 iterations, document thinking tokens.',
    },
    # DeepSeek R1 - Suboptimal at 0.0 but works
    'deepseek-ai/DeepSeek-R1-0528': {
        'temperature': {
            'supported': True,
            'default': 0.6,
            'recommended_range': [0.5, 0.7],
            'reason': 'Works at 0.0 but optimal performance at 0.5-0.7',
        },
        'reproducibility_impact': 'LOW-MEDIUM - Can use 0.0 for determinism or 0.6 for quality',
        'benchmark_notes': 'For reproducibility: use 0.0. For quality benchmarks: use 0.6.',
    },
    'deepseek-ai/DeepSeek-R1-Distill-Llama-70B': {
        'temperature': {
            'supported': True,
            'default': 0.6,
            'recommended_range': [0.5, 0.7],
            'reason': 'Distilled model optimized for temp=0.5-0.7',
        },
        'reproducibility_impact': 'LOW-MEDIUM - Can use 0.0 for determinism or 0.6 for quality',
        'benchmark_notes': 'For reproducibility: use 0.0. For quality benchmarks: use 0.6.',
    },
    'deepseek-ai/DeepSeek-V3.1': {
        'temperature': {
            'supported': True,
            'default': 0.6,
            'recommended_range': [0.5, 0.7],
            'reason': 'Optimal performance at 0.5-0.7',
        },
        'reproducibility_impact': 'LOW-MEDIUM - Can use 0.0 for determinism or 0.6 for quality',
        'benchmark_notes': 'For reproducibility: use 0.0. For quality benchmarks: use 0.6.',
    },
}


def populate_constraints():
    """Populate model parameter constraints in the database."""

    # Get database URI from environment or use default
    database_uri = os.getenv('DATABASE_URI', 'postgresql://postgres:postgres@localhost:5432/benger')

    print(f"Connecting to database: {database_uri}")

    engine = create_engine(database_uri)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Update each model with constraints
        updated_count = 0
        skipped_count = 0

        for model_id, constraints in MODELS_WITH_CONSTRAINTS.items():
            # Check if model exists
            result = session.execute(
                text("SELECT id FROM llm_models WHERE id = :model_id"), {'model_id': model_id}
            ).fetchone()

            if result:
                # Update the model with constraints
                constraints_json = json.dumps(constraints)
                session.execute(
                    text(
                        """
                        UPDATE llm_models
                        SET parameter_constraints = CAST(:constraints_json AS jsonb)
                        WHERE id = :model_id
                    """
                    ),
                    {'model_id': model_id, 'constraints_json': constraints_json},
                )
                print(f"✅ Updated constraints for model: {model_id}")
                updated_count += 1
            else:
                print(f"⚠️  Model not found in database: {model_id}")
                skipped_count += 1

        session.commit()

        print(f"\n{'='*60}")
        print(f"✅ Successfully updated {updated_count} models")
        if skipped_count > 0:
            print(f"⚠️  Skipped {skipped_count} models (not found in database)")
        print(f"{'='*60}\n")

        # Show summary of what was configured
        print("Configured models by reproducibility level:")
        print("-" * 60)

        # Group by reproducibility impact
        by_impact = {}
        for model_id, constraints in MODELS_WITH_CONSTRAINTS.items():
            impact = constraints.get('reproducibility_impact', 'UNKNOWN')
            temp_config = constraints.get('temperature', {})
            temp_value = temp_config.get('required_value') or temp_config.get('default', 0.0)

            if impact not in by_impact:
                by_impact[impact] = []
            by_impact[impact].append((model_id, temp_value))

        for impact in ['LOW', 'LOW-MEDIUM', 'MEDIUM', 'CRITICAL']:
            if impact in by_impact:
                print(f"\n{impact}:")
                for model_id, temp in by_impact[impact]:
                    print(f"  - {model_id}: temperature={temp}")

    except Exception as e:
        session.rollback()
        print(f"❌ Error updating constraints: {e}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Populating Model Parameter Constraints")
    print("=" * 60)
    print()
    populate_constraints()
    print("\n✅ Model parameter constraints populated successfully!")
    print("\nNext steps:")
    print("1. Update worker code to use these constraints")
    print("2. Test GPT-5 mini generation")
    print("3. Document reproducibility methodology")
