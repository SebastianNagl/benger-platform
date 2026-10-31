# Workers Application Image
# Built on top of workers-base (which has Python deps + ML models).
# Code-only changes rebuild in <2 min since deps/models are cached in base.
# Pinned to a CONTENT tag, not :latest. The base only rebuilds on pushes to
# main, so a floating :latest lets this image and its base drift: on
# 2026-08-11 a staging deploy layered numpy 2.x + spaCy 3.8 onto a stale
# Python 3.11 + CUDA base and shipped a stack nobody intended. The tag changes
# in the same commit as the base content, so that cannot happen silently.
# Keep in lockstep with CONTENT_TAG in .github/workflows/build-workers-base.yml.
#
# py313-cpu-r2: first base that runs as uid 1000 and bakes the lang="de"
# BERTScore model (bert-base-multilingual-cased) under HF_HOME=/opt/hf with
# HF_HUB_OFFLINE=1, instead of roberta-large under /root/.cache.
ARG WORKERS_BASE_IMAGE=ghcr.io/sebastiannagl/benger-platform/workers-base:py313-cpu-r2
FROM ${WORKERS_BASE_IMAGE} AS app

# The base ends as uid 1000; the install steps below need root.
USER root
WORKDIR /app

# Safety net: install the worker's locked deps on top of the base.
# workers-base bakes in deps + ML models for fast code builds, but when uv.lock
# changes ahead of a base rebuild, the pinned base lacks (or carries other
# versions of) some packages (e.g. boto3/ijson for object-storage
# export/import, issue #158). Syncing the lock here guarantees the worker image
# always runs exactly the locked set regardless of base staleness. Cached on
# pyproject.toml + uv.lock content, so code-only commits still rebuild fast:
# it is a near no-op when the base already matches the lock.
#
# The lock pins the CPU-only torch wheels, so this cannot silently reinstall
# the CUDA build on top of the slimmed base. --locked fails the build when
# uv.lock no longer matches pyproject.toml; --inexact leaves everything the
# lock does not list (pip, uv) alone.
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.28 && UV_PROJECT_ENVIRONMENT=/usr/local uv sync --locked --no-dev --no-install-project --inexact --no-cache

# Copy application code (this is the only layer that changes on code commits),
# owned by the runtime uid. .dockerignore keeps tests/ and local state out.
COPY --chown=1000:1000 . .

# If shared directory exists in build context, move it to the right location
# (cp -a keeps the uid 1000 ownership from the COPY above). WORKDIR created
# /app as root, so hand the directory itself to uid 1000 as well.
RUN chown 1000:1000 /app && \
    if [ -d "./shared" ]; then \
      mkdir -p /shared && \
      cp -a ./shared/. /shared/ && \
      chown 1000:1000 /shared && \
      rm -rf ./shared; \
    fi

# Same values as the base, repeated so this image is correct even if the base
# ever regresses on them. /tmp (Celery beat schedule, export/import spool) is
# world-writable in the base image already.
ENV HF_HOME=/opt/hf HF_HUB_OFFLINE=1
USER 1000

# Start Celery Worker.
#
# This CMD consumes the FULL union of queues, including the retired `celery` and
# `default` names, so a bare `docker run` of this image never strands a message.
# Deployments override `command` per pool (see workers.queues + workerPools in
# infra/helm/benger/values.yaml) -- that split is where the actual starvation fix
# lives. Compose overrides it too; see infra/docker-compose.yml.
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "interactive,emails,maintenance,generation,evaluation,bulk,celery,default"]

# Test runner image (infra/docker-compose.test.yml test-workers-runner, built
# with `target: test`). Adds the `test` extra and stays root: the runner
# bind-mounts the source over /app, writes coverage files into it from hosts
# with arbitrary uids, and pip-installs requirements-test.txt at start.
FROM app AS test
USER root
# Same locked set as the stage above plus the `test` extra; --inexact keeps
# pip and uv for the runtime requirements-test.txt install.
RUN UV_PROJECT_ENVIRONMENT=/usr/local uv sync --locked --no-dev --extra test --no-install-project --inexact --no-cache

# Production image: the default (last) stage, identical to `app`. Keep it last
# so a plain `docker build` (extended cicd.yml) never produces the test image.
FROM app AS runtime
