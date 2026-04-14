"""
Tests for label config parser output sanitization integration

Verifies that LabelConfigParser automatically sanitizes field metadata
to prevent XSS attacks (Issue #798)
"""


from label_config_parser import LabelConfigParser


class TestParserSanitization:
    """Test that parser sanitizes extracted field metadata"""

    def test_parser_sanitizes_malicious_field_names(self):
        """Parser should sanitize malicious field names by default"""
        # XML with entity-encoded script tag in field name
        xml = '''<View>
            <Text name="&lt;script&gt;alert('XSS')&lt;/script&gt;" value="$text"/>
        </View>'''

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        # After parsing, the XML entities become actual characters
        # But sanitizer should HTML-escape them back
        assert "<script>" not in fields[0]["name"]
        # The sanitized version should contain HTML-escaped script tags
        assert "script" in fields[0]["name"].lower()
        assert "&lt;" in fields[0]["name"] or "&amp;" in fields[0]["name"]

    def test_parser_sanitizes_choice_options(self):
        """Parser should sanitize malicious choice values"""
        xml = '''<View>
            <Choices name="label" toName="text">
                <Choice value="A"/>
                <Choice value="&lt;script&gt;alert('XSS')&lt;/script&gt;"/>
            </Choices>
        </View>'''

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert "options" in fields[0]
        # First option should be clean
        assert fields[0]["options"][0] == "A"
        # Second option should be sanitized
        assert "<script>" not in fields[0]["options"][1]

    def test_parser_can_skip_sanitization(self):
        """Parser should allow disabling sanitization when needed"""
        xml = '''<View>
            <Text name="&lt;script&gt;alert('XSS')&lt;/script&gt;" value="$text"/>
        </View>'''

        # With sanitization disabled (for internal processing)
        fields_unsanitized = LabelConfigParser.extract_fields(xml, sanitize=False)
        fields_sanitized = LabelConfigParser.extract_fields(xml, sanitize=True)

        # Unsanitized should contain the raw parsed value
        assert fields_unsanitized[0]["name"] != fields_sanitized[0]["name"]
        # Sanitized should not contain executable script tags
        assert "<script>" not in fields_sanitized[0]["name"]

    def test_parser_sanitizes_attributes(self):
        """Parser should sanitize all field attributes"""
        xml = '''<View>
            <Text name="test" value="$text" placeholder="&lt;script&gt;alert('XSS')&lt;/script&gt;"/>
        </View>'''

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        # Check that attributes are sanitized
        placeholder = fields[0]["attributes"].get("placeholder", "")
        assert "<script>" not in placeholder

    def test_extract_field_names_returns_sanitized_names(self):
        """extract_field_names should return sanitized names"""
        xml = '''<View>
            <Text name="&lt;script&gt;alert('XSS')&lt;/script&gt;" value="$text"/>
            <TextArea name="normal_name" toName="text"/>
        </View>'''

        field_names = LabelConfigParser.extract_field_names(xml)

        assert len(field_names) == 2
        # First name should be sanitized
        assert "<script>" not in field_names[0]
        # Second name should be unchanged
        assert field_names[1] == "normal_name"

    def test_get_field_by_name_returns_sanitized_field(self):
        """get_field_by_name should return sanitized field metadata"""
        xml = '''<View>
            <Choices name="label" toName="text">
                <Choice value="A"/>
                <Choice value="&lt;script&gt;alert('XSS')&lt;/script&gt;"/>
            </Choices>
        </View>'''

        field = LabelConfigParser.get_field_by_name(xml, "label")

        assert field is not None
        assert "options" in field
        # Options should be sanitized
        assert "<script>" not in field["options"][1]


class TestSanitizationDoesNotBreakLegitimateConfigs:
    """Ensure sanitization doesn't break normal label configs"""

    def test_normal_text_field(self):
        """Normal text fields should pass through unchanged"""
        xml = '<View><Text name="my_text" value="$text"/></View>'
        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert fields[0]["name"] == "my_text"
        assert fields[0]["type"] == "Text"

    def test_normal_choices_field(self):
        """Normal choices fields should work correctly"""
        xml = '''<View>
            <Choices name="sentiment" toName="text">
                <Choice value="Positive"/>
                <Choice value="Negative"/>
                <Choice value="Neutral"/>
            </Choices>
        </View>'''

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert fields[0]["name"] == "sentiment"
        assert fields[0]["options"] == ["Positive", "Negative", "Neutral"]

    def test_special_characters_in_normal_use(self):
        """Special characters used legitimately should be handled"""
        xml = '<View><Text name="user_email" value="$email" placeholder="user@example.com"/></View>'
        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert fields[0]["name"] == "user_email"
        # @ symbol should be preserved (HTML escaped)
        placeholder = fields[0]["attributes"]["placeholder"]
        assert "@" in placeholder or "&#64;" in placeholder or "&commat;" in placeholder
