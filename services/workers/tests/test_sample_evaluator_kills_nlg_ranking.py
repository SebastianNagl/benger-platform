"""Mutation-kill tests for the NLG (``_compute_text_similarity``) and ranking
(``_compute_ranking_metric``) metric families in
``ml_evaluation/sample_evaluator.py``.

Each test here exists to KILL a specific SURVIVING mutant from the mutmut
baseline (the mutation co-gate). A surviving mutant in one of these scoring
formulas is a silently-wrong published benchmark score, so a killing test
asserts the EXACT value / boundary / operator / default-constant the mutation
changes — not merely that a line executes. Expected values are HAND-COMPUTED
(and verified against the installed nltk / rouge_scorer / sacrebleu / scipy /
sklearn in the test container) in each test docstring so a flipped operator, a
wrong default constant, an off-by-one, or a mangled string fails.

Targeted mutant id ranges (from ``_surv_diffs.txt``):
    _compute_text_similarity  #557-642   (source lines ~949-1036)
    _compute_ranking_metric   #760-841   (source lines ~1192-1270)

DEFAULT-PARAM PINNING TECHNIQUE
-------------------------------
For a mutant that changes a default constant read via
``parameters.get(key, DEFAULT)`` (e.g. ``"max_order", 4`` -> ``5``, weight
literals, ``"method1"``, ``char_order", 6``, ``beta", 2``, ``word_order", 0``,
``use_stemmer", True``), we:
  1. call the metric with NO params (uses the source default), and
  2. call it with the params explicitly set to the ORIGINAL default value,
     written as a LITERAL in the test (so the literal is NOT mutated),
  3. assert (1) == (2).
If the source default literal is mutated, branch (1) diverges from the
un-mutated literal in (2) and the equality fails -> mutant killed. Where
feasible we also assert that a DIFFERENT explicit value changes the result, so
the parameter is provably load-bearing (kills the ``.get`` / key-string
mutants, which otherwise ignore the param and return the default unchanged).

EQUIVALENT / SKIPPED mutants are documented in the module-level
``EQUIVALENT_MUTANTS`` note at the bottom of this file.
"""

import math
import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.sample_evaluator import SampleEvaluator  # noqa: E402


@pytest.fixture
def ev():
    return SampleEvaluator(evaluation_id="mut-test", field_configs={})


# A partial-overlap sentence pair: 6/7 unigrams overlap, one mid-sentence token
# differs ("sat" -> "ran"). High enough order n-grams diverge so n-gram weights,
# max_order, and smoothing all become observable (vs identical text, which
# saturates everything to 1.0 and hides those mutants).
GT_PARTIAL = "the cat sat on the mat today"
PRED_PARTIAL = "the cat ran on the mat today"


# ============================================================================
# _compute_text_similarity — `if parameters is None: parameters = {}`  (#557/558)
# ============================================================================
def test_text_similarity_none_parameters_normalized(ev):
    """`if parameters is None: parameters = {}` (#557) and the assignment (#558).

    Inverting the guard to `is not None` (or deleting the `parameters = {}`
    body) leaves `parameters` as `None`, so the very next `parameters.get(...)`
    in the bleu branch raises AttributeError. Calling bleu with an EXPLICIT
    None must therefore return a clean float, not raise. Identical 6-token text
    under the default method1 smoothing -> BLEU == 1.0 (perfect 1..4-gram
    precision, no brevity penalty; needs >= 4 tokens so all 4-grams exist).
    """
    val = ev._compute_text_similarity(
        "bleu", "the cat sat on the mat", "the cat sat on the mat", None
    )
    assert val == pytest.approx(1.0)


# ============================================================================
# BLEU branch
# ============================================================================
def test_bleu_metric_name_label_live(ev):
    """`elif metric_name == "bleu"` (#569) — string mutated to "XXbleuXX".

    A mutated label makes "bleu" fall through the whole if/elif chain to the
    terminal `return 0.0`. Identical non-trivial text has perfect n-gram
    precision and no brevity penalty -> BLEU == 1.0, which a 0.0 fallthrough
    cannot produce.
    """
    assert ev._compute_text_similarity(
        "bleu", "the cat sat on the mat", "the cat sat on the mat"
    ) == pytest.approx(1.0)


