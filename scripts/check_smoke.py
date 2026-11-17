#!/usr/bin/env python3
"""Keep the smoke suites honest (benger-extended issue #193).

The smoke suites are what CI runs on every PR and every push to main; the
full suites run at night. A green smoke run therefore has to mean that every
listed test really ran and passed. ``make test-smoke-<suite>`` runs the tests
named in the suite's manifest and then this check:

    python3 scripts/check_smoke.py api        # services/api/tests/smoke_manifest.txt
    python3 scripts/check_smoke.py workers    # services/workers/tests/smoke_manifest.txt
    python3 scripts/check_smoke.py frontend   # services/frontend/smoke_manifest.txt

A manifest has one entry per line: a pytest node id (a test, a class or a
whole file) or a Jest test file path, sorted, without duplicates. For the
pytest suites every listed test must also carry ``@pytest.mark.smoke`` (the
run uses ``-m smoke``), and every test file that uses the marker must be
listed, so the marker in the code and the manifest cannot drift apart.

The check fails when a manifest entry ran no test (its marker was removed, it
was renamed or deleted), when a test was skipped (a skip could hide a switched
off feature), or when a test failed.

To change a smoke suite: add or remove the marker (pytest) and the manifest
line, then commit both so a reviewer sees the change. Needs only the Python
standard library, so it runs on the host after the containerised test run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SMOKE_MARK = re.compile(r"\bpytest\.mark\.smoke\b")
#: pytest writes an xfail as <skipped type="pytest.xfail">; it ran.
XFAIL_TYPE = "pytest.xfail"


@dataclass(frozen=True)
class Suite:
    kind: str  # "pytest" or "jest"
    root: Path  # directory the manifest entries are relative to
    manifest: Path
    results: Path


SUITES = {
    "api": Suite(
        "pytest",
        REPO / "services/api",
        REPO / "services/api/tests/smoke_manifest.txt",
        REPO / "services/api/.smoke-results.xml",
    ),
    "workers": Suite(
        "pytest",
        REPO / "services/workers",
        REPO / "services/workers/tests/smoke_manifest.txt",
        REPO / "services/workers/.smoke-results.xml",
    ),
    "frontend": Suite(
        "jest",
        REPO / "services/frontend",
        REPO / "services/frontend/smoke_manifest.txt",
        REPO / "services/frontend/.smoke-results.json",
    ),
}


class CheckFailed(Exception):
    """A check found a problem; the message says which and what to do."""


def read_manifest(path: Path) -> list[str]:
    if not path.exists():
        raise CheckFailed(f"{path} does not exist.")
    entries = path.read_text(encoding="utf-8").splitlines()
    problems = []
    if not entries:
        problems.append(f"{path} lists no tests.")
    if any(not entry.strip() or entry != entry.strip() for entry in entries):
        problems.append(f"{path} has blank lines or surrounding whitespace.")
    if entries != sorted(set(entries)):
        problems.append(f"{path} must be sorted (plain byte order, `LC_ALL=C sort`) and free of duplicates.")
    if problems:
        raise CheckFailed("\n".join(problems))
    return entries


def check_entry_files(entries: Sequence[str], root: Path) -> None:
    missing = sorted({entry.split("::")[0] for entry in entries if not (root / entry.split("::")[0]).is_file()})
    if missing:
        raise CheckFailed(
            "The manifest names files that do not exist:\n" + "\n".join(f"  - {name}" for name in missing)
        )


def check_markers(entries: Sequence[str], root: Path) -> None:
    """Every listed file uses the marker, and every file using it is listed."""
    listed = {entry.split("::")[0] for entry in entries}
    marked = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("test_*.py")
        if SMOKE_MARK.search(path.read_text(encoding="utf-8"))
    }
    problems = []
    unmarked = sorted(listed - marked)
    unlisted = sorted(marked - listed)
    if unmarked:
        problems.append(
            "Listed in the manifest, but the file has no pytest.mark.smoke:\n"
            + "\n".join(f"  - {name}" for name in unmarked)
        )
    if unlisted:
        problems.append(
            "Uses pytest.mark.smoke, but no manifest entry names the file:\n"
            + "\n".join(f"  + {name}" for name in unlisted)
        )
    if problems:
        raise CheckFailed("\n".join(problems))


@dataclass
class Outcome:
    node: str
    status: str  # passed, failed, skipped, xfailed
    detail: str = ""


def junit_node_id(case: ET.Element) -> str:
    """Rebuild the pytest node id from an xunit1 <testcase>.

    ``file`` is the module path (``tests/x/test_y.py``), ``classname`` the
    dotted module plus the class chain (``tests.x.test_y.TestA``).
    """
    file = case.get("file") or ""
    module = file[: -len(".py")].replace("/", ".") if file.endswith(".py") else ""
    classname = case.get("classname") or ""
    if not file or not classname.startswith(module):
        raise CheckFailed(
            f"Cannot map junit testcase {classname}::{case.get('name')} to a node id; "
            "run pytest with -o junit_family=xunit1."
        )
    classes = [part for part in classname[len(module) :].split(".") if part]
    return "::".join([file, *classes, case.get("name") or ""])


def read_junit(path: Path) -> list[Outcome]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise CheckFailed(f"Cannot read the pytest results {path}: {exc}") from exc
    outcomes = []
    for case in root.iter("testcase"):
        node = junit_node_id(case)
        skipped = case.find("skipped")
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        if failure is not None:
            outcomes.append(Outcome(node, "failed", failure.get("message") or ""))
        elif skipped is None:
            outcomes.append(Outcome(node, "passed"))
        elif skipped.get("type") == XFAIL_TYPE:
            outcomes.append(Outcome(node, "xfailed"))
        else:
            outcomes.append(Outcome(node, "skipped", skipped.get("message") or ""))
    return outcomes


def read_jest(path: Path, root: Path) -> list[Outcome]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CheckFailed(f"Cannot read the Jest results {path}: {exc}") from exc
    outcomes = []
    for result in report.get("testResults", []):
        name = Path(result["name"])
        try:
            file = name.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            file = name.as_posix()
        if result.get("status") != "passed" and not result.get("assertionResults"):
            outcomes.append(Outcome(file, "failed", (result.get("message") or "")[:500]))
        for assertion in result.get("assertionResults", []):
            node = f"{file}::{assertion.get('fullName') or assertion.get('title')}"
            status = assertion.get("status")
            if status == "passed":
                outcomes.append(Outcome(node, "passed"))
            elif status == "failed":
                outcomes.append(Outcome(node, "failed"))
            else:  # pending, skipped, todo, disabled
                outcomes.append(Outcome(node, "skipped", str(status)))
    return outcomes


def belongs_to(node: str, entry: str) -> bool:
    return node == entry or node.startswith((entry + "::", entry + "["))


def compare(entries: Sequence[str], outcomes: Sequence[Outcome]) -> dict[str, int]:
    """Raise unless every entry ran, nothing was skipped and nothing failed."""
    ran: dict[str, int] = {entry: 0 for entry in entries}
    stray = []
    for outcome in outcomes:
        owners = [entry for entry in entries if belongs_to(outcome.node, entry)]
        for entry in owners:
            ran[entry] += 1
        if not owners:
            stray.append(outcome.node)
    problems = []
    empty = [entry for entry, count in ran.items() if count == 0]
    skipped = [o for o in outcomes if o.status == "skipped"]
    failed = [o for o in outcomes if o.status == "failed"]
    if empty:
        problems.append(
            f"{len(empty)} manifest entr{'y' if len(empty) == 1 else 'ies'} ran no test (marker removed, "
            "test renamed or deleted, or the module skipped at import):\n"
            + "\n".join(f"  - {entry}" for entry in empty)
        )
    if skipped:
        problems.append(
            f"{len(skipped)} smoke test(s) SKIPPED. A skip can hide a feature that is switched off, "
            "so it fails the gate:\n" + "\n".join(f"  - {o.node}: {o.detail}" for o in skipped)
        )
    if failed:
        problems.append(f"{len(failed)} smoke test(s) failed:\n" + "\n".join(f"  - {o.node}" for o in failed))
    if stray:
        problems.append(
            "Tests ran that no manifest entry names (the run must take its tests from the manifest):\n"
            + "\n".join(f"  ? {node}" for node in stray[:20])
        )
    if problems:
        raise CheckFailed("\n".join(problems))
    return ran


def check(name: str, results: Path | None = None) -> str:
    suite = SUITES[name]
    entries = read_manifest(suite.manifest)
    check_entry_files(entries, suite.root)
    if suite.kind == "pytest":
        check_markers(entries, suite.root)
        outcomes = read_junit(results or suite.results)
    else:
        outcomes = read_jest(results or suite.results, suite.root)
    compare(entries, outcomes)
    xfailed = sum(o.status == "xfailed" for o in outcomes)
    note = f", {xfailed} pinned as strict xfail" if xfailed else ""
    return f"Smoke {name}: {len(entries)} manifest entries, {len(outcomes)} tests ran, 0 skipped{note}."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("suite", choices=sorted(SUITES))
    parser.add_argument("results", nargs="?", type=Path, help="results file (default: the suite's)")
    args = parser.parse_args(argv)
    try:
        print(check(args.suite, args.results))
    except CheckFailed as exc:
        print(f"SMOKE CHECK FAILED ({args.suite})\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
