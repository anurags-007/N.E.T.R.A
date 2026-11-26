# syntax=docker/dockerfile:1

# --- Stage 1: Build virtual environment & wheels ---
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# --- Stage 2: Minimal non-root production runtime ---
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 netra \
    && useradd --uid 10001 --gid netra --create-home --shell /bin/false netra

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY backend ./backend
COPY frontend ./frontend
COPY data/geo/india_towers.csv ./data/geo/india_towers.csv
COPY data/test_data ./data/test_data
COPY scripts ./scripts

RUN mkdir -p data/secure_uploads data/generated_requests data/geo data/datasets \
    && chown -R netra:netra /app

USER netra

EXPOSE 8001

CMD ["gunicorn", "backend.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8001", "--workers", "4"]
