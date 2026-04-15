# Model Parameter Constraints for Benchmarking

## Overview

This document details parameter constraints and reproducibility considerations for all LLM models used in BenGER benchmarking. Understanding these constraints is critical for interpreting benchmark results and ensuring fair comparisons.

**Last Updated**: 2025-10-17

---

## Reproducibility Levels

BenGER classifies models into four reproducibility levels based on their ability to produce deterministic outputs:

- **HIGH**: Deterministic outputs (`temperature=0.0` or equivalent). Runs produce identical results. Ideal for reproducible benchmarking.
- **MEDIUM**: Low variance (`temperature=0.5-0.7`). Runs produce similar but not identical results. Variance typically <10%.
- **LOW**: Moderate variance (`temperature≥0.8`). Significant variation between runs. Variance 10-30%.
- **NONE**: High variance or enforced randomness. Results vary substantially between runs. Reproducibility not achievable.

---

## Model-Specific Configurations

### OpenAI GPT-5 Series

**Models**: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`

**Reproducibility Level**: **NONE** (enforced by API)

**Parameters**:
- ❌ **temperature**: REQUIRED=1.0 (cannot be changed)
- ❌ **top_p**: Not supported
- ❌ **presence_penalty**: Not supported
- ❌ **frequency_penalty**: Not supported
- ❌ **logprobs**: Not supported
- ❌ **top_logprobs**: Not supported
- ❌ **logit_bias**: Not supported

**API Behavior**:
```python
# Will fail with 400 error:
response = client.chat.completions.create(
    model="gpt-5-mini",
    temperature=0.0  # ❌ ERROR: Unsupported value
)

