# syntax=docker/dockerfile:1.7
# ─── Stage 1: Builder ────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install uv
RUN pip install uv

WORKDIR /app

# Copy lockfile first for layer caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# ─── Stage 2: Runtime ────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user
RUN groupadd --system pptagent && \
    useradd --system --gid pptagent --create-home --shell /bin/bash pptagent

# Install runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy venv from builder
COPY --from=builder --chown=pptagent:pptagent /app/.venv /app/.venv
COPY --chown=pptagent:pptagent . /app/

USER pptagent

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
