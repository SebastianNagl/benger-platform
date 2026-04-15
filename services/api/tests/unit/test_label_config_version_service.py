"""
Comprehensive tests for label config version service.
Tests versioning, change detection, and schema comparison functionality.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from label_config_version_service import LabelConfigVersionService
from project_models import Project


class TestLabelConfigVersionService:
    """Test label config version service functionality"""

    @pytest.fixture
    def mock_project(self):
        """Create mock project for testing"""
        project = Mock(spec=Project)
        project.id = "test-project-123"
        project.created_by = "user-123"
        project.created_at = datetime(2025, 1, 1, 12, 0, 0)
        project.label_config = None
        project.label_config_version = None
        project.label_config_history = None
        return project

    @pytest.fixture
    def sample_xml_v1(self):
        """Sample Label Studio XML config v1"""
        return """<View>
  <Choices name="sentiment" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
  <TextArea name="comment" toName="text"/>
</View>"""

    @pytest.fixture
    def sample_xml_v2(self):
        """Sample Label Studio XML config v2 with added field"""
        return """<View>
  <Choices name="sentiment" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
    <Choice value="neutral"/>
  </Choices>
  <TextArea name="comment" toName="text"/>
  <Rating name="confidence" toName="text"/>
</View>"""

    @pytest.fixture
    def sample_xml_v3(self):
        """Sample Label Studio XML config v3 with removed field"""
        return """<View>
  <Choices name="sentiment" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