def test_bleu_max_order_default_is_4(ev):
    """`max_order = parameters.get("max_order", 4)` (#570/571/572).

    Pins the default and proves max_order is load-bearing:
      - default (no params)            == explicit {"max_order": 4}  (0.59694918)
      - explicit {"max_order": 3}      != that value                (0.72319755)
    If the `.get`/`"max_order"` key is mutated the param is ignored and
    max_order=3 would equal the default -> the inequality fails -> killed.

    NOTE: the `4 -> 5` LITERAL mutant is EQUIVALENT and is NOT covered here
    (see EQUIVALENT_MUTANTS): default_weights.get(5, [0.25]*4) == [0.25]*4 and
    weights[:5] == weights[:4] for the 4-element weight list, so 4 and 5 yield
    byte-identical BLEU for every input.
    """
    gt = "the quick brown fox jumps over the lazy dog"
    pred = "the quick brown cat jumps over the lazy dog"
    default = ev._compute_text_similarity("bleu", gt, pred, None)
    explicit_4 = ev._compute_text_similarity("bleu", gt, pred, {"max_order": 4})
    explicit_3 = ev._compute_text_similarity("bleu", gt, pred, {"max_order": 3})
    assert default == pytest.approx(explicit_4)
    assert default == pytest.approx(0.5969491792019646)
    assert explicit_3 == pytest.approx(0.7231975529343087)
    assert explicit_3 != pytest.approx(default)


def test_bleu_smoothing_default_is_method1(ev):
    """`smoothing_method = parameters.get("smoothing", "method1")` (#573/574/575).

    On a pair with a missing higher-order n-gram, method1 and method2 diverge:
      - default (no params)        == explicit {"smoothing": "method1"} (0.48892302)
      - explicit {"smoothing": "method2"} != that value                 (0.59154637)
    Mutating the "method1" default makes default diverge from the literal
    "method1"; mutating the key/.get makes "method2" ignored (== default).
    """
    default = ev._compute_text_similarity("bleu", GT_PARTIAL, PRED_PARTIAL, None)
    m1 = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"smoothing": "method1"}
    )
    m2 = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"smoothing": "method2"}
    )
    assert default == pytest.approx(m1)
    assert default == pytest.approx(0.488923022434901)
    assert m2 == pytest.approx(0.5915463685222677)
    assert m2 != pytest.approx(default)


def test_bleu_default_weights_row1(ev):
    """`default_weights` row `1: [1.0]` (#576/577).

    With max_order=1 and no explicit weights, BLEU uses default_weights[1] =
    [1.0]. Pin it: default(max_order=1) == explicit weights=[1.0] (0.85714286),
    and a perturbed weight [2.0] changes the score (0.73469388) — nltk does NOT
    renormalize, so mutating the 1.0 literal is observable.
    """
    base = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 1}
    )
    explicit = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 1, "weights": [1.0]}
    )
    perturbed = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 1, "weights": [2.0]}
    )
    assert base == pytest.approx(explicit)
    assert base == pytest.approx(0.8571428571428571)
    assert perturbed == pytest.approx(0.7346938775510203)
    assert perturbed != pytest.approx(base)


def test_bleu_default_weights_row2(ev):
    """`default_weights` row `2: [0.5, 0.5]` (#578/579/580).

    max_order=2 with no weights uses [0.5, 0.5]. Pin: default == explicit
    [0.5, 0.5] (0.75592895); asymmetric [1.0, 0.5] changes the score
    (0.69985421). Mutating EITHER 0.5 literal makes default != [0.5, 0.5].
    """
    base = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 2}
    )
    explicit = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 2, "weights": [0.5, 0.5]}
    )
    asym = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 2, "weights": [1.0, 0.5]}
    )
    assert base == pytest.approx(explicit)
    assert base == pytest.approx(0.7559289460184544)
    assert asym == pytest.approx(0.6998542122237651)
    assert asym != pytest.approx(base)


def test_bleu_default_weights_row3(ev):
    """`default_weights` row `3: [0.33, 0.33, 0.34]` (#581-584).

    max_order=3 with no weights uses [0.33, 0.33, 0.34] — the one asymmetric
    default row. Pin: default == explicit [0.33, 0.33, 0.34] (0.60883252).
    Each weight is independently load-bearing:
      [0.34,0.33,0.34] -> 0.60789472   (mutating the 1st 0.33)
      [0.33,0.34,0.34] -> 0.60636891   (mutating the 2nd 0.33)
      [0.33,0.33,0.33] -> 0.61443683   (mutating the 0.34)
    All three differ from the default, so any single-literal mutation in row 3
    is observable.
    """
    base = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 3}
    )
    explicit = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 3, "weights": [0.33, 0.33, 0.34]}
    )
    mut_w0 = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 3, "weights": [0.34, 0.33, 0.34]}
    )
    mut_w1 = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 3, "weights": [0.33, 0.34, 0.34]}
    )
    mut_w2 = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"max_order": 3, "weights": [0.33, 0.33, 0.33]}
    )
    assert base == pytest.approx(explicit)
    assert base == pytest.approx(0.6088325190552202)
    assert mut_w0 == pytest.approx(0.607894722583608)
    assert mut_w1 == pytest.approx(0.6063689135292187)
    assert mut_w2 == pytest.approx(0.6144368316876522)
    assert mut_w0 != pytest.approx(base)
    assert mut_w1 != pytest.approx(base)
    assert mut_w2 != pytest.approx(base)


