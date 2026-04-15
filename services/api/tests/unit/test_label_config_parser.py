"""
Unit tests for label config parsing.
Tests field extraction and attribute parsing.
Issue #798: Label config parsing coverage
"""


from label_config_parser import LabelConfigParser


class TestFieldExtraction:
    """Test field extraction from label configs"""

    def test_extract_choices_field(self):
        """Extract Choices field metadata"""
        xml = """<View>
  <Choices name="sentiment" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
    <Choice value="neutral"/>
  </Choices>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "sentiment"
        assert field["type"] == "Choices"
        assert field["toName"] == "text"
        assert field["options"] == ["positive", "negative", "neutral"]
        assert "name" in field["attributes"]
        assert "toName" in field["attributes"]

    def test_extract_textarea_field(self):
        """Extract TextArea field"""
        xml = """<View>
  <TextArea name="comment" toName="text" placeholder="Enter comments"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "comment"
        assert field["type"] == "TextArea"
        assert field["toName"] == "text"
        assert field["attributes"]["placeholder"] == "Enter comments"

    def test_extract_rating_field(self):
        """Extract Rating field"""
        xml = """<View>
  <Rating name="quality" toName="text" maxRating="5"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "quality"
        assert field["type"] == "Rating"
        assert field["toName"] == "text"
        assert field["maxRating"] == 5

    def test_extract_number_field(self):
        """Extract Number field"""
        xml = """<View>
  <Number name="count" toName="text" min="0" max="100"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "count"
        assert field["type"] == "Number"
        assert field["toName"] == "text"
        assert field["min"] == 0.0
        assert field["max"] == 100.0

    def test_extract_text_field(self):
        """Extract Text field"""
        xml = """<View>
  <Text name="title" value="$title"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "title"
        assert field["type"] == "Text"
        assert field["attributes"]["value"] == "$title"

    def test_extract_datetime_field(self):
        """Extract DateTime field"""
        xml = """<View>
  <DateTime name="timestamp" toName="text" format="YYYY-MM-DD"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "timestamp"
        assert field["type"] == "DateTime"
        assert field["toName"] == "text"
        assert field["attributes"]["format"] == "YYYY-MM-DD"

    def test_extract_multiple_fields(self):
        """Extract all fields from complex config"""
        xml = """<View>
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <Choice value="positive"/>
    <Choice value="negative"/>
  </Choices>
  <Rating name="confidence" toName="text" maxRating="5"/>
  <TextArea name="notes" toName="text"/>
  <Number name="score" toName="text" min="0" max="10"/>
  <DateTime name="created_at" toName="text"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 6
        field_names = [f["name"] for f in fields]
        assert "text" in field_names
        assert "label" in field_names
        assert "confidence" in field_names
        assert "notes" in field_names
        assert "score" in field_names
        assert "created_at" in field_names

        # Verify types
        field_types = {f["name"]: f["type"] for f in fields}
        assert field_types["text"] == "Text"
        assert field_types["label"] == "Choices"
        assert field_types["confidence"] == "Rating"
        assert field_types["notes"] == "TextArea"
        assert field_types["score"] == "Number"
        assert field_types["created_at"] == "DateTime"

    def test_extract_field_names_only(self):
        """Get just field names"""
        xml = """<View>
  <Choices name="category" toName="text">
    <Choice value="A"/>
    <Choice value="B"/>
  </Choices>
  <TextArea name="notes" toName="text"/>
  <Rating name="quality" toName="text"/>
</View>"""

        field_names = LabelConfigParser.extract_field_names(xml)

        assert len(field_names) == 3
        assert "category" in field_names
        assert "notes" in field_names
        assert "quality" in field_names


class TestAttributeParsing:
    """Test attribute parsing from fields"""

    def test_parse_field_attributes(self):
        """Extract all attributes"""
        xml = """<View>
  <Choices name="label" toName="text" choice="single" required="true">
    <Choice value="A"/>
  </Choices>
</View>"""

        attributes = LabelConfigParser.parse_field_attributes(xml, "label")

        assert attributes["name"] == "label"
        assert attributes["toName"] == "text"
        assert attributes["choice"] == "single"
        assert attributes["required"] == "true"

    def test_parse_choices_options(self):
        """Extract Choice options"""
        xml = """<View>
  <Choices name="category" toName="text">
    <Choice value="sports"/>
    <Choice value="politics"/>
    <Choice value="technology"/>
  </Choices>
</View>"""

        field = LabelConfigParser.get_field_by_name(xml, "category")

        assert field is not None
        assert "options" in field
        assert field["options"] == ["sports", "politics", "technology"]

    def test_parse_nested_attributes(self):
        """Nested element attributes"""
        xml = """<View>
  <Choices name="label" toName="text" showInline="true">
    <Choice value="yes" selected="true"/>
    <Choice value="no"/>
  </Choices>
</View>"""

        field = LabelConfigParser.get_field_by_name(xml, "label")

        assert field is not None
        assert field["attributes"]["showInline"] == "true"
        # Options should still be extracted (values only)
        assert field["options"] == ["yes", "no"]

    def test_parse_default_values(self):
        """Default attribute values"""
        xml = """<View>
  <Rating name="rating" toName="text"/>
