"""Coder plugins: registration, code hashes, overlays and coder measures.

The acceptance check: a coder plugin registered by an overlay (a fake
package whose workers module exposes ``register_coders``) runs as an analysis
measure and the frame records its name, version, code hash and package.
"""

from __future__ import annotations

import hashlib
import inspect
import math
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
workers_root = os.path.dirname(os.path.dirname(HERE))
for path in (workers_root, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import extension_registry  # noqa: E402
import overlay_coder_fixture  # noqa: E402
from analysis.canonical import json_hash  # noqa: E402
from analysis.coders import (  # noqa: E402
    CODER_FORMAT_VERSION,
    CoderContext,
    CoderError,
    CoderRegistry,
    FunctionCoder,
    coder_code_hash,
    coder_registry,
    load_overlay_coders,
)
from core_version import CORE_API_VERSION  # noqa: E402

OVERLAY = "benger_codes_overlay"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.delenv("BENGER_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    extension_registry.reset()
    coder_registry.unregister("first_blamed")
    yield
    extension_registry.reset()
    coder_registry.unregister("first_blamed")


def _install_overlay(monkeypatch):
    pkg = types.ModuleType(OVERLAY)
    pkg.__file__ = f"/fake/{OVERLAY}/__init__.py"
    pkg.COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]
    workers = types.ModuleType(f"{OVERLAY}.workers")
    workers.register_coders = overlay_coder_fixture.register_coders
    pkg.workers = workers
    monkeypatch.setitem(sys.modules, OVERLAY, pkg)
    monkeypatch.setitem(sys.modules, workers.__name__, workers)
    monkeypatch.setenv("BENGER_EXTENSIONS", OVERLAY)


def _expected_hash():
    source = inspect.getsource(overlay_coder_fixture)
    return json_hash({
        "format": CODER_FORMAT_VERSION,
        "name": "first_blamed",
        "version": "2",
        "outputs": {"side": "text", "mentions": "number", "hedged": "bool"},
        "sources": [{"module": "overlay_coder_fixture",
                     "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()}],
    })


class TestRegistry:
    def test_register_records_version_hash_and_sources(self):
        reg = CoderRegistry()
        entry = reg.register(overlay_coder_fixture.FirstBlamed())
        assert entry.ref == "first_blamed@2"
        assert entry.code_hash == _expected_hash()
        assert entry.sources[0]["module"] == "overlay_coder_fixture"
        assert entry.owner is None
        assert reg.names() == ["first_blamed"]
        assert reg.describe()[0]["code_hash"] == entry.code_hash

    def test_hash_changes_with_version_outputs_and_source(self):
        base = overlay_coder_fixture.FirstBlamed()
        h, _ = coder_code_hash(base)

        class Bumped(overlay_coder_fixture.FirstBlamed):
            version = "3"

        assert coder_code_hash(Bumped())[0] != h

        def fn(text, context):
            return {"n": len(text or "")}

        a = FunctionCoder("length", "1", {"n": "number"}, fn)
        b = FunctionCoder("length", "1", {"n": "text"}, fn)
        assert coder_code_hash(a)[0] != coder_code_hash(b)[0]
        # this test module is a counted source of the function coder
        assert any(s["module"] == __name__ for s in coder_code_hash(a)[1])

    @pytest.mark.parametrize(
        "attrs, needle",
        [
            ({"name": "bad name"}, "identifier"),
            ({"version": ""}, "version"),
            ({"outputs": {}}, "at least one output"),
            ({"outputs": {"x": "float"}}, "has type"),
        ],
    )
    def test_invalid_coders_are_refused(self, attrs, needle):
        cls = type("Broken", (overlay_coder_fixture.FirstBlamed,), attrs)
        with pytest.raises(CoderError, match=needle):
            CoderRegistry().register(cls())

    def test_a_coder_without_readable_source_has_no_hash(self):
        module = types.ModuleType("no_source_module")
        sys.modules["no_source_module"] = module
        try:
            cls = type("Hidden", (overlay_coder_fixture.FirstBlamed,), {"__module__": "no_source_module"})
            with pytest.raises(CoderError, match="not readable"):
                CoderRegistry().register(cls())
        finally:
            del sys.modules["no_source_module"]

    def test_resolve_pins_versions_and_runs_with_coercion(self):
        reg = CoderRegistry()
        reg.register(overlay_coder_fixture.FirstBlamed())
        with pytest.raises(CoderError, match="pins '1'"):
            reg.resolve("first_blamed", "1")
        with pytest.raises(CoderError, match="no coder"):
            reg.resolve("missing")
        entry = reg.resolve("first_blamed", "2")
        out = entry.run("The respondent, perhaps the claimant.", CoderContext())
        assert out == {"side": "D", "mentions": 2.0, "hedged": 1.0}
        empty = entry.run(None, CoderContext())
        assert empty["side"] is None and math.isnan(empty["mentions"])

    def test_a_failing_coder_is_reported(self):
        class Raises(overlay_coder_fixture.FirstBlamed):
            def code(self, text, context):
                raise RuntimeError("boom")

        class NotAMapping(overlay_coder_fixture.FirstBlamed):
            def code(self, text, context):
                return ["P"]

        reg = CoderRegistry()
        with pytest.raises(CoderError, match="failed: RuntimeError: boom"):
            reg.register(Raises()).run("x", CoderContext())
        with pytest.raises(CoderError, match="not a mapping"):
            reg.register(NotAMapping()).run("x", CoderContext())


class TestOverlay:
    def test_overlay_registration_records_owner_and_hash(self, monkeypatch):
        _install_overlay(monkeypatch)
        reg = CoderRegistry()
        assert load_overlay_coders(reg) == [OVERLAY]
        entry = reg.get("first_blamed")
        assert entry.owner == OVERLAY and entry.code_hash == _expected_hash()

    def test_an_inactive_overlay_coder_does_not_run(self, monkeypatch):
        _install_overlay(monkeypatch)
        reg = CoderRegistry()
        load_overlay_coders(reg)
        import extension_activation

        monkeypatch.setattr(extension_activation, "package_active", lambda package, gating="gated": False)
        with pytest.raises(CoderError, match="switched off"):
            reg.resolve("first_blamed")

    def test_overlay_coder_runs_as_a_measure_and_the_frame_records_its_hash(self, monkeypatch):
        """Acceptance: registered by an overlay, run by the engine, hash recorded."""
        from analysis.codes import CodeInputs
        from analysis.frame import build_frame
        from analysis.observations import observations_from_records
        from analysis.spec import normalize_spec

        _install_overlay(monkeypatch)
        load_overlay_coders(force=True)
        records = [
            {"generation_id": "g1", "task_id": "t1", "model_id": "m", "design": "d", "unit": "u1",
             "factors": {"swap": 0}, "answer_text": "The claimant is at fault, not the respondent.",
             "fields": {"reason": "perhaps the respondent"}},
            {"generation_id": "g2", "task_id": "t2", "model_id": "m", "design": "d", "unit": "u1",
             "factors": {"swap": 1}, "answer_text": "The claimant is at fault.", "fields": {}},
            {"generation_id": "g3", "task_id": "t3", "model_id": "m", "design": "d", "unit": "u2",
             "factors": {"swap": 0}, "answer_text": "Nobody is.", "fields": {}},
        ]
        spec = normalize_spec({
            "spec_version": 1, "name": "coder", "inputs": {"designs": ["d"]},
            "measures": {
                "side": {"kind": "coder", "coder": "first_blamed", "version": "2", "output": "side",
                         "parameters": {"default": "nobody"}},
                "mentions": {"kind": "coder", "coder": "first_blamed", "output": "mentions",
                             "parameters": {"default": "nobody"}},
                "reason_side": {"kind": "coder", "coder": "first_blamed", "output": "side",
                                "input": {"field": "reason"}},
                "blames_p": {"kind": "expression", "expr": "100 * (side == 'P')"},
            },
            "estimands": [{"id": "e", "estimator": "mean_rate", "outcome": "blames_p"}],
        })
        built = build_frame(observations_from_records(records), spec, codes=CodeInputs())
        frame = built.frame
        assert frame["side"].tolist() == ["P", "D", "nobody"]
        assert frame["mentions"].tolist() == [2.0, 1.0, 0.0]
        assert frame["reason_side"].tolist() == ["D", None, None]
        assert frame["blames_p"].tolist() == [100.0, 0.0, 0.0]
        recs = {c["measure"]: c for c in built.codes}
        for mid in ("side", "mentions", "reason_side"):
            assert recs[mid]["kind"] == "coder"
            assert recs[mid]["code_hash"] == _expected_hash()
            assert recs[mid]["owner"] == OVERLAY
            assert recs[mid]["version"] == "2" and recs[mid]["name"] == "first_blamed"
        assert recs["side"]["ref"] == "first_blamed@2:side"
        # the identity separates outputs, inputs and parameters
        assert len({recs[m]["hash"] for m in recs}) == 3

    def test_a_spec_pinning_another_version_fails_the_frame(self, monkeypatch):
        from analysis.frame import FrameError, build_frame
        from analysis.observations import observations_from_records
        from analysis.spec import normalize_spec

        _install_overlay(monkeypatch)
        load_overlay_coders(force=True)
        def spec_with(measure):
            return normalize_spec({
                "spec_version": 1, "name": "coder", "inputs": {"designs": ["d"]},
                "measures": {"side": measure},
                "estimands": [{"id": "e", "estimator": "mean_rate", "outcome": "side"}],
            })

        rec = {"generation_id": "g", "task_id": "t", "model_id": "m", "design": "d", "unit": "u",
               "answer_text": "x", "fields": {}}
        pinned = spec_with({"kind": "coder", "coder": "first_blamed", "version": "9", "output": "side"})
        with pytest.raises(FrameError, match="pins '9'"):
            build_frame(observations_from_records([rec]), pinned)
        bad_output = spec_with({"kind": "coder", "coder": "first_blamed", "output": "nope"})
        with pytest.raises(FrameError, match="has no output 'nope'"):
            build_frame(observations_from_records([rec]), bad_output)
        unknown = spec_with({"kind": "coder", "coder": "never_registered", "output": "side"})
        with pytest.raises(FrameError, match="no coder 'never_registered'"):
            build_frame(observations_from_records([rec]), unknown)
