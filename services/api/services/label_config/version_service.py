"""
Label Config Version Management Service

Handles versioning of label_config schemas to preserve data when schemas evolve.
Provides utilities for incrementing versions, storing history, and comparing schemas.
"""

import hashlib
import re
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from project_models import Project


class LabelConfigVersionService:
    """Service for managing label_config schema versions"""

    @staticmethod
    def increment_version(current_version: Optional[str]) -> str:
        """
        Increment a version string.

        Args:
            current_version: Current version (e.g., "v1", "v12", None)

        Returns:
            Next version (e.g., "v2", "v13", "v1")

        Examples:
            >>> increment_version("v1")
            "v2"
            >>> increment_version("v12")
            "v13"
            >>> increment_version(None)
            "v1"
        """
        if not current_version:
            return "v1"

        # Extract number from version string (e.g., "v1" → 1)
        match = re.match(r"v(\d+)", current_version)
        if match:
            current_num = int(match.group(1))
            return f"v{current_num + 1}"

        # Fallback: append "v1" if format doesn't match
        return "v1"

    @staticmethod
    def compute_schema_hash(label_config: str) -> str:
        """
        Compute a hash of the label_config for change detection.

        Args:
            label_config: XML/JSON schema string

        Returns:
            SHA256 hash of the schema
        """
        if not label_config:
            return ""
        return hashlib.sha256(label_config.encode('utf-8')).hexdigest()[:12]

    @staticmethod
    def has_schema_changed(project: Project, new_label_config: str) -> bool:
        """
        Check if the label_config has actually changed.

        Args:
            project: Project instance
            new_label_config: New schema to compare

        Returns:
            True if schema changed, False otherwise
        """
        if not project.label_config and not new_label_config:
            return False

        return project.label_config != new_label_config

    @staticmethod
    def update_version_history(
        project: Project,
        new_label_config: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Update version history when label_config changes.

        This method:
        1. Stores the OLD schema in history
        2. Increments version number
        3. Updates project with new schema and version

        Args:
            project: Project to update
            new_label_config: New schema to apply
            description: Optional description of changes
            user_id: User making the change

        Returns:
            New version string (e.g., "v2")
        """
        # Initialize history if needed
        if not project.label_config_history:
            project.label_config_history = {"versions": {}}

        # Get current version (or v1 if not set)
        current_version = project.label_config_version or "v1"

        # Store current schema in history BEFORE updating
        if project.label_config:
            project.label_config_history["versions"][current_version] = {
                "schema": project.label_config,
                "created_at": datetime.now().isoformat(),
                "created_by": user_id or project.created_by,
                "description": description or f"Schema version {current_version}",
                "schema_hash": LabelConfigVersionService.compute_schema_hash(project.label_config),
            }

        # Increment version
        new_version = LabelConfigVersionService.increment_version(current_version)

        # Update project with new schema and version
        project.label_config = new_label_config
        project.label_config_version = new_version
        project.label_config_history["current_version"] = new_version

        # Mark JSONB field as modified so SQLAlchemy persists changes
        # Only call flag_modified if this is a real SQLAlchemy object (not a mock)
        try:
            flag_modified(project, "label_config_history")
        except AttributeError:
            # If object doesn't have _sa_instance_state, it's not a real SQLAlchemy object (e.g., a mock in tests)
            pass

        return new_version

    @staticmethod
    def get_version_schema(project: Project, version: str) -> Optional[str]:
        """
        Retrieve a specific version of the label_config.

        Args:
            project: Project instance
            version: Version to retrieve (e.g., "v1", "v2")

        Returns:
            Schema string for that version, or None if not found
        """
        if not project.label_config_history:
            return None

        # Check if requesting current version
        if version == project.label_config_version:
            return project.label_config

        # Look up in history
        versions = project.label_config_history.get("versions", {})
        version_data = versions.get(version)

        if version_data:
            return version_data.get("schema")

        return None

    @staticmethod
    def list_versions(project: Project) -> List[Dict]:
        """
        List all available versions with metadata.

        Args:
            project: Project instance

        Returns:
            List of version metadata dicts
        """
        versions = []

        if not project.label_config_history:
            # Return current version only
            if project.label_config_version:
                versions.append(
                    {
                        "version": project.label_config_version,
                        "is_current": True,
                        "created_at": project.created_at.isoformat(),
                        "description": "Current schema",
                    }
                )
            return versions

        # Add historical versions
        version_data = project.label_config_history.get("versions", {})
        for version, data in version_data.items():
            versions.append(
                {
                    "version": version,
                    "is_current": (version == project.label_config_version),
                    "created_at": data.get("created_at"),
                    "created_by": data.get("created_by"),
                    "description": data.get("description"),
                    "schema_hash": data.get("schema_hash"),
                }
            )

        # Add current version if not in history yet
        current_version = project.label_config_version
        if current_version and current_version not in version_data:
            versions.append(
                {
                    "version": current_version,
                    "is_current": True,
                    "created_at": datetime.now().isoformat(),
                    "description": "Current schema (not yet archived)",
                }
            )

        # Sort by version number (v1, v2, v3, ...)
        versions.sort(key=lambda v: int(re.search(r'\d+', v["version"]).group()))

        return versions

    @staticmethod
    def compare_versions(project: Project, version1: str, version2: str) -> Dict:
        """
        Compare two schema versions and identify changes.

        Args:
            project: Project instance
            version1: First version to compare
            version2: Second version to compare

        Returns:
            Dict with comparison results
        """
        schema1 = LabelConfigVersionService.get_version_schema(project, version1)
        schema2 = LabelConfigVersionService.get_version_schema(project, version2)

        if not schema1 or not schema2:
            return {
                "error": "One or both versions not found",
                "version1": version1,
                "version2": version2,
            }

        # Extract field names from both schemas
        fields1 = LabelConfigVersionService._extract_field_names(schema1)
        fields2 = LabelConfigVersionService._extract_field_names(schema2)

        # Compute differences
        fields_added = set(fields2) - set(fields1)
        fields_removed = set(fields1) - set(fields2)
        fields_kept = set(fields1) & set(fields2)

        return {
            "version1": version1,
            "version2": version2,
            "fields_added": list(fields_added),
            "fields_removed": list(fields_removed),
            "fields_kept": list(fields_kept),
            "schema1_hash": LabelConfigVersionService.compute_schema_hash(schema1),
            "schema2_hash": LabelConfigVersionService.compute_schema_hash(schema2),
            "has_breaking_changes": len(fields_removed) > 0,
        }

    @staticmethod
    def _extract_field_names(label_config: str) -> List[str]:
        """
        Extract field names from a Label Studio XML config.

        Args:
            label_config: XML schema string

        Returns:
            List of field names
        """
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(label_config)
            field_names = []

            # Find all elements with 'name' attribute
            for elem in root.iter():
                if elem.tag in ["Choices", "TextArea", "Rating", "Number", "Text", "DateTime"]:
                    name = elem.get("name")
                    if name:
                        field_names.append(name)

            return field_names
        except ET.ParseError:
            return []

    @staticmethod
    def get_generation_version_distribution(project_id: str, db) -> Dict[str, int]:
        """
        Get count of generations per schema version.

        Args:
            project_id: Project ID
            db: Database session

        Returns:
            Dict mapping version → count
        """
        from sqlalchemy import func

        from models import Generation

        # Query generation counts grouped by version
        results = (
            db.query(Generation.label_config_version, func.count(Generation.id).label('count'))
            .join("generation")  # Join with ResponseGeneration
            .filter(Generation.label_config_version.isnot(None))
            .group_by(Generation.label_config_version)
            .all()
        )

        return {version: count for version, count in results}
