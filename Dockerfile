# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a prefix so we can copy them cleanly
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Delta Algo Bot"
LABEL description="SMA-RSI BTC Futures Trading Bot – Headless API"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Copy application source
COPY . .

# Create required runtime directories and set ownership
RUN mkdir -p logs data && \
    chown -R botuser:botuser /app

USER botuser

# Expose FastAPI port
EXPOSE 8501

# Health check – polls the /health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/health')" || exit 1

# Default: run the headless bot + API
CMD ["python", "main.py"]
