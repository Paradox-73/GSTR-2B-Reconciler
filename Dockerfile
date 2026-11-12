# Python services. Targets: api, worker, trainer (docs/runtime-contract.md)
FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /venv
COPY requirements.txt /tmp/requirements.txt
RUN /venv/bin/pip install -r /tmp/requirements.txt

FROM python:3.12-slim AS base
ARG APP_VERSION=dev
ENV PATH=/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=$APP_VERSION
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
COPY --from=deps /venv /venv
WORKDIR /app
COPY config/ config/
COPY matcher/ matcher/
COPY models/ models/
COPY api/ api/
COPY alembic.ini .
USER 10001

FROM base AS api
ENV SERVICE_NAME=api UPLOAD_DIR=/data/uploads
USER root
RUN mkdir -p /data/uploads && chown -R 10001:10001 /data
USER 10001
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
ENV SERVICE_NAME=worker
CMD ["python", "-m", "api.worker"]

FROM base AS trainer
ENV SERVICE_NAME=trainer
COPY datagen/ datagen/
COPY trainer/ trainer/
COPY tests/golden/ tests/golden/
CMD ["python", "-m", "trainer"]
