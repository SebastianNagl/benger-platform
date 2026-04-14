"""
Tests for GenerationStructureParser
Issue #519: Test template interpolation and nested field support
"""

import json

import pytest
from generation_structure_parser import GenerationStructureParser


class TestGenerationStructureParser:
    """Test suite for generation structure parser"""

    def setup_method(self):
        """Setup test fixtures"""
        self.parser = GenerationStructureParser()

        # Sample task data with nested structure
        self.task_data = {
            "id": "task_001",
            "area": "contract_law",
            "prompts": {
                "prompt_clean": "Analyze this contract clause",
                "prompt_detailed": "Provide detailed analysis of the following contract clause with legal precedents",
                "metadata": {"difficulty": "medium", "source": "bar_exam"},
            },
            "context": {
                "jurisdiction": "Germany",
                "legal_system": "civil_law",
                "references": ["BGB §433", "BGB §134"],
            },
            "items": [
                {"name": "clause_1", "text": "Payment terms"},
                {"name": "clause_2", "text": "Liability limitations"},
            ],
            "annotations": {
                "reference_answer": "This should never be sent to LLM",
                "correct_classification": "valid",
            },
            "ground_truth": "Secret answer that must not leak",
        }

    def test_parse_structure_string(self):
        """Test parsing JSON string structure"""
        structure_json = json.dumps(
            {
                "system_prompt": "$area",
                "instruction_prompt": "$prompts.prompt_clean",
                "fields": {"area": "$area", "prompt": "$prompts.prompt_clean"},
            }
        )

        result = self.parser.parse_structure(structure_json)
        assert result is not None
        assert "system_prompt" in result
        assert result["system_prompt"] == "$area"

    def test_parse_structure_dict(self):
        """Test parsing dict structure"""
        structure = {
            "system_prompt": "You are a legal expert",
            "instruction_prompt": "$prompts.prompt_clean",
        }

        result = self.parser.parse_structure(structure)
        assert result == structure

    def test_parse_structure_caching(self):
        """Test that parsed structures are cached"""
        structure_json = json.dumps({"fields": {"test": "$value"}})

        # First parse
        result1 = self.parser.parse_structure(structure_json)
        # Second parse should use cache
        result2 = self.parser.parse_structure(structure_json)

        assert result1 is result2  # Same object reference from cache

    def test_extract_nested_value_simple(self):
        """Test extracting simple nested values"""
        value = self.parser.extract_nested_value(self.task_data, "area")
        assert value == "contract_law"

    def test_extract_nested_value_dot_notation(self):
        """Test extracting values with dot notation"""
        value = self.parser.extract_nested_value(self.task_data, "prompts.prompt_clean")
        assert value == "Analyze this contract clause"

        value = self.parser.extract_nested_value(self.task_data, "prompts.metadata.difficulty")
        assert value == "medium"

        value = self.parser.extract_nested_value(self.task_data, "context.jurisdiction")
        assert value == "Germany"

    def test_extract_nested_value_array_access(self):
        """Test extracting values from arrays"""
        value = self.parser.extract_nested_value(self.task_data, "items[0].name")
        assert value == "clause_1"

        value = self.parser.extract_nested_value(self.task_data, "items[1].text")
        assert value == "Liability limitations"

        value = self.parser.extract_nested_value(self.task_data, "context.references[0]")
        assert value == "BGB §433"

    def test_extract_nested_value_missing(self):
        """Test handling missing values"""
        value = self.parser.extract_nested_value(self.task_data, "nonexistent")
        assert value is None

        value = self.parser.extract_nested_value(self.task_data, "prompts.missing.field")
        assert value is None

        value = self.parser.extract_nested_value(self.task_data, "items[99].name")
        assert value is None

    def test_interpolate_template_simple(self):
        """Test simple template interpolation"""
        template = "Area: {{area}}, Difficulty: {{difficulty}}"
        placeholders = {"area": "contract_law", "difficulty": "medium"}

        result = self.parser.interpolate_template(template, placeholders)
        assert result == "Area: contract_law, Difficulty: medium"

    def test_interpolate_template_complex(self):
        """Test template with complex values"""
        template = "Context: {{context}}\n\nItems: {{items}}"
        placeholders = {"context": {"jurisdiction": "Germany"}, "items": ["item1", "item2"]}

        result = self.parser.interpolate_template(template, placeholders)
        assert '"jurisdiction": "Germany"' in result
        assert '["item1", "item2"]' in result or '[\n  "item1",\n  "item2"\n]' in result

    def test_interpolate_template_missing_placeholder(self):
        """Test template with missing placeholders"""
        template = "Area: {{area}}, Missing: {{missing}}"
        placeholders = {"area": "contract_law"}

        # With allow_missing=False (default)
        result = self.parser.interpolate_template(template, placeholders)
        assert result == "Area: contract_law, Missing: {{missing}}"

        # With allow_missing=True
        result = self.parser.interpolate_template(template, placeholders, allow_missing=True)
        assert result == "Area: contract_law, Missing: {{missing}}"

    def test_filter_task_data_basic(self):
        """Test basic field filtering"""
        mappings = {"area": "area", "prompt": "prompts.prompt_clean"}

        filtered = self.parser.filter_task_data(self.task_data, mappings)

        assert "area" in filtered
        assert filtered["area"] == "contract_law"
        assert "prompt" in filtered
        assert filtered["prompt"] == "Analyze this contract clause"

        # Sensitive fields should not be included
        assert "annotations" not in filtered
        assert "ground_truth" not in filtered

    def test_filter_task_data_security(self):
        """Test that sensitive fields are filtered out"""
        mappings = {
            "area": "area",
            "answer": "annotations.reference_answer",  # Should be filtered
            "truth": "ground_truth",  # Should be filtered
            "classification": "annotations.correct_classification",  # Should be filtered
        }

        filtered = self.parser.filter_task_data(self.task_data, mappings)

        assert "area" in filtered
        assert "answer" not in filtered  # Sensitive field blocked
        assert "truth" not in filtered  # Sensitive field blocked
        assert "classification" not in filtered  # Parent is sensitive

    def test_build_prompts_simple(self):
        """Test building simple prompts from field references"""
        structure = {"system_prompt": "$area", "instruction_prompt": "$prompts.prompt_clean"}

        prompts = self.parser.build_prompts(self.task_data, structure)

        assert prompts["system_prompt"] == "contract_law"
        assert prompts["instruction_prompt"] == "Analyze this contract clause"

    def test_build_prompts_template(self):
        """Test building prompts with templates"""
        structure = {
            "system_prompt": {
                "template": "You are an expert in {{area}} law in {{jurisdiction}}.",
                "fields": {"area": "$area", "jurisdiction": "$context.jurisdiction"},
            },
            "instruction_prompt": {
                "template": "Task: {{prompt}}\n\nDifficulty: {{difficulty}}",
                "fields": {
                    "prompt": "$prompts.prompt_clean",
                    "difficulty": "$prompts.metadata.difficulty",
                },
            },
        }

        prompts = self.parser.build_prompts(self.task_data, structure)

        assert prompts["system_prompt"] == "You are an expert in contract_law law in Germany."
        assert "Task: Analyze this contract clause" in prompts["instruction_prompt"]
        assert "Difficulty: medium" in prompts["instruction_prompt"]

    def test_build_prompts_with_context_fields(self):
        """Test building prompts with context fields"""
        structure = {
            "instruction_prompt": "$prompts.prompt_clean",
            "context_fields": ["$context.jurisdiction", "$context.legal_system"],
        }

        prompts = self.parser.build_prompts(self.task_data, structure)

        assert "Germany" in prompts["instruction_prompt"]
        assert "civil_law" in prompts["instruction_prompt"]
        assert "Context:" in prompts["instruction_prompt"]

    def test_process_generation_structure_complete(self):
        """Test complete processing pipeline"""
        structure = {
            "system_prompt": {
                "template": "You are a {{role}} expert.",
                "fields": {"role": "$area"},
            },
            "instruction_prompt": {
                "template": "{{task}}\n\nJurisdiction: {{jurisdiction}}",
                "fields": {
                    "task": "$prompts.prompt_clean",
                    "jurisdiction": "$context.jurisdiction",
                },
            },
            "exclude_fields": ["internal_notes"],
        }

        prompts, filtered_data = self.parser.process_generation_structure(
            self.task_data, structure, fallback_instruction="Default instruction"
        )

        # Check prompts
        assert prompts["system_prompt"] == "You are a contract_law expert."
        assert "Analyze this contract clause" in prompts["instruction_prompt"]
        assert "Jurisdiction: Germany" in prompts["instruction_prompt"]

        # Check filtered data
        assert "role" in filtered_data
        assert filtered_data["role"] == "contract_law"
        assert "task" in filtered_data
        assert "jurisdiction" in filtered_data

    def test_process_generation_structure_fallback(self):
        """Test fallback behavior with invalid structure"""
        prompts, filtered_data = self.parser.process_generation_structure(
            self.task_data, None, fallback_instruction="Use this fallback"  # No structure
        )

        assert prompts.get("instruction_prompt") == "Use this fallback"
        assert filtered_data == {}

    def test_validate_structure_valid(self):
        """Test structure validation with valid config"""
        structure = {
            "system_prompt": "$area",
            "instruction_prompt": {
                "template": "{{prompt}}",
                "fields": {"prompt": "$prompts.prompt_clean"},
            },
        }

        is_valid, error = self.parser.validate_structure(structure)
        assert is_valid
        assert error is None

    def test_validate_structure_invalid(self):
        """Test structure validation with invalid configs"""
        # Missing required fields
        structure = {}
        is_valid, error = self.parser.validate_structure(structure)
        assert not is_valid
        assert "must define at least one prompt" in error or "Failed to parse structure" in error

        # Invalid template structure
        structure = {
            "system_prompt": {
                # Missing 'template' field
                "fields": {"test": "$value"}
            }
        }
        is_valid, error = self.parser.validate_structure(structure)
        assert not is_valid
        assert "must have 'template' field" in error

        # Invalid field types
        structure = {
            "instruction_prompt": "$valid",
            "exclude_fields": "should_be_array",  # Wrong type
        }
        is_valid, error = self.parser.validate_structure(structure)
        assert not is_valid
        assert "'exclude_fields' must be an array" in error

    def test_complex_real_world_example(self):
        """Test with a complex real-world example"""
        # Complex task data
        task_data = {
            "id": "eval_001",
            "question": {
                "text": "What are the requirements for a valid contract?",
                "type": "multiple_choice",
                "options": ["A", "B", "C", "D"],
            },
            "metadata": {
                "source": "bar_exam_2023",
                "difficulty": "hard",
                "topics": ["contract_formation", "consideration"],
            },
            "reference": {
                "answer": "B",  # Sensitive - should be filtered
                "explanation": "Detailed explanation here",
            },
        }

        # Complex generation structure
        structure = {
            "system_prompt": {
                "template": "You are an expert in {{topics}}. This is a {{difficulty}} question from {{source}}.",
                "fields": {
                    "topics": "$metadata.topics",
                    "difficulty": "$metadata.difficulty",
                    "source": "$metadata.source",
                },
            },
            "instruction_prompt": {
                "template": "Question: {{question}}\n\nOptions:\n{{options}}\n\nProvide your answer and reasoning.",
                "fields": {"question": "$question.text", "options": "$question.options"},
            },
        }

        prompts, filtered_data = self.parser.process_generation_structure(task_data, structure)

        # Verify system prompt
        assert "contract_formation" in prompts["system_prompt"]
        assert "hard question" in prompts["system_prompt"]
        assert "bar_exam_2023" in prompts["system_prompt"]

        # Verify instruction prompt
        assert "What are the requirements" in prompts["instruction_prompt"]
        assert (
            '["A", "B", "C", "D"]' in prompts["instruction_prompt"]
            or 'A' in prompts["instruction_prompt"]
        )

        # Verify sensitive data is filtered
        assert "reference" not in filtered_data
        assert "answer" not in filtered_data
        for key in filtered_data:
            assert filtered_data[key] != "B"  # The answer should not leak


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
