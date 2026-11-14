#!/usr/bin/env python3
"""Assert the queue <-> worker-pool contract holds.

Every queue declared in ``services/shared/celery_queues.py`` must be consumed by
exactly one worker pool in ``infra/helm/benger/values.yaml``. Get this wrong and
the failure is silent: messages pile up on a queue no pod is listening to, tasks
simply never run, and nothing logs an error anywhere.

Lives here rather than in the workers pytest suite because that suite's container
only mounts ``services/workers`` and ``services/shared`` -- ``infra/helm`` is not
reachable from inside it. This runs in the "Python Lint" CI job, which has the
full repo checked out, and via ``make check-queue-pools``.

It also asserts the CPU floor of the probes: every worker pool, in every
values file, must be allowed at least ``MIN_POOL_CPU_MILLIS`` of CPU. Both
probes of a pool run ``celery inspect ping``, a fresh import of ``tasks.py``
inside the pod's cgroup. Below that floor the import does not finish within the
probe timeout, and the pod is restarted by its liveness probe after most
deploys (prod ``aux`` at 500m: 18 restarts in 7 days up to 2026-11-11, one
import took 44 s against a timeout of 25 s; the pools at 1000m had none).

Exit 0 = contract holds. Exit 1 = a queue is stranded, double-served, or unknown,
or a pool is below the CPU floor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Inside the workers test container this file sits at /app/scripts, three
# levels above do not exist there. The suite imports the module for the pure
# functions below; main() runs only where the whole repo is checked out.
_HERE = Path(__file__).resolve()
REPO_ROOT = _HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parent
CHART = REPO_ROOT / "infra" / "helm" / "benger"
VALUES = CHART / "values.yaml"
# The environment files merge key-by-key over ``workerPools`` of VALUES.
OVERLAY_VALUES = (CHART / "values-staging.yaml", CHART / "values-demo.yaml")
SHARED = REPO_ROOT / "services" / "shared"
# What the exec probes of a worker pool need (see the module docstring).
MIN_POOL_CPU_MILLIS = 1000


def _load_queue_contract():
    sys.path.insert(0, str(SHARED))
    import celery_queues

    return celery_queues


def _pool_queues(values: dict) -> dict[str, list[str]]:
    """Map pool name -> its -Q list, across both templates."""
    pools: dict[str, list[str]] = {}

    workers = values.get("workers") or {}
    queues = workers.get("queues")
    if not queues:
        raise SystemExit(
            "values.yaml: workers.queues is missing. deployment-workers.yaml "
            "renders its -Q from it, so an empty value would start the bulk pool "
            "with no queues at all."
        )
    pools[workers.get("name", "workers")] = list(queues)

    for name, pool in (values.get("workerPools") or {}).items():
        if not pool.get("enabled"):
            continue
        pool_queues = pool.get("queues")
        if not pool_queues:
            raise SystemExit(f"values.yaml: workerPools.{name} is enabled but has no queues")
        pools[name] = list(pool_queues)

    return pools


def cpu_millis(value) -> float | None:
    """A Kubernetes CPU quantity in millicores (``"500m"`` -> 500, ``1`` or
    ``"1.5"`` -> 1000 / 1500), or None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) * 1000
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text[:-1]) if text.endswith("m") else float(text) * 1000
        except ValueError:
            return None
    return None


def pool_cpu_limits(values: dict) -> dict[str, object]:
    """``pool name -> resources.limits.cpu`` for every pool a values document
    sizes (the bulk ``workers`` pool and each ``workerPools`` entry that states
    resources; an overlay names only what it overrides)."""
    limits: dict[str, object] = {}
    workers = values.get("workers") or {}
    if isinstance(workers.get("resources"), dict):
        limits[workers.get("name", "workers")] = (workers["resources"].get("limits") or {}).get("cpu")
    for name, pool in (values.get("workerPools") or {}).items():
        if isinstance(pool, dict) and isinstance(pool.get("resources"), dict):
            limits[name] = (pool["resources"].get("limits") or {}).get("cpu")
    return limits


def cpu_floor_errors(limits_by_file: dict[str, dict[str, object]], floor: int = MIN_POOL_CPU_MILLIS) -> list[str]:
    """One message per pool whose CPU limit is below ``floor`` (or cannot be
    read), across the given values files."""
    errors: list[str] = []
    for file_name, limits in limits_by_file.items():
        for pool, raw in sorted(limits.items()):
            millis = cpu_millis(raw)
            if millis is None:
                errors.append(
                    f"{file_name}: pool {pool!r} states no readable CPU limit ({raw!r}); "
                    f"its probes need at least {floor}m"
                )
            elif millis < floor:
                errors.append(
                    f"{file_name}: pool {pool!r} is limited to {raw} CPU, below the {floor}m its "
                    "probes need: `celery inspect ping` re-imports tasks.py in the pod, and below "
                    "the floor the liveness probe times out and restarts the pod after deploys"
                )
    return errors


def main() -> int:
    cq = _load_queue_contract()
    values = yaml.safe_load(VALUES.read_text())
    pools = _pool_queues(values)

    served: list[str] = [q for queues in pools.values() for q in queues]
    served_set = set(served)
    errors: list[str] = []

    print("Worker pools and their queues:")
    for name, queues in sorted(pools.items()):
        print(f"  {name:10s} -Q {','.join(queues)}")
    print()

    # 1. Nothing stranded. This is the failure that costs a production incident.
    stranded = set(cq.QUEUES) - served_set
    if stranded:
        errors.append(
            f"queues declared in celery_queues.QUEUES but consumed by NO pool: "
            f"{sorted(stranded)} -- messages routed there would never run"
        )

    # 2. Legacy names must keep a consumer for the whole drain window.
    undrained = set(cq.LEGACY_QUEUES) - served_set
    if undrained:
        errors.append(
            f"retired queues with no consumer: {sorted(undrained)} -- messages "
            "published before the routing deploy would be stranded. Only remove "
            "a legacy name from LEGACY_QUEUES once its Redis list is empty."
        )

    # 3. Disjoint pools. An overlap silently re-creates the starvation this whole
    #    split exists to remove: the bulk pool would compete for interactive work.
    seen: dict[str, str] = {}
    for pool_name, queues in pools.items():
        for queue in queues:
            if queue in seen:
                errors.append(
                    f"queue {queue!r} is served by BOTH {seen[queue]!r} and "
                    f"{pool_name!r}; pools must be disjoint or slot isolation is lost"
                )
            seen[queue] = pool_name

    # 4. No pool listening to a queue that does not exist (typo guard).
    unknown = served_set - set(cq.QUEUES) - set(cq.LEGACY_QUEUES)
    if unknown:
        errors.append(
            f"pools consume queues unknown to celery_queues: {sorted(unknown)} -- "
            "either a typo, or a queue that needs adding to QUEUES"
        )

    # 5. Every pool gets the CPU its probes need, in every environment.
    limits_by_file = {VALUES.name: pool_cpu_limits(values)}
    for overlay in OVERLAY_VALUES:
        if overlay.exists():
            limits_by_file[overlay.name] = pool_cpu_limits(yaml.safe_load(overlay.read_text()) or {})
    errors.extend(cpu_floor_errors(limits_by_file))

    if errors:
        print("QUEUE/POOL CONTRACT VIOLATED:\n")
        for err in errors:
            print(f"  - {err}")
        print("\nSee services/shared/celery_queues.py and the workerPools block in values.yaml.")
        return 1

    print(
        f"OK: {len(cq.QUEUES)} queues + {len(cq.LEGACY_QUEUES)} draining legacy "
        f"names, all served by exactly one of {len(pools)} disjoint pools."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
