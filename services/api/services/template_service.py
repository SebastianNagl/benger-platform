"""
Template Service for BenGER
Only supports the simplified v3.0 format without Label Studio dependencies
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User

logger = logging.getLogger(__name__)


class TemplateService:
    """Service for template import/export"""

    def __init__(self):
        self.version = "3.0"

    def validate_template(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate v3.0 template structure"""
        try:
            # Debug logging
            logger.info(
                f"Validating template with keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
            )

            # Check if data is a dict
            if not isinstance(data, dict):
                return (
                    False,
                    f"Template data must be a dictionary, got {type(data).__name__}",
                )

            # Check version
            if data.get("version") != "3.0":
                return False, "Only v3.0 format is supported"

            # Validate required keys
            required_keys = ["task", "questions"]
            missing_keys = [key for key in required_keys if key not in data]
            if missing_keys:
                return False, f"Missing required keys: {missing_keys}"

            # Validate task info
            task = data["task"]
            required_task_fields = ["name", "description", "task_type"]
            missing_task_fields = [field for field in required_task_fields if field not in task]
            if missing_task_fields:
                return False, f"Missing task fields: {missing_task_fields}"

            # Validate questions array
            questions = data["questions"]
            if not isinstance(questions, list):
                return False, "questions must be a list"

            if not questions:
                return False, "questions list cannot be empty"

            for i, question in enumerate(questions):
                if not isinstance(question, dict):
                    return (
                        False,
                        f"Question {i} must be an object, got {type(question).__name__}",
                    )
                if "id" not in question:
                    return False, f"Question {i} missing required field: id"
                if "question_data" not in question:
                    return False, f"Question {i} missing required field: question_data"

            return True, None

        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            logger.error(f"Template data type: {type(data)}, Content: {data}")
            return False, f"Validation error: {str(e)}"

    async def import_template(
        self, db: Session, template_data: Dict[str, Any], user: User
    ) -> Dict[str, Any]:
        """Import v3.0 template and create task with direct data storage"""

        # Validate template
        is_valid, error_message = self.validate_template(template_data)
        if not is_valid:
            raise ValueError(f"Invalid template: {error_message}")

        task_info = template_data["task"]
        questions_data = template_data["questions"]
        template_data.get("evaluation_types", [])
        template_data.get("models", [])

        # Convert questions to the format expected by the data column
        tasks_data = []
        for question in questions_data:
            tasks_data.append({"id": question["id"], "data": question["question_data"]})

        try:
            # Get organization assignments from template or use defaults
            organization_ids = template_data.get("organization_ids", [])
            if not organization_ids:
                # Get user's organizations
                user_memberships = (
                    db.query(OrganizationMembership)
                    .filter(
                        OrganizationMembership.user_id == user.id,
                        OrganizationMembership.is_active == True,
                    )
                    .all()
                )
                organization_ids = [membership.organization_id for membership in user_memberships]

                # Add TUM organization if not already included
                tum_org = db.query(Organization).filter(Organization.name == "TUM").first()
                if tum_org and tum_org.id not in organization_ids:
                    organization_ids.append(tum_org.id)

            # Create task directly with simplified approach
            visibility = task_info.get("visibility", "private").lower()
            if visibility not in ["public", "private"]:
                visibility = "private"

            # Project removed - use project-based workflow
            # Template import functionality has been migrated to project system
            raise NotImplementedError(
                "Template import has been migrated to project-based workflow. "
                "Please use the project creation API instead."
            )

            # UNREACHABLE CODE BELOW - Kept for reference only
            # db.add(new_project)
            # db.commit()
            # db.refresh(new_project)
            #
            # # DEPRECATED: Native annotation project creation
            # # This entire template import workflow has been migrated to project-based API
            # # The code below is kept commented for reference but should not be used
            #
            # # from models import AnnotationProject, AnnotationTemplate
            # # ... template creation code removed ...
            # # annotation_project = AnnotationProject(...)
            # # db.add(annotation_project)
            #
            # db.commit()  # Just commit the new_project
            #
            # return {
            #     "task_id": new_project.id,
            #     "message": f"Successfully imported {len(tasks_data)} questions",
            #     "imported_tasks": len(tasks_data),
            #     "imported_prompts": 0,  # No prompts in v3.0 import
            #     "llm_responses_converted": 0,  # No responses in v3.0 import
            #     "annotation_project_id": annotation_project.id,
            #     "template_format": "3.0",
            #     "features_enabled": {
            #         "native_annotation": True,
            #         "llm_evaluation": True,
            #         "human_evaluation": True,
            #     },
            # }

        except Exception as e:
            logger.error(f"Failed to import template: {e}")
            db.rollback()
            raise Exception(f"Import failed: {str(e)}")

    async def export_template(self, db: Session, task_id: str, user: User) -> Dict[str, Any]:
        """Export task as v3.0 template"""

        # Project query removed - use project-based workflow
        task = None
        if not task:
            raise ValueError(f"Project {task_id} not found")

        if not task.data:
            raise ValueError(f"Project {task_id} has no data to export")

        # Convert task data to v3.0 format
        questions_data = []
        for item in task.data:
            questions_data.append({"id": item.get("id"), "question_data": item.get("data", {})})

        export_data = {
            "version": "3.0",
            "task": {
                "name": task.name,
                "description": task.description,
                "task_type": task.task_type_id,
                "visibility": task.visibility or "private",
            },
            "questions": questions_data,
            "evaluation_types": task.evaluation_type_ids or [],
            "models": task.model_ids or [],
            "organization_ids": task.organization_ids or [],
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "exported_by": user.id,
                "task_id": task_id,
            },
        }

        return export_data

    def _get_default_fields_config(self, task_type: str) -> list:
        """Get default annotation fields config for task type"""
        if task_type == "qa_reasoning":
            return [
                {
                    "name": "answer",
                    "type": "select",
                    "label": "Answer",
                    "required": True,
                    "options": ["Ja", "Nein"],
                },
                {
                    "name": "reasoning",
                    "type": "textarea",
                    "label": "Legal Reasoning",
                    "required": True,
                    "placeholder": "Provide detailed legal reasoning...",
                },
                {
                    "name": "confidence",
                    "type": "select",
                    "label": "Confidence",
                    "required": False,
                    "options": ["High", "Medium", "Low"],
                },
            ]
        elif task_type == "qa":
            return [
                {
                    "name": "answer",
                    "type": "textarea",
                    "label": "Answer",
                    "required": True,
                    "placeholder": "Enter your answer...",
                }
            ]
        elif task_type == "multiple_choice":
            return [
                {
                    "name": "selected_answer",
                    "type": "radio",
                    "label": "Select Answer",
                    "required": True,
                    "options": ["A", "B", "C", "D"],
                },
                {
                    "name": "confidence",
                    "type": "rating",
                    "label": "Confidence",
                    "required": False,
                    "min": 1,
                    "max": 5,
                },
            ]
        elif task_type == "generation":
            return [
                {
                    "name": "generated_text",
                    "type": "textarea",
                    "label": "Generated Response",
                    "required": True,
                    "placeholder": "Enter or edit the generated text...",
                },
                {
                    "name": "quality_rating",
                    "type": "rating",
                    "label": "Quality",
                    "required": False,
                    "min": 1,
                    "max": 5,
                },
                {
                    "name": "needs_revision",
                    "type": "checkbox",
                    "label": "Needs Revision",
                    "required": False,
                },
            ]
        else:
            # Default fields for unknown task types
            return [
                {
                    "name": "annotation",
                    "type": "textarea",
                    "label": "Annotation",
                    "required": True,
                    "placeholder": "Enter your annotation...",
                }
            ]

    def _get_default_template(self, task_type: str) -> str:
        """Get minimal template for task type"""
        templates = {
            "qa": """<View>
  <Text name="question" value="$question"/>
  <TextArea name="answer" toName="question" placeholder="Enter answer..." required="true"/>
</View>""",
            "qa_reasoning": """<View>
  <Text name="case_name" value="$case_name"/>
  <Text name="area" value="$area"/>
  <Text name="fall" value="$fall"/>
  <Text name="prompt" value="$prompt"/>
  <Choices name="solution" toName="fall">
    <Choice value="Ja"/>
    <Choice value="Nein"/>
  </Choices>
  <TextArea name="reasoning" toName="fall" placeholder="Legal reasoning..." required="true"/>
</View>""",
            "multiple_choice": """<View>
  <Header value="Question"/>
  <Text name="question" value="$question" style="white-space: pre-wrap; font-size: 16px; margin-bottom: 15px;"/>
  
  <Text name="context" value="$context" style="color: #666; font-style: italic; margin-bottom: 10px;"/>
  
  <Header value="Choose the correct answer:"/>
  <Choices name="selected_answer" toName="question" choice="single-radio" required="true">
    <Choice value="A" style="margin-bottom: 8px;"/>
    <Choice value="B" style="margin-bottom: 8px;"/>
    <Choice value="C" style="margin-bottom: 8px;"/>
    <Choice value="D" style="margin-bottom: 8px;"/>
  </Choices>
  
  <Header value="Answer Options"/>
  <Text name="choice_a" value="A) $choice_a" style="margin-bottom: 5px;"/>
  <Text name="choice_b" value="B) $choice_b" style="margin-bottom: 5px;"/>
  <Text name="choice_c" value="C) $choice_c" style="margin-bottom: 5px;"/>
  <Text name="choice_d" value="D) $choice_d" style="margin-bottom: 5px;"/>
  
  <Header value="Confidence Level"/>
  <Rating name="confidence" toName="question" maxRating="5" defaultValue="3"/>
</View>""",
            "generation": """<View>
  <Header value="Prompt"/>
  <Text name="prompt" value="$prompt" style="white-space: pre-wrap; font-size: 16px; margin-bottom: 15px;"/>
  
  <Text name="context" value="$context" style="color: #666; font-style: italic; margin-bottom: 10px;"/>
  
  <Header value="Generated Response"/>
  <TextArea name="generated_text" toName="prompt" placeholder="Enter or edit the generated text..." required="true" rows="8"/>
  
  <Header value="Quality Assessment"/>
  <Rating name="quality_rating" toName="prompt" maxRating="5" defaultValue="3"/>
  
  <Checkbox name="needs_revision" toName="prompt">
    <Label value="Needs Revision"/>
  </Checkbox>
  
  <TextArea name="revision_notes" toName="prompt" placeholder="Explain what needs to be improved..." rows="3"/>
</View>""",
        }

        return templates.get(task_type, templates["qa"])


# Global instance
template_service = TemplateService()
# Legacy alias for backward compatibility
universal_template_service_v3 = template_service
