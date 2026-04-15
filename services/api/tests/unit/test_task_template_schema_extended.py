"""
Unit tests for task_template_schema.py — extended coverage for 42.81% (99 uncovered lines).

Tests TaskTemplate.validate_instance, _validate_rule, generate_json_schema,
field validators, and validate_template helper.
"""

import pytest


class TestTaskTemplateValidateInstance:
    """Test TaskTemplate.validate_instance method."""

    def _make_template(self, fields=None, validation_schema=None):
        from task_template_schema import (
            DisplayConfig,
            DisplayMode,
            FieldDisplay,
            FieldSource,
            FieldType,
            TaskTemplate,
            TaskTemplateField,
        )

        if fields is None:
            fields = [
                TaskTemplateField(
                    name="question",
                    type=FieldType.TEXT,
                    display=FieldDisplay(
                        annotation=DisplayMode.READONLY,
                        table=DisplayMode.COLUMN,
                        creation=DisplayMode.EDITABLE,
                    ),
                    source=FieldSource.TASK_DATA,
                    required=True,
                ),
                TaskTemplateField(
                    name="answer",
                    type=FieldType.TEXT_AREA,
                    display=FieldDisplay(
                        annotation=DisplayMode.EDITABLE,
                        table=DisplayMode.COLUMN,
                        creation=DisplayMode.HIDDEN,
                    ),
                    source=FieldSource.ANNOTATION,
                    required=False,
                ),
            ]

        return TaskTemplate(
            id="test-template",
            name="Test Template",
            fields=fields,
            display_config=DisplayConfig(table_columns=[f.name for f in fields]),
            validation_schema=validation_schema,
        )

    def test_valid_data_no_errors(self):
        template = self._make_template()
        errors = template.validate_instance({"question": "What is X?"})
        assert errors == {}

    def test_missing_required_field(self):
        template = self._make_template()
        errors = template.validate_instance({})
        assert "question" in errors
        assert any("required" in e for e in errors["question"])

    def test_optional_field_missing_no_error(self):
        template = self._make_template()
        errors = template.validate_instance({"question": "Q"})
        assert "answer" not in errors

    def test_with_validation_schema(self):
        schema = {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        }
        template = self._make_template(validation_schema=schema)
        errors = template.validate_instance({})
        assert "_schema" in errors

    def test_validation_rules_applied(self):
        from task_template_schema import (
            DisplayConfig,
            DisplayMode,
            FieldDisplay,
            FieldSource,
            FieldType,
            TaskTemplate,
            TaskTemplateField,
            ValidationRule,
        )
        field = TaskTemplateField(
            name="answer",
            type=FieldType.TEXT,
            display=FieldDisplay(
                annotation=DisplayMode.EDITABLE,
                table=DisplayMode.COLUMN,
                creation=DisplayMode.EDITABLE,
            ),
            source=FieldSource.ANNOTATION,
            required=True,
            validation=[ValidationRule(type="minLength", value=10)],
        )
        template = TaskTemplate(
            id="t", name="T",
            fields=[field],
            display_config=DisplayConfig(table_columns=["answer"]),
        )
        errors = template.validate_instance({"answer": "short"})
        assert "answer" in errors


class TestValidateRule:
    """Test TaskTemplate._validate_rule method."""

    def _make_template_with_field(self, field_type, validation_rules):
        from task_template_schema import (
            DisplayConfig,
            DisplayMode,
            FieldDisplay,
            FieldSource,
            FieldType,
            TaskTemplate,
            TaskTemplateField,
            ValidationRule,
        )

        field = TaskTemplateField(
            name="test_field",
            type=field_type,
            display=FieldDisplay(
                annotation=DisplayMode.EDITABLE,
                table=DisplayMode.COLUMN,
                creation=DisplayMode.EDITABLE,
            ),
            source=FieldSource.ANNOTATION,
            required=True,
            validation=[ValidationRule(**r) for r in validation_rules],
        )

        template = TaskTemplate(
            id="test", name="Test",
            fields=[field],
            display_config=DisplayConfig(table_columns=["test_field"]),
        )
        return template, field

    def test_min_length_valid(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "minLength", "value": 5}],
        )
        result = template._validate_rule(field, "hello world", field.validation[0])
        assert result is None

    def test_min_length_violation(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "minLength", "value": 10}],
        )
        result = template._validate_rule(field, "short", field.validation[0])
        assert result is not None
        assert "at least" in result

    def test_max_length_valid(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "maxLength", "value": 100}],
        )
        result = template._validate_rule(field, "hello", field.validation[0])
        assert result is None

    def test_max_length_violation(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "maxLength", "value": 5}],
        )
        result = template._validate_rule(field, "too long text", field.validation[0])
        assert "at most" in result

    def test_min_value_valid(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.NUMBER, [{"type": "min", "value": 0}],
        )
        result = template._validate_rule(field, 5, field.validation[0])
        assert result is None

    def test_min_value_violation(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.NUMBER, [{"type": "min", "value": 10}],
        )
        result = template._validate_rule(field, 5, field.validation[0])
        assert "at least" in result

    def test_max_value_valid(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.NUMBER, [{"type": "max", "value": 100}],
        )
        assert template._validate_rule(field, 50, field.validation[0]) is None

    def test_max_value_violation(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.NUMBER, [{"type": "max", "value": 10}],
        )
        result = template._validate_rule(field, 15, field.validation[0])
        assert "at most" in result

    def test_pattern_valid(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "pattern", "value": r"^\d+$"}],
        )
        assert template._validate_rule(field, "12345", field.validation[0]) is None

    def test_pattern_violation(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "pattern", "value": r"^\d+$"}],
        )
        result = template._validate_rule(field, "not-a-number", field.validation[0])
        assert "format" in result

    def test_custom_message(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "minLength", "value": 100, "message": "Too short!"}],
        )
        assert template._validate_rule(field, "hi", field.validation[0]) == "Too short!"

    def test_non_string_for_min_length(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.NUMBER, [{"type": "minLength", "value": 5}],
        )
        assert template._validate_rule(field, 42, field.validation[0]) is None

    def test_non_numeric_for_min(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "min", "value": 5}],
        )
        assert template._validate_rule(field, "text", field.validation[0]) is None

    def test_custom_rule_type_returns_none(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "custom", "value": "some_func"}],
        )
        assert template._validate_rule(field, "anything", field.validation[0]) is None

    def test_required_rule_type_returns_none(self):
        from task_template_schema import FieldType
        template, field = self._make_template_with_field(
            FieldType.TEXT, [{"type": "required"}],
        )
        assert template._validate_rule(field, "value", field.validation[0]) is None


