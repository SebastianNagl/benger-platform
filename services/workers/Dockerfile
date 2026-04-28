# Workers Application Image
# Built on top of workers-base (which has Python deps + ML models).
# Code-only changes rebuild in <2 min since deps/models are cached in base.
ARG WORKERS_BASE_IMAGE=ghcr.io/sebastiannagl/benger-platform/workers-base:latest
FROM ${WORKERS_BASE_IMAGE}

WORKDIR /app

# Copy application code (this is the only layer that changes on code commits)
COPY . .

# If shared directory exists in build context, move it to the right location
RUN if [ -d "./shared" ]; then \
      mkdir -p /shared && \
      cp -r ./shared/* /shared/ && \
      rm -rf ./shared; \
    fi

# Start Celery Worker
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "celery,emails,default,generation"]
