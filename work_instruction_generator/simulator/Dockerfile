# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# mqtt-spb-wrapper pins the vulnerable protobuf==3.20.3, but its generated pb2
# code runs fine on protobuf 5.x — install it --no-deps (mirroring the ingest
# image) so requirements.txt's safe protobuf==5.29.6 is what's used.
RUN pip install --no-cache-dir --no-deps mqtt-spb-wrapper==2.1.2 paho_mqtt==1.6.1 && \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN groupadd --gid 1000 appgroup && useradd --uid 1000 --gid 1000 --home /home/appuser --create-home appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
