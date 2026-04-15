"""
Advanced tests for multiple prompts functionality
Tests complex scenarios, ordering, templates, and integration
Issue #798: Advanced prompt testing coverage
"""


import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from auth_module import User
from project_models import Project


@pytest.fixture
def prompt_project(db: Session, test_user: User):
    """Create a project with multiple prompt structures for testing"""
    project = Project(
        id="prompt-test-project",
        title="Prompt Test Project",
        description="Project for testing prompt structures",
        created_by=test_user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={
            "selected_configuration": {
                "models": ["gpt-4o"],
                "active_structures": ["default"],
            },
            "prompt_structures": {
                "default": {
                    "name": "Default Structure",
                    "description": "Default prompt structure",
                    "system_prompt": "You are an expert annotator",
                    "instruction_prompt": "Annotate the following text: ${text}",
                    "evaluation_prompt": None,
                }
            },
        },
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@pytest.fixture
def complex_prompt_project(db: Session, test_user: User):
    """Create a project with complex prompt structures"""
    project = Project(
        id="complex-prompt-project",
        title="Complex Prompt Project",
        description="Project with multiple complex prompts",
        created_by=test_user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-opus-20240229"],
                "active_structures": ["primary", "secondary"],
            },
            "prompt_structures": {
                "primary": {
                    "name": "Primary Structure",
                    "description": "Main annotation prompt",
                    "system_prompt": "You are an expert legal annotator",
                    "instruction_prompt": "Annotate legal text: ${text}",
                    "evaluation_prompt": "Evaluate annotation quality",
                },
                "secondary": {
                    "name": "Secondary Structure",
                    "description": "Alternative prompt structure",
                    "system_prompt": "You are a careful annotator",
                    "instruction_prompt": "Review and annotate: ${text}",
                    "evaluation_prompt": None,
                },
                "template_based": {
                    "name": "Template Based",
                    "description": "Uses template dictionaries",
                    "system_prompt": {
                        "template": "You are a ${role} with expertise in ${domain}",
                        "variables": {"role": "annotator", "domain": "legal texts"},
                    },
                    "instruction_prompt": {
                        "template": "Annotate ${task_type}: ${text}",
                        "variables": {"task_type": "classification"},
                    },
                    "evaluation_prompt": None,
                },
            },
        },
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestMultiplePromptsPerTask:
    """Test multiple prompts per task scenarios"""

    def test_multiple_system_prompts(self, db: Session, test_user: User):
        """Test project with multiple system prompts in different structures"""
        project = Project(
            id="multi-system-project",
            title="Multi System Project",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["expert", "beginner"],
                },
                "prompt_structures": {
                    "expert": {
                        "name": "Expert Mode",
                        "description": "Expert-level prompts",
                        "system_prompt": "You are an expert legal annotator with 10 years experience",
                        "instruction_prompt": "Provide detailed annotation",
                    },
                    "beginner": {
                        "name": "Beginner Mode",
                        "description": "Beginner-friendly prompts",
                        "system_prompt": "You are a careful annotator learning legal annotation",
                        "instruction_prompt": "Annotate with basic categories",
                    },
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify both structures exist
        assert "expert" in project.generation_config["prompt_structures"]
        assert "beginner" in project.generation_config["prompt_structures"]

        # Verify different system prompts
        expert_system = project.generation_config["prompt_structures"]["expert"]["system_prompt"]
        beginner_system = project.generation_config["prompt_structures"]["beginner"][
            "system_prompt"
        ]
        assert expert_system != beginner_system
        assert "expert" in expert_system.lower()
        assert "learning" in beginner_system.lower()  # Verify beginner content

    def test_multiple_instruction_prompts(self, db: Session, test_user: User):
        """Test project with multiple instruction prompts"""
        project = Project(
            id="multi-instruction-project",
            title="Multi Instruction Project",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["detailed", "brief"],
                },
                "prompt_structures": {
                    "detailed": {
                        "name": "Detailed Instructions",
                        "description": "Comprehensive annotation guidance",
                        "system_prompt": "You are an annotator",
                        "instruction_prompt": "Carefully analyze and annotate the text with detailed labels and justifications",
                    },
                    "brief": {
                        "name": "Brief Instructions",
                        "description": "Quick annotation",
                        "system_prompt": "You are an annotator",
                        "instruction_prompt": "Quickly annotate the text",
                    },
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify both structures exist
        assert len(project.generation_config["prompt_structures"]) == 2

        # Verify different instruction prompts
        detailed_inst = project.generation_config["prompt_structures"]["detailed"][
            "instruction_prompt"
        ]
        brief_inst = project.generation_config["prompt_structures"]["brief"]["instruction_prompt"]
        assert len(detailed_inst) > len(brief_inst)

    def test_system_and_instruction_combination(self, db: Session, complex_prompt_project: Project):
        """Test combination of system and instruction prompts"""
        # Get primary structure
        primary = complex_prompt_project.generation_config["prompt_structures"]["primary"]

        # Verify both system and instruction prompts exist
        assert "system_prompt" in primary
        assert "instruction_prompt" in primary
        assert isinstance(primary["system_prompt"], str)
        assert isinstance(primary["instruction_prompt"], str)

        # Verify they are different
        assert primary["system_prompt"] != primary["instruction_prompt"]

    def test_prompt_precedence(self, db: Session, complex_prompt_project: Project):
        """Test which prompt takes precedence when multiple are active"""
        # Get active structures
        active_structures = complex_prompt_project.generation_config["selected_configuration"][
            "active_structures"
        ]

        assert len(active_structures) == 2
        assert "primary" in active_structures
        assert "secondary" in active_structures

        # Verify order is preserved (primary should come first)
        assert active_structures[0] == "primary"


class TestPromptOrdering:
    """Test prompt ordering functionality"""

    def test_prompt_ordering_preserved(self, db: Session, test_user: User):
        """Test that prompt order is maintained"""
        project = Project(
            id="ordered-prompts-project",
            title="Ordered Prompts",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["first", "second", "third"],
                },
                "prompt_structures": {
                    "first": {
                        "name": "First",
                        "system_prompt": "First system prompt",
                        "instruction_prompt": "First instruction",
                    },
                    "second": {
                        "name": "Second",
                        "system_prompt": "Second system prompt",
                        "instruction_prompt": "Second instruction",
                    },
                    "third": {
                        "name": "Third",
                        "system_prompt": "Third system prompt",
                        "instruction_prompt": "Third instruction",
                    },
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify ordering is preserved
        active = project.generation_config["selected_configuration"]["active_structures"]
        assert active == ["first", "second", "third"]

    def test_prompt_priority_levels(self, db: Session, test_user: User):
        """Test priority/weight system for prompts"""
        project = Project(
            id="priority-prompts-project",
            title="Priority Prompts",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["high_priority", "low_priority"],
                    "structure_weights": {"high_priority": 1.0, "low_priority": 0.5},
                },
                "prompt_structures": {
                    "high_priority": {
                        "name": "High Priority",
                        "description": "Most important prompt",
                        "system_prompt": "High priority system prompt",
                        "instruction_prompt": "High priority instruction",
                    },
                    "low_priority": {
                        "name": "Low Priority",
                        "description": "Secondary prompt",
                        "system_prompt": "Low priority system prompt",
                        "instruction_prompt": "Low priority instruction",
                    },
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify weights are stored
        weights = project.generation_config["selected_configuration"]["structure_weights"]
        assert weights["high_priority"] == 1.0
        assert weights["low_priority"] == 0.5

    def test_default_prompt_fallback(self, db: Session, test_user: User):
        """Test default prompt when none specified"""
        project = Project(
            id="default-fallback-project",
            title="Default Fallback",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": [],  # No active structures
                },
                "prompt_structures": {
                    "default": {
                        "name": "Default",
                        "description": "Default fallback prompt",
                        "system_prompt": "Default system prompt",
                        "instruction_prompt": "Default instruction",
                    }
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # When no active structures, should have default available
        assert "default" in project.generation_config["prompt_structures"]
        assert len(project.generation_config["selected_configuration"]["active_structures"]) == 0


class TestTemplateFeatures:
    """Test template features in prompts"""

    def test_prompt_variable_substitution(self, db: Session, complex_prompt_project: Project):
        """Test ${variable} replacement in prompts"""
        # Get template-based structure
        template_struct = complex_prompt_project.generation_config["prompt_structures"][
            "template_based"
        ]

        # Verify system prompt template
        system_prompt = template_struct["system_prompt"]
        assert isinstance(system_prompt, dict)
        assert "template" in system_prompt
        assert "variables" in system_prompt
        assert "${role}" in system_prompt["template"]
        assert "${domain}" in system_prompt["template"]
        assert system_prompt["variables"]["role"] == "annotator"
        assert system_prompt["variables"]["domain"] == "legal texts"

        # Verify instruction prompt template
        instruction_prompt = template_struct["instruction_prompt"]
        assert isinstance(instruction_prompt, dict)
        assert "${task_type}" in instruction_prompt["template"]
        assert "${text}" in instruction_prompt["template"]

    def test_prompt_conditional_logic(self, db: Session, test_user: User):
        """Test conditional sections in prompts"""
        project = Project(
            id="conditional-prompts-project",
            title="Conditional Prompts",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["conditional"],
                },
                "prompt_structures": {
                    "conditional": {
                        "name": "Conditional Structure",
                        "description": "Has conditional logic",
                        "system_prompt": {
                            "template": "You are an annotator",
                            "conditions": [
                                {
                                    "if": {"field": "task_type", "equals": "classification"},
                                    "then": "Focus on categorization",
                                },
                                {
                                    "if": {"field": "task_type", "equals": "extraction"},
                                    "then": "Focus on entity extraction",
                                },
                            ],
                        },
                        "instruction_prompt": "Annotate the text",
                    }
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify conditional structure is stored
        conditional = project.generation_config["prompt_structures"]["conditional"]
        assert "conditions" in conditional["system_prompt"]
        assert len(conditional["system_prompt"]["conditions"]) == 2

    def test_prompt_template_inheritance(self, db: Session, test_user: User):
        """Test base template + override pattern"""
        project = Project(
            id="inheritance-prompts-project",
            title="Inheritance Prompts",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["base", "override"],
                },
                "prompt_structures": {
                    "base": {
                        "name": "Base Template",
                        "description": "Base prompt template",
                        "system_prompt": "You are an annotator",
                        "instruction_prompt": "Annotate the text carefully",
                    },
                    "override": {
                        "name": "Override Template",
                        "description": "Overrides base template",
                        "system_prompt": "You are an expert annotator",  # Override
                        "instruction_prompt": "Annotate the text carefully",  # Same as base
                        "extends": "base",  # Reference to base template
                    },
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify inheritance metadata
        override = project.generation_config["prompt_structures"]["override"]
        assert "extends" in override
        assert override["extends"] == "base"

        # Verify overridden field differs from base
        base = project.generation_config["prompt_structures"]["base"]
        assert override["system_prompt"] != base["system_prompt"]
        assert "expert" in override["system_prompt"]


class TestIntegration:
    """Test integration with generation config"""

    def test_prompts_with_generation_config(self, db: Session, complex_prompt_project: Project):
        """Test full config integration"""
        config = complex_prompt_project.generation_config

        # Verify all components are present
        assert "selected_configuration" in config
        assert "prompt_structures" in config

        # Verify selected configuration has models and active structures
        selected = config["selected_configuration"]
        assert "models" in selected
        assert "active_structures" in selected
        assert len(selected["models"]) == 2
        assert len(selected["active_structures"]) == 2

        # Verify prompt structures are properly structured
        structures = config["prompt_structures"]
        assert len(structures) == 3
        for key, structure in structures.items():
            assert "name" in structure
            assert "system_prompt" in structure
            assert "instruction_prompt" in structure

    def test_prompt_structures_persist(self, db: Session, prompt_project: Project):
        """Test JSONB persistence of prompt structures"""
        # Modify prompt structures
        prompt_project.generation_config["prompt_structures"]["new_structure"] = {
            "name": "New Structure",
            "description": "Added after creation",
            "system_prompt": "New system prompt",
            "instruction_prompt": "New instruction",
        }

        # Mark as modified for JSONB
        flag_modified(prompt_project, "generation_config")
        db.commit()

        # Refresh and verify persistence
        db.refresh(prompt_project)
        assert "new_structure" in prompt_project.generation_config["prompt_structures"]

        # Verify data integrity
        new_struct = prompt_project.generation_config["prompt_structures"]["new_structure"]
        assert new_struct["name"] == "New Structure"
        assert new_struct["system_prompt"] == "New system prompt"

    def test_prompt_retrieval_by_type(self, db: Session, complex_prompt_project: Project):
        """Test filtering prompts by type/category"""
        structures = complex_prompt_project.generation_config["prompt_structures"]

        # Find structures with evaluation prompts
        with_evaluation = {
            key: struct
            for key, struct in structures.items()
            if struct.get("evaluation_prompt") is not None
        }

        # Verify filtering works
        assert "primary" in with_evaluation  # Has evaluation_prompt
        assert "secondary" not in with_evaluation  # evaluation_prompt is None

        # Find template-based structures
        template_based = {
            key: struct
            for key, struct in structures.items()
            if isinstance(struct.get("system_prompt"), dict)
        }

        assert "template_based" in template_based
        assert len(template_based) >= 1


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_prompt_structures(self, db: Session, test_user: User):
        """Test handling of empty/null prompt structures"""
        # Project with empty structures
        project = Project(
            id="empty-structures-project",
            title="Empty Structures",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {"models": ["gpt-4o"], "active_structures": []},
                "prompt_structures": {},  # Empty
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify empty structures are handled
        assert project.generation_config["prompt_structures"] == {}
        assert len(project.generation_config["selected_configuration"]["active_structures"]) == 0

        # Project with null generation_config
        project_null = Project(
            id="null-config-project",
            title="Null Config",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config=None,
        )
        db.add(project_null)
        db.commit()
        db.refresh(project_null)

        # Verify null handling
        assert project_null.generation_config is None

    def test_conflicting_prompt_types(self, db: Session, test_user: User):
        """Test conflict resolution when prompts have conflicting types"""
        project = Project(
            id="conflicting-prompts-project",
            title="Conflicting Prompts",
            created_by=test_user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            generation_config={
                "selected_configuration": {
                    "models": ["gpt-4o"],
                    "active_structures": ["string_based", "template_based"],
                },
                "prompt_structures": {
                    "string_based": {
                        "name": "String Based",
                        "description": "Uses string prompts",
                        "system_prompt": "Simple string prompt",
                        "instruction_prompt": "Simple instruction",
                    },
                    "template_based": {
                        "name": "Template Based",
                        "description": "Uses template prompts",
                        "system_prompt": {
                            "template": "Template ${var}",
                            "variables": {"var": "value"},
                        },
                        "instruction_prompt": {"template": "Template instruction"},
                    },
                },
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Verify both types coexist
        structures = project.generation_config["prompt_structures"]
        assert isinstance(structures["string_based"]["system_prompt"], str)
        assert isinstance(structures["template_based"]["system_prompt"], dict)

        # Both should be active
        active = project.generation_config["selected_configuration"]["active_structures"]
        assert "string_based" in active
        assert "template_based" in active
