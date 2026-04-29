"""
Task Formatting Service for consistent presentation to annotators and LLMs
Issue #482: Ensure tasks are formatted identically for both human and model annotations
"""

import json
import logging
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


def _find_key_insensitive(d: Dict[str, Any], key: str) -> Optional[str]:
    """Find a key in dict matching case-insensitively. Prefers exact match."""
    if key in d:
        return key
    lower_key = key.lower()
    for k in d:
        if k.lower() == lower_key:
            return k
    return None


class TaskFormatter:
    """
    Service to format tasks consistently for both human annotators and LLM models.
    Supports multiple presentation modes based on project configuration.
    """

    @staticmethod
    def format_task(
        task_data: Dict[str, Any],
        label_config: Optional[str] = None,
        presentation_mode: str = "auto",
        instruction: Optional[str] = None,
        field_mappings: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Format a task for presentation to annotators or LLMs.

        Args:
            task_data: Raw task data from database
            label_config: XML/JSON label configuration
            presentation_mode: How to present the task ("label_config", "template", "raw_json", "auto")
            instruction: Optional instruction text
            field_mappings: Optional field name mappings for clarity

        Returns:
            Formatted task data ready for presentation
        """
        formatted = {
            "task_id": task_data.get("id"),
            "instruction": instruction or "Please complete the following annotation task:",
            "data": {},
            "metadata": {},
        }

        if presentation_mode == "label_config" and label_config:
            formatted.update(TaskFormatter._format_with_label_config(task_data, label_config))
        elif presentation_mode == "template":
            formatted.update(TaskFormatter._format_with_template(task_data, field_mappings))
        elif presentation_mode == "raw_json":
            formatted["data"] = task_data
        else:  # auto mode
            formatted.update(TaskFormatter._format_auto(task_data, label_config))

        return formatted

    @staticmethod
    def _format_with_label_config(task_data: Dict[str, Any], label_config: str) -> Dict[str, Any]:
        """
        Format task using label configuration structure.
        Parses the label config to understand data fields and annotation requirements.
        """
        result = {"data": {}, "annotation_requirements": {}}

        try:
            # Parse label config XML
            root = ET.fromstring(label_config)

            # Extract data field references
            for element in root.iter():
                if "name" in element.attrib:
                    field_name = element.attrib["name"]

                    # Check for value attribute (data binding)
                    if "value" in element.attrib:
                        value_ref = element.attrib["value"]
                        # Remove $ prefix if present
                        value_ref = value_ref.lstrip("$")

                        actual_key = _find_key_insensitive(task_data, value_ref)
                        if actual_key is not None:
                            result["data"][field_name] = task_data[actual_key]

                    # Extract choices for classification tasks
                    if element.tag == "Choices":
                        choices = []
                        for choice in element.findall("Choice"):
                            choices.append(choice.attrib.get("value", ""))
                        if choices:
                            result["annotation_requirements"]["choices"] = choices

                    # Extract labels for NER/span tasks
                    if element.tag == "Labels":
                        labels = []
                        for label in element.findall("Label"):
                            labels.append(label.attrib.get("value", ""))
                        if labels:
                            result["annotation_requirements"]["labels"] = labels

            # If no structured data found, include all task data
            if not result["data"]:
                result["data"] = task_data

        except ET.ParseError as e:
            logger.warning(f"Failed to parse label config: {e}")
            result["data"] = task_data

        return result

    @staticmethod
    def _format_with_template(
        task_data: Dict[str, Any], field_mappings: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Format task using template with field mappings for clarity.
        """
        result = {"data": {}}

        # Apply field mappings if provided
        if field_mappings:
            for original_key, mapped_key in field_mappings.items():
                if original_key in task_data:
                    result["data"][mapped_key] = task_data[original_key]
        else:
            result["data"] = task_data

        # Generate a human-readable template
        template_parts = []
        for key, value in result["data"].items():
            if isinstance(value, str) and len(value) > 100:
                # Long text fields
                template_parts.append(f"[{key.upper()}]\n{value}\n")
            else:
                # Short fields
                template_parts.append(f"{key}: {value}")

        result["formatted_text"] = "\n".join(template_parts)

        return result

    @staticmethod
    def _format_auto(
        task_data: Dict[str, Any], label_config: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Automatically detect and format task based on common patterns.
        """
        result = {"data": {}}

        # Try label config first if available
        if label_config:
            return TaskFormatter._format_with_label_config(task_data, label_config)

        # Detect common field patterns
        common_fields = {
            "text": ["text", "content", "document", "article", "passage"],
            "question": ["question", "query", "prompt"],
            "image": ["image", "img", "picture", "photo"],
            "audio": ["audio", "sound", "recording"],
            "choices": ["choices", "options", "alternatives"],
            "context": ["context", "background", "reference"],
        }

        detected_type = None
        for field_type, patterns in common_fields.items():
            for pattern in patterns:
                actual_key = _find_key_insensitive(task_data, pattern)
                if actual_key is not None:
                    detected_type = field_type
                    result["data"][field_type] = task_data[actual_key]
                    break
            if detected_type:
                break

        # Include all other fields
        for key, value in task_data.items():
            if key not in result["data"].values():
                result["data"][key] = value

        # Add detected type as metadata
        if detected_type:
            result["detected_type"] = detected_type

        return result

    @staticmethod
    def batch_format_tasks(
        tasks: List[Dict[str, Any]],
        label_config: Optional[str] = None,
        presentation_mode: str = "auto",
        instruction: Optional[str] = None,
        field_mappings: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Format multiple tasks in batch.

        Args:
            tasks: List of task data dictionaries
            label_config: XML/JSON label configuration
            presentation_mode: How to present tasks
            instruction: Optional instruction text
            field_mappings: Optional field name mappings

        Returns:
            List of formatted tasks
        """
        formatted_tasks = []

        for task in tasks:
            try:
                formatted = TaskFormatter.format_task(
                    task_data=task,
                    label_config=label_config,
                    presentation_mode=presentation_mode,
                    instruction=instruction,
                    field_mappings=field_mappings,
                )
                formatted_tasks.append(formatted)
            except Exception as e:
                task_id = task.get("id") if task else None
                logger.error(f"Failed to format task {task_id}: {e}")
                # Include raw task on error
                formatted_tasks.append(
                    {
                        "task_id": task_id,
                        "data": task,
                        "error": f"Formatting failed: {str(e)}",
                    }
                )

        return formatted_tasks

    @staticmethod
    def create_llm_prompt(
        formatted_task: Dict[str, Any],
        system_prompt: Optional[str] = None,
        instruction_prompt: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Create prompts for LLM generation from formatted task.

        Args:
            formatted_task: Task formatted by format_task method
            system_prompt: Optional system prompt for the LLM
            instruction_prompt: Optional instruction prompt

        Returns:
            Dictionary with system and user prompts
        """
        # Default system prompt
        if not system_prompt:
            system_prompt = (
                "You are an expert annotator. Follow the instructions carefully "
                "and provide accurate, consistent annotations for the given task."
            )

        # Build user prompt
        user_prompt_parts = []

        # Add instruction
        if instruction_prompt:
            user_prompt_parts.append(instruction_prompt)
        elif formatted_task.get("instruction"):
            user_prompt_parts.append(formatted_task["instruction"])

        # Add task data
        if formatted_task.get("formatted_text"):
            user_prompt_parts.append(formatted_task["formatted_text"])
        else:
            data = formatted_task.get("data", {})
            if isinstance(data, dict):
                for key, value in data.items():
                    if key not in ["id", "task_id", "created_at", "updated_at"]:
                        user_prompt_parts.append(f"{key}: {value}")
            else:
                user_prompt_parts.append(json.dumps(data, indent=2))

        # Add annotation requirements if present
        if formatted_task.get("annotation_requirements"):
            reqs = formatted_task["annotation_requirements"]
            if reqs.get("choices"):
                user_prompt_parts.append(f"Choose from: {', '.join(reqs['choices'])}")
            if reqs.get("labels"):
                # Add NER/span annotation instructions (Issue #964)
                labels = reqs["labels"]
                user_prompt_parts.append(
                    f"Identify named entities in the text and return them as a JSON array.\n"
                    f"Available entity types: {', '.join(labels)}\n"
                    f"For each entity, provide:\n"
                    f"- \"start\": character offset where entity begins (0-indexed)\n"
                    f"- \"end\": character offset where entity ends (exclusive)\n"
                    f"- \"text\": the exact text of the entity\n"
                    f"- \"type\": one of [{', '.join(labels)}]\n\n"
                    f"Example format:\n"
                    f"[{{\"start\": 0, \"end\": 10, \"text\": \"John Smith\", \"type\": \"{labels[0]}\"}}]"
                )

        return {"system": system_prompt, "user": "\n\n".join(user_prompt_parts)}
