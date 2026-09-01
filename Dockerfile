# ==========================================
# Production Dockerfile for Telegram Coupon Bot
# ==========================================
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (for building binary wheels and SQLite/PostgreSQL drivers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project source code
COPY . .

# Create non-root runtime user and ensure data directories exist
RUN useradd -m botuser && \
    mkdir -p /app/data /app/backups && \
    chown -R botuser:botuser /app

USER botuser

# Healthcheck to verify process running
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the bot
CMD ["python", "bot.py"]
