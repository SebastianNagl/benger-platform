"""Name labels (``shared/user_display.py``)."""

from types import SimpleNamespace

import pytest

from user_display import display_name, masked_name, prefers_pseudonym, pseudonym_hint

pytestmark = pytest.mark.unit


def _user(**overrides):
    base = {
        "name": "Erika Mustermann",
        "username": "erika",
        "pseudonym": "Kluge Eule",
        "use_pseudonym": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestDisplayName:
    def test_pseudonym_is_the_default_label(self):
        assert display_name(_user()) == "Kluge Eule"

    def test_privileged_viewer_gets_the_real_name(self):
        assert display_name(_user(), reveal_real_name=True) == "Erika Mustermann"
        assert display_name(_user(), True) == "Erika Mustermann"

    def test_real_name_falls_back_to_username(self):
        assert display_name(_user(name=None), reveal_real_name=True) == "erika"
        assert display_name(_user(name="   "), reveal_real_name=True) == "erika"

    def test_pseudonym_turned_off_shows_the_name(self):
        assert display_name(_user(use_pseudonym=False)) == "Erika Mustermann"

    def test_missing_pseudonym_shows_the_name(self):
        assert display_name(_user(pseudonym=None)) == "Erika Mustermann"
        assert display_name(_user(pseudonym="")) == "Erika Mustermann"
        assert display_name(_user(pseudonym=None, name=None)) == "erika"

    def test_unset_preference_keeps_the_pseudonym(self):
        # NULL / missing means the column default: pseudonym on.
        assert display_name(_user(use_pseudonym=None)) == "Kluge Eule"
        bare = SimpleNamespace(name="Erika", username="erika", pseudonym="Kluge Eule")
        assert display_name(bare) == "Kluge Eule"

    def test_objects_without_name_fields(self):
        assert display_name(SimpleNamespace(username="erika")) == "erika"
        assert display_name(SimpleNamespace()) == ""
        assert display_name(None) == ""

    def test_column_overrides_without_an_object(self):
        assert display_name(name="Erika", username="e", pseudonym="Eule") == "Eule"
        assert (
            display_name(name="Erika", pseudonym="Eule", reveal_real_name=True)
            == "Erika"
        )
        assert (
            display_name(name="Erika", pseudonym="Eule", use_pseudonym=False)
            == "Erika"
        )

    def test_override_wins_over_the_object(self):
        user = _user()
        assert display_name(user, pseudonym=None) == "Erika Mustermann"
        assert display_name(user, use_pseudonym=False) == "Erika Mustermann"
        assert display_name(user, name="Other", reveal_real_name=True) == "Other"

    def test_matches_the_orm_model(self):
        from models import User

        user = User(
            name="Erika Mustermann",
            username="erika",
            email="erika@example.com",
            pseudonym="Kluge Eule",
            use_pseudonym=True,
        )
        assert display_name(user) == "Kluge Eule"
        assert display_name(user, reveal_real_name=True) == "Erika Mustermann"


class TestPseudonymHint:
    def test_only_shown_next_to_a_revealed_real_name(self):
        assert pseudonym_hint(_user(), reveal_real_name=True) == "Kluge Eule"
        assert pseudonym_hint(_user(), reveal_real_name=False) is None

    def test_no_pseudonym_no_hint(self):
        assert pseudonym_hint(_user(pseudonym=None), reveal_real_name=True) is None
        assert pseudonym_hint(None, reveal_real_name=True) is None
        assert pseudonym_hint(pseudonym=" Eule ", reveal_real_name=True) == "Eule"


class TestPrefersPseudonym:
    def test_follows_the_preference(self):
        assert prefers_pseudonym(_user()) is True
        assert prefers_pseudonym(_user(use_pseudonym=False)) is False

    def test_unset_means_on(self):
        assert prefers_pseudonym(_user(use_pseudonym=None)) is True
        assert prefers_pseudonym(SimpleNamespace()) is True
        assert prefers_pseudonym(None) is True
        assert prefers_pseudonym(use_pseudonym=False) is False


class TestMaskedName:
    def test_shows_the_pseudonym(self):
        assert masked_name(_user()) == "Kluge Eule"
        # Even when the user turned it off: a masked row never falls back.
        assert masked_name(_user(use_pseudonym=False)) == "Kluge Eule"

    def test_neutral_label_without_a_pseudonym(self):
        user = SimpleNamespace(
            id="0123456789abcdef", name="Erika Mustermann", username="erika", pseudonym=None
        )
        assert masked_name(user) == "User 01234567"
        assert masked_name(user_id="abcdef0123", pseudonym="  ") == "User abcdef01"

    def test_never_empty(self):
        assert masked_name(None) == "User"
        assert masked_name(SimpleNamespace(name="Erika")) == "User"

