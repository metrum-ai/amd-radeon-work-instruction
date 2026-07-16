# syntax=docker/dockerfile:1.4
# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

# ── Builder stage: compile/install deps with the full toolchain ────────────────
FROM python:3.12.10-slim-bookworm AS builder

# build-essential (gcc/g++/make) + libffi headers are needed only to build any
# wheels from source. They stay in this stage and never reach the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install into an isolated venv we copy into the runtime image.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY work_instruction_generator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ── Runtime stage: runtime shared libs only, no compiler toolchain ─────────────
FROM python:3.12.10-slim-bookworm

# Runtime shared libraries required for OpenCV/PIL, WeasyPrint (Pango/Cairo),
# and the healthcheck. Same set as before minus build-essential.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Bring in the pre-built dependency venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Create non‑root user (UID/GID 1000) and give ownership of the workdir
RUN addgroup --gid 1000 appgroup && adduser --uid 1000 --gid 1000 --home /home/appuser --disabled-password --gecos "" appuser && chown -R appuser:appgroup /app

# Copy application code (deps already installed in the venv above)
COPY work_instruction_generator /app/work_instruction_generator

RUN mkdir -p /data/wig/artifacts && chown -R appuser:appgroup /data/wig

USER appuser

# Expose FastAPI port
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command runs the WIG API server
CMD ["uvicorn", "work_instruction_generator.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
