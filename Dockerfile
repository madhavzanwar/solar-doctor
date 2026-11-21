# ==============================================================================
# SolarDoctor Enterprise Backend Dockerfile
# Multi-stage build: builder -> runtime
# ==============================================================================

# Stage 1: Build stage
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONSAFEPATH=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install compilation tools and header libraries required for compiling wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    libffi-dev \
    libssl-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment to isolate installed dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements_platform.txt ./requirements_platform.txt
COPY ml/thermal/requirements.txt ./ml/requirements.txt

# Compile wheels & install dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements_platform.txt -r ./ml/requirements.txt

# Stage 2: Production runtime stage
FROM python:3.11-slim AS runtime

# PYTHONSAFEPATH=1 stops Python from putting cwd on sys.path, so the repo's
# `platform/` package can't shadow the stdlib `platform` module.
ENV PYTHONUNBUFFERED=1 \
    PYTHONSAFEPATH=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    SOLARDOCTOR_OUTPUT_DIR=/app/data/output \
    SOLARDOCTOR_DB_URL=sqlite:////app/data/solardoctor.db

WORKDIR /app

# Install minimal runtime shared libraries (no compilers or header files)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Create unprivileged application user and group (UID/GID 10001)
RUN groupadd -g 10001 solardoctor && \
    useradd -u 10001 -g solardoctor -m -s /bin/sh solardoctor

# Copy application source code
COPY . /app

# Install the application package into the virtualenv (without reinstalling dependencies)
RUN pip install --no-deps -e /app

# Ensure data and output directories exist with correct permissions
RUN mkdir -p /app/data /app/data/output /app/data/orthos /tmp/solardoctor && \
    chown -R solardoctor:solardoctor /app /opt/venv /tmp/solardoctor

USER solardoctor:solardoctor

EXPOSE 8000

# Container healthcheck querying the health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# Listen on $PORT (Cloud Run sets 8080; HF Spaces uses app_port; default 8000).
# Run from /tmp so the repo root is never on sys.path (shadow fix).
CMD ["sh", "-c", "cd /tmp && exec python -m uvicorn solardoctor.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
