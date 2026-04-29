"""
Unit tests for label config validation

Tests XML validation, field type validation, and security for label configurations.
Implements comprehensive test coverage for Issue #798: Critical gap in label config validation

Test Categories:
1. XML Validation (8 tests) - Well-formedness, parsing, size limits
2. Field Type Validation (5 tests) - Supported types, required attributes
3. Security Tests (4 tests) - XXE, entity expansion, injection
4. Attribute Validation (3 tests) - Required attributes, duplicates, values
5. Error Handling (3 tests) - Error messages, structure, multiple errors
6. Edge Cases (2 tests) - Whitespace, special characters

Total: 25 tests
"""


from label_config_validator import LabelConfigValidator


class TestExtensionFieldTypes:
    """Tags registered via register_field_types are accepted by the validator."""

    def teardown_method(self):
        # Avoid leaking registrations across tests
        LabelConfigValidator._EXTENSION_FIELD_TYPES.clear()
        LabelConfigValidator._EXTENSION_NAMED_FIELD_TYPES.clear()

    def test_unknown_tag_is_rejected_by_default(self):
        xml = '<View><Angabe name="a" toName="x"/></View>'
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("Unsupported field type: 'Angabe'" in e for e in errors)

    def test_registered_tag_is_accepted(self):
        LabelConfigValidator.register_field_types(
            ["Angabe", "Notizen", "Gliederung", "Loesung"],
            named_types=["Angabe", "Notizen", "Gliederung", "Loesung"],
        )
        xml = """<View>
  <Angabe name="angabe" toName="sachverhalt"/>
  <Notizen name="notizen" toName="sachverhalt"/>
  <Gliederung name="gliederung" toName="sachverhalt"/>
  <Loesung name="loesung" toName="sachverhalt"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True, errors

    def test_registered_named_type_still_requires_name(self):
        LabelConfigValidator.register_field_types(
            ["Angabe"], named_types=["Angabe"]
        )
        xml = '<View><Angabe toName="x"/></View>'
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("requires a 'name' attribute" in e for e in errors)


class TestXMLValidation:
    """Test XML parsing and well-formedness validation"""

    def test_valid_xml_parsing(self):
        """Valid XML should parse successfully"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_malformed_xml_unclosed_tags(self):
        """Unclosed tags should be rejected"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <Choice value="positive"/>
  </Choices>
"""  # Missing </View>
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert len(errors) > 0
        assert any("parsing failed" in err.lower() for err in errors)

    def test_malformed_xml_invalid_chars(self):
        """Invalid XML characters should be rejected"""
        xml = """<View>
  <Text name="text" value="$text" invalid-attr="value with & unescaped"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert len(errors) > 0

    def test_empty_xml(self):
        """Empty string should be rejected"""
        is_valid, errors = LabelConfigValidator.validate("")
        assert is_valid is False
        assert len(errors) > 0
        assert any("empty" in err.lower() for err in errors)

    def test_none_xml(self):
        """None value should be rejected"""
        is_valid, errors = LabelConfigValidator.validate(None)
        assert is_valid is False
        assert len(errors) > 0
        assert any("none" in err.lower() for err in errors)

    def test_xml_with_comments(self):
        """Comments in XML should be handled properly"""
        xml = """<View>
  <!-- This is a comment -->
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <!-- Another comment -->
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_large_xml(self):
        """Large configs should be rejected if over size limit"""
        # Create a config that exceeds 10KB
        large_xml = '<View>\n' + '<Text name="text" value="$text"/>\n' * 500 + '</View>'

        if len(large_xml) > LabelConfigValidator.MAX_CONFIG_SIZE:
            is_valid, errors = LabelConfigValidator.validate(large_xml)
            assert is_valid is False
            assert any("maximum size" in err.lower() for err in errors)
        else:
            # If it's still under limit, it should pass
            is_valid, _ = LabelConfigValidator.validate(large_xml)
            assert is_valid is True

    def test_xml_declaration(self):
        """XML declaration should be handled properly"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<View>
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0


class TestFieldTypeValidation:
    """Test field type validation"""

    def test_valid_choices_field(self):
        """Valid Choices field should be accepted"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <Choices name="sentiment" toName="text" choice="single">
    <Choice value="positive"/>
    <Choice value="negative"/>
    <Choice value="neutral"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_valid_textarea_field(self):
        """Valid TextArea field should be accepted"""
        xml = """<View>
  <Text name="question" value="$question"/>
  <TextArea name="answer" toName="question" placeholder="Enter answer..." rows="5"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_valid_rating_field(self):
        """Valid Rating field should be accepted"""
        xml = """<View>
  <Text name="document" value="$document"/>
  <Rating name="quality" toName="document" maxRating="5" defaultValue="3"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_mixed_field_types(self):
        """Multiple different field types should work together"""
        xml = """<View>
  <Header value="Document Analysis"/>
  <Text name="document" value="$document"/>
  <Choices name="category" toName="document">
    <Choice value="legal"/>
    <Choice value="financial"/>
  </Choices>
  <TextArea name="notes" toName="document" placeholder="Notes..."/>
  <Rating name="confidence" toName="document" maxRating="5"/>
  <Checkbox name="needs_review" toName="document">
    <Label value="Needs Review"/>
  </Checkbox>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_unsupported_field_type(self):
        """Unsupported field type should be rejected"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <InvalidField name="bad" toName="text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("unsupported field type" in err.lower() for err in errors)
        assert any("InvalidField" in err for err in errors)