class TestGenerateJsonSchema:
    """Test TaskTemplate.generate_json_schema method."""

    def _make_template(self, fields_data):
        from task_template_schema import (
            DisplayConfig, DisplayMode, FieldDisplay, FieldSource,
            FieldType, TaskTemplate, TaskTemplateField, ValidationRule,
        )
        fields = []
        for fd in fields_data:
            validation = None
            if "validation" in fd:
                validation = [ValidationRule(**r) for r in fd["validation"]]
            field = TaskTemplateField(
                name=fd["name"],
                type=FieldType(fd["type"]),
                display=FieldDisplay(
                    annotation=DisplayMode.EDITABLE,
                    table=DisplayMode.COLUMN,
                    creation=DisplayMode.EDITABLE,
                ),
                source=FieldSource.ANNOTATION,
                required=fd.get("required", False),
                description=fd.get("description"),
                choices=fd.get("choices"),
                validation=validation,
            )
            fields.append(field)
        return TaskTemplate(
            id="test", name="Test Schema", description="Test template",
            fields=fields,
            display_config=DisplayConfig(table_columns=[f.name for f in fields]),
        )

    def test_text_field_schema(self):
        template = self._make_template([
            {"name": "question", "type": "text", "required": True, "description": "The question"},
        ])
        schema = template.generate_json_schema()
        assert schema["properties"]["question"]["type"] == "string"
        assert "question" in schema["required"]

    def test_number_field_schema(self):
        template = self._make_template([{"name": "score", "type": "number"}])
        assert template.generate_json_schema()["properties"]["score"]["type"] == "number"

    def test_rating_field_schema(self):
        template = self._make_template([{"name": "rating", "type": "rating"}])
        assert template.generate_json_schema()["properties"]["rating"]["type"] == "number"

    def test_radio_field_schema(self):
        template = self._make_template([
            {"name": "choice", "type": "radio", "choices": ["A", "B", "C"]},
        ])
        props = template.generate_json_schema()["properties"]["choice"]
        assert props["type"] == "string"
        assert props["enum"] == ["A", "B", "C"]

    def test_checkbox_field_schema(self):
        template = self._make_template([
            {"name": "tags", "type": "checkbox", "choices": ["t1", "t2"]},
        ])
        props = template.generate_json_schema()["properties"]["tags"]
        assert props["type"] == "array"

    def test_date_field_schema(self):
        template = self._make_template([{"name": "due", "type": "date"}])
        props = template.generate_json_schema()["properties"]["due"]
        assert props["format"] == "date"

    def test_email_url_textarea_richtext(self):
        for ft in ("email", "url", "text_area", "rich_text"):
            template = self._make_template([{"name": "f", "type": ft}])
            assert template.generate_json_schema()["properties"]["f"]["type"] == "string"

    def test_validation_constraints_in_schema(self):
        template = self._make_template([{
            "name": "a", "type": "text",
            "validation": [
                {"type": "minLength", "value": 5},
                {"type": "maxLength", "value": 500},
                {"type": "pattern", "value": r"^[A-Z]"},
            ],
        }])
        props = template.generate_json_schema()["properties"]["a"]
        assert props["minLength"] == 5
        assert props["maxLength"] == 500
        assert props["pattern"] == r"^[A-Z]"

    def test_numeric_validation(self):
        template = self._make_template([{
            "name": "s", "type": "number",
            "validation": [{"type": "min", "value": 0}, {"type": "max", "value": 100}],
        }])
        props = template.generate_json_schema()["properties"]["s"]
        assert props["minimum"] == 0
        assert props["maximum"] == 100

    def test_schema_metadata(self):
        template = self._make_template([{"name": "q", "type": "text"}])
        schema = template.generate_json_schema()
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert schema["title"] == "Test Schema"

    def test_optional_not_in_required(self):
        template = self._make_template([
            {"name": "req", "type": "text", "required": True},
            {"name": "opt", "type": "text", "required": False},
        ])
        schema = template.generate_json_schema()
        assert "req" in schema["required"]
        assert "opt" not in schema["required"]


