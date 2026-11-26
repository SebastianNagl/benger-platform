"""Behavioural tests for the Makefile's Docker cleanup (test-prune, clean-docker, test-quiet).

Several compose stacks (dev, test, parallel worktree stacks) share one Docker
daemon on a development host, so cleanup must stay inside the compose project
it started. The real make targets run here against a fake `docker` placed
first on PATH, which records every call and never touches a real daemon.

The oracle is Docker's CLI contract: `docker <system|image|builder|buildx|
volume|container|network> prune` acts on the whole daemon, and a `name=`
filter matches by substring, so neither may ever be called. Compose calls are
scoped by `-p <project>`, and leftover listing by the compose project label
`com.docker.compose.project=<project>`. The test project must differ from the
dev project, otherwise `down -v` on the test stack deletes the dev database.
Before the fix, test-prune and test-quiet ran `docker image prune -f` and
`docker builder prune -f`, which the prune assertion rejects.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PRUNE_SCOPES = {
    "system",
    "image",
    "builder",
    "buildx",
    "volume",
    "container",
    "network",
}
LEFTOVER_VOLUME = "leftover-volume-id"

FAKE_DOCKER = f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({{"argv": args, "traefik": os.environ.get("BENGER_TRAEFIK_PROJECT")}}) + "\\n")
if args[:2] == ["volume", "ls"]:
    print("{LEFTOVER_VOLUME}")
"""


def _run_make(
    tmp_path: Path, *args: str, compose_project_name: str | None = None
) -> tuple[subprocess.CompletedProcess, list[dict]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    # test-quiet also runs the frontend suites and waits for the stack to boot.
    for name in ("npm", "npx", "sleep"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    log = tmp_path / "docker-calls.jsonl"
    log.unlink(missing_ok=True)

    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "MAKEFLAGS",
            "MAKELEVEL",
            "MFLAGS",
            "COMPOSE_PROJECT_NAME",
            "BENGER_TRAEFIK_PROJECT",
        }
    }
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_DOCKER_LOG"] = str(log)
    if compose_project_name is not None:
        env["COMPOSE_PROJECT_NAME"] = compose_project_name

    result = subprocess.run(
        ["make", "-C", str(REPO), "--no-print-directory", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    calls = (
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        if log.exists()
        else []
    )
    return result, calls


def _is_compose_version(call: dict) -> bool:
    return call["argv"][:2] == ["compose", "version"]


def _assert_scoped_to(calls: list[dict], project: str, *, test_stack: bool) -> None:
    label = f"label=com.docker.compose.project={project}"
    for call in calls:
        argv = call["argv"]
        assert not (
            len(argv) >= 2 and argv[0] in PRUNE_SCOPES and argv[1] == "prune"
        ), argv
        assert not any(a.startswith(("name=", "--filter=name=")) for a in argv), argv
        if _is_compose_version(call):
            continue
        if argv[0] == "compose":
            assert argv[argv.index("-p") + 1] == project, argv
            if test_stack:
                assert call["traefik"] == project, call
        elif argv[:2] in (["volume", "ls"], ["image", "ls"]):
            assert label in argv, argv


SCENARIOS = [
    # (COMPOSE_PROJECT_NAME, dev project, test project)
    (None, "benger", "benger-test"),
    ("x", "x", "x-test"),
]


@pytest.mark.parametrize(
    ("compose_project_name", "dev_project", "test_project"), SCENARIOS
)
def test_test_prune_removes_only_the_test_project(
    tmp_path, compose_project_name, dev_project, test_project
):
    result, calls = _run_make(
        tmp_path, "test-prune", compose_project_name=compose_project_name
    )

    assert result.returncode == 0, result.stdout + result.stderr
    _assert_scoped_to(calls, test_project, test_stack=True)
    downs = [
        c["argv"] for c in calls if c["argv"][0] == "compose" and "down" in c["argv"]
    ]
    assert downs and all({"-v", "--remove-orphans"} <= set(d) for d in downs), downs
    assert ["volume", "rm", LEFTOVER_VOLUME] in [c["argv"] for c in calls]
    assert dev_project != test_project


@pytest.mark.parametrize(
    ("compose_project_name", "dev_project", "test_project"), SCENARIOS
)
def test_clean_docker_removes_only_the_dev_project(
    tmp_path, compose_project_name, dev_project, test_project
):
    result, calls = _run_make(
        tmp_path, "clean-docker", compose_project_name=compose_project_name
    )

    assert result.returncode == 0, result.stdout + result.stderr
    _assert_scoped_to(calls, dev_project, test_stack=False)
    assert any(c["argv"][0] == "compose" and "down" in c["argv"] for c in calls)
    assert ["volume", "rm", LEFTOVER_VOLUME] in [c["argv"] for c in calls]


@pytest.mark.parametrize(
    ("compose_project_name", "dev_project", "test_project"), SCENARIOS
)
def test_test_quiet_runs_and_cleans_up_only_the_test_project(
    tmp_path, compose_project_name, dev_project, test_project
):
    result, calls = _run_make(
        tmp_path, "test-quiet", compose_project_name=compose_project_name
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All passed" in result.stdout
    _assert_scoped_to(calls, test_project, test_stack=True)
    assert any(
        c["argv"][0] == "compose" and "down" in c["argv"] and "-v" in c["argv"]
        for c in calls
    )


@pytest.mark.parametrize(
    "target", ["test-prune", "clean-docker", "docker-remove-project-leftovers"]
)
def test_equal_dev_and_test_project_is_refused_before_any_removal(tmp_path, target):
    result, calls = _run_make(
        tmp_path,
        "DEV_COMPOSE_PROJECT=same",
        "TEST_COMPOSE_PROJECT=same",
        "PROJECT=same",
        target,
    )

    assert result.returncode != 0
    assert "distinct names" in result.stderr
    assert all(_is_compose_version(c) for c in calls), calls
