# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY documents ./documents

RUN groupadd --gid 1000 appgroup && useradd --uid 1000 --gid 1000 --home /home/appuser --create-home appuser \
    && chown -R appuser:appgroup /app
USER appuser

# One-shot batch job — no long-running HTTP server to probe
HEALTHCHECK NONE

CMD ["python", "-m", "app.main"]