class TestSecurityValidation:
    """Test security vulnerability prevention"""

    def test_xxe_attack_prevention(self):
        """XXE injection should be blocked"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<View>
  <Text name="text" value="&xxe;"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("entity" in err.lower() for err in errors)

    def test_billion_laughs_prevention(self):
        """Entity expansion attack should be blocked"""
        xml = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<View>
  <Text name="text" value="&lol3;"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("entity" in err.lower() for err in errors)

    def test_script_injection(self):
        """Script tags should be sanitized/rejected"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <script>alert('XSS')</script>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("script" in err.lower() for err in errors)

    def test_external_entity_blocked(self):
        """External entities should be blocked"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY ext SYSTEM "http://evil.com/evil.dtd">
]>
<View>
  <Text name="text" value="&ext;"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("entity" in err.lower() or "system" in err.lower() for err in errors)


class TestAttributeValidation:
    """Test attribute validation"""

    def test_required_name_attribute(self):
        """Missing 'name' attribute on named fields should be rejected"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <Choices toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("name" in err.lower() and "attribute" in err.lower() for err in errors)

    def test_duplicate_field_names(self):
        """Duplicate field names should be rejected"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <Choice value="A"/>
  </Choices>
  <TextArea name="label" toName="text" placeholder="Notes..."/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("duplicate" in err.lower() and "label" in err for err in errors)

    def test_invalid_attribute_values(self):
        """Empty or invalid attribute values should be rejected"""
        xml = """<View>
  <Text name="" value="$text"/>
  <Choices name="label" toName="">
    <Choice value="positive"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert len(errors) > 0
        # Should report empty attribute values
        assert any("empty" in err.lower() or "cannot be empty" in err.lower() for err in errors)


