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

Exit 0 = contract holds. Exit 1 = a queue is stranded, double-served, or unknown.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
VALUES = REPO_ROOT / "infra" / "helm" / "benger" / "values.yaml"
SHARED = REPO_ROOT / "services" / "shared"


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