def test_bleu_default_weights_row4(ev):
    """`default_weights` row `4: [0.25, 0.25, 0.25, 0.25]` (#585-589) and the
    `weights = parameters.get("weights", default_weights.get(max_order, [0.25]*4))`
    line (#590-595).

    Default max_order=4 with no weights uses [0.25]*4. Pin: default ==
    explicit [0.25,0.25,0.25,0.25] (0.59694918); a skewed [0.4,0.2,0.2,0.2]
    changes the score. Mutating any 0.25 literal in row 4, or mutating the
    `[0.25]*4` fallback / the "weights" key / `.get`, makes default diverge
    from the explicit literal.
    """
    gt = "the quick brown fox jumps over the lazy dog"
    pred = "the quick brown cat jumps over the lazy dog"
    base = ev._compute_text_similarity("bleu", gt, pred, None)
    explicit = ev._compute_text_similarity(
        "bleu", gt, pred, {"weights": [0.25, 0.25, 0.25, 0.25]}
    )
    skewed = ev._compute_text_similarity(
        "bleu", gt, pred, {"weights": [0.4, 0.2, 0.2, 0.2]}
    )
    assert base == pytest.approx(explicit)
    assert base == pytest.approx(0.5969491792019646)
    assert skewed != pytest.approx(base)


def test_bleu_lowercases_inputs(ev):
    """`reference = [gt.lower().split()]` (#596) and
    `candidate = pred.lower().split()` (#597).

    Dropping `.lower()` would make a mixed-case prediction mismatch its
    reference. BLEU is case-insensitive here: scoring "The Cat Sat" against
    "the cat sat" equals scoring the all-lowercase pair (0.5623, brevity-
    penalised short identical text). If either `.lower()` is removed, the
    cased call diverges.
    """
    cased = ev._compute_text_similarity("bleu", "The Cat Sat", "the cat sat")
    lowered = ev._compute_text_similarity("bleu", "the cat sat", "the cat sat")
    assert cased == pytest.approx(lowered)
    assert cased == pytest.approx(0.5623413251903491)


def test_bleu_empty_candidate_guard(ev):
    """`if not candidate: return 0.0` (#598/599).

    Empty prediction -> candidate == [] -> early `return 0.0`. A guard
    inversion (`if not candidate` -> `if candidate`) would skip the early
    return for the empty case (then sentence_bleu raises / returns garbage)
    and instead early-return 0.0 for a NON-empty case. So we pin both arms:
      - empty pred                 -> 0.0  (guard true, returns 0.0)
      - identical non-empty pred   -> 1.0  (guard false, real BLEU)
    The `return 0.0 -> 1.0` constant flip is killed by the empty==0.0 arm.
    (Identical 6-token text so all 4-grams exist and BLEU == 1.0 cleanly.)
    """
    assert ev._compute_text_similarity("bleu", "the cat sat", "") == 0.0
    assert ev._compute_text_similarity(
        "bleu", "the cat sat on the mat", "the cat sat on the mat"
    ) == pytest.approx(1.0)


def test_bleu_valid_smoothing_method_accepted(ev):
    """SmoothingFunction() (#600), allowed_smoothing set construction
    (#601-605: `startswith("method")`, `not startswith("__")`, the `and`), and
    `if smoothing_method not in allowed_smoothing` (#606).

    "method1" is a real SmoothingFunction method and MUST be accepted (no
    raise) and produce real scores. This kills:
      - `not in` -> `in` (#606): would raise on the VALID method1,
      - `startswith("method")`/`and`/`"__"` mutations that drop method1 from
        the allowed set (-> valid call raises),
      - the SmoothingFunction()/getattr lines (no smoothing -> no score).
    """
    val = ev._compute_text_similarity(
        "bleu", GT_PARTIAL, PRED_PARTIAL, {"smoothing": "method1"}
    )
    assert val == pytest.approx(0.488923022434901)


