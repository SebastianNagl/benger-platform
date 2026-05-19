"""
Project Report models for publishing evaluation results

This module provides the data model for project reports, enabling superadmins to
create, edit, and publish research results with customizable content sections.

Key Features:
- Progressive report building (sections populate as project progresses)
- Editable content with default templates
- Publication workflow with validation
- Organization-based access control
"""

import os

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Import compatibility for testing environments
if "sqlite" in os.environ.get("DATABASE_URL", "sqlite:///:memory:").lower():
    ContentJSONB = JSON
else:
    ContentJSONB = JSONB

from database import Base


class ProjectReport(Base):
    """
    Project report model for publishing evaluation results

    Reports are automatically created when projects are created and progressively
    populated as the project advances through its lifecycle (data import, annotation,
    generation, evaluation). Superadmins can edit content at any stage and publish
    when all sections are complete.

    Content Structure:
    {
        "sections": {
            "project_info": {
                "title": "Default or custom title",
                "description": "Default or custom description",
                "status": "completed" | "pending",
                "custom_title": str | null,
                "custom_description": str | null,
                "visible": bool
            },
            "data": {
                "task_count": int,
                "custom_text": str | null,
                "show_count": bool,
                "status": "completed" | "pending",
                "visible": bool
            },
            "annotations": {
                "annotation_count": int,
                "participants": [{"id": str, "name": str, "count": int}],
                "custom_text": str | null,
                "show_count": bool,
                "show_participants": bool,
                "acknowledgment_text": str | null,
                "status": "completed" | "pending",
                "visible": bool
            },
            "generation": {
                "models": [str],
                "custom_text": str | null,
                "show_models": bool,
                "show_config": bool,
                "status": "completed" | "pending",
                "visible": bool
            },
            "evaluation": {
                "methods": [str],
                "metrics": dict,
                "charts_config": dict,
                "custom_interpretation": str | null,
                "conclusions": str | null,
                "status": "completed" | "pending",
                "visible": bool
            }
        },
        "metadata": {
            "last_auto_update": ISO datetime,
            "sections_completed": [str],
            "can_publish": bool
        }
    }
    """

    __tablename__ = "project_reports"

    # Core fields
    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Report content (editable sections)
    content = Column(ContentJSONB, nullable=False)

    # Publication status
    is_published = Column(Boolean, default=False, nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by = Column(String, ForeignKey("users.id"), nullable=True)

    # Audit fields
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])
    publisher = relationship("User", foreign_keys=[published_by])

    def __repr__(self):
        return f"<ProjectReport(id={self.id}, project_id={self.project_id}, is_published={self.is_published})>"
