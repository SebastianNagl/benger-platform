"""ASCII sanitization for S3/MinIO object metadata.

S3 user-defined object metadata travels in HTTP headers, so boto3 rejects
any non-ASCII value at parameter-validation time ("Non ascii characters
found in S3 metadata"). Export filenames are derived from project titles,
which are frequently non-ASCII ("ZJS_Fälle_export.json"), so every dict
handed to boto3 as ``Metadata`` must pass through here first.

Values are percent-encoded (UTF-8, RFC 3986) only when they contain
non-ASCII characters; pure-ASCII values are passed through byte-identical
so existing objects' metadata stays comparable. The encoding is reversible
with ``urllib.parse.unquote`` — but the metadata is informational only; the
authoritative filename for downloads lives in the DB (uploaded_data /
export_jobs), never in S3 metadata.
"""

from typing import Dict
from urllib.parse import quote


def ascii_safe_metadata(metadata: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of ``metadata`` whose values are guaranteed ASCII."""
    safe = {}
    for key, value in metadata.items():
        value = str(value)
        if not value.isascii():
            value = quote(value, safe=" /.,-_()")
        safe[key] = value
    return safe
