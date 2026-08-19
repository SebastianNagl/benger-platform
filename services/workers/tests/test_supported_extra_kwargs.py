"""``_supported_extra_kwargs`` — signature-probing kwargs filter.

The Falllösung bulk branch passes the newer context kwargs
(korrekturhinweise / bearbeitervermerk / zusatzmaterial) to the extended
hook only when the installed benger_extended version accepts them. A wrong
filter either TypeErrors old hooks (kwarg leaked through) or silently drops
grading context on new ones (kwarg withheld).
"""

from evaluation.cell_evaluator import _supported_extra_kwargs


def _new_hook(*, sachverhalt="", korrekturhinweise="", bearbeitervermerk="",
              zusatzmaterial=""):
    pass


def _old_hook(*, sachverhalt=""):
    pass


PAIRS = (
    ("korrekturhinweise", "Hinweis"),
    ("bearbeitervermerk", None),
    ("zusatzmaterial", "Auszug"),
)


def test_new_hook_receives_all_supported_kwargs_stringified():
    out = _supported_extra_kwargs(_new_hook, PAIRS)
    # Falsy values become "" (the hook's neutral default), never None.
    assert out == {
        "korrekturhinweise": "Hinweis",
        "bearbeitervermerk": "",
        "zusatzmaterial": "Auszug",
    }


def test_old_hook_gets_nothing_it_does_not_accept():
    assert _supported_extra_kwargs(_old_hook, PAIRS) == {}


def test_partial_support_filters_per_kwarg():
    def hook(*, sachverhalt="", korrekturhinweise=""):
        pass

    assert _supported_extra_kwargs(hook, PAIRS) == {"korrekturhinweise": "Hinweis"}


def test_non_string_values_are_stringified():
    def hook(*, zusatzmaterial=""):
        pass

    assert _supported_extra_kwargs(hook, (("zusatzmaterial", 42),)) == {
        "zusatzmaterial": "42"
    }
