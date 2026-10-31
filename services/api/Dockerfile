# Multi-stage optimized Dockerfile for FastAPI
#
# PYTHON_VERSION is the single source of truth: it selects the base image AND
# the site-packages path the runner stage copies out of the deps stage. Those
# two used to be independent literals, so bumping the base silently broke the
# COPY (it points at a path that no longer exists). Keep it as one ARG.
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management. Pinned: it reads uv.lock, so the
# version that wrote the lock (or newer) must be the one that installs it.
RUN pip install uv==0.11.28

# Dependencies stage
FROM base AS deps
WORKDIR /app

# Copy dependency files (manifest + lock) before the code for layer caching
COPY pyproject.toml uv.lock ./

# Install exactly the locked set into the system interpreter (/usr/local), the
# environment the runner stage copies out. --locked fails the build when
# uv.lock no longer matches pyproject.toml instead of re-resolving; --inexact
# keeps pip and uv themselves, which the lock does not list (the compose test
# runners pip-install requirements-test.txt on top at runtime).
RUN UV_PROJECT_ENVIRONMENT=/usr/local uv sync --locked --no-dev --no-install-project --inexact --no-cache

# Production stage
FROM base AS runner
# Re-declare inside the stage: a global ARG is not visible in a build stage
# until it is re-declared there.
ARG PYTHON_VERSION
WORKDIR /app

# Copy installed dependencies from deps stage
COPY --from=deps /usr/local/lib/python${PYTHON_VERSION}/site-packages /usr/local/lib/python${PYTHON_VERSION}/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# If shared directory exists in build context, move it to the right location
RUN if [ -d "./shared" ]; then \
      mkdir -p /shared && \
      cp -r ./shared/* /shared/ && \
      rm -rf ./shared; \
    fi

# Exponiere Port
EXPOSE 8000

# Starte Anwendung
# Production setup: No reload for stability, development uses override
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--access-log"] 