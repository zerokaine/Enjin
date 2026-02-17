FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required by lxml, spaCy, and asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libxml2-dev \
        libxslt-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir . && \
    python -m spacy download en_core_web_sm

# Copy application code
COPY app/ app/

# Default: run the Celery worker
CMD ["celery", "-A", "app.main", "worker", "--loglevel=info", "--concurrency=4"]