# Must use:
response = client.chat.completions.create(
    model="gpt-5-mini",
    temperature=1.0  # ✅ Required value
)
# Or omit temperature parameter entirely (defaults to 1.0)
```

**Benchmark Implications**:
- These models are **inherently non-deterministic**
- **Recommendation**: Run each benchmark 5+ times and report:
  - Mean response score
  - Standard deviation
  - Min/max variance
  - 95% confidence interval
- Results cannot be directly compared to deterministic models
- Consider separate leaderboards for deterministic vs non-deterministic models
- Document all runs in evaluation reports

**Error Message**:
```
Error code: 400 - {'error': {'message': "Unsupported value: 'temperature' does not
support 0.0 with this model. Only the default (1) value is supported."}}
```

---

### Anthropic Claude Opus 4.1

**Model**: `claude-opus-4-1-20250805`

**Reproducibility Level**: **HIGH**

**Parameters**:
- ✅ **temperature**: 0.0 (for deterministic output)
- ⚠️ **top_p**: Cannot use if temperature is set

**API Behavior**:
```python
# Will fail:
response = client.messages.create(
    model="claude-opus-4-1-20250805",
    temperature=0.0,
    top_p=0.9  # ❌ ERROR: Cannot use both
)

# Correct usage:
response = client.messages.create(
    model="claude-opus-4-1-20250805",
    temperature=0.0  # ✅ Deterministic
    # Do NOT include top_p
)
```

**Benchmark Implications**:
- Can achieve full reproducibility
- Use `temperature=0.0`, omit `top_p`
- Results directly comparable to other deterministic models
- No need for multiple runs
- Standard deviation should be 0.0

---

### Qwen Thinking Models

**Models**: `Qwen/QwQ-32B`, `Qwen/Qwen3-235B-A22B-Thinking-2507`

**Reproducibility Level**: **MEDIUM**

**Parameters**:
- ⚠️ **temperature**: 0.6 (minimum stable value)
- ✅ **top_p**: 0.95 (recommended)
- ❌ **temperature**: 0.0 causes endless repetitions

**API Behavior**:
```python
# Will cause endless repetitions:
response = client.chat.completions.create(
    model="Qwen/QwQ-32B",
    temperature=0.0  # ❌ Model breaks - infinite loop
)

# Correct usage:
response = client.chat.completions.create(
    model="Qwen/QwQ-32B",
    temperature=0.6,  # ✅ Stable minimum
    top_p=0.95       # ✅ Recommended
)
```

**Benchmark Implications**:
- Cannot achieve full determinism (`temp=0.0` breaks model)
- Lowest stable temperature is 0.6
- **Recommendation**: Run 3+ iterations, report variance
- Expected variance: ~5-10% between runs
- Document "thinking tokens" if model exposes them
- Results should include confidence intervals

**Known Issues**:
- Greedy decoding (temp=0.0) triggers repetition bug
- Model enters infinite loop generating same tokens
- Recommended by Qwen team: temp=0.6, top_p=0.95

---

### DeepSeek R1 Models

**Models**: `deepseek-ai/DeepSeek-R1-0528`, `deepseek-ai/DeepSeek-R1-Distill-Llama-70B`, `deepseek-ai/DeepSeek-V3.1`

**Reproducibility Level**: **Configurable** (HIGH or MEDIUM)

**Parameters**:
- ✅ **temperature**: 0.0 (works) OR 0.6 (optimal)
- **Recommended**: 0.5-0.7 for quality

**API Behavior**:
```python
# For reproducibility benchmarks:
response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-R1",
    temperature=0.0  # ✅ Fully deterministic
)

# For quality benchmarks:
response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-R1",
    temperature=0.6  # ✅ Optimal performance
)
```

**Benchmark Implications**:
- **Two benchmarking strategies**:
  1. **Reproducibility-focused**: Use `temp=0.0` for determinism
  2. **Quality-focused**: Use `temp=0.6` for optimal model performance
- Document which strategy is used in benchmark reports
- Results at `temp=0.0` may be slightly lower quality than `temp=0.6`
- Via DeepInfra: `temp=0.5-0.7` recommended to prevent repetitions

**Recommendation**:
- For research requiring reproducibility: Use `temp=0.0`
- For production quality assessment: Use `temp=0.6`
- Clearly label which configuration was used

---

### All Other Models

**Models**: GPT-3.5 Turbo, GPT-4o/Mini, Claude 3.x/4 (non-Opus-4.1), Gemini (all), Llama (all), Qwen (non-thinking)

**Reproducibility Level**: **HIGH**

**Parameters**:
- ✅ **temperature**: 0.0 (fully supported)
- ✅ All standard parameters supported

**Benchmark Implications**:
- Full reproducibility achievable
- Results are deterministic (identical on repeat runs)
- Ideal for benchmarking comparisons
- No need for multiple runs
- Standard deviation should be 0.0

---

## Benchmark Configuration Recommendations

### Scenario 1: Maximum Reproducibility

**Goal**: Minimize variance, ensure reproducible results for research

```python
BENCHMARK_CONFIG = {
    'default_temperature': 0.0,
    'model_overrides': {
        # GPT-5 series - Cannot be deterministic
        'gpt-5': {'temperature': 1.0, 'run_count': 5},
        'gpt-5-mini': {'temperature': 1.0, 'run_count': 5},
        'gpt-5-nano': {'temperature': 1.0, 'run_count': 5},

        # Qwen thinking - Minimum stable temperature
        'Qwen/QwQ-32B': {'temperature': 0.6, 'run_count': 3},
        'Qwen/Qwen3-235B-A22B-Thinking-2507': {'temperature': 0.6, 'run_count': 3},

        # DeepSeek - Use deterministic mode
        'deepseek-ai/DeepSeek-R1-0528': {'temperature': 0.0, 'run_count': 1},
        'deepseek-ai/DeepSeek-R1-Distill-Llama-70B': {'temperature': 0.0, 'run_count': 1},
        'deepseek-ai/DeepSeek-V3.1': {'temperature': 0.0, 'run_count': 1},
    },
    'reporting': {
        'include_variance': True,
        'report_all_runs': True,
        'flag_non_deterministic': True,
        'separate_leaderboards': True  # Separate deterministic vs non-deterministic
    }
}
```

### Scenario 2: Quality-Focused Benchmarking

**Goal**: Evaluate models at their optimal settings

```python
BENCHMARK_CONFIG = {
    'default_temperature': 0.0,  # Still use 0.0 for most models
    'model_overrides': {
        # GPT-5 series - Must use 1.0
        'gpt-5': {'temperature': 1.0},
        'gpt-5-mini': {'temperature': 1.0},
        'gpt-5-nano': {'temperature': 1.0},

        # Qwen thinking - Optimal setting
        'Qwen/QwQ-32B': {'temperature': 0.6},
        'Qwen/Qwen3-235B-A22B-Thinking-2507': {'temperature': 0.6},

        # DeepSeek - Use optimal (not deterministic)
        'deepseek-ai/DeepSeek-R1-0528': {'temperature': 0.6},
        'deepseek-ai/DeepSeek-R1-Distill-Llama-70B': {'temperature': 0.6},
        'deepseek-ai/DeepSeek-V3.1': {'temperature': 0.6},
    }
}
```

---

## Reporting Requirements

When publishing benchmark results, include:

### 1. Model Configuration Table

Example format:

| Model | Temperature | Top-P | Reproducibility | Runs | Mean Score | Std Dev | Variance |
|-------|-------------|-------|-----------------|------|------------|---------|----------|
| gpt-4o | 0.0 | default | HIGH | 1 | 85.3 | 0.0 | 0.0% |
| gpt-5-mini | 1.0 | omitted | NONE | 5 | 82.1 | 4.2 | 12.3% |
| Qwen/QwQ-32B | 0.6 | 0.95 | MEDIUM | 3 | 87.5 | 2.1 | 5.7% |
| claude-opus-4-1 | 0.0 | omitted | HIGH | 1 | 91.2 | 0.0 | 0.0% |
| DeepSeek-R1 | 0.0 | default | HIGH | 1 | 89.8 | 0.0 | 0.0% |

### 2. Reproducibility Disclaimer

Include in all benchmark reports:

> **Reproducibility Note**: This benchmark includes models with varying levels of reproducibility:
> - **HIGH** (temperature=0.0): Results are deterministic and identical on repeated runs
> - **MEDIUM** (temperature=0.6): Results show ~5-10% variance between runs
> - **NONE** (temperature=1.0, enforced): Results show significant variance (>10%) between runs
>
> Models classified as NONE (GPT-5 series) were run 5 times with variance reported.
> Scores should be interpreted as mean ± standard deviation.

### 3. Comparison Caveats

When comparing models across reproducibility levels:

- ⚠️ **Direct comparisons should note reproducibility differences**
- Models with NONE reproducibility may show artificially higher/lower scores due to sampling variance
- Consider confidence intervals when ranking models
- Prefer comparing models within the same reproducibility tier
- For research requiring strict reproducibility, filter to HIGH-reproducibility models only

### 4. Separate Leaderboards (Recommended)

**Deterministic Models Leaderboard** (HIGH reproducibility):
- GPT-3.5/4o, Claude, Gemini, Llama, DeepSeek (at temp=0.0)
- Rankings are stable and reproducible

**Non-Deterministic Models Leaderboard** (MEDIUM/NONE reproducibility):
- GPT-5 series, Qwen thinking models, DeepSeek (at temp=0.6)
- Rankings include confidence intervals

---

## Database Storage

All parameter configurations are automatically stored in generation metadata for post-hoc analysis:

```json
{
  "generation_metadata": {
    "temperature": 0.6,
    "reproducibility_level": "MEDIUM",
    "params_omitted": ["top_p"],
    "reproducibility_impact": "MEDIUM - Use temp=0.6 for best reproducibility",
    "benchmark_notes": "Lowest stable temperature for this model",
    "constraint_reason": "Greedy decoding causes repetitions"
  }
}
```

This enables filtering and analysis by reproducibility level in evaluation reports.

---

## Implementation Notes

### For Developers

Parameter constraints are stored in the `llm_models.parameter_constraints` JSONB column and automatically applied by the worker during generation.

```python
# Worker automatically applies constraints
from model_parameter_config import get_model_generation_params

params = get_model_generation_params(
    db=db,
    model_id=model_id,
    user_temp=user_override
)

# params['temperature'] respects model constraints
# params['warnings'] lists any overrides applied
# params['reproducibility_level'] indicates expected variance
```

### For Researchers

When designing benchmarks:

1. **Decide on reproducibility requirements** early
2. **Filter models** by reproducibility level if strict determinism is needed
3. **Document variance** for non-deterministic models
4. **Use confidence intervals** when comparing models with different reproducibility levels
5. **Consider separate analyses** for deterministic vs non-deterministic models

---

## References

- OpenAI GPT-5 API Documentation
- Qwen Team Recommendations: [https://huggingface.co/Qwen/QwQ-32B/discussions/5](https://huggingface.co/Qwen/QwQ-32B/discussions/5)
- DeepInfra DeepSeek R1 Guidelines
- Anthropic Claude API Documentation

---

## Changelog

**2025-10-17**: Initial documentation
- Added constraints for GPT-5 series, Claude Opus 4.1, Qwen thinking models, DeepSeek R1 series
- Defined reproducibility levels
- Created benchmark configuration recommendations
