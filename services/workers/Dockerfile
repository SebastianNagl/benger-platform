# Workers Application Image
# Built on top of workers-base (which has Python deps + ML models).
# Code-only changes rebuild in <2 min since deps/models are cached in base.
ARG WORKERS_BASE_IMAGE=ghcr.io/sebastiannagl/benger-platform/workers-base:latest
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

# Start Celery Worker
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "celery,emails,default,generation,evaluation"]
