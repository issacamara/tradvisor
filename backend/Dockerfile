FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY pyproject.toml /app/backend/pyproject.toml
COPY requirements/runtime.lock /app/backend/requirements/runtime.lock
RUN python -m pip install --no-cache-dir --require-hashes \
    -r /app/backend/requirements/runtime.lock

COPY . /app/backend/
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation /app/backend \
    && sha256sum /app/backend/requirements/runtime.lock \
      > /usr/share/tradvisor-backend-lock.sha256

USER 10001:10001
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
