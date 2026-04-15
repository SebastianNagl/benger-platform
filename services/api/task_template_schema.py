"""
Task Template Schema and Validation

Defines the structure and validation for the unified task configuration system.
These schemas enable declarative task definitions that work across task creation,
annotation, data display, LLM generation, and evaluation.

Issue #216: Implement Unified Task Configuration and Display System
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate
from pydantic import BaseModel, Field, field_validator


class FieldType(str, Enum):
    """Supported field types in the template system"""

    TEXT = "text"  # Single line text input
    TEXT_AREA = "text_area"  # Multi-line text input
    RADIO = "radio"  # Single choice selection
    CHECKBOX = "checkbox"  # Multiple choice selection
    RATING = "rating"  # Numeric rating/scale
    HIGHLIGHT = "highlight"  # Text highlighting/annotation
    RICH_TEXT = "rich_text"  # Formatted text editor
    FILE_UPLOAD = "file_upload"  # File attachments
    NUMBER = "number"  # Numeric input
    DATE = "date"  # Date picker
    EMAIL = "email"  # Email input
    URL = "url"  # URL input


class FieldSource(str, Enum):
    """Source of field data"""

    TASK_DATA = "task_data"  # From task data (questions, etc.)
    ANNOTATION = "annotation"  # From user annotations
    GENERATED = "generated"  # From LLM generation
    COMPUTED = "computed"  # Computed from other fields


class DisplayMode(str, Enum):
    """Display modes for fields in different contexts"""

    READONLY = "readonly"
    EDITABLE = "editable"
    HIDDEN = "hidden"
    COLUMN = "column"
    IN_ANSWER_CELL = "in_answer_cell"
    REFERENCE = "reference"


class ValidationRuleType(str, Enum):
    """Types of validation rules"""

    REQUIRED = "required"
    MIN_LENGTH = "minLength"
    MAX_LENGTH = "maxLength"
    MIN = "min"
    MAX = "max"
    PATTERN = "pattern"
    CUSTOM = "custom"


class ConditionType(str, Enum):
    """Types of field conditions"""

    EXISTS = "exists"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    CUSTOM = "custom"


class ValidationRule(BaseModel):
    """Validation rule for a field"""

    type: ValidationRuleType
    value: Optional[Any] = None
    message: Optional[str] = None
    custom_validator: Optional[str] = Field(None, description="Function name for custom validation")


class FieldDisplay(BaseModel):
    """Display configuration for a field in different contexts"""

    annotation: DisplayMode
    table: DisplayMode
    creation: DisplayMode
    review: Optional[DisplayMode] = None


class FieldCondition(BaseModel):
    """Condition for showing/hiding a field"""

    type: ConditionType
    field: Optional[str] = None
    value: Optional[Any] = None
    custom_condition: Optional[str] = Field(None, description="Function name for custom conditions")


class TaskTemplateField(BaseModel):
    """Definition of a single field in a task template"""

    name: str
    type: FieldType
    display: FieldDisplay
    source: FieldSource
    required: bool = False
    label: Optional[str] = None
    description: Optional[str] = None
    placeholder: Optional[str] = None
    default_value: Optional[Any] = Field(None, alias="defaultValue")
    choices: Optional[List[str]] = Field(None, description="For radio/checkbox fields")
    validation: Optional[List[ValidationRule]] = None
    condition: Optional[Union[FieldCondition, str]] = Field(
        None, description="'exists' shorthand or full condition"
    )
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("label")
    @classmethod
    def set_label(cls, v, info):
        """Auto-generate label from name if not provided"""
        if v is None and hasattr(info, "data") and "name" in info.data:
            return info.data["name"].replace("_", " ").title()
        return v

    @field_validator("choices")
    @classmethod
    def validate_choices(cls, v, info):
        """Ensure choices are provided for choice fields"""
        if hasattr(info, "data"):
            field_type = info.data.get("type")
            if field_type in [FieldType.RADIO, FieldType.CHECKBOX]:
                # Check if dynamic choices are enabled
                metadata = info.data.get("metadata", {})
                if metadata.get("dynamic_choices", False):
                    # Allow empty choices for dynamic choice fields
                    return v or []
                elif not v or len(v) == 0:
                    raise ValueError(f"Choices must be provided for {field_type} fields")
        return v


class AnswerDisplay(BaseModel):
    """Configuration for answer display in tables"""

    fields: List[str]
    separator: Literal["divider", "space", "newline"] = "divider"


class DisplayConfig(BaseModel):
    """Display configuration for the template"""

    table_columns: List[str] = Field(..., description="Field names to show as table columns")
    answer_display: Optional[AnswerDisplay] = None
    grouping: Optional[Dict[str, List[str]]] = Field(None, description="Group fields together")
    column_widths: Optional[Dict[str, int]] = Field(None, description="Custom column widths")


class LLMConfig(BaseModel):
    """LLM generation configuration"""

    prompt_template: str = Field(..., description="Template string with {{field}} placeholders")
    response_parser: str = Field(..., description="Parser function name")
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)
    response_format: Optional[Literal["json", "text", "structured"]] = "text"
    field_mapping: Optional[Dict[str, str]] = Field(
        None, description="Map LLM response fields to template fields"
    )


class EvaluationMetric(BaseModel):
    """Definition of an evaluation metric"""

    name: str
    type: Literal["accuracy", "f1", "bleu", "rouge", "exact_match", "reasoning_quality", "custom"]
    config: Optional[Dict[str, Any]] = None
    weight: Optional[float] = Field(1.0, ge=0.0)


class EvaluationConfig(BaseModel):
    """Evaluation configuration for the template"""

    metrics: List[EvaluationMetric]
    requires_reference: bool = True
    custom_evaluator: Optional[str] = Field(None, description="Function name for custom evaluation")
    threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum score threshold")


class TemplateMetadata(BaseModel):
    """Metadata for the template"""

    author: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: Optional[List[str]] = None
    compatible_models: Optional[List[str]] = None


class TaskTemplate(BaseModel):
    """Complete task template definition"""

    id: str
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    category: Optional[str] = Field(
        None, description="e.g., 'qa', 'classification', 'generation', 'custom'"
    )
    fields: List[TaskTemplateField]
    display_config: DisplayConfig
    llm_config: Optional[LLMConfig] = None
    evaluation_config: Optional[EvaluationConfig] = None
    metadata: Optional[TemplateMetadata] = None
    validation_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON Schema for additional validation"
    )

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, v):
        """Ensure field names are unique"""
        names = [field.name for field in v]
        if len(names) != len(set(names)):
            raise ValueError("Field names must be unique")
        return v

    @field_validator("display_config")
    @classmethod
    def validate_display_config(cls, v, info):
        """Ensure display columns reference existing fields"""
        if hasattr(info, "data") and "fields" in info.data:
            field_names = {field.name for field in info.data["fields"]}
            for column in v.table_columns:
                if column not in field_names:
                    raise ValueError(f"Display column '{column}' not found in fields")

            if v.answer_display:
                for field in v.answer_display.fields:
                    if field not in field_names:
                        raise ValueError(f"Answer display field '{field}' not found in fields")
        return v

    def validate_instance(self, data: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate data against this template"""
        errors = {}

        # Check required fields
        for field in self.fields:
            if field.required and field.name not in data:
                errors.setdefault(field.name, []).append(f"{field.label or field.name} is required")

            # Validate field values
            if field.name in data and field.validation:
                value = data[field.name]
                for rule in field.validation:
                    error_msg = self._validate_rule(field, value, rule)
                    if error_msg:
                        errors.setdefault(field.name, []).append(error_msg)

        # Apply JSON schema validation if provided
        if self.validation_schema:
            try:
                validate(instance=data, schema=self.validation_schema)
            except JsonSchemaValidationError as e:
                errors.setdefault("_schema", []).append(str(e))

        return errors

    def _validate_rule(
        self, field: TaskTemplateField, value: Any, rule: ValidationRule
    ) -> Optional[str]:
        """Validate a single rule against a value"""
        if rule.type == ValidationRuleType.MIN_LENGTH:
            if isinstance(value, str) and len(value) < rule.value:
                return (
                    rule.message
                    or f"{field.label or field.name} must be at least {rule.value} characters"
                )

        elif rule.type == ValidationRuleType.MAX_LENGTH:
            if isinstance(value, str) and len(value) > rule.value:
                return (
                    rule.message
                    or f"{field.label or field.name} must be at most {rule.value} characters"
                )

        elif rule.type == ValidationRuleType.MIN:
            if isinstance(value, (int, float)) and value < rule.value:
                return rule.message or f"{field.label or field.name} must be at least {rule.value}"

        elif rule.type == ValidationRuleType.MAX:
            if isinstance(value, (int, float)) and value > rule.value:
                return rule.message or f"{field.label or field.name} must be at most {rule.value}"

        elif rule.type == ValidationRuleType.PATTERN:
            if isinstance(value, str):
                import re

                if not re.match(rule.value, value):
                    return rule.message or f"{field.label or field.name} format is invalid"

        return None

    def generate_json_schema(self) -> Dict[str, Any]:
        """Generate JSON Schema from template fields"""
        properties = {}
        required = []

        for field in self.fields:
            prop = {"title": field.label or field.name}

            if field.description:
                prop["description"] = field.description

            # Map field types to JSON Schema types
            if field.type in [
                FieldType.TEXT,
                FieldType.TEXT_AREA,
                FieldType.RICH_TEXT,
                FieldType.EMAIL,
                FieldType.URL,
            ]:
                prop["type"] = "string"
            elif field.type in [FieldType.NUMBER, FieldType.RATING]:
                prop["type"] = "number"
            elif field.type == FieldType.CHECKBOX:
                prop["type"] = "array"
                prop["items"] = {"type": "string", "enum": field.choices or []}
            elif field.type == FieldType.RADIO:
                prop["type"] = "string"
                prop["enum"] = field.choices or []
            elif field.type == FieldType.DATE:
                prop["type"] = "string"
                prop["format"] = "date"

            # Add validation constraints
            if field.validation:
                for rule in field.validation:
                    if rule.type == ValidationRuleType.MIN_LENGTH:
                        prop["minLength"] = rule.value
                    elif rule.type == ValidationRuleType.MAX_LENGTH:
                        prop["maxLength"] = rule.value
                    elif rule.type == ValidationRuleType.MIN:
                        prop["minimum"] = rule.value
                    elif rule.type == ValidationRuleType.MAX:
                        prop["maximum"] = rule.value
                    elif rule.type == ValidationRuleType.PATTERN:
                        prop["pattern"] = rule.value

            properties[field.name] = prop

            if field.required:
                required.append(field.name)

        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": self.name,
            "description": self.description,
            "properties": properties,
            "required": required,
        }


# Template validation helper
def validate_template(template_data: Dict[str, Any]) -> TaskTemplate:
    """Validate and parse template data"""
    try:
        return TaskTemplate(**template_data)
    except Exception as e:
        raise ValueError(f"Invalid template: {str(e)}")


# Field type helpers
def is_text_field(field_type: FieldType) -> bool:
    """Check if field type is text-based"""
    return field_type in [FieldType.TEXT, FieldType.TEXT_AREA, FieldType.RICH_TEXT]


def is_choice_field(field_type: FieldType) -> bool:
    """Check if field type is choice-based"""
    return field_type in [FieldType.RADIO, FieldType.CHECKBOX]


def is_numeric_field(field_type: FieldType) -> bool:
    """Check if field type is numeric"""
    return field_type in [FieldType.NUMBER, FieldType.RATING]