def test_bleu_invalid_smoothing_raises_valueerror(ev):
    """The academic-rigor guard: invalid smoothing -> ValueError (#606/607/608).

    `parameters={"smoothing": "not_a_real_method"}` is not in allowed_smoothing,
    so the branch raises ValueError whose message contains "smoothing method".
    `match="smoothing"` kills the message-string mutants (#607/608) — the
    XX..XX-mutated message would not contain "smoothing" — and the `not in` ->
    `in` inversion (which would NOT raise on the invalid value).
    """
    with pytest.raises(ValueError, match="smoothing"):
        ev._compute_text_similarity(
            "bleu", GT_PARTIAL, PRED_PARTIAL, {"smoothing": "not_a_real_method"}
        )


# ============================================================================
# ROUGE branch
# ============================================================================
def test_rouge_metric_name_label_live(ev):
    """`elif metric_name == "rouge"` (#612) — label mutated to "XXrougeXX".

    Identical text -> ROUGE-L f-measure == 1.0; a mutated label falls through
    to the terminal `return 0.0`.
    """
    assert ev._compute_text_similarity(
        "rouge", "the cat sat on the mat", "the cat sat on the mat"
    ) == pytest.approx(1.0)


def test_rouge_variant_default_is_rougeL(ev):
    """`variant = parameters.get("variant", "rougeL")` (#613/614/615).

    For gt="the cat sat on the mat", pred="the mat the cat" the LCS-based
    rougeL f-measure is 0.4, while rouge1 (unigram overlap) is 0.8. Pin:
      - default (no params)         == explicit {"variant": "rougeL"} (0.4)
      - explicit {"variant": "rouge1"} != that                       (0.8)
    """
    gt, pred = "the cat sat on the mat", "the mat the cat"
    default = ev._compute_text_similarity("rouge", gt, pred, None)
    rouge_l = ev._compute_text_similarity("rouge", gt, pred, {"variant": "rougeL"})
    rouge_1 = ev._compute_text_similarity("rouge", gt, pred, {"variant": "rouge1"})
    assert default == pytest.approx(rouge_l)
    assert default == pytest.approx(0.4)
    assert rouge_1 == pytest.approx(0.8)
    assert rouge_1 != pytest.approx(default)


def test_rouge_use_stemmer_default_is_true(ev):
    """`use_stemmer = parameters.get("use_stemmer", True)` (#616/617/618).

    gt="running quickly", pred="run quick": with stemming, "running"->"run" and
    "quickly"->"quick" match -> rougeL f == 0.5; without stemming nothing
    matches -> 0.0. Pin:
      - default (no params)             == explicit {"use_stemmer": True}  (0.5)
      - explicit {"use_stemmer": False} != that                           (0.0)
    The `True -> False` default flip makes the default collapse to 0.0.
    """
    gt, pred = "running quickly", "run quick"
    default = ev._compute_text_similarity("rouge", gt, pred, None)
    stemmed = ev._compute_text_similarity("rouge", gt, pred, {"use_stemmer": True})
    unstemmed = ev._compute_text_similarity("rouge", gt, pred, {"use_stemmer": False})
    assert default == pytest.approx(stemmed)
    assert default == pytest.approx(0.5)
    assert unstemmed == pytest.approx(0.0)
    assert unstemmed != pytest.approx(default)


# ============================================================================
# METEOR branch
# ============================================================================
def test_meteor_metric_name_label_live(ev):
    """`elif metric_name == "meteor"` (#622) — label mutated to "XXmeteorXX".

    Identical non-trivial text -> METEOR ~= 0.9977 (> 0); a mutated label
    falls through to the terminal `return 0.0`. Assert > 0 (well clear of the
    0.0 fallthrough) plus the exact value.
    """
    val = ev._compute_text_similarity(
        "meteor", "the cat sat on the mat", "the cat sat on the mat"
    )
    assert val == pytest.approx(0.9976851851851852)
    assert val > 0.5


def test_meteor_lowercases_inputs(ev):
    """`reference = gt.lower().split()` (#623) and `candidate = pred.lower().split()`
    (#624).

    Mixed-case prediction must score identically to the lowercase pair if
    `.lower()` is applied to both sides. "The Cat Sat Now" vs "the cat sat now"
    -> 0.9921875, same as the all-lowercase identical pair.
    """
    cased = ev._compute_text_similarity("meteor", "The Cat Sat Now", "the cat sat now")
    lowered = ev._compute_text_similarity("meteor", "the cat sat now", "the cat sat now")
    assert cased == pytest.approx(lowered)
    assert cased == pytest.approx(0.9921875)


