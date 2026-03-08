# syntax=docker/dockerfile:1.7-labs

############################
# STAGE 1: Builder
############################
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ARG INSTALL_DEPENDENCIES=true

# Install Torch (optional)
RUN if [ "$INSTALL_DEPENDENCIES" = "true" ]; then \
    uv pip install torch --index-url https://download.pytorch.org/whl/cpu; \
    else \
    echo "Skipping Torch installation"; \
    fi

# Copy requirement files from back/
COPY back/requirements-base.txt .
COPY back/requirements.txt .

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_DEPENDENCIES" = "true" ]; then \
        uv pip install -r requirements-base.txt && \
        uv pip install -r requirements.txt; \
    else \
        echo "Skipping requirements installation"; \
    fi

RUN mkdir -p /opt/models


############################
# STAGE 2: Runner
############################
FROM python:3.11-slim

WORKDIR /app

RUN useradd -m agora_user

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv
COPY --from=builder /opt/venv /opt/venv

# Copy downloaded models
COPY --from=builder --chown=agora_user:agora_user /opt/models /opt/models

# Set environment
ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/models

# Copy backend source
COPY --chown=agora_user:agora_user back/ /app/

# Copy shared resources folder from root
COPY --chown=agora_user:agora_user resources/ /app/resources/

RUN chown -R agora_user:agora_user /app

# Entrypoint: fix permissions on bind-mounted volumes then exec as agora_user
COPY --chown=root:root back/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Do NOT switch to agora_user here — entrypoint runs as root, drops to agora_user itself
CMD ["/docker-entrypoint.sh"]
