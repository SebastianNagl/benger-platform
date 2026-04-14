"""
JSON Deep Merge Utility

Provides deep merging functionality for nested dictionaries, specifically designed
for handling PostgreSQL JSONB fields where partial updates should preserve existing
nested structures.

Issue #818: Prevent generation_config updates from overwriting unrelated fields
"""

from typing import Any, Dict, Optional


def deep_merge_dicts(
    base: Optional[Dict[str, Any]], update: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Deep merge two dictionaries, preserving nested structures.

    Merging rules:
    - Nested dicts are merged recursively
    - Lists are replaced (not concatenated)
    - None values in update remove the key from base
    - If base or update is None/empty, handles gracefully

    Args:
        base: Original dictionary (can be None)
        update: Dictionary with updates (can be None)

    Returns:
        Merged dictionary (new dict, doesn't modify inputs)

    Examples:
        >>> base = {"a": {"b": 1, "c": 2}, "d": [1, 2]}
        >>> update = {"a": {"c": 3, "e": 4}, "f": 5}
        >>> deep_merge_dicts(base, update)
        {"a": {"b": 1, "c": 3, "e": 4}, "d": [1, 2], "f": 5}

        >>> base = {"selected_configuration": {"models": ["gpt-4"], "active_structures": ["s1", "s2"]}}
        >>> update = {"selected_configuration": {"models": ["claude-3"]}}
        >>> result = deep_merge_dicts(base, update)
        >>> result["selected_configuration"]["active_structures"]
        ["s1", "s2"]  # Preserved!
    """
    # Handle None/empty cases
    if base is None or base == {}:
        return update.copy() if update else {}
    if update is None or update == {}:
        return base.copy()

    # Create a copy to avoid modifying the input
    result = base.copy()

    for key, value in update.items():
        if value is None:
            # None values remove the key
            result.pop(key, None)
        elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = deep_merge_dicts(result[key], value)
        else:
            # Replace value (includes primitives, lists, and new keys)
            result[key] = value

    return result
