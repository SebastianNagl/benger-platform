"""
Tests for label config output sanitization
Ensures XSS vulnerabilities are prevented at output layer

Addresses Issue #798: HIGH RISK - Stored XSS vulnerability in label config field names
"""


from label_config_sanitizer import LabelConfigSanitizer


class TestFieldNameSanitization:
    """Test field name sanitization"""

    def test_sanitize_script_tags(self):
        """Script tags should be HTML escaped"""
        malicious = "<script>alert('XSS')</script>"
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        # Should not contain actual script tags
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized

    def test_sanitize_event_handlers(self):
        """Event handlers should be removed"""
        malicious = "text onclick=alert('XSS')"
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        assert "onclick" not in sanitized

    def test_sanitize_javascript_protocol(self):
        """JavaScript protocol should be removed"""
        malicious = "javascript:alert('XSS')"
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        assert "javascript:" not in sanitized

    def test_sanitize_iframe(self):
        """Iframe tags should be escaped"""
        malicious = "<iframe src='evil.com'></iframe>"
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        assert "<iframe" not in sanitized
        assert "&lt;iframe" in sanitized

    def test_sanitize_normal_field_name(self):
        """Normal field names should pass through (but HTML escaped)"""
        normal = "my_field_name"
        sanitized = LabelConfigSanitizer.sanitize_field_name(normal)

        assert sanitized == "my_field_name"

    def test_sanitize_empty_string(self):
        """Empty strings should return as-is"""
        sanitized = LabelConfigSanitizer.sanitize_field_name("")
        assert sanitized == ""

    def test_sanitize_none(self):
        """None values should return as-is"""
        sanitized = LabelConfigSanitizer.sanitize_field_name(None)
        assert sanitized is None

    def test_sanitize_xml_entities(self):
        """XML entities in field names should be escaped"""
        malicious = "&lt;script&gt;alert('XSS')&lt;/script&gt;"
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        # After HTML escape, the &lt; becomes &amp;lt;
        assert "&lt;" not in sanitized or "&amp;lt;" in sanitized
        # Should not contain actual script tags
        assert "<script>" not in sanitized


class TestFieldDictSanitization:
    """Test field dictionary sanitization"""

    def test_sanitize_field_dict(self):
        """All string values in field dict should be sanitized"""
        field = {
            "name": "<script>alert('XSS')</script>",
            "type": "Choices",
            "options": ["A", "<script>alert('XSS')</script>"],
        }

        sanitized = LabelConfigSanitizer.sanitize_field(field)

        assert "<script>" not in sanitized["name"]
        assert "<script>" not in sanitized["options"][1]
        assert "&lt;script&gt;" in sanitized["name"]

    def test_sanitize_nested_dict(self):
        """Nested dictionaries should be sanitized recursively"""
        field = {
            "name": "test",
            "attributes": {
                "placeholder": "<script>alert('XSS')</script>",
                "value": "normal",
            },
        }

        sanitized = LabelConfigSanitizer.sanitize_field(field)

        assert "<script>" not in sanitized["attributes"]["placeholder"]
        assert "&lt;script&gt;" in sanitized["attributes"]["placeholder"]
        assert sanitized["attributes"]["value"] == "normal"

    def test_sanitize_non_string_values(self):
        """Non-string values should pass through unchanged"""
        field = {"name": "test", "maxRating": 5, "required": True, "choices": None}

        sanitized = LabelConfigSanitizer.sanitize_field(field)

        assert sanitized["maxRating"] == 5
        assert sanitized["required"] is True
        assert sanitized["choices"] is None

    def test_sanitize_non_dict_input(self):
        """Non-dict inputs should return as-is"""
        result = LabelConfigSanitizer.sanitize_field("not a dict")
        assert result == "not a dict"

        result = LabelConfigSanitizer.sanitize_field(None)
        assert result is None


class TestLabelConfigResponseSanitization:
    """Test full label config sanitization"""

    def test_sanitize_xml_for_display(self):
        """XML should be escaped for safe display"""
        xml = '<View><Text name="text" value="$text"/></View>'
        sanitized = LabelConfigSanitizer.sanitize_label_config_response(xml)

        # Should be HTML escaped for display
        assert "&lt;View&gt;" in sanitized
        assert "<View>" not in sanitized

    def test_sanitize_xml_with_malicious_content(self):
        """XML with malicious content should be escaped"""
        xml = '<View><Text name="<script>alert(\'XSS\')</script>" value="$text"/></View>'
        sanitized = LabelConfigSanitizer.sanitize_label_config_response(xml)

        # Should not contain actual script tags
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized

    def test_sanitize_empty_xml(self):
        """Empty XML should return as-is"""
        sanitized = LabelConfigSanitizer.sanitize_label_config_response("")
        assert sanitized == ""

    def test_sanitize_none_xml(self):
        """None should return as-is"""
        sanitized = LabelConfigSanitizer.sanitize_label_config_response(None)
        assert sanitized is None


class TestXSSVectors:
    """Test against known XSS attack vectors from Issue #798"""

    def test_xss_vector_xml_entities(self):
        """Test the exact XSS vector from Issue #798"""
        # Attack vector: XML entities that become malicious after parsing
        malicious_name = "&lt;script&gt;alert('XSS')&lt;/script&gt;"

        # After XML parsing, this becomes: <script>alert('XSS')</script>
        # Our sanitizer should handle this
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious_name)

        # Should not contain executable script tags
        assert "<script>" not in sanitized
        assert "alert" in sanitized  # But content is still visible (escaped)

    def test_xss_vector_direct_tags(self):
        """Test direct script tag injection"""
        malicious = "<script>alert('XSS')</script>"
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized

    def test_xss_vector_img_onerror(self):
        """Test img tag with onerror handler"""
        malicious = '<img src=x onerror=alert("XSS")>'
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        assert "onerror" not in sanitized
        assert "<img" not in sanitized

    def test_xss_vector_svg_onload(self):
        """Test SVG with onload handler"""
        malicious = '<svg onload=alert("XSS")>'
        sanitized = LabelConfigSanitizer.sanitize_field_name(malicious)

        assert "onload" not in sanitized
        assert "<svg" not in sanitized
