# Safe Generation Structure with Field Interpolation

## Overview

The Safe Generation Structure feature (Issue #507) prevents reference answer leakage during LLM generation by implementing secure field filtering and interpolation. This ensures that sensitive data such as reference answers, annotations, and ground truth labels are never sent to language models during evaluation.

## Problem Solved

Previously, the system performed simple string interpolation of all task data into prompts, which meant that reference answers and annotations could accidentally be sent to LLMs during evaluation. This defeated the purpose of evaluation by providing the correct answers to the models being tested.

## How It Works

### 1. Generation Structure Definition

Projects can define a JSON generation structure that specifies:
- Which task data fields to include (`$variable` syntax)
- Fields to explicitly exclude
- Output format expectations
- Custom instructions

Example generation structure:
```json
{
  "task_format": "question_answer_reasoning",
  "fields": {
    "question": "$question",
    "context": "$context"
  },
  "exclude_fields": ["reference_answer", "annotations"],
  "output_structure": {
    "answer": "string",
    "reasoning": "string",
    "confidence": "high|medium|low"
  },
  "instructions": "Answer the question based on the provided context."
}
```

### 2. Field Filtering Process

The `GenerationStructureParser` class:
1. Parses the generation structure JSON
2. Extracts field mappings using the `$variable` syntax (same as label_config)
3. Filters task data to only include explicitly mapped fields
4. Automatically excludes sensitive fields:
   - `annotations`
   - `reference_answer`
   - `ground_truth`
   - `correct_answer`
   - `expected_output`
   - `label`/`labels`
   - `gold_standard`

### 3. Safe Prompt Generation

When generating prompts for LLMs:
1. Only filtered data is available for interpolation
2. Sensitive fields are never included, even if explicitly requested
3. Nested sensitive data is detected and excluded
4. Field names are validated against security patterns

## Feature Flag Control

The feature is controlled by the existing `generation` feature flag (no separate flag needed):

1. **Enable the feature**:
   - Navigate to `/admin/feature-flags`
   - Find "generation"
   - Toggle to enable

2. **Default state**: Controlled by generation flag state

3. **When disabled**: Original interpolation behavior is used

## Configuration Guide

### Setting Up Generation Structure

1. **Navigate to your project settings**
2. **Open the Generation Structure editor**
3. **Define your structure** using the provided templates or create custom:

```json
{
  "task_format": "your_task_type",
  "fields": {
    "field_name": "$task_data_field"
  },
  "exclude_fields": ["additional_fields_to_exclude"],
  "instructions": "Custom instructions for the LLM"
}
```

### Field Mapping Syntax

- Use `$variable` to reference task data fields
- Field names must be alphanumeric with underscores only
- Invalid characters in field names are rejected for security

### Examples

#### Question-Answer Task
```json
{
  "task_format": "question_answer",
  "fields": {
    "question": "$question",
    "context": "$context"
  },
  "output_structure": {
    "answer": "string"
  }
}
```

#### Classification Task
```json
{
  "task_format": "classification",
  "fields": {
    "text": "$text"
  },
  "output_structure": {
    "label": "string",
    "reasoning": "string"
  },
  "categories": ["relevant", "not_relevant"]
}
```

## Security Considerations

### Automatic Protections

1. **Sensitive field filtering**: Known sensitive field names are always excluded
2. **Nested data scanning**: Detects sensitive data in nested structures
3. **Field name validation**: Prevents injection attacks via field names
4. **Whitelist approach**: Only explicitly mapped fields are included

### Manual Exclusions

You can add additional fields to exclude using the `exclude_fields` array in your generation structure.

## Backward Compatibility

- **Feature flag disabled**: Original behavior maintained
- **No generation structure defined**: Falls back to original interpolation
- **Existing projects**: Continue to work without modification
- **Migration path**: Enable feature flag and define generation structures as needed

## Testing

### Unit Tests
Located in: `/services/workers/tests/test_generation_structure_parser.py`

Tests cover:
- JSON parsing and validation
- Field extraction and mapping
- Sensitive data filtering
- Security validation
- Edge cases and error handling

### Integration Tests
Located in: `/services/workers/tests/test_generation_structure_integration.py`

Tests cover:
- Full generation pipeline with filtering
- Feature flag enable/disable behavior
- Backward compatibility
- Performance with large datasets

### Running Tests
```bash
cd services/workers
python -m pytest tests/test_generation_structure_parser.py -v
python -m pytest tests/test_generation_structure_integration.py -v
```

## Troubleshooting

### Generation structure not being applied

1. **Check feature flag**: Ensure `generation` is enabled
2. **Validate JSON**: Use the validation tool in the UI
3. **Check logs**: Look for parser errors in worker logs

### Fields not appearing in prompts

1. **Verify field exists**: Check that the field name matches exactly
2. **Check exclusion list**: Ensure field isn't in sensitive list
3. **Validate mapping**: Confirm `$variable` syntax is correct

### Performance issues

- The parser caches parsed structures for efficiency
- Large task data (>1000 fields) is handled efficiently
- Consider reducing the number of mapped fields if needed

## API Reference

### GenerationStructureParser

```python
from generation_structure_parser import GenerationStructureParser

parser = GenerationStructureParser()

# Parse and validate structure
structure = parser.parse_structure(json_string)

# Extract field mappings
mappings = parser.extract_field_mappings(structure)

# Filter task data
filtered_data = parser.filter_task_data(
    task_data=original_data,
    field_mappings=mappings,
    exclude_fields=["custom_exclusion"]
)

# Build prompt context
prompt = parser.build_prompt_context(
    filtered_data=filtered_data,
    structure=structure,
    instruction_prompt="Optional instruction"
)
```

## Migration from Unsafe Interpolation

1. **Enable generation feature flag** in `/admin/feature-flags`
2. **Define generation structures** for each project
3. **Test generation** with a few tasks first
4. **Monitor logs** for any filtering issues
5. **Gradually roll out** to all projects

## Related Documentation

- [Generation Implementation](./generation-implementation.md)
- [Task Formatting](../services/api/task_formatter.py)
- [Label Config Syntax](../services/frontend/src/components/projects/FieldMappingSettings.tsx)