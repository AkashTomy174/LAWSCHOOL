# ---------------------------------------------------------------------------
# LawSchool backend image.
#
# Multi-stage so the final layer carries no build toolchain: psycopg2 and Pillow
# need compilers to install, but nothing at runtime needs them.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build dependencies only -- discarded with the builder stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libjpeg-dev \
        zlib1g-dev \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

COPY requirements/ ./requirements/
# Build wheels once, then install them in the runtime stage without a compiler.
RUN pip install --upgrade pip wheel && \
    pip wheel --wheel-dir /wheels -r requirements/base.txt


# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# Runtime shared libraries only (no -dev packages).  curl is used by the
# container healthcheck; libmagic supports upload validation.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libjpeg62-turbo \
        zlib1g \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements/ ./requirements/
RUN pip install --no-index --find-links=/wheels -r requirements/base.txt && \
    rm -rf /wheels

COPY . .

# Static files are collected at build time.  WhiteNoise serves them, so the image
# is self-contained and needs no separate webserver for the API.
RUN SECRET_KEY=build-only-not-a-real-secret \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    REDIS_URL=redis://localhost:6379/0 \
    CORS_ALLOWED_ORIGINS=http://localhost:5173 \
    RAZORPAY_KEY_ID=build \
    RAZORPAY_KEY_SECRET=build \
    RAZORPAY_WEBHOOK_SECRET=build \
    CLOUDFLARE_ACCOUNT_ID=build \
    CLOUDFLARE_API_TOKEN=build \
    CLOUDFLARE_STREAM_KEY_ID=build \
    CLOUDFLARE_STREAM_SIGNING_KEY=build \
    python manage.py collectstatic --noinput

# Writable directories for runtime artifacts.
RUN mkdir -p /app/media /app/staticfiles && \
    chown -R appuser:appuser /app

# Never run the application as root: a container escape should not also be a
# privilege escalation.
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

# Migrations are deliberately NOT run here: every replica would race to apply
# them.  Run them once as a release step (see docs/deployment.md).
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]