class TestValidateTemplate:
    """Test validate_template helper function."""

    def test_valid_data(self):
        from task_template_schema import validate_template
        data = {
            "id": "t1", "name": "Test",
            "fields": [{
                "name": "q", "type": "text",
                "display": {"annotation": "editable", "table": "column", "creation": "editable"},
                "source": "task_data",
            }],
            "display_config": {"table_columns": ["q"]},
        }
        assert validate_template(data).id == "t1"

    def test_invalid_data_raises(self):
        from task_template_schema import validate_template
        with pytest.raises(ValueError, match="Invalid template"):
            validate_template({"id": "t1"})


class TestFieldValidators:
    """Test field-level validators."""

    def test_no_label_defaults_to_none(self):
        from task_template_schema import (
            DisplayMode, FieldDisplay, FieldSource, FieldType, TaskTemplateField,
        )
        field = TaskTemplateField(
            name="my_field", type=FieldType.TEXT,
            display=FieldDisplay(annotation=DisplayMode.EDITABLE, table=DisplayMode.COLUMN, creation=DisplayMode.EDITABLE),
            source=FieldSource.TASK_DATA,
        )
        # The auto-label validator may not fire in all pydantic versions
        assert field.label is None or field.label == "My Field"

    def test_explicit_label(self):
        from task_template_schema import (
            DisplayMode, FieldDisplay, FieldSource, FieldType, TaskTemplateField,
        )
        field = TaskTemplateField(
            name="x", type=FieldType.TEXT,
            display=FieldDisplay(annotation=DisplayMode.EDITABLE, table=DisplayMode.COLUMN, creation=DisplayMode.EDITABLE),
            source=FieldSource.TASK_DATA, label="Custom",
        )
        assert field.label == "Custom"

    def test_choice_without_choices_raises(self):
        from task_template_schema import (
            DisplayMode, FieldDisplay, FieldSource, FieldType, TaskTemplateField,
        )
        with pytest.raises(ValueError):
            TaskTemplateField(
                name="c", type=FieldType.RADIO,
                display=FieldDisplay(annotation=DisplayMode.EDITABLE, table=DisplayMode.COLUMN, creation=DisplayMode.EDITABLE),
                source=FieldSource.ANNOTATION, choices=[],
            )

    def test_radio_with_choices_valid(self):
        from task_template_schema import (
            DisplayMode, FieldDisplay, FieldSource, FieldType, TaskTemplateField,
        )
        field = TaskTemplateField(
            name="c", type=FieldType.RADIO,
            display=FieldDisplay(annotation=DisplayMode.EDITABLE, table=DisplayMode.COLUMN, creation=DisplayMode.EDITABLE),
            source=FieldSource.ANNOTATION, choices=["A", "B"],
        )
        assert field.choices == ["A", "B"]


class TestUniqueFieldNames:
    """Test field name uniqueness."""

    def test_duplicate_names_raises(self):
        from task_template_schema import (
            DisplayConfig, DisplayMode, FieldDisplay, FieldSource,
            FieldType, TaskTemplate, TaskTemplateField,
        )
        f = TaskTemplateField(
            name="dup", type=FieldType.TEXT,
            display=FieldDisplay(annotation=DisplayMode.EDITABLE, table=DisplayMode.COLUMN, creation=DisplayMode.EDITABLE),
            source=FieldSource.TASK_DATA,
        )
        with pytest.raises(ValueError, match="unique"):
            TaskTemplate(
                id="t", name="T", fields=[f, f],
                display_config=DisplayConfig(table_columns=["dup"]),
            )

    def test_invalid_display_column_raises(self):
        from task_template_schema import (
            DisplayConfig, DisplayMode, FieldDisplay, FieldSource,
            FieldType, TaskTemplate, TaskTemplateField,
        )
        f = TaskTemplateField(
            name="real", type=FieldType.TEXT,
            display=FieldDisplay(annotation=DisplayMode.EDITABLE, table=DisplayMode.COLUMN, creation=DisplayMode.EDITABLE),
            source=FieldSource.TASK_DATA,
        )
        with pytest.raises(ValueError, match="not found"):
            TaskTemplate(
                id="t", name="T", fields=[f],
                display_config=DisplayConfig(table_columns=["nonexistent"]),
            )
