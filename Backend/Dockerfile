# ============================================================
# WattPilot AI - Backend Dockerfile
# Multi-stage build for the FastAPI backend service.
# ============================================================

# --------------------------------------------------
# Stage 1: Build dependencies
# Use uv for fast, reliable Python dependency resolution.
# --------------------------------------------------
FROM python:3.14-slim AS builder

# Install uv for fast package management
RUN pip install --no-cache-dir uv

# Set working directory inside the container
WORKDIR /app

# Copy only dependency files first to leverage Docker layer caching.
# Changes to source code won't trigger a full dependency reinstall.
COPY requirements.txt ./

# Install Python dependencies into the system site-packages
# --no-cache: don't store pip's download cache (smaller image)
RUN uv pip install --system --no-cache -r requirements.txt

# --------------------------------------------------
# Stage 2: Production image
# Copy only what's needed for runtime.
# --------------------------------------------------
FROM python:3.14-slim AS runtime

# Set environment variables for Python
# - PYTHONDONTWRITEBYTECODE: don't write .pyc files (faster startup)
# - PYTHONUNBUFFERED: flush stdout/stderr immediately (real-time logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required at runtime (curl for health checks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set working directory
WORKDIR /app

# Copy application source code (excluding items in .dockerignore)
COPY Backend/ ./Backend/
COPY main.py ./

# Expose the port the FastAPI server listens on
EXPOSE 8000

# Health check to verify the container is running and responsive
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the FastAPI server with uvicorn.
# NOTE: main.py binds to 127.0.0.1 by default for local dev; inside a container
# we must bind to 0.0.0.0 so the process is reachable from outside the container
# (Docker port forwarding lands on the container's non-loopback interface).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
