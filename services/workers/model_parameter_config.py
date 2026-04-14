"""
Model Parameter Configuration for Reproducible Benchmarking

This module handles model-specific parameter constraints to maximize
reproducibility while respecting API limitations.
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_model_generation_params(
    db: Session,
    model_id: str,
    user_temp: Optional[float] = None,
    project_config: Optional[dict] = None,
    model_orm_class: Any = None,
) -> dict:
    """
    Get generation parameters for a specific model, respecting constraints.

    Priority order:
    1. Model hard requirements (will fail API calls if violated)
    2. User/project override (if allowed by model)
    3. Model recommendations (for reproducibility/quality balance)
    4. System defaults (temperature=0.0)

    Args:
        db: Database session
        model_id: The model identifier
        user_temp: Optional user-specified temperature
        project_config: Optional project configuration
        model_orm_class: ORM class for LLMModel (to avoid circular imports)

    Returns:
        dict: {
            'temperature': float,
            'params_used': dict,
            'params_omitted': list,
            'reproducibility_level': str,  # 'HIGH', 'MEDIUM', 'LOW', 'NONE'
            'warnings': list,
            'benchmark_notes': str
        }
    """
    warnings = []
    params = {}
    omitted_params = []
    reproducibility_level = 'HIGH'  # Default to HIGH (temp=0.0)
    benchmark_notes = ''

    # Fetch model constraints from database
    constraints = {}
    if model_orm_class:
        try:
            model = db.query(model_orm_class).filter(model_orm_class.id == model_id).first()
            if model and model.parameter_constraints:
                constraints = model.parameter_constraints
        except Exception as e:
            logger.warning(f"Could not fetch model constraints: {e}")

    # Temperature handling
    temp_config = constraints.get('temperature', {})

    if not temp_config.get('supported', True):
        # Model doesn't support custom temperature (e.g., GPT-5)
        required_temp = temp_config.get('required_value', 1.0)
        if user_temp is not None and user_temp != required_temp:
            warning_msg = (
                f"Model {model_id} requires temperature={required_temp}. "
                f"Ignoring user setting of {user_temp}. "
                f"Reason: {temp_config.get('reason', 'API requirement')}"
            )
            warnings.append(warning_msg)
            logger.warning(f"⚠️ {warning_msg}")

        params['temperature'] = required_temp
        reproducibility_level = 'NONE'  # Cannot achieve determinism
        logger.info(
            f"🔒 Model {model_id} enforces temperature={required_temp} " f"(non-deterministic)"
        )

    else:
        # Temperature is supported -- apply user value or model default, then clamp
        if user_temp is not None:
            params['temperature'] = user_temp
        else:
            params['temperature'] = temp_config.get('default', 0.0)

        # Clamp to allowed min/max range
        min_temp = temp_config.get('min')
        max_temp = temp_config.get('max')
        if min_temp is not None and params['temperature'] < min_temp:
            warning_msg = (
                f"Model {model_id}: clamping temperature from {params['temperature']} to min {min_temp}. "
                f"Reason: {temp_config.get('reason', 'Model constraint')}"
            )
            warnings.append(warning_msg)
            logger.warning(f"⚠️ {warning_msg}")
            params['temperature'] = min_temp
        if max_temp is not None and params['temperature'] > max_temp:
            warning_msg = (
                f"Model {model_id}: clamping temperature from {params['temperature']} to max {max_temp}. "
                f"Reason: {temp_config.get('reason', 'Model constraint')}"
            )
            warnings.append(warning_msg)
            logger.warning(f"⚠️ {warning_msg}")
            params['temperature'] = max_temp

        reproducibility_level = 'HIGH' if params['temperature'] == 0.0 else 'MEDIUM'

    # Handle conflicting parameters (e.g., Claude Opus 4.1 temperature vs top_p)
    for param_name, param_config in constraints.items():
        if isinstance(param_config, dict) and 'conflicts_with' in param_config:
            conflicts = param_config['conflicts_with']
            if 'temperature' in conflicts and params.get('temperature') is not None:
                omitted_params.append(param_name)
                warning_msg = (
                    f"Omitting {param_name} for {model_id} due to conflict with temperature. "
                    f"Reason: {param_config.get('reason', 'Parameter conflict')}"
                )
                warnings.append(warning_msg)
                logger.info(f"ℹ️  {warning_msg}")

    # Handle unsupported parameters (e.g., GPT-5 doesn't support logprobs)
    unsupported = constraints.get('unsupported_params', [])
    if unsupported:
        omitted_params.extend(unsupported)
        logger.info(f"ℹ️  Model {model_id} does not support: {', '.join(unsupported)}")

    # Add max_tokens (always supported)
    if project_config and 'max_tokens' in project_config:
        params['max_tokens'] = project_config['max_tokens']
    else:
        params['max_tokens'] = 1500  # Default

    # Get reproducibility impact and benchmark notes
    reproducibility_impact = constraints.get('reproducibility_impact', '')
    if reproducibility_impact:
        # Override level from constraints if specified
        if 'CRITICAL' in reproducibility_impact or 'NONE' in reproducibility_impact:
            reproducibility_level = 'NONE'
        elif 'LOW-MEDIUM' in reproducibility_impact:
            reproducibility_level = 'MEDIUM'
        elif 'LOW' in reproducibility_impact and params['temperature'] > 0.0:
            reproducibility_level = 'MEDIUM'

    benchmark_notes = constraints.get('benchmark_notes', '')

    # Log final configuration for benchmarking
    logger.info(
        f"🎯 BENCHMARK_CONFIG: model={model_id}, "
        f"temperature={params['temperature']}, "
        f"reproducibility={reproducibility_level}"
    )

    if benchmark_notes:
        logger.info(f"📝 Benchmark notes: {benchmark_notes}")

    return {
        'temperature': params['temperature'],
        'max_tokens': params['max_tokens'],
        'params_used': params,
        'params_omitted': omitted_params,
        'reproducibility_level': reproducibility_level,
        'warnings': warnings,
        'benchmark_notes': benchmark_notes,
        'reproducibility_impact': reproducibility_impact,
    }
