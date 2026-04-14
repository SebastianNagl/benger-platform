"""
Unit tests for TaskFormatter service
Issue #482: Test task formatting for consistent presentation
"""


from task_formatter import TaskFormatter


class TestTaskFormatter:
    """Test suite for TaskFormatter service"""

    def test_format_task_with_auto_mode(self):
        """Test auto-detection of task format"""
        task_data = {
            "id": "task123",
            "text": "This is a sample text to annotate",
            "metadata": {"source": "test"},
        }

        result = TaskFormatter.format_task(task_data=task_data, presentation_mode="auto")

        assert result["task_id"] == "task123"
        assert "data" in result
        assert result["data"]["text"] == "This is a sample text to annotate"
        assert result["detected_type"] == "text"

    def test_format_task_with_label_config(self):
        """Test formatting with label configuration"""
        task_data = {"text": "Sample text", "author": "John Doe"}

        label_config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="sentiment" toName="text">
                <Choice value="positive"/>
                <Choice value="negative"/>
                <Choice value="neutral"/>
            </Choices>
        </View>
        """

        result = TaskFormatter.format_task(
            task_data=task_data, label_config=label_config, presentation_mode="label_config"
        )

        assert "data" in result
        assert result["data"]["text"] == "Sample text"
        assert "annotation_requirements" in result
        assert "choices" in result["annotation_requirements"]
        assert "positive" in result["annotation_requirements"]["choices"]

    def test_format_task_with_template_mode(self):
        """Test formatting with template mode and field mappings"""
        task_data = {"q": "What is the capital of France?", "ctx": "France is a country in Europe."}

        field_mappings = {"q": "question", "ctx": "context"}

        result = TaskFormatter.format_task(
            task_data=task_data, presentation_mode="template", field_mappings=field_mappings
        )

        assert result["data"]["question"] == "What is the capital of France?"
        assert result["data"]["context"] == "France is a country in Europe."
        assert "formatted_text" in result
        assert "question:" in result["formatted_text"].lower()

    def test_format_task_raw_json_mode(self):
        """Test raw JSON presentation mode"""
        task_data = {"id": "123", "complex": {"nested": {"data": "value"}}, "array": [1, 2, 3]}

        result = TaskFormatter.format_task(task_data=task_data, presentation_mode="raw_json")

        assert result["data"] == task_data
        assert result["data"]["complex"]["nested"]["data"] == "value"

    def test_format_task_with_custom_instruction(self):
        """Test custom instruction override"""
        task_data = {"text": "Sample"}
        custom_instruction = "Please analyze this text carefully"

        result = TaskFormatter.format_task(task_data=task_data, instruction=custom_instruction)

        assert result["instruction"] == custom_instruction

    def test_batch_format_tasks(self):
        """Test batch formatting of multiple tasks"""
        tasks = [
            {"id": "1", "text": "First task"},
            {"id": "2", "text": "Second task"},
            {"id": "3", "text": "Third task"},
        ]

        results = TaskFormatter.batch_format_tasks(tasks=tasks, presentation_mode="auto")

        assert len(results) == 3
        assert results[0]["task_id"] == "1"
        assert results[1]["data"]["text"] == "Second task"
        assert all("data" in r for r in results)

    def test_batch_format_with_error_handling(self):
        """Test batch formatting handles errors gracefully"""
        tasks = [
            {"id": "1", "text": "Valid task"},
            None,  # Invalid task
            {"id": "3", "text": "Another valid task"},
        ]

        results = TaskFormatter.batch_format_tasks(tasks=tasks, presentation_mode="auto")

        assert len(results) == 3
        assert results[0]["task_id"] == "1"
        assert "error" in results[1]
        assert results[2]["task_id"] == "3"

    def test_create_llm_prompt_default(self):
        """Test LLM prompt creation with defaults"""
        formatted_task = {
            "task_id": "123",
            "instruction": "Annotate this task",
            "data": {"text": "Sample text"},
        }

        prompts = TaskFormatter.create_llm_prompt(formatted_task)

        assert "system" in prompts
        assert "user" in prompts
        assert "expert annotator" in prompts["system"].lower()
        assert "Annotate this task" in prompts["user"]
        assert "text: Sample text" in prompts["user"]

    def test_create_llm_prompt_with_requirements(self):
        """Test LLM prompt with annotation requirements"""
        formatted_task = {
            "task_id": "123",
            "data": {"text": "Sample"},
            "annotation_requirements": {
                "choices": ["positive", "negative", "neutral"],
                "labels": ["PERSON", "LOCATION", "DATE"],
            },
        }

        prompts = TaskFormatter.create_llm_prompt(formatted_task)

        assert "Choose from: positive, negative, neutral" in prompts["user"]
        assert "Available entity types: PERSON, LOCATION, DATE" in prompts["user"]

    def test_create_llm_prompt_custom(self):
        """Test LLM prompt with custom system and instruction prompts"""
        formatted_task = {"task_id": "123", "data": {"text": "Sample"}}

        custom_system = "You are a legal expert"
        custom_instruction = "Analyze this legal document"

        prompts = TaskFormatter.create_llm_prompt(
            formatted_task, system_prompt=custom_system, instruction_prompt=custom_instruction
        )

        assert prompts["system"] == custom_system
        assert custom_instruction in prompts["user"]

    def test_format_task_with_ner_labels(self):
        """Test formatting with NER label configuration"""
        task_data = {"text": "John lives in New York"}

        label_config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="label" toName="text">
                <Label value="PER" background="red"/>
                <Label value="LOC" background="blue"/>
            </Labels>
        </View>
        """

        result = TaskFormatter.format_task(
            task_data=task_data, label_config=label_config, presentation_mode="label_config"
        )

        assert "annotation_requirements" in result
        assert "labels" in result["annotation_requirements"]
        assert "PER" in result["annotation_requirements"]["labels"]
        assert "LOC" in result["annotation_requirements"]["labels"]

    def test_format_task_detect_common_fields(self):
        """Test auto-detection of common field patterns"""
        test_cases = [
            ({"question": "What?"}, "question"),
            ({"image": "path/to/image.jpg"}, "image"),
            ({"audio": "audio.mp3"}, "audio"),
            ({"context": "Background info"}, "context"),
        ]

        for task_data, expected_type in test_cases:
            result = TaskFormatter.format_task(task_data=task_data, presentation_mode="auto")
            assert result.get("detected_type") == expected_type
            assert expected_type in result["data"]

    def test_format_task_with_malformed_label_config(self):
        """Test graceful handling of malformed label config"""
        task_data = {"text": "Sample"}
        malformed_config = "<View><Text>Unclosed tag"

        result = TaskFormatter.format_task(
            task_data=task_data, label_config=malformed_config, presentation_mode="label_config"
        )

        # Should fall back to including all task data
        assert result["data"] == task_data

    def test_format_task_preserves_all_fields(self):
        """Test that all task fields are preserved in output"""
        task_data = {
            "id": "123",
            "text": "Main text",
            "extra_field_1": "value1",
            "extra_field_2": 42,
            "extra_field_3": {"nested": "data"},
        }

        result = TaskFormatter.format_task(task_data=task_data, presentation_mode="auto")

        # All fields should be in data
        assert "extra_field_1" in result["data"]
        assert "extra_field_2" in result["data"]
        assert result["data"]["extra_field_3"]["nested"] == "data"


class TestTaskFormatterEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_task_data(self):
        """Test handling of empty task data"""
        result = TaskFormatter.format_task(task_data={}, presentation_mode="auto")

        assert result["data"] == {}
        assert result["task_id"] is None

    def test_none_values_in_task_data(self):
        """Test handling of None values in task data"""
        task_data = {"id": "123", "text": None, "value": "actual value"}

        result = TaskFormatter.format_task(task_data=task_data, presentation_mode="auto")

        assert result["task_id"] == "123"
        assert result["data"]["text"] is None
        assert result["data"]["value"] == "actual value"

    def test_very_long_text_field(self):
        """Test template formatting with very long text"""
        long_text = "x" * 200
        task_data = {"short": "brief", "long": long_text}

        result = TaskFormatter.format_task(task_data=task_data, presentation_mode="template")

        # Long fields should be formatted differently
        assert "[LONG]" in result["formatted_text"].upper()
        assert "short: brief" in result["formatted_text"]

    def test_create_prompt_with_formatted_text(self):
        """Test prompt creation uses formatted_text when available"""
        formatted_task = {
            "task_id": "123",
            "formatted_text": "Custom formatted presentation",
            "data": {"ignored": "this should not appear"},
        }

        prompts = TaskFormatter.create_llm_prompt(formatted_task)

        assert "Custom formatted presentation" in prompts["user"]
        assert "ignored" not in prompts["user"]