def test_meteor_empty_candidate_guard(ev):
    """`if not candidate: return 0.0` (#625/626).

    Empty prediction -> candidate == [] -> early `return 0.0`. Non-empty
    identical text -> ~0.9977. Pins both arms (kills the guard inversion and
    the `return 0.0 -> 1.0` flip).
    """
    assert ev._compute_text_similarity("meteor", "the cat sat", "") == 0.0
    assert ev._compute_text_similarity(
        "meteor", "the cat sat on the mat", "the cat sat on the mat"
    ) == pytest.approx(0.9976851851851852)


# ============================================================================
# chrF branch
# ============================================================================
def test_chrf_metric_name_label_live(ev):
    """`elif metric_name == "chrf"` (#629 label) — mutated to "XXchrfXX".

    Identical text -> chrF == 100.0 / 100 == 1.0; mutated label falls through
    to the terminal `return 0.0`.
    """
    assert ev._compute_text_similarity(
        "chrf", "hello world foo", "hello world foo"
    ) == pytest.approx(1.0)


def test_chrf_char_order_default_is_6(ev):
    """`char_order = parameters.get("char_order", 6)` (#630/631).

    Pin: default == explicit {"char_order": 6} (0.71555802); {"char_order": 7}
    differs (0.67583545). The `6 -> 7` literal flip makes the default change to
    the char_order=7 value.
    """
    default = ev._compute_text_similarity("chrf", GT_PARTIAL, PRED_PARTIAL, None)
    co6 = ev._compute_text_similarity(
        "chrf", GT_PARTIAL, PRED_PARTIAL, {"char_order": 6}
    )
    co7 = ev._compute_text_similarity(
        "chrf", GT_PARTIAL, PRED_PARTIAL, {"char_order": 7}
    )
    assert default == pytest.approx(co6)
    assert default == pytest.approx(0.7155580201245836)
    assert co7 == pytest.approx(0.6758354458210718)
    assert co7 != pytest.approx(default)


def test_chrf_word_order_default_is_0(ev):
    """`word_order = parameters.get("word_order", 0)` (#633/634).

    Pin: default == explicit {"word_order": 0} (0.71555802); {"word_order": 1}
    differs (0.73578443). The `0 -> 1` literal flip makes the default change.
    """
    default = ev._compute_text_similarity("chrf", GT_PARTIAL, PRED_PARTIAL, None)
    wo0 = ev._compute_text_similarity(
        "chrf", GT_PARTIAL, PRED_PARTIAL, {"word_order": 0}
    )
    wo1 = ev._compute_text_similarity(
        "chrf", GT_PARTIAL, PRED_PARTIAL, {"word_order": 1}
    )
    assert default == pytest.approx(wo0)
    assert default == pytest.approx(0.7155580201245836)
    assert wo1 == pytest.approx(0.7357844254129084)
    assert wo1 != pytest.approx(default)


def test_chrf_beta_default_is_2(ev):
    """`beta = parameters.get("beta", 2)` (#636/637).

    beta only shifts the score when precision != recall, so we use a strongly
    asymmetric pair gt="the cat sat on the mat", pred="the dog ran":
      - default (no params)     == explicit {"beta": 2} (0.10054025)
      - explicit {"beta": 3}    != that                 (0.09540452)
    The `2 -> 3` literal flip makes the default change to the beta=3 value.
    """
    gt, pred = "the cat sat on the mat", "the dog ran"
    default = ev._compute_text_similarity("chrf", gt, pred, None)
    b2 = ev._compute_text_similarity("chrf", gt, pred, {"beta": 2})
    b3 = ev._compute_text_similarity("chrf", gt, pred, {"beta": 3})
    assert default == pytest.approx(b2)
    assert default == pytest.approx(0.10054024660266517)
    assert b3 == pytest.approx(0.0954045200278189)
    assert b3 != pytest.approx(default)


# ============================================================================
# Terminal `return 0.0` of _compute_text_similarity  (#642)
# ============================================================================
def test_text_similarity_unknown_metric_returns_zero(ev):
    """Terminal `return 0.0` (#642) — flip to `return 1.0`.

    An unrecognised metric name matches no branch and must return 0.0.
    Asserting EXACTLY 0.0 kills the constant flip. (Also defends every
    `elif metric_name == "..."` label mutant: a mutated label sends a VALID
    metric down here, which the per-metric tests above already catch.)
    """
    assert ev._compute_text_similarity(
        "definitely_not_a_metric", "the cat sat", "the cat sat"
    ) == 0.0


