"""
Canonical annotation value extraction for Label Studio results.

All services (API, workers) should use these functions instead of
implementing their own extraction logic. Handles all value types:
text, markdown, choices, rating, number, spans/labels.
"""

from typing import Any, Dict, List, Optional


def _normalize_german(s: str) -> str:
    """Lowercase and normalize German umlauts for matching."""
    return (
        s.lower()
        .replace("ö", "oe")
        .replace("ä", "ae")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _extract_value(result: Dict, return_first_choice: bool = True) -> Any:
    """Extract the actual value from a single annotation result item.

    Checks keys in order: spans (for labels type), text, markdown,
    choices, rating, number. Returns the first match.

    If ``value`` is not a dict (e.g. a bare string from a textarea region
    that the annotator submitted empty), it is returned as-is or as None
    when empty — without indexing it as a dict.
    """
    value = result.get("value", {})
    result_type = result.get("type")

    if not isinstance(value, dict):
        # Bare scalar (string from a textarea region, list from spans, etc.)
        if isinstance(value, str):
            return value or None
        if isinstance(value, list):
            return value[0] if return_first_choice and value else value
        return value if value not in (None, "", [], {}) else None

    if result_type == "labels" and "spans" in value:
        return value.get("spans", [])

    if "text" in value:
        text = value["text"]
        return text[0] if isinstance(text, list) and text else text

    if "markdown" in value:
        return value["markdown"]

    if "choices" in value:
        choices = value["choices"]
        if return_first_choice:
            return choices[0] if choices else None
        return choices

    if "rating" in value:
        return str(value["rating"])

    if "number" in value:
        return str(value["number"])

    return None


def extract_field_value(
    results: List[Dict],
    field_name: str,
    *,
    normalize_umlauts: bool = True,
    return_first_choice: bool = True,
) -> Any:
    """Extract a field value from Label Studio annotation results.

    Args:
        results: List of annotation result items (each has from_name, value, type).
        field_name: The field name to match against from_name.
        normalize_umlauts: If True, match with German umlaut normalization.
        return_first_choice: If True, return only the first choice for Choices fields.

    Returns:
        Extracted value, or None if the field is not found.
    """
    if not results or not isinstance(results, list):
        return None

    field_lower = field_name.lower()
    field_normalized = _normalize_german(field_name) if normalize_umlauts else field_lower

    for result in results:
        from_name = result.get("from_name", "")
        from_lower = from_name.lower()

        if from_lower == field_lower:
            return _extract_value(result, return_first_choice)

        if normalize_umlauts and _normalize_german(from_name) == field_normalized:
            return _extract_value(result, return_first_choice)

    return None


def extract_all_field_values(
    results: List[Dict],
    *,
    return_first_choice: bool = True,
) -> Dict[str, Any]:
    """Extract all field values from annotation results into a dict.

    Args:
        results: List of annotation result items.
        return_first_choice: If True, return only the first choice for Choices fields.

    Returns:
        Dict mapping from_name to extracted value.
    """
    if not results or not isinstance(results, list):
        return {}

    field_values = {}
    for result in results:
        from_name = result.get("from_name")
        if not from_name:
            continue
        extracted = _extract_value(result, return_first_choice)
        if extracted is not None:
            field_values[from_name] = extracted

    return field_values


def extract_first_value(results: List[Dict]) -> Any:
    """Extract the first extractable value from any result.

    Scans all results regardless of field name, returns the first
    value found (any type: text, markdown, choices, rating, number).
    """
    if not results or not isinstance(results, list):
        return None

    for result in results:
        extracted = _extract_value(result)
        if extracted is not None:
            return extracted

    return None


def extract_first_text_value(results: List[Dict]) -> Optional[str]:
    """Extract the first text or markdown value found in any result.

    Scans all results regardless of field name, returns the first
    text/markdown value found. Ignores choices, rating, number.
    """
    if not results or not isinstance(results, list):
        return None

    for result in results:
        value = result.get("value", {})
        result_type = result.get("type")

        if result_type in ("textarea", "text") or "text" in value:
            text = value.get("text", [])
            if isinstance(text, list) and text:
                return text[0]
            elif isinstance(text, str):
                return text

        if "markdown" in value:
            md = value["markdown"]
            if isinstance(md, str) and md:
                return md

    return None
