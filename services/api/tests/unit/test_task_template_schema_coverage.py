"""
Unit tests for task_template_schema.py to increase coverage.
Covers enums and helper functions.
"""

import pytest

from task_template_schema import (
    FieldType,
    FieldSource,
    DisplayMode,
    is_choice_field,
    is_numeric_field,
    is_text_field,
    ValidationRuleType,
    ConditionType,
)


class TestFieldType:
    def test_all_values(self):
        assert FieldType.TEXT == "text"
        assert FieldType.TEXT_AREA == "text_area"
        assert FieldType.RADIO == "radio"
        assert FieldType.CHECKBOX == "checkbox"
        assert FieldType.RATING == "rating"
        assert FieldType.HIGHLIGHT == "highlight"
        assert FieldType.RICH_TEXT == "rich_text"
        assert FieldType.FILE_UPLOAD == "file_upload"
        assert FieldType.NUMBER == "number"
        assert FieldType.DATE == "date"
        assert FieldType.EMAIL == "email"
        assert FieldType.URL == "url"

    def test_count(self):
        assert len(FieldType) == 12


class TestFieldSource:
    def test_all_values(self):
        assert FieldSource.TASK_DATA == "task_data"
        assert FieldSource.ANNOTATION == "annotation"
        assert FieldSource.GENERATED == "generated"
        assert FieldSource.COMPUTED == "computed"

    def test_count(self):
        assert len(FieldSource) == 4


class TestDisplayMode:
    def test_all_values(self):
        assert DisplayMode.READONLY == "readonly"
        assert DisplayMode.EDITABLE == "editable"


class TestValidationRuleType:
    def test_values(self):
        assert ValidationRuleType.REQUIRED == "required"
        assert ValidationRuleType.MIN_LENGTH == "minLength"
        assert ValidationRuleType.MAX_LENGTH == "maxLength"
        assert ValidationRuleType.MIN == "min"
        assert ValidationRuleType.MAX == "max"
        assert ValidationRuleType.PATTERN == "pattern"
        assert ValidationRuleType.CUSTOM == "custom"


class TestConditionType:
    def test_values(self):
        assert ConditionType.EQUALS == "equals"
        assert ConditionType.NOT_EQUALS == "not_equals"


class TestHelperFunctions:
    def test_is_choice_field_true(self):
        assert is_choice_field(FieldType.RADIO) is True
        assert is_choice_field(FieldType.CHECKBOX) is True

    def test_is_choice_field_false(self):
        assert is_choice_field(FieldType.TEXT) is False
        assert is_choice_field(FieldType.NUMBER) is False
        assert is_choice_field(FieldType.RATING) is False
        assert is_choice_field(FieldType.HIGHLIGHT) is False

    def test_is_numeric_field_true(self):
        assert is_numeric_field(FieldType.NUMBER) is True
        assert is_numeric_field(FieldType.RATING) is True

    def test_is_numeric_field_false(self):
        assert is_numeric_field(FieldType.TEXT) is False
        assert is_numeric_field(FieldType.RADIO) is False
        assert is_numeric_field(FieldType.CHECKBOX) is False

    def test_is_text_field_true(self):
        assert is_text_field(FieldType.TEXT) is True
        assert is_text_field(FieldType.TEXT_AREA) is True
        assert is_text_field(FieldType.RICH_TEXT) is True

    def test_is_text_field_false(self):
        assert is_text_field(FieldType.NUMBER) is False
        assert is_text_field(FieldType.RADIO) is False
        assert is_text_field(FieldType.RATING) is False
        assert is_text_field(FieldType.DATE) is False
        assert is_text_field(FieldType.HIGHLIGHT) is False
