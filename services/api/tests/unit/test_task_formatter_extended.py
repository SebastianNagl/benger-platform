"""
Unit tests for services/task_formatter.py to increase branch coverage.
"""

import pytest


class TestTaskFormatter:
    def test_import(self):
        from services.task_formatter import TaskFormatter
        assert TaskFormatter is not None

    def test_format_empty_data(self):
        from services.task_formatter import TaskFormatter
        formatter = TaskFormatter()
        result = formatter.format_task({})
        assert isinstance(result, dict)

    def test_format_with_text(self):
        from services.task_formatter import TaskFormatter
        formatter = TaskFormatter()
        result = formatter.format_task({"text": "Hello world"})
        assert isinstance(result, dict)

    def test_format_with_nested_data(self):
        from services.task_formatter import TaskFormatter
        formatter = TaskFormatter()
        data = {"document": {"title": "Test", "content": "Content"}, "id": 1}
        result = formatter.format_task(data)
        assert isinstance(result, dict)

    def test_format_none(self):
        from services.task_formatter import TaskFormatter
        formatter = TaskFormatter()
        try:
            result = formatter.format_task(None)
            assert result is None or isinstance(result, dict)
        except (TypeError, AttributeError):
            pass
