"""The CPU floor of the worker pools' probes
(``scripts/check_celery_queue_pools.py``).

Both probes of a pool run ``celery inspect ping``, a fresh import of
``tasks.py`` inside the pod. A pool limited to 500m did not finish that import
within the probe timeout and was restarted after most deploys (prod ``aux``,
2026-11-11). The chart itself is checked by the script in the Python Lint job,
because this container cannot see ``infra/helm``; these tests pin the rule the
script applies.
"""

import importlib.util
from pathlib import Path

import pytest


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_celery_queue_pools.py"
    spec = importlib.util.spec_from_file_location("check_celery_queue_pools", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCpuQuantity:
    @pytest.mark.parametrize("value, millis", [
        ("500m", 500), ("1000m", 1000), (" 250m ", 250), ("1", 1000), ("1.5", 1500), (1, 1000), (0.5, 500), (6, 6000),
    ])
    def test_a_kubernetes_quantity_in_millicores(self, value, millis):
        assert _script().cpu_millis(value) == millis

    @pytest.mark.parametrize("value", [None, "", "viel", "m", True, ["1"], {"cpu": 1}])
    def test_anything_else_is_no_quantity(self, value):
        assert _script().cpu_millis(value) is None


class TestPoolLimits:
    def test_the_bulk_pool_and_every_sized_pool_are_read(self):
        values = {
            "workers": {"name": "workers", "resources": {"limits": {"cpu": "6000m"}}},
            "workerPools": {
                "fast": {"resources": {"limits": {"cpu": "1000m", "memory": "1536Mi"}}},
                "aux": {"resources": {"limits": {"cpu": "500m"}}},
                # An overlay that only changes the replica count sizes nothing.
                "ocr": {"replicaCount": 1},
                "maintenance": {"resources": {"requests": {"cpu": "50m"}}},
            },
        }
        assert _script().pool_cpu_limits(values) == {
            "workers": "6000m", "fast": "1000m", "aux": "500m", "maintenance": None,
        }

    def test_a_document_without_pools_sizes_nothing(self):
        script = _script()
        assert script.pool_cpu_limits({}) == {}
        assert script.pool_cpu_limits({"workers": {"concurrency": 1}, "workerPools": None}) == {}


class TestFloor:
    def test_the_floor_is_one_cpu(self):
        assert _script().MIN_POOL_CPU_MILLIS == 1000

    def test_pools_at_the_floor_pass(self):
        limits = {"values.yaml": {"workers": "6000m", "fast": "1000m", "aux": 1}}
        assert _script().cpu_floor_errors(limits) == []

    def test_a_pool_below_the_floor_is_named_with_its_file(self):
        errors = _script().cpu_floor_errors({
            "values.yaml": {"fast": "1000m", "aux": "500m"},
            "values-staging.yaml": {"maintenance": "0.5", "workers": "1000m"},
        })
        assert len(errors) == 2
        assert errors[0].startswith("values.yaml: pool 'aux' is limited to 500m CPU, below the 1000m its probes need")
        assert errors[1].startswith("values-staging.yaml: pool 'maintenance' is limited to 0.5 CPU, below the 1000m")

    def test_a_pool_without_a_readable_limit_is_named_too(self):
        errors = _script().cpu_floor_errors({"values-demo.yaml": {"aux": None, "fast": "viel"}})
        assert errors == [
            "values-demo.yaml: pool 'aux' states no readable CPU limit (None); its probes need at least 1000m",
            "values-demo.yaml: pool 'fast' states no readable CPU limit ('viel'); its probes need at least 1000m",
        ]
