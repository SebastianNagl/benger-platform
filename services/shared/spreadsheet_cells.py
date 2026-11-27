"""Cells for CSV files that people open in a spreadsheet.

Excel and LibreOffice run a cell that starts with ``=``, ``+``, ``-``, ``@``,
a tab or a carriage return as a formula, so free text written by a
participant (``=HYPERLINK(...)``) must not reach a cell unchanged. A leading
apostrophe makes the spreadsheet show the text as it was typed.
"""

from typing import Any

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def formula_safe(value: Any) -> Any:
    """A text cell a spreadsheet will not run as a formula (other values unchanged)."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value
