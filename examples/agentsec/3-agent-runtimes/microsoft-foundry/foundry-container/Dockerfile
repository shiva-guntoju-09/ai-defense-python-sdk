# =============================================================================
# Dockerfile for Azure AI Foundry Container Deployment
# =============================================================================
# This Dockerfile builds a container image for the SRE agent.
# It uses Python 3.11 slim as the base image.
#
# Build context should be the microsoft-foundry example root directory:
#   docker build -f foundry-container/Dockerfile -t foundry-agent .
#
# Note: agentsec is not on PyPI, so we copy it from source.
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pip dependencies
COPY foundry-container/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy agentsec from the repository (since it's not on PyPI)
# The deploy.sh script copies agentsec to the root directory before build
COPY agentsec /app/agentsec

# Copy shared code (agent_factory, tools)
COPY _shared /app/_shared

# Copy the app entrypoint
COPY foundry-container/app.py /app/app.py

# Set default log level (credentials should be set via env vars at runtime)
ENV AGENTSEC_LOG_LEVEL=DEBUG

# Expose the default port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the Flask app
CMD ["python", "app.py"]
