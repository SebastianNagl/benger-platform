"""Tests for scripts/check_smoke.py, the guard behind the CI smoke gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "check_smoke.py"
_spec = importlib.util.spec_from_file_location("check_smoke", SCRIPT)
check_smoke = importlib.util.module_from_spec(_spec)
# dataclasses resolve their module through sys.modules.
sys.modules["check_smoke"] = check_smoke
_spec.loader.exec_module(check_smoke)

CheckFailed = check_smoke.CheckFailed


def _junit(path: Path, cases: list[str]) -> Path:
    path.write_text(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>", encoding="utf-8")
    return path


def _case(file: str, classname: str, name: str, body: str = "") -> str:
    return f'<testcase file="{file}" classname="{classname}" name="{name}">{body}</testcase>'


@pytest.fixture
def service(tmp_path):
    """A service dir with two test files and a manifest naming one test."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (tests / "test_plain.py").write_text("def test_y(): pass\n", encoding="utf-8")
    manifest = tests / "smoke_manifest.txt"
    manifest.write_text("tests/test_a.py::test_x\n", encoding="utf-8")
    return tmp_path


def _suite(service: Path, monkeypatch, kind: str = "pytest", results: str = ".smoke-results.xml"):
    manifest = service / ("tests/smoke_manifest.txt" if kind == "pytest" else "smoke_manifest.txt")
    suite = check_smoke.Suite(kind, service, manifest, service / results)
    monkeypatch.setitem(check_smoke.SUITES, "probe", suite)
    return suite


class TestManifest:
    def test_unsorted_manifest_is_refused(self, tmp_path):
        manifest = tmp_path / "m.txt"
        manifest.write_text("b\na\n", encoding="utf-8")
        with pytest.raises(CheckFailed, match="sorted"):
            check_smoke.read_manifest(manifest)

    def test_duplicates_and_blank_lines_are_refused(self, tmp_path):
        manifest = tmp_path / "m.txt"
        manifest.write_text("a\na\n\n", encoding="utf-8")
        with pytest.raises(CheckFailed):
            check_smoke.read_manifest(manifest)

    def test_empty_manifest_is_refused(self, tmp_path):
        manifest = tmp_path / "m.txt"
        manifest.write_text("", encoding="utf-8")
        with pytest.raises(CheckFailed, match="no tests"):
            check_smoke.read_manifest(manifest)

    def test_missing_file_is_named(self, service):
        with pytest.raises(CheckFailed, match="tests/test_gone.py"):
            check_smoke.check_entry_files(["tests/test_gone.py::test_x"], service)


class TestJunit:
    def test_node_ids_are_rebuilt_from_xunit1_cases(self, tmp_path):
        path = _junit(
            tmp_path / "r.xml",
            [
                _case("tests/unit/test_a.py", "tests.unit.test_a", "test_x"),
                _case("tests/unit/test_a.py", "tests.unit.test_a.TestK", "test_y[p.1]"),
            ],
        )
        nodes = [o.node for o in check_smoke.read_junit(path)]
        assert nodes == ["tests/unit/test_a.py::test_x", "tests/unit/test_a.py::TestK::test_y[p.1]"]

    def test_a_case_without_file_asks_for_xunit1(self, tmp_path):
        path = tmp_path / "r.xml"
        path.write_text('<testsuite><testcase classname="tests.test_a" name="t"/></testsuite>', encoding="utf-8")
        with pytest.raises(CheckFailed, match="xunit1"):
            check_smoke.read_junit(path)

    def test_outcomes(self, tmp_path):
        path = _junit(
            tmp_path / "r.xml",
            [
                _case("tests/test_a.py", "tests.test_a", "ok"),
                _case("tests/test_a.py", "tests.test_a", "bad", '<failure message="boom"/>'),
                _case("tests/test_a.py", "tests.test_a", "err", '<error message="boom"/>'),
                _case("tests/test_a.py", "tests.test_a", "skip", '<skipped message="off"/>'),
                _case("tests/test_a.py", "tests.test_a", "xf", '<skipped type="pytest.xfail" message="bug"/>'),
            ],
        )
        assert [o.status for o in check_smoke.read_junit(path)] == ["passed", "failed", "failed", "skipped", "xfailed"]