</View>"""

    # ========================================
    # Version Incrementing Tests
    # ========================================

    def test_increment_version_from_none(self):
        """Test incrementing version from None returns v1"""
        result = LabelConfigVersionService.increment_version(None)
        assert result == "v1"

    def test_increment_version_v1_to_v2(self):
        """Test incrementing v1 to v2"""
        result = LabelConfigVersionService.increment_version("v1")
        assert result == "v2"

    def test_increment_version_v99_to_v100(self):
        """Test incrementing v99 to v100"""
        result = LabelConfigVersionService.increment_version("v99")
        assert result == "v100"

    def test_increment_version_invalid_format(self):
        """Test incrementing invalid format returns v1"""
        result = LabelConfigVersionService.increment_version("invalid")
        assert result == "v1"

    def test_increment_version_empty_string(self):
        """Test incrementing empty string returns v1"""
        result = LabelConfigVersionService.increment_version("")
        assert result == "v1"

    # ========================================
    # Schema Hash Computation Tests
    # ========================================

    def test_compute_schema_hash_deterministic(self, sample_xml_v1):
        """Test same input produces same hash"""
        hash1 = LabelConfigVersionService.compute_schema_hash(sample_xml_v1)
        hash2 = LabelConfigVersionService.compute_schema_hash(sample_xml_v1)
        assert hash1 == hash2
        assert len(hash1) == 12  # Truncated to 12 chars

    def test_compute_schema_hash_different(self, sample_xml_v1, sample_xml_v2):
        """Test different XML produces different hash"""
        hash1 = LabelConfigVersionService.compute_schema_hash(sample_xml_v1)
        hash2 = LabelConfigVersionService.compute_schema_hash(sample_xml_v2)
        assert hash1 != hash2

    def test_compute_schema_hash_empty(self):
        """Test empty string returns empty hash"""
        result = LabelConfigVersionService.compute_schema_hash("")
        assert result == ""

    def test_compute_schema_hash_none(self):
        """Test None returns empty hash"""
        result = LabelConfigVersionService.compute_schema_hash(None)
        assert result == ""

    def test_compute_schema_hash_whitespace_sensitive(self):
        """Test whitespace changes produce different hash"""
        xml1 = "<View><Choices name=\"test\"/></View>"
        xml2 = "<View>\n  <Choices name=\"test\"/>\n</View>"
        hash1 = LabelConfigVersionService.compute_schema_hash(xml1)
        hash2 = LabelConfigVersionService.compute_schema_hash(xml2)
        assert hash1 != hash2

    # ========================================
    # Change Detection Tests
    # ========================================

    def test_has_schema_changed_same(self, mock_project, sample_xml_v1):
        """Test no change when schemas are identical"""
        mock_project.label_config = sample_xml_v1
        result = LabelConfigVersionService.has_schema_changed(mock_project, sample_xml_v1)
        assert result is False

    def test_has_schema_changed_different(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test change detected when schemas differ"""
        mock_project.label_config = sample_xml_v1
        result = LabelConfigVersionService.has_schema_changed(mock_project, sample_xml_v2)
        assert result is True

    def test_has_schema_changed_whitespace_only(self, mock_project):
        """Test whitespace-only changes are detected"""
        xml1 = "<View><Choices name=\"test\"/></View>"
        xml2 = "<View>\n  <Choices name=\"test\"/>\n</View>"
        mock_project.label_config = xml1
        result = LabelConfigVersionService.has_schema_changed(mock_project, xml2)
        assert result is True

    def test_has_schema_changed_both_none(self, mock_project):
        """Test no change when both are None"""
        mock_project.label_config = None
        result = LabelConfigVersionService.has_schema_changed(mock_project, None)
        assert result is False

    def test_has_schema_changed_both_empty(self, mock_project):
        """Test no change when both are empty string"""
        mock_project.label_config = ""
        result = LabelConfigVersionService.has_schema_changed(mock_project, "")
        assert result is False

    def test_has_schema_changed_from_none_to_value(self, mock_project, sample_xml_v1):
        """Test change detected when going from None to value"""
        mock_project.label_config = None
        result = LabelConfigVersionService.has_schema_changed(mock_project, sample_xml_v1)
        assert result is True

    def test_has_schema_changed_from_value_to_none(self, mock_project, sample_xml_v1):
        """Test change detected when going from value to None"""
        mock_project.label_config = sample_xml_v1
        result = LabelConfigVersionService.has_schema_changed(mock_project, None)
        assert result is True

    # ========================================
    # Version History Update Tests
    # ========================================

    def test_update_version_history_first_time(self, mock_project, sample_xml_v1):
        """Test initializing version history for first time"""
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None

        new_version = LabelConfigVersionService.update_version_history(
            mock_project, sample_xml_v1, description="Initial schema", user_id="user-123"
        )

        # Service increments from v1 (default when None) to v2
        assert new_version == "v2"
        assert mock_project.label_config == sample_xml_v1
        assert mock_project.label_config_version == "v2"
        # No v1 in history since there was no previous schema
        assert mock_project.label_config_history == {"versions": {}, "current_version": "v2"}

    def test_update_version_history_preserve_old(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test old schema is preserved in history"""
        mock_project.label_config = sample_xml_v1
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = {"versions": {}}

        new_version = LabelConfigVersionService.update_version_history(
            mock_project, sample_xml_v2, description="Added confidence rating", user_id="user-456"
        )

        assert new_version == "v2"
        assert mock_project.label_config == sample_xml_v2
        assert mock_project.label_config_version == "v2"

        # Verify v1 was saved in history
        assert "v1" in mock_project.label_config_history["versions"]
        v1_entry = mock_project.label_config_history["versions"]["v1"]
        assert v1_entry["schema"] == sample_xml_v1
        assert v1_entry["created_by"] == "user-456"
        assert v1_entry["description"] == "Added confidence rating"
        assert "schema_hash" in v1_entry
        assert "created_at" in v1_entry

    def test_update_version_history_increment(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test version increments correctly"""
        mock_project.label_config = sample_xml_v1
        mock_project.label_config_version = "v5"
        mock_project.label_config_history = {"versions": {}}

        new_version = LabelConfigVersionService.update_version_history(mock_project, sample_xml_v2)

        assert new_version == "v6"
        assert mock_project.label_config_version == "v6"

    def test_update_version_history_metadata(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test user ID and description are saved correctly"""
        mock_project.label_config = sample_xml_v1
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = {"versions": {}}

        LabelConfigVersionService.update_version_history(
            mock_project, sample_xml_v2, description="Custom description", user_id="custom-user-789"
        )

        v1_entry = mock_project.label_config_history["versions"]["v1"]
        assert v1_entry["created_by"] == "custom-user-789"
        assert v1_entry["description"] == "Custom description"

    def test_update_version_history_no_description(
        self, mock_project, sample_xml_v1, sample_xml_v2
    ):
        """Test default description is used when not provided"""
        mock_project.label_config = sample_xml_v1
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = {"versions": {}}

        LabelConfigVersionService.update_version_history(
            mock_project, sample_xml_v2, user_id="user-123"
        )

        v1_entry = mock_project.label_config_history["versions"]["v1"]
        assert v1_entry["description"] == "Schema version v1"

    def test_update_version_history_no_user_id(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test created_by falls back to project creator when user_id not provided"""
        mock_project.label_config = sample_xml_v1
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = {"versions": {}}
        mock_project.created_by = "original-creator-999"

        LabelConfigVersionService.update_version_history(mock_project, sample_xml_v2)

        v1_entry = mock_project.label_config_history["versions"]["v1"]
        assert v1_entry["created_by"] == "original-creator-999"

    # ========================================
    # Version Retrieval Tests
    # ========================================

    def test_get_version_schema_current(self, mock_project, sample_xml_v2):
        """Test retrieving current version schema"""
        mock_project.label_config = sample_xml_v2
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": "<View></View>"}}}

        result = LabelConfigVersionService.get_version_schema(mock_project, "v2")
        assert result == sample_xml_v2

    def test_get_version_schema_historical(self, mock_project, sample_xml_v1):
        """Test retrieving old version schema from history"""
        mock_project.label_config = "<View><New/></View>"
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": sample_xml_v1}}}

        result = LabelConfigVersionService.get_version_schema(mock_project, "v1")
        assert result == sample_xml_v1

    def test_get_version_schema_not_found(self, mock_project):
        """Test retrieving non-existent version returns None"""
        mock_project.label_config = "<View></View>"
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": "<View></View>"}}}

        result = LabelConfigVersionService.get_version_schema(mock_project, "v99")
        assert result is None

    def test_get_version_schema_no_history(self, mock_project):
        """Test retrieving version when no history exists returns None"""
        mock_project.label_config = "<View></View>"
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = None

        result = LabelConfigVersionService.get_version_schema(mock_project, "v1")
        assert result is None

    # ========================================
    # Version Listing Tests
    # ========================================

    def test_list_versions_empty(self, mock_project):
        """Test listing versions when no history exists"""
        mock_project.label_config_version = None
        mock_project.label_config_history = None

        result = LabelConfigVersionService.list_versions(mock_project)
        assert result == []

    def test_list_versions_current_only(self, mock_project):
        """Test listing versions with only current version (no history)"""
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = None
        mock_project.created_at = datetime(2025, 1, 15, 10, 30, 0)

        result = LabelConfigVersionService.list_versions(mock_project)

        assert len(result) == 1
        assert result[0]["version"] == "v1"
        assert result[0]["is_current"] is True
        assert result[0]["description"] == "Current schema"

    def test_list_versions_multiple(self, mock_project):
        """Test listing multiple versions sorted correctly"""
        mock_project.label_config_version = "v3"
        mock_project.label_config_history = {
            "versions": {
                "v1": {
                    "created_at": "2025-01-01T10:00:00",
                    "created_by": "user-1",
                    "description": "Version 1",
                    "schema_hash": "abc123",
                },
                "v2": {
                    "created_at": "2025-01-02T10:00:00",
                    "created_by": "user-2",
                    "description": "Version 2",
                    "schema_hash": "def456",
                },
            }
        }

        result = LabelConfigVersionService.list_versions(mock_project)

        assert len(result) == 3  # v1, v2, v3
        # Should be sorted by version number
        assert result[0]["version"] == "v1"
        assert result[1]["version"] == "v2"
        assert result[2]["version"] == "v3"

    def test_list_versions_current_marker(self, mock_project):
        """Test is_current flag is set correctly"""
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {
            "versions": {
                "v1": {
                    "created_at": "2025-01-01T10:00:00",
                    "created_by": "user-1",
                    "description": "Version 1",
                    "schema_hash": "abc123",
                }
            }
        }

        result = LabelConfigVersionService.list_versions(mock_project)

        v1_entry = next(v for v in result if v["version"] == "v1")
        v2_entry = next(v for v in result if v["version"] == "v2")

        assert v1_entry["is_current"] is False
        assert v2_entry["is_current"] is True

    # ========================================
    # Version Comparison Tests
    # ========================================

    def test_compare_versions_fields_added(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test detecting added fields in version comparison"""
        mock_project.label_config = sample_xml_v2
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": sample_xml_v1}}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v2")

        assert result["version1"] == "v1"
        assert result["version2"] == "v2"
        assert "confidence" in result["fields_added"]  # Rating field added
        assert result["has_breaking_changes"] is False

    def test_compare_versions_fields_removed(self, mock_project, sample_xml_v1, sample_xml_v3):
        """Test detecting removed fields (breaking change)"""
        mock_project.label_config = sample_xml_v3
        mock_project.label_config_version = "v3"
        mock_project.label_config_history = {"versions": {"v1": {"schema": sample_xml_v1}}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v3")

        assert "comment" in result["fields_removed"]  # TextArea field removed
        assert result["has_breaking_changes"] is True

    def test_compare_versions_fields_renamed(self, mock_project):
        """Test detecting field rename (shows as remove + add)"""
        xml_before = """<View><Choices name="old_name"/></View>"""
        xml_after = """<View><Choices name="new_name"/></View>"""

        mock_project.label_config = xml_after
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": xml_before}}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v2")

        assert "old_name" in result["fields_removed"]
        assert "new_name" in result["fields_added"]
        assert result["has_breaking_changes"] is True

    def test_compare_versions_breaking_changes(self, mock_project, sample_xml_v1, sample_xml_v3):
        """Test has_breaking_changes flag is set correctly"""
        mock_project.label_config = sample_xml_v3
        mock_project.label_config_version = "v3"
        mock_project.label_config_history = {"versions": {"v1": {"schema": sample_xml_v1}}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v3")

        # Removing fields is a breaking change
        assert result["has_breaking_changes"] is True

    def test_compare_versions_no_breaking_changes(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test has_breaking_changes is False when only adding fields"""
        mock_project.label_config = sample_xml_v2
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": sample_xml_v1}}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v2")

        # Only adding fields, no breaking changes
        assert result["has_breaking_changes"] is False

    def test_compare_versions_version_not_found(self, mock_project):
        """Test comparison when one version doesn't exist"""
        mock_project.label_config = "<View></View>"
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = {"versions": {}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v99")

        assert "error" in result
        assert result["error"] == "One or both versions not found"

    def test_compare_versions_schema_hashes(self, mock_project, sample_xml_v1, sample_xml_v2):
        """Test schema hashes are included in comparison"""
        mock_project.label_config = sample_xml_v2
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {"versions": {"v1": {"schema": sample_xml_v1}}}

        result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v2")

        assert "schema1_hash" in result
        assert "schema2_hash" in result
        assert result["schema1_hash"] != result["schema2_hash"]

    # ========================================
    # Field Extraction Tests
    # ========================================

    def test_extract_field_names_choices(self):
        """Test extracting Choices field names"""
        xml = """<View>
  <Choices name="sentiment" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
</View>"""

        result = LabelConfigVersionService._extract_field_names(xml)
        assert "sentiment" in result
        assert len(result) == 1

    def test_extract_field_names_textarea(self):
        """Test extracting TextArea field names"""
        xml = """<View>
  <TextArea name="comment" toName="text"/>
</View>"""

        result = LabelConfigVersionService._extract_field_names(xml)
        assert "comment" in result
        assert len(result) == 1

    def test_extract_field_names_mixed(self):
        """Test extracting mixed field types"""
        xml = """<View>
  <Choices name="category" toName="text"/>
  <TextArea name="notes" toName="text"/>
  <Rating name="quality" toName="text"/>
  <Number name="count" toName="text"/>
</View>"""

        result = LabelConfigVersionService._extract_field_names(xml)
        assert "category" in result
        assert "notes" in result
        assert "quality" in result
        assert "count" in result
        assert len(result) == 4

    def test_extract_field_names_invalid_xml(self):
        """Test extracting field names from malformed XML returns empty list"""
        xml = "<View><Choices name=\"test\""  # Missing closing tags

        result = LabelConfigVersionService._extract_field_names(xml)
        assert result == []

    def test_extract_field_names_empty_xml(self):
        """Test extracting field names from empty XML"""
        result = LabelConfigVersionService._extract_field_names("")
        assert result == []

    def test_extract_field_names_no_name_attribute(self):
        """Test fields without name attribute are not extracted"""
        xml = """<View>
  <Choices toName="text">
    <Choice value="yes"/>
  </Choices>
</View>"""

        result = LabelConfigVersionService._extract_field_names(xml)
        assert len(result) == 0

    def test_extract_field_names_datetime_field(self):
        """Test extracting DateTime field names"""
        xml = """<View>
  <DateTime name="timestamp" toName="text"/>
</View>"""

        result = LabelConfigVersionService._extract_field_names(xml)
        assert "timestamp" in result

    def test_extract_field_names_text_field(self):
        """Test extracting Text field names"""
        xml = """<View>
  <Text name="title" toName="text"/>
</View>"""

        result = LabelConfigVersionService._extract_field_names(xml)
        assert "title" in result