class TestErrorHandling:
    """Test error message quality and structure"""

    def test_detailed_error_messages(self):
        """Error messages should be clear and actionable"""
        xml = """<View>
  <InvalidField name="bad"/>
  <Text name="" value="$text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert len(errors) > 0
        # Each error should have meaningful content
        for error in errors:
            assert len(error) > 10  # More than just a code
            assert isinstance(error, str)

    def test_validation_error_structure(self):
        """Validation should return structured results"""
        xml = """<View>
  <Text name="text" value="$text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)

        # Should return tuple
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

        # Valid config should have no errors
        assert is_valid is True
        assert len(errors) == 0

    def test_multiple_errors(self):
        """Multiple errors should be reported together"""
        xml = """<View>
  <InvalidField name="bad1"/>
  <Text name=""/>
  <Choices name="duplicate" toName="text">
    <Choice value="A"/>
  </Choices>
  <TextArea name="duplicate" toName="text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        # Should have multiple errors (at least 3: unsupported type, empty name, duplicate)
        assert len(errors) >= 3


class TestEdgeCases:
    """Test edge cases and special scenarios"""

    def test_whitespace_only(self):
        """Whitespace-only string should be rejected"""
        xml = "   \n  \t  \n   "
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("empty" in err.lower() for err in errors)

    def test_special_characters_in_names(self):
        """Field names with special characters should be validated"""
        # Valid: letters, numbers, underscores
        xml_valid = """<View>
  <Text name="field_name_123" value="$text"/>
  <Choices name="_private_field" toName="field_name_123">
    <Choice value="A"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml_valid)
        assert is_valid is True
        assert len(errors) == 0

        # Invalid: spaces, hyphens
        xml_invalid = """<View>
  <Text name="field-name" value="$text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml_invalid)
        assert is_valid is False
        assert any("invalid field name" in err.lower() for err in errors)

        # Invalid: starting with number
        xml_invalid2 = """<View>
  <Text name="123field" value="$text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml_invalid2)
        assert is_valid is False
        assert any("invalid field name" in err.lower() for err in errors)


class TestRealWorldExamples:
    """Test with real-world label config examples from BenGER"""

    def test_qa_reasoning_template(self):
        """Test QA reasoning template from database.py"""
        xml = """<View>
  <Text name="case_name" value="$case_name"/>
  <Text name="area" value="$area"/>
  <Text name="fall" value="$fall"/>
  <Text name="prompt" value="$prompt"/>
  <Choices name="solution" toName="fall">
    <Choice value="Ja"/>
    <Choice value="Nein"/>
  </Choices>
  <TextArea name="reasoning" toName="fall" placeholder="Legal reasoning..." required="true"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_multiple_choice_template(self):
        """Test multiple choice template from template_service.py"""
        xml = """<View>
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
  <Text name="choice_a" value="A) $choice_a" style="margin-bottom: 5px;"/>
  <Text name="choice_b" value="B) $choice_b" style="margin-bottom: 5px;"/>
  <Text name="choice_c" value="C) $choice_c" style="margin-bottom: 5px;"/>
  <Text name="choice_d" value="D) $choice_d" style="margin-bottom: 5px;"/>
  <Header value="Confidence Level"/>
  <Rating name="confidence" toName="question" maxRating="5" defaultValue="3"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_generation_template(self):
        """Test generation template with quality assessment"""
        xml = """<View>
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
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_complex_nested_structure(self):
        """Test complex nested View structures"""
        xml = """<View>
  <Text name="document" value="$document_text" showLabel="true"/>
  <View style="margin-top: 24px; padding: 16px; background-color: #f7f7f7; border-radius: 8px">
    <Header value="Legal Analysis" level="3"/>
    <Choices name="is_relevant" toName="document" label="Is this document legally relevant?" choice="single" required="true" layout="horizontal">
      <Choice value="Yes" selected="false"/>
      <Choice value="No" selected="false"/>
    </Choices>
    <TextArea name="legal_justification" toName="document" label="Legal Justification" placeholder="Please explain your decision..." rows="4" required="true"/>
    <Choices name="confidence_level" toName="document" label="How confident are you?" choice="single" required="false" layout="vertical">
      <Choice value="Very Confident"/>
      <Choice value="Somewhat Confident"/>
      <Choice value="Not Confident"/>
    </Choices>
  </View>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0


