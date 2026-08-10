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

# Install uv for dependency management
RUN pip install uv

# Dependencies stage
FROM base AS deps
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY requirements.txt* ./

# Install dependencies only
RUN uv pip install --system --no-cache-dir -r pyproject.toml

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