# ============================================================================
# _compute_ranking_metric — `if parameters is None: parameters = {}` (#760/761)
# ============================================================================
def test_ranking_none_parameters_ok(ev):
    """`if parameters is None: parameters = {}` (#760/761).

    Spearman of identical lists with explicit parameters=None must return 1.0
    (hits the `gt_list == pred_list` short-circuit). The guard never touches
    `parameters` for spearman, but this exercises the None path cleanly and
    pins the early-return; the bleu None test above already kills the guard
    inversion on a param-reading branch.
    """
    assert ev._compute_ranking_metric("spearman", [1, 2, 3], [1, 2, 3], None) == 1.0


# ============================================================================
# SPEARMAN branch  (#767-781)
# ============================================================================
def test_spearman_metric_name_and_identical(ev):
    """`elif metric_name == "spearman"` (#767) + `if gt_list == pred_list: return 1.0`
    (#770/771).

    Identical lists -> the equality short-circuit returns 1.0. A mutated
    "spearman" label falls through to the terminal `return 0.0`; the
    `== -> !=` inversion or `return 1.0 -> 2.0` flip both break the 1.0.
    """
    assert ev._compute_ranking_metric("spearman", [1, 2, 3], [1, 2, 3]) == 1.0


def test_spearman_length_mismatch_returns_zero(ev):
    """`if len(gt_list) != len(pred_list): return 0.0` (#772/773).

    Unequal-length, non-equal lists -> 0.0. The `!= -> ==` inversion would
    instead take this branch only for EQUAL lengths (and skip it here, falling
    into spearmanr on ragged input). The `return 0.0 -> 1.0` flip breaks the
    exact 0.0.
    """
    assert ev._compute_ranking_metric("spearman", [1, 2, 3, 4], [1, 2, 3]) == 0.0


def test_spearman_anticorrelated_clamped_to_zero(ev):
    """`if len(gt_list) > 1:` (#774/775) + `max(0.0, corr) if not np.isnan(corr)`
    (#776/777/778/779).

    Reversed equal-length rankings -> Spearman corr == -1.0 -> max(0.0, -1.0)
    == 0.0. This exercises the multi-element branch (len 3 > 1) and the
    `max(0.0, corr)` clamp. The `> 1 -> >= 1` boundary mutant does not change
    this case (3 satisfies both) — the single-element test below pins that
    boundary instead.
    """
    assert ev._compute_ranking_metric("spearman", [1, 2, 3], [3, 2, 1]) == 0.0


def test_spearman_positive_correlation_value(ev):
    """`corr, _ = spearmanr(...)` + `max(0.0, corr)` (#776-779), positive arm.

    gt=[1,2,3,4], pred=[1,2,4,3] are equal-length, NOT identical (so the
    short-circuit is skipped), len 4 > 1, and rank-correlate to Spearman
    rho = 0.8. max(0.0, 0.8) == 0.8. A non-degenerate positive value here
    proves the real spearmanr path runs (kills any short-circuit-to-constant
    mutation that would force 0.0 or 1.0).
    """
    val = ev._compute_ranking_metric("spearman", [1, 2, 3, 4], [1, 2, 4, 3])
    assert val == pytest.approx(0.8)


def test_spearman_single_element_returns_one(ev):
    """`if len(gt_list) > 1:` (#774/775) false-arm + trailing `return 1.0` (#780).

    Single, non-equal elements: gt=[5], pred=[9] are equal-length (1==1) and
    NOT equal, so the `> 1` branch is skipped and the trailing `return 1.0`
    fires ("single element lists have perfect correlation"). This pins:
      - `> 1 -> >= 1`: would enter spearmanr on a 1-element pair (-> nan ->
        0.0) instead of returning 1.0,
      - the trailing `return 1.0 -> 2.0` flip.
    """
    assert ev._compute_ranking_metric("spearman", [5], [9]) == 1.0


# ============================================================================
# KENDALL branch  (#783-797)
# ============================================================================
def test_kendall_metric_name_and_identical(ev):
    """`elif metric_name == "kendall"` (#783) + `if gt_list == pred_list: return 1.0`
    (#786/787)."""
    assert ev._compute_ranking_metric("kendall", [1, 2, 3], [1, 2, 3]) == 1.0


def test_kendall_length_mismatch_returns_zero(ev):
    """`if len(gt_list) != len(pred_list): return 0.0` (#788/789)."""
    assert ev._compute_ranking_metric("kendall", [1, 2, 3, 4], [1, 2, 3]) == 0.0


