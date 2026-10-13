"""Opaque cursors of the public API."""

import base64
import json

import pytest

from routers.v1._errors import V1Error
from routers.v1._pagination import decode_cursor, encode_cursor, page


def test_round_trip_and_no_padding():
    cursor = encode_cursor("tasks", {"inner_id": 7, "id": "t-7"})
    assert "=" not in cursor
    assert decode_cursor("tasks", cursor) == {"inner_id": 7, "id": "t-7"}


def test_first_page_has_no_position():
    assert decode_cursor("tasks", None) is None
    assert decode_cursor("tasks", "") is None


@pytest.mark.parametrize("cursor", ["not base64 !!", "e30", "W10"])  # "{}" lacks k, "[]"
def test_malformed_cursor_is_400(cursor):
    with pytest.raises(V1Error) as exc:
        decode_cursor("tasks", cursor)
    assert exc.value.status_code == 400 and exc.value.code == "invalid_cursor"


def test_cursor_of_another_list_is_rejected():
    cursor = encode_cursor("projects", {"id": "p"})
    with pytest.raises(V1Error):
        decode_cursor("tasks", cursor)


def test_page_split():
    rows = list(range(6))
    items, nxt = page("n", rows, 5, lambda r: {"v": r})
    assert items == [0, 1, 2, 3, 4]
    assert decode_cursor("n", nxt) == {"v": 4}
    items, nxt = page("n", rows[:3], 5, lambda r: {"v": r})
    assert items == [0, 1, 2] and nxt is None
    raw = json.loads(base64.urlsafe_b64decode(encode_cursor("n", {"v": 1}) + "=="))
    assert raw == {"k": "n", "v": 1}