</View>"""

        field = LabelConfigParser.get_field_by_name(xml, "rating")

        assert field is not None
        # maxRating not specified, should not be in field
        assert "maxRating" not in field
        # But attributes should contain what's present
        assert field["attributes"]["name"] == "rating"
        assert field["attributes"]["toName"] == "text"


class TestErrorHandling:
    """Test error handling in parsing"""

    def test_parse_invalid_xml_gracefully(self):
        """Invalid XML handled"""
        invalid_xml = """<View>
  <Choices name="label"
</View>"""

        fields = LabelConfigParser.extract_fields(invalid_xml)
        assert fields == []

        field_names = LabelConfigParser.extract_field_names(invalid_xml)
        assert field_names == []

        field = LabelConfigParser.get_field_by_name(invalid_xml, "label")
        assert field is None

    def test_parse_empty_config(self):
        """Empty config handled"""
        fields = LabelConfigParser.extract_fields("")
        assert fields == []

        fields = LabelConfigParser.extract_fields(None)
        assert fields == []

        field_names = LabelConfigParser.extract_field_names("")
        assert field_names == []

        field = LabelConfigParser.get_field_by_name("", "test")
        assert field is None

    def test_unknown_field_type_handling(self):
        """Unknown types handled"""
        xml = """<View>
  <UnknownField name="test" toName="text"/>
  <Choices name="valid" toName="text">
    <Choice value="A"/>
  </Choices>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        # Should only extract the known Choices field
        assert len(fields) == 1
        assert fields[0]["name"] == "valid"
        assert fields[0]["type"] == "Choices"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_field_without_name_attribute(self):
        """Fields without name attribute are ignored"""
        xml = """<View>
  <Choices toName="text">
    <Choice value="A"/>
  </Choices>
  <Choices name="valid" toName="text">
    <Choice value="B"/>
  </Choices>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert fields[0]["name"] == "valid"

    def test_field_without_toname(self):
        """Fields without toName still extracted"""
        xml = """<View>
  <Text name="standalone" value="$data"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert fields[0]["name"] == "standalone"
        assert "toName" not in fields[0]

    def test_choices_without_options(self):
        """Choices field with no Choice children"""
        xml = """<View>
  <Choices name="empty" toName="text"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        assert fields[0]["name"] == "empty"
        assert fields[0]["options"] == []

    def test_rating_without_max(self):
        """Rating field without maxRating attribute"""
        xml = """<View>
  <Rating name="rating" toName="text"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["name"] == "rating"
        assert "maxRating" not in field

    def test_number_with_only_min(self):
        """Number field with only min attribute"""
        xml = """<View>
  <Number name="value" toName="text" min="0"/>
</View>"""

        fields = LabelConfigParser.extract_fields(xml)

        assert len(fields) == 1
        field = fields[0]
        assert field["min"] == 0.0
        assert "max" not in field

    def test_get_nonexistent_field(self):
        """Get field by name when it doesn't exist"""
        xml = """<View>
  <Choices name="exists" toName="text">
    <Choice value="A"/>
  </Choices>
</View>"""

        field = LabelConfigParser.get_field_by_name(xml, "doesnotexist")
        assert field is None


class TestValidation:
    """Test config validation functionality"""

    def test_validate_valid_config(self):
        """Validate valid configuration"""
        xml = """<View>
  <Choices name="label" toName="text">
    <Choice value="A"/>
  </Choices>
  <TextArea name="notes" toName="text"/>
</View>"""

        result = LabelConfigParser.validate_config(xml)

        assert result["valid"] is True
        assert result["field_count"] == 2
        assert "Choices" in result["field_types"]
        assert "TextArea" in result["field_types"]

    def test_validate_empty_config(self):
        """Validate empty configuration"""
        result = LabelConfigParser.validate_config("")

        assert result["valid"] is False
        assert "error" in result
        assert "Empty configuration" in result["error"]

    def test_validate_invalid_xml(self):
        """Validate malformed XML"""
        invalid_xml = """<View>
  <Choices name="test"
</View>"""

        result = LabelConfigParser.validate_config(invalid_xml)

        assert result["valid"] is False
        assert "error" in result
        assert "Invalid XML" in result["error"]

    def test_validate_no_fields(self):
        """Validate config with no valid fields"""
        xml = """<View>
  <SomeTag>Content</SomeTag>
</View>"""

        result = LabelConfigParser.validate_config(xml)

        assert result["valid"] is False
        assert "error" in result
        assert "No valid fields found" in result["error"]

    def test_validate_duplicate_field_names(self):
        """Validate config with duplicate field names"""
        xml = """<View>
  <Choices name="label" toName="text">
    <Choice value="A"/>
  </Choices>
  <TextArea name="label" toName="text"/>
</View>"""

        result = LabelConfigParser.validate_config(xml)

        assert result["valid"] is False
        assert "error" in result
        assert "Duplicate field names" in result["error"]
        assert "label" in result["error"]