class TestCompare:
    def _outcomes(self, *pairs):
        return [check_smoke.Outcome(node, status) for node, status in pairs]

    def test_class_file_and_parametrized_entries_own_their_tests(self):
        ran = check_smoke.compare(
            ["tests/test_a.py", "tests/test_b.py::TestK", "tests/test_c.py::test_p"],
            self._outcomes(
                ("tests/test_a.py::test_x", "passed"),
                ("tests/test_b.py::TestK::test_y", "passed"),
                ("tests/test_c.py::test_p[1]", "passed"),
                ("tests/test_c.py::test_p[2]", "xfailed"),
            ),
        )
        assert ran == {"tests/test_a.py": 1, "tests/test_b.py::TestK": 1, "tests/test_c.py::test_p": 2}

    def test_an_entry_that_ran_nothing_fails(self):
        with pytest.raises(CheckFailed, match="ran no test"):
            check_smoke.compare(
                ["tests/test_a.py::test_x", "tests/test_a.py::test_z"],
                self._outcomes(("tests/test_a.py::test_x", "passed")),
            )

    def test_a_prefix_is_not_a_match(self):
        with pytest.raises(CheckFailed, match="ran no test"):
            check_smoke.compare(
                ["tests/test_a.py::test_x"], self._outcomes(("tests/test_a.py::test_xy", "passed"))
            )

    def test_a_skip_fails(self):
        with pytest.raises(CheckFailed, match="SKIPPED"):
            check_smoke.compare(["tests/test_a.py"], self._outcomes(("tests/test_a.py::test_x", "skipped")))

    def test_a_failure_fails(self):
        with pytest.raises(CheckFailed, match="failed"):
            check_smoke.compare(["tests/test_a.py"], self._outcomes(("tests/test_a.py::test_x", "failed")))

    def test_a_test_outside_the_manifest_fails(self):
        with pytest.raises(CheckFailed, match="no manifest entry"):
            check_smoke.compare(
                ["tests/test_a.py"],
                self._outcomes(("tests/test_a.py::test_x", "passed"), ("tests/test_b.py::test_y", "passed")),
            )


class TestJest:
    def _report(self, root: Path, results: list[dict]) -> Path:
        path = root / ".smoke-results.json"
        path.write_text(json.dumps({"testResults": results}), encoding="utf-8")
        return path

    def test_paths_are_made_relative_and_pending_counts_as_skipped(self, tmp_path):
        path = self._report(
            tmp_path,
            [
                {
                    "name": str(tmp_path / "src/a.test.ts"),
                    "status": "passed",
                    "assertionResults": [
                        {"fullName": "a works", "status": "passed"},
                        {"fullName": "a later", "status": "pending"},
                    ],
                }
            ],
        )
        outcomes = check_smoke.read_jest(path, tmp_path)
        assert [(o.node, o.status) for o in outcomes] == [
            ("src/a.test.ts::a works", "passed"),
            ("src/a.test.ts::a later", "skipped"),
        ]

    def test_a_suite_that_failed_to_run_is_a_failure(self, tmp_path):
        path = self._report(
            tmp_path,
            [{"name": str(tmp_path / "src/a.test.ts"), "status": "failed", "message": "SyntaxError", "assertionResults": []}],
        )
        assert [o.status for o in check_smoke.read_jest(path, tmp_path)] == ["failed"]


class TestEndToEnd:
    def test_pytest_suite_passes(self, service, monkeypatch):
        _suite(service, monkeypatch)
        _junit(service / ".smoke-results.xml", [_case("tests/test_a.py", "tests.test_a", "test_x")])
        assert "1 tests ran, 0 skipped" in check_smoke.check("probe")

    def test_pytest_suite_whose_entry_ran_nothing_fails(self, service, monkeypatch):
        _suite(service, monkeypatch)
        _junit(service / ".smoke-results.xml", [])
        with pytest.raises(CheckFailed, match="ran no test"):
            check_smoke.check("probe")

    def test_missing_results_file_fails(self, service, monkeypatch):
        _suite(service, monkeypatch)
        with pytest.raises(CheckFailed, match="Cannot read"):
            check_smoke.check("probe")

    def test_jest_suite_passes(self, tmp_path, monkeypatch):
        (tmp_path / "src").mkdir()
        (tmp_path / "src/a.test.ts").write_text("", encoding="utf-8")
        (tmp_path / "smoke_manifest.txt").write_text("src/a.test.ts\n", encoding="utf-8")
        _suite(tmp_path, monkeypatch, kind="jest", results=".smoke-results.json")
        self_report = {
            "testResults": [
                {"name": str(tmp_path / "src/a.test.ts"), "status": "passed",
                 "assertionResults": [{"fullName": "x", "status": "passed"}]}
            ]
        }
        (tmp_path / ".smoke-results.json").write_text(json.dumps(self_report), encoding="utf-8")
        assert "1 tests ran" in check_smoke.check("probe")

    def test_the_repository_manifests_are_well_formed(self):
        for suite in check_smoke.SUITES.values():
            entries = check_smoke.read_manifest(suite.manifest)
            check_smoke.check_entry_files(entries, suite.root)

    def test_main_exit_codes(self, service, monkeypatch, capsys):
        _suite(service, monkeypatch)
        assert check_smoke.main(["probe"]) == 1
        assert "SMOKE CHECK FAILED (probe)" in capsys.readouterr().err
        _junit(service / ".smoke-results.xml", [_case("tests/test_a.py", "tests.test_a", "test_x")])
        assert check_smoke.main(["probe"]) == 0
