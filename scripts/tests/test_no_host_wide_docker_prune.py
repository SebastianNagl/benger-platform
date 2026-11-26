"""Guard: no host-wide Docker prune in the Makefile, scripts, infra or docs.

Several compose stacks (dev, test, parallel worktree stacks) share one Docker
daemon on a development host. A host-wide prune (`docker system prune`,
`docker image prune`, `docker builder prune`, ...) or a volume removal fed by a
substring `name=` filter deletes the other stacks' images, volumes and build
cache. Cleanup must be scoped to the compose project it started: `compose down
-v --remove-orphans --rmi local` plus the `com.docker.compose.project=<name>`
label filter (see `docker-remove-project-leftovers` in the Makefile).

GitHub workflows are exempt: they run on ephemeral GitHub-hosted runners that
no other stack shares.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve().relative_to(REPO).as_posix()
EXEMPT_PREFIXES = (".github/workflows/",)

HOST_WIDE_PRUNE = re.compile(
    r"\bdocker(?:-compose)?\s+(?:system|image|images|builder|buildx|volume|container|network)\s+prune\b"
)
# `docker volume ls --filter name=benger-test | xargs docker volume rm` matches
# every volume whose name merely contains the string, other stacks' included.
NAME_FILTERED_REMOVAL = re.compile(
    r"\bdocker\s+(?:volume|image|container|network)\s+ls\b[^\n|]*--filter[\s=]+[\"']?name=[^\n]*\|\s*xargs\b[^\n]*\brm\b"
)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [p for p in out.decode().split("\0") if p]


def _violations(text: str) -> list[tuple[int, str]]:
    found = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if HOST_WIDE_PRUNE.search(line) or NAME_FILTERED_REMOVAL.search(line):
            found.append((lineno, line.strip()))
    return found


@pytest.mark.parametrize(
    "line",
    [
        "\t@docker system prune -f",
        "\t@docker image prune -f 2>/dev/null || true",
        "\tdocker builder prune -f 2>/dev/null || true; \\",
        "docker buildx prune --all",
        "docker volume prune",
        "docker system prune -a --volumes",
        '\t@docker volume ls -q --filter "name=benger-test" 2>/dev/null | xargs -r docker volume rm',
    ],
)
def test_patterns_catch_host_wide_cleanup(line: str) -> None:
    assert _violations(line)


@pytest.mark.parametrize(
    "line",
    [
        "\t@$(DOCKER_COMPOSE_TEST) --profile test down -v --remove-orphans --rmi local",
        '\t@docker volume ls -q --filter "label=com.docker.compose.project=$(PROJECT)" | xargs -r docker volume rm',
        "find scripts -name __pycache__ -type d -prune -exec rm -rf {} +",
        "git worktree prune",
        "docker buildx du",
    ],
)
def test_patterns_allow_scoped_cleanup(line: str) -> None:
    assert not _violations(line)


def test_no_host_wide_docker_prune_outside_ci_workflows() -> None:
    offenders = []
    for rel in _tracked_files():
        if rel == THIS_FILE or rel.startswith(EXEMPT_PREFIXES):
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        offenders += [f"{rel}:{n}: {line}" for n, line in _violations(text)]
    assert not offenders, (
        "Host-wide Docker cleanup found; scope it to the compose project "
        "(compose down -v --remove-orphans --rmi local, label "
        "com.docker.compose.project=<name>):\n" + "\n".join(offenders)
    )