class TestSecurityEventHandlers:
    """Additional security tests for event handlers and javascript"""

    def test_onclick_handler_blocked(self):
        """onclick event handler should be blocked"""
        xml = """<View>
  <Text name="text" value="$text" onclick="alert('XSS')"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("event handler" in err.lower() for err in errors)

    def test_onload_handler_blocked(self):
        """onload event handler should be blocked"""
        xml = """<View onload="maliciousCode()">
  <Text name="text" value="$text"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("event handler" in err.lower() for err in errors)

    def test_javascript_protocol_blocked(self):
        """javascript: protocol should be blocked"""
        xml = """<View>
  <Text name="text" value="$text" href="javascript:void(0)"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is False
        assert any("javascript" in err.lower() for err in errors)


class TestUnicodeFieldNames:
    """Test Unicode character support in field names (Issue #1026)"""

    def test_german_umlauts_in_field_name_allowed(self):
        """Field names with German umlauts should be accepted"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <TextArea name="Lösung" toName="text" placeholder="Enter answer..."/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_german_umlauts_in_display_elements_allowed(self):
        """German umlauts in display elements should be allowed"""
        xml = """<View>
  <Header value="Rechtliche Prüfung"/>
  <Text name="fall" value="$fall"/>
  <TextArea name="solution" toName="fall" placeholder="Geben Sie Ihre Lösung ein..."/>
  <Choices name="answer" toName="fall">
    <Choice value="Ja"/>
    <Choice value="Nein"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_multiple_unicode_field_names_allowed(self):
        """Multiple Unicode field names should all be accepted"""
        xml = """<View>
  <Text name="Fäll" value="$text"/>
  <TextArea name="Antwört" toName="Fäll" placeholder="Enter..."/>
  <Choices name="Bewërtung" toName="Fäll">
    <Choice value="A"/>
  </Choices>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_various_unicode_letters_allowed(self):
        """Various Unicode letters from different languages should be accepted"""
        test_cases = [
            ("café", "French accent"),
            ("naïve", "French diaeresis"),
            ("señor", "Spanish tilde"),
            ("日本語", "Japanese characters"),
            ("émoji", "Accented character"),
            ("Größe", "German sharp s and umlaut"),
            ("über", "German umlaut"),
        ]
        for name, description in test_cases:
            xml = f"""<View>
  <Text name="{name}" value="$text"/>
</View>"""
            is_valid, errors = LabelConfigValidator.validate(xml)
            assert is_valid is True, f"Should accept {description}: {name}"
            assert len(errors) == 0, f"Should have no errors for {name}"

    def test_invalid_identifiers_rejected(self):
        """Invalid identifiers should still be rejected"""
        invalid_names = [
            ("123start", "starting with number"),
            ("has-hyphen", "containing hyphen"),
            ("has space", "containing space"),
            ("has.dot", "containing dot"),
            ("", "empty string"),
        ]
        for name, description in invalid_names:
            if name:  # Skip empty string test here, handled separately
                xml = f"""<View>
  <Text name="{name}" value="$text"/>
</View>"""
                is_valid, errors = LabelConfigValidator.validate(xml)
                assert is_valid is False, f"Should reject {description}: {name}"
                assert len(errors) > 0, f"Should have errors for {name}"

    def test_full_german_legal_template(self):
        """Full German legal template with Unicode field names should work"""
        xml = """<View>
  <Header value="Rechtliche Fallanalyse"/>
  <Text name="Fäll" value="$fall"/>
  <Header value="Ihre Lösung"/>
  <TextArea name="Lösung" toName="Fäll" placeholder="Geben Sie Ihre rechtliche Begründung ein..." rows="5"/>
  <Header value="Bewertung"/>
  <Choices name="Urtëil" toName="Fäll" choice="single">
    <Choice value="Schuldig"/>
    <Choice value="Nicht schuldig"/>
    <Choice value="Freispruch"/>
  </Choices>
  <Rating name="Konfidënz" toName="Fäll" maxRating="5"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_ascii_field_names_still_work(self):
        """Verify ASCII field names continue to work correctly"""
        xml = """<View>
  <Text name="legal_case" value="$fall"/>
  <TextArea name="solution_text" toName="legal_case" placeholder="Lösung eingeben..."/>
  <Choices name="verdict_123" toName="legal_case">
    <Choice value="Schuldig"/>
    <Choice value="Nicht schuldig"/>
  </Choices>
  <Rating name="_internal_score" toName="legal_case" maxRating="5"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

    def test_underscore_prefix_with_unicode(self):
        """Field names starting with underscore followed by Unicode should work"""
        xml = """<View>
  <Text name="_privateÜber" value="$text"/>
  <TextArea name="_lösung" toName="_privateÜber"/>
</View>"""
        is_valid, errors = LabelConfigValidator.validate(xml)
        assert is_valid is True
        assert len(errors) == 0

