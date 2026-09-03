# NIFTY 50 Drawdown Alert System - production image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for building SQLite/yfinance deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the application
COPY src/ src/
COPY config/ config/

# Volumes: persistent data and logs
RUN mkdir -p /app/data /app/logs
VOLUME ["/app/data", "/app/logs"]

# Health check - verifies the app is alive via a lightweight probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/health_check.py || exit 1

COPY health_check.py .

# Run the main alert engine
CMD ["python", "-u", "-m", "src.main"]