def test_kendall_anticorrelated_clamped_to_zero(ev):
    """`if len(gt_list) > 1:` (#790/791) + `max(0.0, tau) if not np.isnan(tau)`
    (#792/793/794/795).

    Reversed equal-length rankings -> Kendall tau == -1.0 -> max(0.0, -1.0)
    == 0.0.
    """
    assert ev._compute_ranking_metric("kendall", [1, 2, 3], [3, 2, 1]) == 0.0


def test_kendall_positive_value(ev):
    """`tau, _ = kendalltau(...)` + `max(0.0, tau)` (#792-795), positive arm.

    gt=[1,2,3,4], pred=[1,2,4,3]: one discordant pair out of six ->
    tau = (5-1)/6 = 0.6666...; max(0.0, .) == 0.6666... A non-degenerate
    positive value proves the real kendalltau path runs.
    """
    val = ev._compute_ranking_metric("kendall", [1, 2, 3, 4], [1, 2, 4, 3])
    assert val == pytest.approx(0.6666666666666669)


def test_kendall_single_element_returns_one(ev):
    """`if len(gt_list) > 1:` (#790/791) false-arm + trailing `return 1.0` (#796).

    gt=[5], pred=[9]: equal-length, not equal, `> 1` false -> trailing
    `return 1.0`. Kills the `> 1 -> >= 1` boundary and the `return 1.0 -> 2.0`
    flip.
    """
    assert ev._compute_ranking_metric("kendall", [5], [9]) == 1.0


# ============================================================================
# NDCG branch  (#799-810)
# ============================================================================
def test_ndcg_metric_name_and_identical(ev):
    """`elif metric_name == "ndcg"` (#799) + the non-empty real-score path.

    Identical non-empty relevance lists -> NDCG == 1.0 (ideal == actual gain).
    A mutated "ndcg" label falls through to the terminal `return 0.0`.
    """
    assert ev._compute_ranking_metric("ndcg", [3, 2, 1], [3, 2, 1]) == pytest.approx(1.0)


def test_ndcg_empty_guard_both_empty(ev):
    """`if not gt_list or not pred_list: return 1.0 if gt_list == pred_list else 0.0`
    (#802-807), both-empty arm.

    Both lists empty -> the guard is true and gt_list == pred_list -> 1.0.
    Kills the `or -> and` mutation of the guard's left side only when combined
    with the next test (one-empty), and the `== -> !=` inversion inside the
    ternary (which would return 0.0 for equal-empty).
    """
    assert ev._compute_ranking_metric("ndcg", [], []) == 1.0


def test_ndcg_empty_guard_one_empty(ev):
    """`if not gt_list or not pred_list:` (#802) `or` + ternary else-branch
    (#805/806/807).

    gt empty, pred non-empty -> guard true (via the `or`), and gt_list !=
    pred_list -> the ternary's else returns 0.0. The `or -> and` mutation would
    make the guard FALSE here (only one side empty) and try to build a ragged
    np.array -> RuntimeError instead of the clean 0.0. The
    `1.0 if .. else 0.0 -> 1.0 if .. else 1.0` flip breaks the 0.0.
    """
    assert ev._compute_ranking_metric("ndcg", [], [1]) == 0.0


def test_ndcg_ragged_input_raises_runtimeerror(ev):
    """`raise RuntimeError(f"NDCG score computation failed: {e}")` (#810).

    Two non-empty lists of DIFFERENT length pass the empty-guard, then
    np.array([gt_list]) / np.array([pred_list]) -> ndcg_score raises (ragged /
    non-broadcastable), which the except re-raises as RuntimeError. `match="NDCG"`
    kills the XX..XX message-string mutant — the mangled message would not
    contain "NDCG".
    """
    with pytest.raises(RuntimeError, match="NDCG"):
        ev._compute_ranking_metric("ndcg", [3, 2, 1, 0], [3, 2, 1])


# ============================================================================
# MAP branch  (#817-840)
# ============================================================================
def test_map_empty_guard_both_empty(ev):
    """`if not gt_set or not pred_list: return 1.0 if not gt_set and not pred_list
    else 0.0` (#817-822), both-empty arm.

    Both empty -> guard true, and `not gt_set and not pred_list` true -> 1.0.
    """
    assert ev._compute_ranking_metric("map", set(), []) == 1.0


def test_map_empty_guard_one_empty(ev):
    """MAP empty-guard else-branch (#818-822).

    gt non-empty, pred empty -> guard true (via `or`), but
    `not gt_set and not pred_list` is false -> 0.0. Kills the `and -> or`
    inside the ternary (which would return 1.0 here) and the
    `1.0 if .. else 0.0 -> .. else 1.0` flip.
    """
    assert ev._compute_ranking_metric("map", {"a"}, []) == 0.0


