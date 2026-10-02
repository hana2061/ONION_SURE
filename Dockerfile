# ==============================================================================
# ONION_SURE — Production Multi-Platform Dockerfile
# Smart India Hackathon 2026 - Problem Statement PS26031
# ==============================================================================

FROM python:3.11-slim as base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install minimal OS runtime libraries for OpenCV Headless and PyTorch CPU
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install pinned requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Create application non-privileged user and directories
RUN groupadd -r onionsure && \
    useradd -r -g onionsure -d /app -s /sbin/nologin onionsure && \
    mkdir -p /app/uploads /app/data /app/ml/weights && \
    chown -R onionsure:onionsure /app

# Copy application source code
COPY --chown=onionsure:onionsure alembic.ini ./
COPY --chown=onionsure:onionsure alembic/ ./alembic/
COPY --chown=onionsure:onionsure config/ ./config/
COPY --chown=onionsure:onionsure web/ ./web/
COPY --chown=onionsure:onionsure ml/ ./ml/
COPY --chown=onionsure:onionsure onion_sure/ ./onion_sure/

# Switch to non-root user
USER onionsure

# Expose FastAPI server port
EXPOSE 8000

# Docker healthcheck targeting the backend health status endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch production server with Uvicorn workers
CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn onion_sure.backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips '*'"]
