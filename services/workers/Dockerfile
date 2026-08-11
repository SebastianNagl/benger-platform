# Workers Application Image
# Built on top of workers-base (which has Python deps + ML models).
# Code-only changes rebuild in <2 min since deps/models are cached in base.
# Pinned to a CONTENT tag, not :latest. The base only rebuilds on pushes to
# main, so a floating :latest lets this image and its base drift: on
# 2026-08-11 a staging deploy layered numpy 2.x + spaCy 3.8 onto a stale
# Python 3.11 + CUDA base and shipped a stack nobody intended. The tag changes
# in the same commit as the base content, so that cannot happen silently.
# Keep in lockstep with CONTENT_TAG in .github/workflows/build-workers-base.yml.
ARG WORKERS_BASE_IMAGE=ghcr.io/sebastiannagl/benger-platform/workers-base:py313-cpu
FROM ${WORKERS_BASE_IMAGE}

WORKDIR /app

# Safety net: install the worker's declared deps on top of the base.
# workers-base bakes in deps + ML models for fast code builds, but when a new
# dependency is added to pyproject.toml ahead of a base rebuild, the pinned
# base lacks it (e.g. boto3/ijson for object-storage export/import — issue #158).
# Installing the declared deps here guarantees the worker image always has its
# declared deps regardless of base staleness. Cached on pyproject.toml
# content, so code-only commits still rebuild fast — it's a near no-op when the
# base is already current (all packages already satisfied).
#
# This resolve reads the same pyproject.toml as the base, so it inherits the
# CPU-only torch index declared there — it cannot silently reinstall the CUDA
# build on top of the slimmed base.
COPY pyproject.toml ./pyproject.toml
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache-dir -r pyproject.toml

# Copy application code (this is the only layer that changes on code commits)
COPY . .

# If shared directory exists in build context, move it to the right location
RUN if [ -d "./shared" ]; then \
      mkdir -p /shared && \
      cp -r ./shared/* /shared/ && \
      rm -rf ./shared; \
    fi

# Start Celery Worker.
#
# This CMD consumes the FULL union of queues, including the retired `celery` and
# `default` names, so a bare `docker run` of this image never strands a message.
# Deployments override `command` per pool (see workers.queues + workerPools in
# infra/helm/benger/values.yaml) -- that split is where the actual starvation fix
# lives. Compose overrides it too; see infra/docker-compose.yml.
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "interactive,emails,maintenance,generation,evaluation,bulk,celery,default"]