def test_map_perfect_ranking_value(ev):
    """`return sum_precisions / len(gt_set) if gt_set else 0.0` (#837).

    gt_set={a,b,c}, pred=[a,b,c]: every position is a hit, AP =
    (1/1 + 2/2 + 3/3) / 3 == 1.0. Pins the AP division (the `/ len(gt_set)`
    and the `if gt_set else 0.0` tail). A perfect-recall ranking must score
    exactly 1.0.
    """
    assert ev._compute_ranking_metric("map", ["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)


def test_map_partial_ranking_value(ev):
    """MAP average-precision formula (#837) — non-degenerate value.

    gt_set={a,b,c}, pred=[a,x,b]: hit at rank 1 (prec 1/1), miss at rank 2,
    hit at rank 3 (2 hits / rank 3 = 2/3). AP = (1.0 + 0.6666...) / 3 ==
    0.5555... A non-trivial fractional value proves the precision accumulation
    loop and the `/ len(gt_set)` divisor (a mutated divisor or accumulator
    yields a different number).
    """
    val = ev._compute_ranking_metric("map", ["a", "b", "c"], ["a", "x", "b"])
    assert val == pytest.approx((1.0 + 2.0 / 3.0) / 3.0)


# ============================================================================
# WEIGHTED_KAPPA branch  (#763-765)  and terminal return (#841)
# ============================================================================
def test_weighted_kappa_raises_aggregate_only(ev):
    """`if metric_name == "weighted_kappa": raise RuntimeError("... aggregate-only
    ...")` (#763/764/765).

    Weighted Kappa is aggregate-only and must raise per-sample. `match=
    "aggregate-only"` kills the XX..XX message-string mutants (#764/765) — the
    mangled message would not contain "aggregate-only" — and the `"weighted_kappa"`
    label mutant (#763), which would route a valid call to the terminal 0.0
    return instead of raising.
    """
    with pytest.raises(RuntimeError, match="aggregate-only"):
        ev._compute_ranking_metric("weighted_kappa", [1, 2], [1, 2])


def test_ranking_unknown_metric_returns_zero(ev):
    """Terminal `return 0.0` of _compute_ranking_metric (#841) — flip to 1.0.

    An unrecognised ranking metric matches no branch and must return exactly
    0.0. Also defends the `elif metric_name == "..."` labels: a mutated label
    routes a valid metric here, which the per-metric tests above already catch.
    """
    assert ev._compute_ranking_metric("not_a_ranking_metric", [1, 2, 3], [1, 2, 3]) == 0.0


# ============================================================================
# EQUIVALENT_MUTANTS — deliberately not killed, with proof of equivalence.
# ============================================================================
EQUIVALENT_MUTANTS = """
_compute_text_similarity #571 (the `4` LITERAL in
`max_order = parameters.get("max_order", 4)` mutated to `5`):
    EQUIVALENT. With max_order defaulting to 5, the weights default is
    `default_weights.get(5, [0.25]*4)` -> key 5 is absent -> `[0.25]*4` (the
    SAME 4-element list as max_order=4's `default_weights.get(4)`), and the
    slice `weights[:5]` on a 4-element list equals `weights[:4]`. So
    sentence_bleu receives an identical 4-tuple of weights and produces a
    byte-identical score for EVERY input. Verified empirically: bleu(no params)
    == bleu({"max_order": 5}) for both identical and partial-overlap pairs
    (0.5969491792019646 in the partial-overlap case). No input can distinguish
    4 from 5, so no test can kill it. The `.get`/`"max_order"`-key mutants on
    the same line ARE killed by test_bleu_max_order_default_is_4 (max_order=3
    observably changes the score).

NOTE on RuntimeError message mutants for Spearman (#781) and Kendall (#797):
    These raise only when scipy itself raises inside the try block. With the
    `gt_list == pred_list`, length-mismatch, and `len > 1` guards in front,
    every reachable equal-length non-identical multi-element numeric input is
    consumed by spearmanr/kendalltau WITHOUT raising (they return nan at worst,
    which the `not np.isnan` clamp turns into 0.0 — NOT an exception). The
    except-body RuntimeError wording is therefore not reliably reachable from
    this method's public surface without monkeypatching scipy, which these
    tests avoid (no source edits, deterministic inputs only). The reachable
    guard/return/clamp mutants in both branches ARE killed by the
    test_spearman_* / test_kendall_* tests above. Left as message-only,
    hard-to-reach mutants.
"""
