# API test-count history — reconciling the "7,113 → ~5,200" drop

**Status: reconciled 2026-06-12** (benger-extended issue #33, section A).

The coverage audit of 2026-05-20 reported the platform API pytest suite at
"~5,200 tests (301 files)" against a 2026-03-21 baseline of "7,113" — an
apparent ~27% drop. This document reconstructs what actually happened from
git history and fresh measurements. Short version: **no evidence of a real
~1,900-test loss was found. The two numbers were measured across a repo
boundary and (for the May figure) with a counting method we could not
reproduce.** The only sizable real deletions were intentional, tied to
feature removals, and total ~376 test functions across three commits.

## Measurements

Two measurement methods are used below — they are NOT directly comparable:

- **fn** = `git grep -c "def test_" <sha> -- services/api/tests` summed.
  Counts test *functions* in source (includes `async def test_`, ignores
  parametrize expansion). Reproducible at any commit without Docker.
- **collected** = `pytest tests/ --collect-only -q --ignore=tests/e2e`
  inside the dockerized test env. Counts test *items* (parametrize
  expands). Only measured at HEAD; historical collection would require
  checking out old SHAs into the test container.

### Test-function counts over time (method: fn)

| Date | Commit | fn | files w/ tests |
|---|---|---|---|
| 2026-04-15 | `6bdb01d` (initial open-source commit) | 6,579 | 282 |
| 2026-05-01 | `fde923c` | 6,532 | 284 |
| 2026-05-15 | `d6f6d13` | 6,621 | 297 |
| 2026-05-19 | `fc5393a` | 6,603 | 301 |
| 2026-05-21 | `62f6403` | 6,606 | 302 |
| 2026-06-01 | `9022d67` | 6,696 | 308 |
| 2026-06-12 | `5833aa3` (dev HEAD) | 6,458 | 303 |

### Collected counts at 2026-06-12 (method: collected, dockerized)

| Scope | Items |
|---|---|
| `tests/` minus `tests/e2e` (the CI invocation) | 6,435 |
| `tests/unit` + `tests/integration` only | 6,166 |

## What the git history shows

**1. The repo's history starts 2026-04-15.** The open-core split shipped as
a squashed "Initial release" commit (`6bdb01d`). The 2026-03-21 baseline of
7,113 was measured in the *pre-split private repo*, whose test tree
included tests for features that moved to `benger-extended` (timer,
korrektur review/feedback, human leaderboards, judge pre-config,
immediate eval) and whatever else didn't survive the split curation. That
number is **not reproducible from this repo and not comparable** to any
post-split count.

**2. Function counts were stable-to-growing April → June.** 6,579 at the
initial commit, 6,696 by June 1 — net +117 despite two deletion events.
There is no window in this repo's history where ~1,900 tests disappeared.

**3. Three commits deleted test files, all tied to intentional feature
removals** (counted at each commit's parent):

| Commit | Date | Test fns deleted | Why |
|---|---|---|---|
| `c4c3d63` | 2026-05-02 | 82 (4 files) | Polymorphic task assignments rework; replaced org/member coverage paths |
| `fcea403` | 2026-05-19 | 65 (2 files) | Digest pipeline deleted as dead code (model columns + template gone) |
| `b5c508c` | 2026-06-05 | 229 (9 files, −7,697 lines) | Issue #158: sync import/export endpoints deleted; object storage became the only transport. The deleted suites tested endpoints that no longer exist; async export/import has its own suites (e.g. `test_export_import_roundtrip.py`, `test_import_memory_bound.py`) |

That `b5c508c` deletion is the entire June dip in the table above
(6,696 → 6,458; the rest of June added tests).

**4. `f481c79` (2026-05-19 model-file consolidation) is exonerated.** It
was suspected because it landed in the audit window, but it touched only
`services/workers/tests/conftest.py` and `test_email_service.py`
(+18/−5 lines) and deleted **zero** API test files or functions.

## Why the audit numbers don't line up

- **"7,113 (Mar 21)"**: pre-split repo, different test tree. Inflated
  relative to this repo by the proprietary tests that moved out, plus
  possible method differences. Cross-boundary comparison — invalid.
- **"~5,200 (May 2026)"**: could not be reproduced. At the audit date
  (`fc5393a`, 2026-05-19 — whose 301 files-with-tests matches the audit's
  "301 files" exactly) the source contained 6,603 test functions, and
  collected counts are always ≥ function counts (parametrize only adds).
  Scoping doesn't explain it either: even today's `tests/unit` +
  `tests/integration` alone collect 6,166. Plausible causes: a count
  taken from a partially-errored collection, a `wc -l`-style count that
  under-matched class-method tests, or a passed-tests count from a run
  with failures/deselects. The audit itself flagged this number as
  "needs reconciliation".
- Corroborating the method-drift theory: the same audit table lists
  Workers at "~2,600" tests against a Mar-21 baseline of 1,936 — but the
  full workers suite today collects 1,934 items (run 2026-06-12, 1,932
  passed + 2 skipped). The Mar-21 "baseline" matches today's suite almost
  exactly, while the May figure is ~35% high. The May audit's counting
  method was simply not consistent with either baseline.

## Conclusion

- **Real, intentional losses**: ~376 test functions across three
  feature-removal commits (largest: #158 sync-import/export deletion,
  which removed the code under test as well).
- **No silent erosion**: outside those commits, the API test count grew
  steadily April → June.
- **The "27% drop" was an artifact** of comparing a pre-split,
  proprietary-inclusive baseline against a post-split count taken with an
  unreproducible method. The honest current numbers (2026-06-12) are:
  **6,435 collected** (dockerized, `--ignore=tests/e2e`) from **6,467 test
  functions in 303 files** on this branch.

If a future audit needs a baseline, use the `fn` method above (it needs
no infrastructure and is exact per commit) and record the exact command
next to the number.
