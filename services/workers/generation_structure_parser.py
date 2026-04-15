"""
Generation Structure Parser with template interpolation and nested field support
Issue #519: Implement proper field mapping and template interpolation
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class GenerationStructureParser:
    """
    Parser for generation structure with:
    - Template interpolation using {{placeholder}} syntax
    - Nested field extraction with dot notation ($parent.child)
    - Support for complex prompt templates
    - Security validation to prevent answer leakage
    """

    # Pattern for valid field names (alphanumeric + underscore)
    FIELD_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    # Pattern for nested field paths (e.g., prompts.prompt_clean)
    NESTED_FIELD_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$')

    # Pattern for array access (e.g., items[0])
    ARRAY_ACCESS_PATTERN = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]$')

    # Pattern for $variable references with nested support
    VARIABLE_PATTERN = re.compile(
        r'\$([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*(?:\[\d+\])?)'
    )

    # Pattern for {{placeholder}} template variables
    TEMPLATE_PATTERN = re.compile(r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}')

    # Fields that should never be sent to LLMs
    SENSITIVE_FIELDS = {
        'annotations',
        'annotation',
        'reference_answer',
        'reference',
        'ground_truth',
        'correct_answer',
        'expected_output',
        'label',
        'labels',
        'gold_standard',
        'binary_solution',
        'reasoning',
        'answer',
        'solution',
    }

    def __init__(self):
        """Initialize the parser with caching for parsed structures"""
        self._cache: Dict[str, Dict[str, Any]] = {}

    def parse_structure(
        self, generation_structure: Optional[Union[str, dict]]
    ) -> Optional[Dict[str, Any]]:
        """
        Parse and validate generation structure.

        Args:
            generation_structure: JSON string or dict defining generation structure

        Returns:
            Parsed structure dict or None if invalid/empty
        """
        if not generation_structure:
            return None

        # Handle both string and dict inputs
        if isinstance(generation_structure, str):
            # Check cache for strings
            if generation_structure in self._cache:
                return self._cache[generation_structure]

            try:
                structure = json.loads(generation_structure)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in generation structure: {e}")
                return None
        else:
            structure = generation_structure

        # Validate structure
        if not isinstance(structure, dict):
            logger.warning("Generation structure must be a JSON object")
            return None

        # Cache if it was a string
        if isinstance(generation_structure, str):
            self._cache[generation_structure] = structure

        return structure

    def extract_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        Extract value from nested data using dot notation.

        Args:
            data: Data dictionary
            path: Dot notation path (e.g., "prompts.prompt_clean" or "items[0].name")

        Returns:
            Value at path or None if not found
        """
        if not data or not path:
            return None

        current = data

        # Split path by dots, but handle array notation
        parts = []
        current_part = []
        in_brackets = False

        for char in path:
            if char == '[':
                if current_part:
                    parts.append(''.join(current_part))
                    current_part = []
                in_brackets = True
                current_part.append(char)
            elif char == ']':
                current_part.append(char)
                parts.append(''.join(current_part))
                current_part = []
                in_brackets = False
            elif char == '.' and not in_brackets:
                if current_part:
                    parts.append(''.join(current_part))
                    current_part = []
            else:
                current_part.append(char)

        if current_part:
            parts.append(''.join(current_part))

        # Navigate through the path
        for part in parts:
            if current is None:
                return None

            # Check for array access
            if '[' in part and ']' in part:
                # Extract field name and index
                bracket_pos = part.index('[')
                field_name = part[:bracket_pos] if bracket_pos > 0 else None
                index_str = part[bracket_pos + 1 : -1]

                try:
                    index = int(index_str)

                    # If there's a field name, navigate to it first
                    if field_name:
                        if isinstance(current, dict) and field_name in current:
                            current = current[field_name]
                        else:
                            return None

                    # Now apply array index
                    if isinstance(current, list) and 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            else:
                # Regular field access
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None

        return current

    def extract_field_mappings(self, structure: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract field mappings from generation structure.

        Args:
            structure: Parsed generation structure

        Returns:
            Dict mapping placeholder names to field paths
        """
        mappings = {}

        # Handle both old format (fields object) and new format (prompt templates)
        if 'system_prompt' in structure:
            mappings.update(self._extract_prompt_mappings(structure.get('system_prompt')))

        if 'instruction_prompt' in structure:
            mappings.update(self._extract_prompt_mappings(structure.get('instruction_prompt')))

        if 'fields' in structure:
            # Legacy format support
            fields = structure['fields']
            if isinstance(fields, dict):
                for field_name, field_value in fields.items():
                    if isinstance(field_value, str) and field_value.startswith('$'):
                        mappings[field_name] = field_value[1:]

        return mappings

    def _extract_prompt_mappings(self, prompt_config: Union[str, dict]) -> Dict[str, str]:
        """
        Extract mappings from a prompt configuration.

        Args:
            prompt_config: Either a simple string like "$field" or a dict with template and fields

        Returns:
            Mappings dict
        """
        mappings = {}

        if isinstance(prompt_config, str):
            # Simple field reference like "$area"
            if prompt_config.startswith('$'):
                # Use the field name as both key and value
                field_name = prompt_config[1:]
                mappings[field_name] = field_name
        elif isinstance(prompt_config, dict):
            # Complex template format
            if 'fields' in prompt_config and isinstance(prompt_config['fields'], dict):
                for placeholder, field_ref in prompt_config['fields'].items():
                    if isinstance(field_ref, str) and field_ref.startswith('$'):
                        mappings[placeholder] = field_ref[1:]

        return mappings

    def interpolate_template(
        self, template: str, placeholders: Dict[str, Any], allow_missing: bool = False
    ) -> str:
        """
        Interpolate {{placeholder}} variables in template with values.

        Args:
            template: Template string with {{placeholder}} syntax
            placeholders: Dict of placeholder names to values
            allow_missing: If True, leave missing placeholders as-is

        Returns:
            Interpolated string
        """
        result = template

        # Find all {{placeholder}} references
        matches = self.TEMPLATE_PATTERN.findall(template)

        for placeholder in matches:
            if placeholder in placeholders:
                value = placeholders[placeholder]

                # Convert value to string
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value, ensure_ascii=False, indent=2)
                elif value is None:
                    value_str = ""
                else:
                    value_str = str(value)

                # Replace {{placeholder}} with value
                result = result.replace(f"{{{{{placeholder}}}}}", value_str)
            elif not allow_missing:
                logger.warning(f"Placeholder {{{{{placeholder}}}}} not found in data")

        return result

    def filter_task_data(
        self,
        task_data: Dict[str, Any],
        field_mappings: Dict[str, str],
        exclude_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Filter task data to only include explicitly mapped fields.

        Args:
            task_data: Original task data containing all fields
            field_mappings: Mappings from placeholder names to field paths
            exclude_fields: Additional fields to exclude

        Returns:
            Filtered data with placeholder names as keys
        """
        filtered_data = {}

        # Combine sensitive fields with custom exclusions
        excluded = set(self.SENSITIVE_FIELDS)
        if exclude_fields:
            excluded.update(exclude_fields)

        # Extract mapped fields
        for placeholder, field_path in field_mappings.items():
            # Check if any part of the path is sensitive
            path_parts = field_path.split('.')
            if any(part.lower() in excluded for part in path_parts):
                logger.warning(f"Skipping sensitive field: {field_path}")
                continue

            # Extract value using nested path
            value = self.extract_nested_value(task_data, field_path)

            if value is not None:
                # Additional safety check for nested sensitive data
                if self._contains_sensitive_data(value):
                    logger.warning(f"Field {field_path} contains sensitive nested data, skipping")
                    continue

                filtered_data[placeholder] = value
            else:
                logger.debug(f"Field {field_path} not found in task data")

        return filtered_data

    def _contains_sensitive_data(self, value: Any) -> bool:
        """
        Check if a value contains sensitive nested data.

        Args:
            value: Value to check

        Returns:
            True if sensitive data detected
        """
        if isinstance(value, dict):
            for key in value.keys():
                if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                    return True
        elif isinstance(value, list) and value:
            for item in value:
                if isinstance(item, dict) and self._contains_sensitive_data(item):
                    return True

        return False

    def build_prompts(self, task_data: Dict[str, Any], structure: Dict[str, Any]) -> Dict[str, str]:
        """
        Build system and instruction prompts from task data and structure.

        Args:
            task_data: Original task data
            structure: Generation structure configuration

        Returns:
            Dict with 'system_prompt' and 'instruction_prompt' keys
        """
        prompts = {}

        # Process system prompt
        if 'system_prompt' in structure:
            prompts['system_prompt'] = self._build_single_prompt(
                task_data, structure['system_prompt']
            )

        # Process instruction prompt
        if 'instruction_prompt' in structure:
            prompts['instruction_prompt'] = self._build_single_prompt(
                task_data, structure['instruction_prompt']
            )

        # Add context fields if specified
        if 'context_fields' in structure:
            context_parts = []
            for field_ref in structure['context_fields']:
                if isinstance(field_ref, str) and field_ref.startswith('$'):
                    field_path = field_ref[1:]
                    value = self.extract_nested_value(task_data, field_path)
                    if value is not None:
                        context_parts.append(str(value))
            if context_parts:
                context = "\n\n".join(context_parts)
                if 'instruction_prompt' in prompts:
                    prompts['instruction_prompt'] += f"\n\nContext:\n{context}"
                else:
                    prompts['instruction_prompt'] = f"Context:\n{context}"

        return prompts

    def _build_single_prompt(
        self, task_data: Dict[str, Any], prompt_config: Union[str, dict]
    ) -> str:
        """
        Build a single prompt from configuration.

        Args:
            task_data: Task data
            prompt_config: Prompt configuration (simple string or template dict)

        Returns:
            Built prompt string
        """
        if isinstance(prompt_config, str):
            # Simple field reference
            if prompt_config.startswith('$'):
                field_path = prompt_config[1:]
                value = self.extract_nested_value(task_data, field_path)
                if value is not None:
                    if isinstance(value, (dict, list)):
                        return json.dumps(value, ensure_ascii=False, indent=2)
                    return str(value)
                return ""
            else:
                # Literal string
                return prompt_config

        elif isinstance(prompt_config, dict):
            # Template-based prompt
            template = prompt_config.get('template', '')
            fields = prompt_config.get('fields', {})

            # Extract field values
            placeholders = {}
            for placeholder, field_ref in fields.items():
                if isinstance(field_ref, str) and field_ref.startswith('$'):
                    field_path = field_ref[1:]
                    value = self.extract_nested_value(task_data, field_path)
                    if value is not None:
                        placeholders[placeholder] = value

            # Interpolate template
            return self.interpolate_template(template, placeholders)

        return ""

    def process_generation_structure(
        self,
        task_data: Dict[str, Any],
        generation_structure: Optional[Union[str, dict]],
        fallback_instruction: Optional[str] = None,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Complete processing of generation structure for a task.

        Args:
            task_data: Original task data
            generation_structure: Generation structure configuration
            fallback_instruction: Fallback instruction if no structure

        Returns:
            Tuple of (prompts_dict, filtered_data)
        """
        # Parse structure
        structure = self.parse_structure(generation_structure)
        if not structure:
            # Fallback: return basic prompts
            logger.debug("No valid generation structure, using fallback")
            prompts = {}
            if fallback_instruction:
                prompts['instruction_prompt'] = fallback_instruction
            return prompts, {}

        # Extract field mappings
        mappings = self.extract_field_mappings(structure)

        # Get additional exclude fields from structure
        exclude_fields = structure.get('exclude_fields', [])

        # Filter task data
        filtered_data = self.filter_task_data(task_data, mappings, exclude_fields)

        # Build prompts
        prompts = self.build_prompts(task_data, structure)

        # Add fallback instruction if no instruction prompt generated
        if 'instruction_prompt' not in prompts and fallback_instruction:
            prompts['instruction_prompt'] = fallback_instruction

        return prompts, filtered_data

    def validate_structure(
        self, generation_structure: Union[str, dict]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a generation structure configuration.

        Args:
            generation_structure: Structure to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        structure = self.parse_structure(generation_structure)
        if not structure:
            return False, "Failed to parse structure"

        try:
            # Check for at least one prompt definition
            has_prompts = any(
                key in structure for key in ['system_prompt', 'instruction_prompt', 'fields']
            )
            if not has_prompts:
                return False, "Structure must define at least one prompt"

            # Validate prompt configurations
            for prompt_key in ['system_prompt', 'instruction_prompt']:
                if prompt_key in structure:
                    prompt_config = structure[prompt_key]
                    if isinstance(prompt_config, dict):
                        if 'template' not in prompt_config:
                            return False, f"{prompt_key} dict must have 'template' field"
                        if 'fields' in prompt_config:
                            if not isinstance(prompt_config['fields'], dict):
                                return False, f"{prompt_key}.fields must be an object"
                    elif not isinstance(prompt_config, str):
                        return False, f"{prompt_key} must be string or object"

            # Check optional fields
            if 'exclude_fields' in structure:
                if not isinstance(structure['exclude_fields'], list):
                    return False, "'exclude_fields' must be an array"

            if 'parameters' in structure:
                if not isinstance(structure['parameters'], dict):
                    return False, "'parameters' must be an object"

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"
